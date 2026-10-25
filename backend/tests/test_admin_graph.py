"""Тесты /admin/graph на синтетическом графе из test_recommendations; файлы — только в tmp_path."""

import io
import json
import os
import pickle
from pathlib import Path

import networkx as nx
import osmnx as ox
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.graph_state import GraphRegistry
from backend.app.db.models.user import UserRole
from backend.app.services import graph_service
from backend.tests.conftest import ClientFactory, make_test_settings
from backend.tests.test_recommendations import (  # noqa: F401 — branches: фикстура
    NODES,
    _headers,
    branches,
    build_graph,
)

URL = "/api/v1/admin/graph"
DRIVER_URL = "/api/v1/recommendations/driver?lat=56.32&lon=44.0"


@pytest.fixture
def graph_path(tmp_path: Path) -> Path:
    return tmp_path / "graphs" / "nn_graph.pkl"


@pytest.fixture
def admin_client(make_client: ClientFactory, graph_path: Path) -> TestClient:
    """Клиент с синтетическим графом в памяти и GRAPH_PATH во временном каталоге."""
    return make_client(
        make_test_settings(GRAPH_PATH=graph_path),
        setup=lambda app: app.state.graph_registry.replace_graph(build_graph()),
    )


@pytest.fixture
def admin(db_session: Session) -> dict[str, str]:
    return _headers(db_session, UserRole.ADMIN)


def _registry(client: TestClient) -> GraphRegistry:
    return client.app.state.graph_registry


def _post_file(client, path: str, name: str, content: bytes | str, headers) -> object:
    data = content.encode() if isinstance(content, str) else content
    return client.post(f"{URL}/{path}", files={"file": (name, io.BytesIO(data))}, headers=headers)


def _graphml(graph: nx.MultiDiGraph) -> bytes:
    buffer = io.BytesIO()
    nx.write_graphml(graph, buffer)
    return buffer.getvalue()


# --- доступ и сводка ---


def test_graph_endpoints_admin_only(admin_client: TestClient, db_session: Session) -> None:
    for role in (UserRole.MANAGER, UserRole.EXECUTIVE, UserRole.DRIVER):
        headers = _headers(db_session, role)
        assert admin_client.get(f"{URL}/info", headers=headers).status_code == 403
        assert admin_client.post(f"{URL}/reload", headers=headers).status_code == 403
        assert _post_file(admin_client, "weights", "w.csv", "u,v", headers).status_code == 403
        assert _post_file(admin_client, "upload", "g.json", "{}", headers).status_code == 403
    assert admin_client.get(f"{URL}/info").status_code == 401


def test_info(admin_client: TestClient, admin, graph_path: Path) -> None:
    body = admin_client.get(f"{URL}/info", headers=admin).json()
    assert body["status"] == "ready" and body["version"] == 1 and body["source"] == "memory"
    assert body["nodes"] == len(NODES) and body["edges"] == 8
    assert body["loaded_at"] and body["bbox"]["min_lat"] == 56.30
    assert body["graph_path"] == str(graph_path) and body["file_exists"] is False
    assert body["upload_max_mb"] == 100


# --- веса ---


@pytest.mark.usefixtures("branches")
def test_weights_change_recommendation_and_persist(
    admin_client: TestClient, db_session: Session, admin, graph_path: Path
) -> None:
    driver = _headers(db_session, UserRole.DRIVER)
    assert admin_client.get(DRIVER_URL, headers=driver).json()["branch_name"] == "Центр"

    # Пробка на всех рёбрах к «Центру»: 1→2 (оба параллельных), 1→3
    csv_text = "u,v,key,multiplier\n1,2,,10\n1,3,,10\n"
    response = _post_file(admin_client, "weights", "traffic.csv", csv_text, admin)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["format"] == "csv" and report["rows_applied"] == 2
    assert report["edges_updated"] == 3 and report["rows_skipped"] == 0
    assert report["changed"] and report["persisted"]
    assert report["graph"]["version"] == 2 and report["graph"]["file_exists"]

    body = admin_client.get(DRIVER_URL, headers=driver).json()
    # 1→2→3: 600 + 60 = 660 с = 11 мин > 6.7 мин до «Севера»
    assert body["branch_name"] == "Север" and body["graph_version"] == 2

    saved = pickle.loads(graph_path.read_bytes())
    assert saved[1][2][0]["travel_time"] == 600.0
    assert saved[1][2][0]["travel_time_base"] == 60.0
    assert [p.name for p in graph_path.parent.iterdir()] == ["nn_graph.pkl"]  # без .tmp

    # Множитель — к исходному времени, не накапливается; 1 — снять пробку
    _post_file(admin_client, "weights", "t.csv", csv_text, admin)
    assert _registry(admin_client).snapshot().graph[1][2][0]["travel_time"] == 600.0
    rows = [{"u": 1, "v": 2, "multiplier": 1}, {"u": 1, "v": 3, "multiplier": 1}]
    response = _post_file(admin_client, "weights", "reset.json", json.dumps(rows), admin)
    assert response.json()["format"] == "json"
    assert admin_client.get(DRIVER_URL, headers=driver).json()["branch_name"] == "Центр"


def test_weights_travel_time_with_key(admin_client: TestClient, admin) -> None:
    payload = {"rows": [{"u": 1, "v": 2, "key": 1, "travel_time": 42.5}]}
    response = _post_file(admin_client, "weights", "w.json", json.dumps(payload), admin)
    assert response.json()["edges_updated"] == 1
    edges = _registry(admin_client).snapshot().graph[1][2]
    assert edges[0]["travel_time"] == 60.0 and edges[1]["travel_time"] == 42.5


def test_weights_skipped_reasons(admin_client: TestClient, admin) -> None:
    csv_text = "\n".join(
        [
            "u;v;key;travel_time;multiplier",
            "1;2;;30;",  # ок
            "1;999;;30;",  # нет узла
            "3;1;;30;",  # нет ребра
            "1;2;7;30;",  # нет ключа
            "1;2;x;30;",  # некорректный ключ
            "1;3;;0;",  # не > 0
            "1;3;;abc;",  # не число
            "1;3;;30;2",  # оба поля
            "1;3;;;",  # ни одного
        ]
    )
    report = _post_file(admin_client, "weights", "w.csv", csv_text, admin).json()
    assert report["rows_total"] == 9 and report["rows_applied"] == 1
    assert report["rows_skipped"] == 8 and not report["skipped_truncated"]
    reasons = {item["row"]: item["reason"] for item in report["skipped"]}
    assert "отсутствует" in reasons[2] and "нет в графе" in reasons[3]
    assert "key=7" in reasons[4] and "некорректный key" in reasons[5]
    assert "> 0" in reasons[6] and "> 0" in reasons[7]
    assert "ровно одно" in reasons[8] and "ровно одно" in reasons[9]


def test_weights_all_invalid_keeps_graph(admin_client: TestClient, admin, graph_path) -> None:
    rows = [{"u": 1, "v": 999, "multiplier": 2}] * 60
    report = _post_file(admin_client, "weights", "w.json", json.dumps(rows), admin).json()
    assert report["rows_skipped"] == 60 and len(report["skipped"]) == 50
    assert report["skipped_truncated"] and not report["changed"] and not report["persisted"]
    assert report["graph"]["version"] == 1 and not graph_path.exists()


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("w.csv", "from,to,weight\n1,2,3\n", 422),
        ("w.csv", "u,v\n1,2\n", 422),
        ("w.json", "{not json", 422),
        ("w.json", '{"foo": 1}', 422),
        ("w.csv", b"\xff\xfe\x00bad", 422),
        ("w.pkl", "u,v,multiplier\n1,2,3\n", 415),
        ("w.csv", pickle.dumps([{"u": 1}]), 415),
    ],
)
def test_weights_bad_files(admin_client: TestClient, admin, name, content, code) -> None:
    response = _post_file(admin_client, "weights", name, content, admin)
    assert response.status_code == code, response.text
    assert _registry(admin_client).snapshot().version == 1


def test_weights_without_graph_503(make_client: ClientFactory, admin, tmp_path) -> None:
    client = make_client(make_test_settings(GRAPH_PATH=tmp_path / "g.pkl"))
    response = _post_file(client, "weights", "w.csv", "u,v,multiplier\n1,2,3\n", admin)
    assert response.status_code == 503


# --- загрузка графа ---


@pytest.mark.usefixtures("branches")
def test_upload_graphml(admin_client: TestClient, db_session: Session, admin, graph_path) -> None:
    graph = build_graph()
    graph[1][2][0]["travel_time"] = 5000.0  # теперь к «Центру» быстрее по прямому 1→3
    graph[1][2][1]["travel_time"] = 5000.0
    response = _post_file(admin_client, "upload", "city.graphml", _graphml(graph), admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "graphml" and body["persisted"]
    assert body["graph"]["version"] == 2 and body["graph"]["source"] == "upload:city.graphml"

    snapshot = _registry(admin_client).snapshot()
    assert set(snapshot.graph.nodes) == set(NODES)  # id узлов снова int
    assert isinstance(snapshot.graph.nodes[1]["x"], float)
    assert pickle.loads(graph_path.read_bytes()).number_of_edges() == 8

    rec = admin_client.get(DRIVER_URL, headers=_headers(db_session, UserRole.DRIVER)).json()
    assert rec["branch_name"] == "Центр" and rec["route"] == [list(NODES[1]), list(NODES[3])]


def test_upload_graphml_with_string_ids(admin_client: TestClient, admin) -> None:
    graph = nx.relabel_nodes(build_graph(), {n: f"n{n}" for n in NODES})
    response = _post_file(admin_client, "upload", "g.xml", _graphml(graph), admin)
    assert response.status_code == 200, response.text
    assert "n1" in _registry(admin_client).snapshot().graph


@pytest.mark.parametrize("edges_key", ["edges", "links"])
def test_upload_node_link(admin_client: TestClient, admin, edges_key: str) -> None:
    data = nx.node_link_data(build_graph(), edges=edges_key)
    response = _post_file(admin_client, "upload", "graph.json", json.dumps(data), admin)
    assert response.status_code == 200, response.text
    assert response.json()["format"] == "node-link"
    snapshot = _registry(admin_client).snapshot()
    assert snapshot.edge_count == 8 and isinstance(snapshot.graph, nx.MultiDiGraph)


def test_upload_node_link_undirected_becomes_directed(admin_client: TestClient, admin) -> None:
    data = {
        "directed": False,
        "nodes": [{"id": 1, "x": 44.0, "y": 56.32}, {"id": 2, "x": 44.01, "y": 56.33}],
        "edges": [{"source": 1, "target": 2, "travel_time": "15"}],
    }
    response = _post_file(admin_client, "upload", "graph.json", json.dumps(data), admin)
    assert response.status_code == 200, response.text
    graph = _registry(admin_client).snapshot().graph
    assert graph.has_edge(1, 2) and graph.has_edge(2, 1)
    assert graph[1][2][0]["travel_time"] == 15.0


def test_upload_rejects_pickle(admin_client: TestClient, admin, graph_path: Path) -> None:
    payload = pickle.dumps(build_graph())
    for name in ("graph.pkl", "graph.pickle", "graph.json", "graph.graphml", "graph"):
        response = _post_file(admin_client, "upload", name, payload, admin)
        assert response.status_code == 415, name
        assert "Pickle" in response.json()["detail"]
    assert _registry(admin_client).snapshot().version == 1 and not graph_path.exists()


def _invalid_graphs() -> list[tuple[str, bytes | str]]:
    no_time = build_graph()
    for *_, data in no_time.edges(keys=True, data=True):
        del data["travel_time"]
    no_coords = build_graph()
    del no_coords.nodes[3]["x"]
    return [
        ("no_time.graphml", _graphml(no_time)),
        ("no_coords.json", json.dumps(nx.node_link_data(no_coords))),
        ("broken.graphml", "<graphml><graph><node id="),
        ("empty.json", '{"nodes": [], "edges": []}'),
        ("bad.json", '{"nodes": "x"}'),
        ("bad.json", '{"nodes": [{"id": 1, "x": 500, "y": 56}], "edges": []}'),
        ("bad.json", '{"nodes": [{"x": 1}], "edges": []}'),
        ("bad.json", "[1, 2]"),
        ("bad.json", "{oops"),
        ("empty.json", ""),
    ]


@pytest.mark.parametrize(("name", "content"), _invalid_graphs())
def test_upload_invalid_graph_422(admin_client: TestClient, admin, name, content) -> None:
    response = _post_file(admin_client, "upload", name, content, admin)
    assert response.status_code == 422, response.text
    assert _registry(admin_client).snapshot().version == 1


def test_upload_validation_errors_listed(admin_client: TestClient, admin) -> None:
    graph = build_graph()
    for *_, data in graph.edges(keys=True, data=True):
        data["travel_time"] = -1
    response = _post_file(
        admin_client, "upload", "g.json", json.dumps(nx.node_link_data(graph)), admin
    )
    detail = response.json()["detail"]
    assert detail["message"] == "Граф не прошёл проверку" and len(detail["errors"]) == 8


def test_upload_unknown_format_415(admin_client: TestClient, admin) -> None:
    response = _post_file(admin_client, "upload", "graph.txt", "hello", admin)
    assert response.status_code == 415


def test_upload_too_large_413(make_client: ClientFactory, admin, graph_path: Path) -> None:
    client = make_client(
        make_test_settings(GRAPH_PATH=graph_path, GRAPH_UPLOAD_MAX_MB=0.001),
        setup=lambda app: app.state.graph_registry.replace_graph(build_graph()),
    )
    big = _graphml(build_graph())
    assert len(big) > 0.001 * 1024 * 1024
    assert _post_file(client, "upload", "g.graphml", big, admin).status_code == 413
    weights = "u,v,multiplier\n" + "1,2,2\n" * 300
    assert _post_file(client, "weights", "w.csv", weights, admin).status_code == 413
    assert not graph_path.exists()


def test_upload_while_loading_409(admin_client: TestClient, admin) -> None:
    _registry(admin_client).mark_loading()
    data = json.dumps(nx.node_link_data(build_graph()))
    assert _post_file(admin_client, "upload", "g.json", data, admin).status_code == 409
    assert admin_client.post(f"{URL}/reload", headers=admin).status_code == 409


def test_persist_failure_keeps_graph(
    admin_client: TestClient, admin, graph_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_replace(*_args) -> None:
        raise OSError("диск переполнен")

    monkeypatch.setattr(graph_service.os, "replace", broken_replace)
    response = _post_file(admin_client, "weights", "w.csv", "u,v,multiplier\n1,2,5\n", admin)
    assert response.status_code == 500 and "диск переполнен" in response.json()["detail"]
    assert _registry(admin_client).snapshot().version == 1
    assert _registry(admin_client).snapshot().graph[1][2][0]["travel_time"] == 60.0
    assert list(graph_path.parent.iterdir()) == []  # временный файл удалён


def test_persist_graph_atomic(tmp_path: Path) -> None:
    target = tmp_path / "g.pkl"
    target.write_bytes(b"old")
    graph_service.persist_graph(build_graph(), target)
    assert pickle.loads(target.read_bytes()).number_of_nodes() == len(NODES)
    assert os.listdir(tmp_path) == ["g.pkl"]


# --- перечитывание с диска ---


def test_reload(admin_client: TestClient, admin, graph_path: Path) -> None:
    assert admin_client.post(f"{URL}/reload", headers=admin).status_code == 404

    graph = build_graph()
    graph.add_node(8, x=44.05, y=56.35)
    graph_path.parent.mkdir(parents=True)
    graph_path.write_bytes(pickle.dumps(graph))
    response = admin_client.post(f"{URL}/reload", headers=admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action"] == "reload" and body["graph"]["nodes"] == len(NODES) + 1
    assert body["graph"]["version"] == 2 and body["graph"]["source"] == str(graph_path)

    graph_path.write_bytes(b"not a pickle")
    response = admin_client.post(f"{URL}/reload", headers=admin)
    assert response.status_code == 422
    assert _registry(admin_client).snapshot().version == 2  # прежний граф работает


def test_upload_osmnx_graphml(admin_client: TestClient, admin, tmp_path: Path) -> None:
    source = tmp_path / "osmnx.graphml"
    ox.save_graphml(build_graph(), source)
    response = _post_file(admin_client, "upload", "osmnx.graphml", source.read_bytes(), admin)
    assert response.status_code == 200, response.text
    graph = _registry(admin_client).snapshot().graph
    assert set(graph.nodes) == set(NODES) and graph[1][2][0]["travel_time"] == 60.0
