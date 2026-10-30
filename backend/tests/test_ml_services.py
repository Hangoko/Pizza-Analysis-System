"""Тесты ML-сервисов (KMeansAnalyzer и RoutingService) с чтением данных из БД."""

from datetime import UTC, datetime, timedelta

import networkx as nx
from sqlalchemy.orm import Session

from backend.app.db.models import Branch, Order, OrderStatus
from backend.app.ml.services.kmeans_service import KMeansAnalyzer, haversine_km
from backend.app.ml.services.routing_service import RoutingService


def _build_test_graph() -> nx.MultiDiGraph:
    """Компактный тестовый граф дорог для проверки алгоритма Дейкстры без OSM."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    # Узел 1 — водитель, Узел 2 — Филиал Центр (близко), Узел 3 — Филиал Север (далеко)
    G.add_node(1, x=44.0000, y=56.3200)
    G.add_node(2, x=44.0100, y=56.3210)
    G.add_node(3, x=43.8500, y=56.3600)

    # Время проезда: до узла 2 — 5 мин (300 с), до узла 3 — 20 мин (1200 с)
    G.add_edge(1, 2, travel_time=300.0)
    G.add_edge(1, 3, travel_time=1200.0)
    return G


def test_haversine_distance() -> None:
    dist = haversine_km(56.322974, 44.034741, 56.322974, 44.034741)
    assert dist == 0.0
    # Между центром Нижнего Новгорода и Автозаводом ~14 км
    dist_avtozavod = haversine_km(56.322974, 44.034741, 56.241094, 43.861618)
    assert 12.0 <= dist_avtozavod <= 16.0


def test_kmeans_analyzer_reads_orders_and_branches_from_db(db_session: Session) -> None:
    t0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    # 1. Создаем 2 активных филиала и 1 неактивный
    b_active_high = Branch(
        name="Филиал Центр", lat=56.3200, lon=44.0000, current_queue=3, is_active=True
    )
    b_active_low = Branch(
        name="Филиал Окраина", lat=56.2000, lon=43.8000, current_queue=0, is_active=True
    )
    b_closed = Branch(
        name="Закрытый филиал", lat=56.4000, lon=44.1000, current_queue=5, is_active=False
    )
    db_session.add_all([b_active_high, b_active_low, b_closed])
    db_session.flush()

    orders: list[Order] = []
    idx = 1
    # Зона 1 (рядом с "Филиал Центр"): 10 доставленных заказов -> "Филиал рентабелен"
    for _ in range(10):
        orders.append(
            Order(
                external_id=f"ORD-{idx:04d}",
                client_lat=56.3201,
                client_lon=44.0001,
                branch_id=b_active_high.id,
                order_time=t0 + timedelta(minutes=idx),
                delivery_time_minutes=25,
                status=OrderStatus.DELIVERED.value,
            )
        )
        idx += 1

    # Зона 2 (рядом с "Филиал Окраина"): 2 доставленных заказа -> "Закрыть филиал"
    for _ in range(2):
        orders.append(
            Order(
                external_id=f"ORD-{idx:04d}",
                client_lat=56.2001,
                client_lon=43.8001,
                branch_id=b_active_low.id,
                order_time=t0 + timedelta(minutes=idx),
                delivery_time_minutes=30,
                status=OrderStatus.DELIVERED.value,
            )
        )
        idx += 1

    # Зона 3 (вдали от активных филиалов, рядом закрытый): 12 заказов -> "Открыть филиал"
    for _ in range(12):
        orders.append(
            Order(
                external_id=f"ORD-{idx:04d}",
                client_lat=56.4000,
                client_lon=44.1000,
                branch_id=b_active_high.id,
                order_time=t0 + timedelta(minutes=idx),
                delivery_time_minutes=40,
                status=OrderStatus.DELIVERED.value,
            )
        )
        idx += 1

    db_session.add_all(orders)
    db_session.commit()

    analyzer = KMeansAnalyzer(
        n_clusters=3,
        session=db_session,
        coverage_radius_km=2.0,
        high_demand_threshold=10,
        low_demand_threshold=5,
    )
    results = analyzer.analyze_demand()
    assert len(results) == 3

    verdicts = {r["recommendation"] for r in results}
    assert verdicts == {"Филиал рентабелен", "Закрыть филиал", "Открыть филиал"}


def test_routing_service_reads_and_refreshes_branches_from_db(db_session: Session) -> None:
    b_near = Branch(name="Филиал Центр", lat=56.3210, lon=44.0100, current_queue=1, is_active=True)
    b_far = Branch(name="Филиал Север", lat=56.3600, lon=43.8500, current_queue=2, is_active=True)
    db_session.add_all([b_near, b_far])
    db_session.commit()

    graph = _build_test_graph()
    router = RoutingService(session=db_session, graph=graph)

    # 1. При малых очередях выигрывает "Филиал Центр" (5 - 1*2 = 3 против 20 - 2*2 = 16)
    rec1 = router.get_driver_recommendation(56.3200, 44.0000)
    assert rec1 is not None
    assert rec1["branch_name"] == "Филиал Центр"
    assert rec1["queue_size"] == 1

    # 2. Обновляем очередь в БД у дальнего филиала до 15 заказов (20 - 15*2 = -10)
    b_far.current_queue = 15
    db_session.commit()

    rec2 = router.get_driver_recommendation(56.3200, 44.0000)
    assert rec2 is not None
    assert rec2["branch_name"] == "Филиал Север"
    assert rec2["queue_size"] == 15
