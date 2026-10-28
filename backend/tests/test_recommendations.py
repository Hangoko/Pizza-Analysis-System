"""Тесты /recommendations и /branches на синтетическом графе (без скачивания OSM) и SQLite."""

import pickle
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.config import BASE_DIR
from backend.app.core.graph_state import GraphRegistry, GraphStatus, build_snapshot
from backend.app.core.security import create_access_token
from backend.app.db.models import Branch, Order, OrderStatus, User
from backend.app.db.models.user import UserRole
from backend.app.ml.services.routing_service import RoutingService
from backend.app.services.routing_adapter import (
    FastRoutingService,
    PointOutsideGraphError,
    dijkstra_to_targets,
)
from backend.tests.conftest import ClientFactory, make_test_settings

# Координаты узлов (lat, lon)
NODES = {
    1: (56.3200, 44.0000),  # водитель
    2: (56.3220, 44.0050),
    3: (56.3210, 44.0100),  # филиал «Центр»
    4: (56.3300, 43.9900),
    5: (56.3400, 43.9800),  # филиал «Север»
    6: (56.3000, 44.0200),  # филиал «Тупик» — недостижим из узла 1
    7: (56.3100, 44.0300),  # изолированный узел: из него никуда не доехать
}


def build_graph() -> nx.MultiDiGraph:
    """
    Кратчайший путь 1→3: 1-2-3 (60 + 60 = 120 с), прямое ребро 1→3 — 300 с,
    параллельное ребро 1→2 — 500 с (берётся минимальное). Путь 1→5: 1-4-5 (400 с).
    """
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "epsg:4326"
    for node, (lat, lon) in NODES.items():
        graph.add_node(node, x=lon, y=lat)
    for u, v, t in [
        (1, 2, 60.0),
        (1, 2, 500.0),
        (2, 3, 60.0),
        (1, 3, 300.0),
        (1, 4, 200.0),
        (4, 5, 200.0),
        (2, 5, 900.0),
        (6, 1, 10.0),
    ]:
        graph.add_edge(u, v, travel_time=t)
    return graph


@pytest.fixture
def branches(db_session: Session) -> dict[str, Branch]:
    items = {
        "center": Branch(name="Центр", lat=56.3210, lon=44.0100, current_queue=0),
        "north": Branch(name="Север", lat=56.3400, lon=43.9800, current_queue=0),
        "dead_end": Branch(name="Тупик", lat=56.3000, lon=44.0200, current_queue=100),
        "closed": Branch(name="Закрыт", lat=56.3200, lon=44.0000, is_active=False),
    }
    db_session.add_all(items.values())
    db_session.commit()
    return items


def _headers(session: Session, role: UserRole) -> dict[str, str]:
    user = User(username=f"user_{role.value}", password_hash="x", role=role.value)
    session.add(user)
    session.commit()
    token = create_access_token(user.id, user.role, settings=make_test_settings())
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def graph_client(make_client: ClientFactory) -> TestClient:
    """Клиент с уже загруженным синтетическим графом."""
    return make_client(setup=lambda app: app.state.graph_registry.replace_graph(build_graph()))


def _wait_for(predicate: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "условие не выполнилось вовремя"
        time.sleep(0.02)


# --- алгоритм ---


def test_dijkstra_to_targets_known_path() -> None:
    dist, pred = dijkstra_to_targets(build_graph(), 1, {3, 5, 6})
    assert dist[3] == 120.0
    assert dist[5] == 400.0
    assert 6 not in dist
    assert pred[3] == 2 and pred[2] == 1


@pytest.mark.parametrize(
    ("queues", "point"),
    [
        ({"center": 0, "north": 0}, NODES[1]),
        ({"center": 0, "north": 3}, NODES[1]),
        ({"center": 5, "north": 1}, (56.3301, 43.9901)),
        ({"center": 1, "north": 1}, NODES[2]),
    ],
)
def test_fast_path_matches_original_routing_service(
    db_session: Session,
    branches: dict[str, Branch],
    queues: dict[str, int],
    point: tuple[float, float],
) -> None:
    for key, queue in queues.items():
        branches[key].current_queue = queue
    db_session.commit()
    graph = build_graph()

    original = RoutingService(session=db_session, graph=graph).get_driver_recommendation(*point)
    fast = FastRoutingService(build_snapshot(graph, version=1, source="test"), session=db_session)
    result = fast.get_driver_recommendation(*point)

    assert original is not None
    assert result == original


def test_fast_path_rejects_point_outside_graph(db_session: Session, branches) -> None:
    fast = FastRoutingService(
        build_snapshot(build_graph(), version=1, source="test"),
        session=db_session,
        max_snap_distance_km=2.0,
    )
    with pytest.raises(PointOutsideGraphError):
        fast.get_driver_recommendation(55.75, 37.62)  # Москва


# --- реестр графа ---


def test_registry_replace_graph_recomputes_branch_cache() -> None:
    registry = GraphRegistry()
    assert registry.status == GraphStatus.NOT_LOADED and registry.snapshot() is None

    first = registry.replace_graph(build_graph())
    assert first.branch_node(56.3210, 44.0100) == 3

    moved = build_graph()
    moved.nodes[3]["x"], moved.nodes[3]["y"] = 44.0150, 56.3250  # теперь ближе узел 2
    second = registry.replace_graph(moved, source="reload")
    assert registry.snapshot() is second
    assert second.version == 2 and registry.status == GraphStatus.READY
    assert second.cached_branch_coords == [(56.3210, 44.0100)]
    assert second.branch_node(56.3210, 44.0100) == 2
    # Старый снимок не изменился — запросы, начатые до замены, досчитываются на нём
    assert first.branch_node(56.3210, 44.0100) == 3


def test_registry_rejects_invalid_graph() -> None:
    registry = GraphRegistry()
    with pytest.raises(ValueError):
        registry.replace_graph(nx.MultiDiGraph())
    assert registry.snapshot() is None


def test_lifespan_loads_graph_from_pickle(make_client: ClientFactory, tmp_path: Path) -> None:
    path = tmp_path / "graph.pkl"
    path.write_bytes(pickle.dumps(build_graph()))
    client = make_client(make_test_settings(LOAD_GRAPH_ON_STARTUP=True, GRAPH_PATH=path))
    registry: GraphRegistry = client.app.state.graph_registry

    _wait_for(lambda: registry.status != GraphStatus.LOADING)
    assert registry.status == GraphStatus.READY
    assert registry.snapshot().node_count == len(NODES)

    body = client.get("/api/v1/health/ready").json()
    assert body["status"] == "ready"
    assert body["components"]["graph"]["status"] == "ok"


def test_lifespan_missing_graph_fails_without_download(
    make_client: ClientFactory, tmp_path: Path, db_session: Session
) -> None:
    settings = make_test_settings(LOAD_GRAPH_ON_STARTUP=True, GRAPH_PATH=tmp_path / "none.pkl")
    client = make_client(settings)
    registry: GraphRegistry = client.app.state.graph_registry
    _wait_for(lambda: registry.status != GraphStatus.LOADING)
    assert registry.status == GraphStatus.FAILED
    assert "не найден" in registry.error

    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["components"]["graph"]["status"] == "error"

    headers = _headers(db_session, UserRole.DRIVER)
    response = client.get("/api/v1/recommendations/driver?lat=56.32&lon=44.0", headers=headers)
    assert response.status_code == 503
    assert "не найден" in response.json()["detail"]


def test_health_graph_optional_when_startup_loading_disabled(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    graph = response.json()["components"]["graph"]
    assert graph["status"] == "not_configured" and graph["required"] is False


# --- /recommendations/driver ---


def test_driver_recommendation(graph_client: TestClient, db_session: Session, branches) -> None:
    headers = _headers(db_session, UserRole.DRIVER)
    response = graph_client.get(
        "/api/v1/recommendations/driver", params={"lat": 56.3200, "lon": 44.0000}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["branch_id"] == branches["center"].id
    assert body["branch_name"] == "Центр"
    assert body["travel_time_minutes"] == 2.0
    assert body["queue_size"] == 0
    assert body["score"] == 2.0
    assert body["driver_node"] == 1 and body["branch_node"] == 3
    assert body["route"] == [list(NODES[1]), list(NODES[2]), list(NODES[3])]
    assert body["graph_version"] == 1
    assert body["elapsed_ms"] >= 0


def test_driver_recommendation_503_while_loading(
    make_client: ClientFactory, db_session: Session, branches
) -> None:
    client = make_client(setup=lambda app: app.state.graph_registry.mark_loading())
    headers = _headers(db_session, UserRole.DRIVER)
    for path in ("/api/v1/recommendations/driver", "/api/v1/recommendations/driver/map"):
        response = client.get(path, params={"lat": 56.32, "lon": 44.0}, headers=headers)
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "30"
    # Загрузка графа обязательна только при LOAD_GRAPH_ON_STARTUP=true
    assert client.get("/api/v1/health/ready").json()["components"]["graph"]["status"] == "loading"


def test_driver_recommendation_503_when_not_loaded(client: TestClient, db_session: Session) -> None:
    headers = _headers(db_session, UserRole.ADMIN)
    response = client.get("/api/v1/recommendations/driver?lat=56.32&lon=44.0", headers=headers)
    assert response.status_code == 503
    assert "Retry-After" in response.headers


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"lat": 55.75, "lon": 37.62}, 422),  # далеко за пределами графа
        ({"lat": 100, "lon": 44.0}, 422),  # некорректная широта
        ({"lat": 56.32}, 422),  # нет долготы
        ({"lat": 56.3100, "lon": 44.0300}, 404),  # изолированный узел — маршрута нет
    ],
)
def test_driver_recommendation_errors(
    graph_client: TestClient, db_session: Session, branches, params: dict, code: int
) -> None:
    headers = _headers(db_session, UserRole.MANAGER)
    response = graph_client.get("/api/v1/recommendations/driver", params=params, headers=headers)
    assert response.status_code == code


def test_driver_recommendation_roles(graph_client: TestClient, db_session: Session) -> None:
    url = "/api/v1/recommendations/driver?lat=56.32&lon=44.0"
    assert graph_client.get(url).status_code == 401
    headers = _headers(db_session, UserRole.EXECUTIVE)
    assert graph_client.get(url, headers=headers).status_code == 403


def test_queue_update_changes_recommendation(
    graph_client: TestClient, db_session: Session, branches
) -> None:
    driver = _headers(db_session, UserRole.DRIVER)
    url = "/api/v1/recommendations/driver?lat=56.32&lon=44.0"
    assert graph_client.get(url, headers=driver).json()["branch_name"] == "Центр"

    north_id = branches["north"].id
    manager = _headers(db_session, UserRole.MANAGER)
    response = graph_client.patch(
        f"/api/v1/branches/{north_id}/queue", json={"current_queue": 3}, headers=manager
    )
    assert response.status_code == 200
    assert response.json()["current_queue"] == 3

    body = graph_client.get(url, headers=driver).json()
    # 400 с = 6.7 мин - 3 * 2 = 0.7 < 2.0 у «Центра»
    assert body["branch_name"] == "Север"
    assert body["queue_size"] == 3
    assert body["route"] == [list(NODES[1]), list(NODES[4]), list(NODES[5])]


def test_branch_queue_validation_and_roles(
    client: TestClient, db_session: Session, branches
) -> None:
    url = f"/api/v1/branches/{branches['center'].id}/queue"
    executive = _headers(db_session, UserRole.EXECUTIVE)
    assert client.patch(url, json={"current_queue": 1}, headers=executive).status_code == 403
    admin = _headers(db_session, UserRole.ADMIN)
    assert client.patch(url, json={"current_queue": -1}, headers=admin).status_code == 422
    response = client.patch("/api/v1/branches/9999/queue", json={"current_queue": 1}, headers=admin)
    assert response.status_code == 404


def test_list_branches(client: TestClient, db_session: Session, branches) -> None:
    driver = _headers(db_session, UserRole.DRIVER)
    names = [b["name"] for b in client.get("/api/v1/branches", headers=driver).json()]
    assert names == ["Центр", "Север", "Тупик"]
    response = client.get("/api/v1/branches?include_inactive=true", headers=driver)
    assert len(response.json()) == 4
    assert client.get("/api/v1/branches").status_code == 401


def _repo_data_files() -> set[Path]:
    data_dir = BASE_DIR / "data"
    return set(data_dir.glob("*.html")) if data_dir.exists() else set()


def test_driver_map_returns_html(graph_client: TestClient, db_session: Session, branches) -> None:
    before = _repo_data_files()
    headers = _headers(db_session, UserRole.DRIVER)
    response = graph_client.get(
        "/api/v1/recommendations/driver/map", params={"lat": 56.32, "lon": 44.0}, headers=headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "leaflet" in response.text.lower()
    # Карта пишется во временный каталог и удаляется — в data/ ничего не остаётся
    assert _repo_data_files() == before


# --- /recommendations/branches (K-Means) ---


@pytest.fixture
def demand_orders(db_session: Session) -> None:
    """Три зоны спроса (как в test_ml_services): рентабелен / закрыть / открыть."""
    center = Branch(name="Филиал Центр", lat=56.3200, lon=44.0000)
    outskirts = Branch(name="Филиал Окраина", lat=56.2000, lon=43.8000)
    db_session.add_all([center, outskirts])
    db_session.flush()
    t0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    zones = [(56.3201, 44.0001, 10), (56.2001, 43.8001, 2), (56.4000, 44.1000, 12)]
    idx = 0
    for lat, lon, n in zones:
        for _ in range(n):
            idx += 1
            db_session.add(
                Order(
                    external_id=f"ORD-{idx:04d}",
                    client_lat=lat,
                    client_lon=lon,
                    branch_id=center.id,
                    order_time=t0 + timedelta(hours=idx),
                    delivery_time_minutes=30,
                    status=OrderStatus.DELIVERED.value,
                )
            )
    db_session.add(
        Order(
            external_id="ORD-CANCELED",
            client_lat=56.5,
            client_lon=44.5,
            branch_id=center.id,
            order_time=t0,
            status=OrderStatus.CANCELED.value,
        )
    )
    db_session.commit()


DEMAND_PARAMS = {"n_clusters": 3, "high_demand_threshold": 10, "low_demand_threshold": 5}


def test_branch_recommendations(client: TestClient, db_session: Session, demand_orders) -> None:
    headers = _headers(db_session, UserRole.EXECUTIVE)
    response = client.get("/api/v1/recommendations/branches", params=DEMAND_PARAMS, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["n_clusters"] == 3 and body["orders_count"] == 24
    verdicts = {z["order_count"]: z["recommendation"] for z in body["zones"]}
    assert verdicts == {10: "Филиал рентабелен", 2: "Закрыть филиал", 12: "Открыть филиал"}


def test_branch_recommendations_period_and_errors(
    client: TestClient, db_session: Session, demand_orders
) -> None:
    headers = _headers(db_session, UserRole.MANAGER)
    url = "/api/v1/recommendations/branches"
    # Первые 10 заказов (зона «Центр») — в первые 10 часов
    period = {"date_from": "2026-10-01T12:00:00", "date_to": "2026-10-01T23:00:00"}
    body = client.get(url, params={"n_clusters": 1, **period}, headers=headers).json()
    assert body["orders_count"] == 10 and len(body["zones"]) == 1

    too_many = client.get(url, params={"n_clusters": 11, **period}, headers=headers)
    assert too_many.status_code == 422
    assert "Недостаточно" in too_many.json()["detail"]

    empty = {"date_from": "2020-01-01", "date_to": "2020-02-01"}
    assert client.get(url, params=empty, headers=headers).status_code == 422
    assert client.get(url, params={"n_clusters": 0}, headers=headers).status_code == 422
    assert client.get(url, params={"n_clusters": 51}, headers=headers).status_code == 422
    reversed_period = {"date_from": "2026-10-02", "date_to": "2026-10-01"}
    assert client.get(url, params=reversed_period, headers=headers).status_code == 422


def test_branch_recommendations_roles(client: TestClient, db_session: Session) -> None:
    url = "/api/v1/recommendations/branches"
    assert client.get(url).status_code == 401
    driver = _headers(db_session, UserRole.DRIVER)
    assert client.get(url, headers=driver).status_code == 403
    assert client.get(f"{url}/map", headers=driver).status_code == 403


def test_branch_map_returns_html(client: TestClient, db_session: Session, demand_orders) -> None:
    before = _repo_data_files()
    headers = _headers(db_session, UserRole.ADMIN)
    response = client.get(
        "/api/v1/recommendations/branches/map", params=DEMAND_PARAMS, headers=headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Открыть филиал" in response.text
    assert _repo_data_files() == before
