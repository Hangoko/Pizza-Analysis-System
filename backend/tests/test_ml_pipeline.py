"""
Unit-тесты для генератора заказов, K-Means анализатора спроса и алгоритма маршрутизации Дейкстры.
Выполнены в рамках задачи QA (Issue #25).
"""

from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from backend.app.db.models import Branch, Order, OrderStatus
from backend.app.ml.data_generation.generator import generate_orders
from backend.app.ml.services.kmeans_service import KMeansAnalyzer
from backend.app.ml.services.routing_service import RoutingService


def _run_generator(num_orders: int, seed: int) -> pd.DataFrame:
    """Запускает генератор и читает сгенерированный CSV-файл."""
    generate_orders(num_orders=num_orders, seed=seed)
    base_dir = Path(__file__).resolve().parents[2]
    file_path = base_dir / "data" / "synthetic_orders.csv"
    assert file_path.exists()
    return pd.read_csv(file_path)


# ============================================================================
# 1. ТЕСТЫ ГЕНЕРАТОРА ЗАКАЗОВ: generate_orders()
# ============================================================================


def test_generate_orders_schema_and_types() -> None:
    """Генератор создает CSV-файл со строго заданными колонками и типами."""
    df = _run_generator(num_orders=20, seed=42)
    assert isinstance(df, pd.DataFrame)
    expected_cols = {
        "order_id",
        "client_lat",
        "client_lon",
        "branch_id",
        "driver_id",
        "order_time",
        "delivery_time_minutes",
        "status",
    }
    assert expected_cols.issubset(set(df.columns))
    assert len(df) == 20


def test_generate_orders_reproducibility() -> None:
    """Одинаковый seed дает идентичные выборки; разные seed дают разные данные."""
    df_a = _run_generator(num_orders=30, seed=777)
    # Копируем для чистоты сравнения, т.к. генератор перезаписывает один файл
    df_a_copy = df_a.copy()

    df_b = _run_generator(num_orders=30, seed=777)
    pd.testing.assert_frame_equal(df_a_copy, df_b)

    df_diff = _run_generator(num_orders=30, seed=888)
    assert not df_b["client_lat"].equals(df_diff["client_lat"])


def test_generate_orders_business_logic_consistency() -> None:
    """Проверка бизнес-правил: координаты в черте города, время доставки только у Delivered."""
    df = _run_generator(num_orders=100, seed=123)

    # 1. Координаты в пределах агломерации Нижнего Новгорода
    assert df["client_lat"].between(56.15, 56.45).all()
    assert df["client_lon"].between(43.70, 44.20).all()

    # 2. Корректность филиалов и водителей
    assert df["branch_id"].between(1, 7).all()
    assert df["driver_id"].between(1, 20).all()

    # 3. Статусы и соответствие delivery_time_minutes
    delivered = df[df["status"] == "Delivered"]
    canceled = df[df["status"] == "Canceled"]

    assert len(delivered) > 0
    assert len(canceled) > 0
    assert delivered["delivery_time_minutes"].notna().all()
    assert (delivered["delivery_time_minutes"] >= 15).all()
    assert (delivered["delivery_time_minutes"] <= 60).all()
    assert canceled["delivery_time_minutes"].isna().all()


def test_generate_orders_empty_or_small() -> None:
    """Генератор корректно отрабатывает малое число заказов."""
    df = _run_generator(num_orders=1, seed=1)
    assert len(df) == 1
    assert df.iloc[0]["order_id"] == "ORD-0001"


# ============================================================================
# 2. ТЕСТЫ КЛАСТЕРИЗАЦИИ K-MEANS: KMeansAnalyzer.analyze_demand()
# ============================================================================


def test_kmeans_analyzer_empty_database_returns_empty_list(db_session: Session) -> None:
    """При отсутствии заказов в БД analyze_demand возвращает пустой список без падения."""
    analyzer = KMeansAnalyzer(n_clusters=3, session=db_session)
    results = analyzer.analyze_demand()
    assert results == []


def test_kmeans_analyzer_fewer_orders_than_clusters_handled(db_session: Session) -> None:
    """Если доставленных заказов меньше n_clusters, K-Means адаптирует число кластеров."""
    b = Branch(name="Филиал Тест", lat=56.32, lon=44.00, current_queue=0, is_active=True)
    db_session.add(b)
    db_session.flush()

    orders = [
        Order(
            external_id="ORD-01",
            client_lat=56.321,
            client_lon=44.001,
            branch_id=b.id,
            order_time=datetime(2026, 10, 1, tzinfo=UTC),
            delivery_time_minutes=20,
            status=OrderStatus.DELIVERED.value,
        ),
        Order(
            external_id="ORD-02",
            client_lat=56.322,
            client_lon=44.002,
            branch_id=b.id,
            order_time=datetime(2026, 10, 1, tzinfo=UTC),
            delivery_time_minutes=25,
            status=OrderStatus.DELIVERED.value,
        ),
    ]
    db_session.add_all(orders)
    db_session.commit()

    analyzer = KMeansAnalyzer(n_clusters=5, session=db_session)
    results = analyzer.analyze_demand()
    # Число кластеров должно быть ограничено фактическим числом заказов
    assert len(results) <= 2


def test_kmeans_analyzer_output_contract_and_order_sum(db_session: Session) -> None:
    """Проверка структуры ответа центроидов и суммы заказов по всем зонам."""
    b = Branch(name="Филиал Центр", lat=56.3200, lon=44.0000, current_queue=0, is_active=True)
    db_session.add(b)
    db_session.flush()

    total_orders = 30
    orders = []
    for i in range(total_orders):
        orders.append(
            Order(
                external_id=f"ORD-C-{i:03d}",
                client_lat=56.3200 + (i % 3) * 0.005,
                client_lon=44.0000 + (i % 3) * 0.005,
                branch_id=b.id,
                order_time=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
                delivery_time_minutes=25,
                status=OrderStatus.DELIVERED.value,
            )
        )
    db_session.add_all(orders)
    db_session.commit()

    analyzer = KMeansAnalyzer(n_clusters=3, session=db_session, coverage_radius_km=2.0)
    results = analyzer.analyze_demand()

    assert len(results) == 3
    total_counted = sum(r["order_count"] for r in results)
    assert total_counted == total_orders

    for r in results:
        assert "zone_id" in r
        assert "center_lat" in r
        assert "center_lon" in r
        assert "order_count" in r
        assert "recommendation" in r
        assert r["recommendation"] in {
            "Филиал рентабелен",
            "Закрыть филиал",
            "Открыть филиал",
            "Спрос низкий",
        }


# ============================================================================
# 3. ТЕСТЫ МАРШРУТИЗАЦИИ ДЕЙКСТРЫ: RoutingService.get_driver_recommendation()
# ============================================================================


def _create_multi_branch_graph() -> nx.MultiDiGraph:
    """Тестовый граф с несколькими узлами и разным временем проезда."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"

    # Узел 10: Водитель (56.3000, 44.0000)
    # Узел 20: Филиал А (56.3100, 44.0100) — путь 300 сек (5 мин)
    # Узел 30: Филиал Б (56.3200, 44.0200) — путь 600 сек (10 мин)
    # Узел 40: Изолированный филиал В — пути нет
    G.add_node(10, x=44.0000, y=56.3000)
    G.add_node(20, x=44.0100, y=56.3100)
    G.add_node(30, x=44.0200, y=56.3200)
    G.add_node(40, x=44.0500, y=56.3500)

    G.add_edge(10, 20, travel_time=300.0)
    G.add_edge(10, 30, travel_time=600.0)
    return G


def test_routing_service_no_active_branches(db_session: Session) -> None:
    """Если все филиалы неактивны, рекомендация возвращает None."""
    b_inactive = Branch(name="Неактивный", lat=56.31, lon=44.01, current_queue=0, is_active=False)
    db_session.add(b_inactive)
    db_session.commit()

    graph = _create_multi_branch_graph()
    router = RoutingService(session=db_session, graph=graph)
    assert router.get_driver_recommendation(56.3000, 44.0000) is None


def test_routing_service_score_formula_and_queue_weight(db_session: Session) -> None:
    """
    Проверка формулы скоринга: Score = travel_time_minutes - queue * 2.
    При равных условиях выигрывает филиал с большим числом заказов в очереди.
    """
    b1 = Branch(name="Ближний (пустой)", lat=56.3100, lon=44.0100, current_queue=0, is_active=True)
    b2 = Branch(
        name="Дальний (с заказами)",
        lat=56.3200,
        lon=44.0200,
        current_queue=6,
        is_active=True,
    )
    db_session.add_all([b1, b2])
    db_session.commit()

    graph = _create_multi_branch_graph()
    router = RoutingService(session=db_session, graph=graph)

    # b1: 5.0 - 0 * 2 = 5.0
    # b2: 10.0 - 6 * 2 = -2.0  -> b2 выигрывает!
    rec = router.get_driver_recommendation(56.3000, 44.0000)
    assert rec is not None
    assert rec["branch_name"] == "Дальний (с заказами)"
    assert rec["travel_time_minutes"] == pytest.approx(10.0, 0.1)
    assert rec["queue_size"] == 6


def test_routing_service_unreachable_branch_ignored(db_session: Session) -> None:
    """Изолированный филиал без пути в графе корректно игнорируется Дейкстрой."""
    b_isolated = Branch(
        name="Островной",
        lat=56.3500,
        lon=44.0500,
        current_queue=50,
        is_active=True,
    )
    b_reachable = Branch(
        name="Достижимый",
        lat=56.3100,
        lon=44.0100,
        current_queue=0,
        is_active=True,
    )
    db_session.add_all([b_isolated, b_reachable])
    db_session.commit()

    graph = _create_multi_branch_graph()
    router = RoutingService(session=db_session, graph=graph)

    rec = router.get_driver_recommendation(56.3000, 44.0000)
    assert rec is not None
    assert rec["branch_name"] == "Достижимый"
