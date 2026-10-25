"""Тесты KPI: чистые функции на известном DataFrame и эндпоинты /api/v1/stats на SQLite."""

import json
from datetime import UTC, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token
from backend.app.db.models import Branch, Order, User
from backend.app.db.models.user import UserRole
from backend.app.repositories.order import ORDER_DF_COLUMNS, OrderRepository
from backend.app.services.stats_service import (
    aggregate,
    branch_load,
    summary_kpi,
    timeseries,
    to_records,
)
from backend.tests.conftest import make_test_settings

D, C, P = "Delivered", "Canceled", "Pending"

# (branch_id, driver_id, order_time UTC, delivery_time_minutes, status)
ROWS = [
    (1, 1, datetime(2024, 1, 1, 10, 5, tzinfo=UTC), 20, D),
    (1, 1, datetime(2024, 1, 1, 10, 40, tzinfo=UTC), 30, D),
    (1, 2, datetime(2024, 1, 1, 12, 10, tzinfo=UTC), None, C),
    (2, 2, datetime(2024, 1, 2, 9, 0, tzinfo=UTC), 40, D),
    (2, 2, datetime(2024, 1, 8, 11, 0, tzinfo=UTC), 50, D),
    (2, None, datetime(2024, 1, 8, 11, 30, tzinfo=UTC), None, P),
    # Доставлен, но время не записано — в средних не участвует
    (2, None, datetime(2024, 1, 8, 11, 45, tzinfo=UTC), None, D),
]


def make_df(rows: list[tuple] = ROWS) -> pd.DataFrame:
    """DataFrame в формате OrderRepository.fetch_df."""
    records = [
        (f"ORD-{i:04d}", 56.3, 44.0, b, d, t, None, m, s)
        for i, (b, d, t, m, s) in enumerate(rows, start=1)
    ]
    df = pd.DataFrame(records, columns=ORDER_DF_COLUMNS)
    for column in ("order_time", "delivered_at"):
        df[column] = pd.to_datetime(df[column], utc=True)
    for column in ("branch_id", "driver_id", "delivery_time_minutes"):
        df[column] = df[column].astype("Int64")
    return df


# --- чистые функции ---


def test_summary_kpi_exact_values() -> None:
    kpi = summary_kpi(make_df())
    assert kpi == {
        "total_orders": 7,
        "delivered": 5,
        "canceled": 1,
        "cancel_rate": 0.1429,
        "avg_delivery_minutes": 35.0,
        "median_delivery_minutes": 35.0,
        # np.percentile([20, 30, 40, 50], 90) = 40 + 0.7 * 10
        "p90_delivery_minutes": 47.0,
    }


def test_summary_kpi_empty_frame() -> None:
    kpi = summary_kpi(make_df([]))
    assert kpi == {
        "total_orders": 0,
        "delivered": 0,
        "canceled": 0,
        "cancel_rate": 0.0,
        "avg_delivery_minutes": None,
        "median_delivery_minutes": None,
        "p90_delivery_minutes": None,
    }


def test_summary_kpi_all_canceled() -> None:
    rows = [(1, None, datetime(2024, 1, 1, h, tzinfo=UTC), None, C) for h in range(3)]
    kpi = summary_kpi(make_df(rows))
    assert kpi["total_orders"] == 3
    assert kpi["delivered"] == 0
    assert kpi["canceled"] == 3
    assert kpi["cancel_rate"] == 1.0
    assert kpi["avg_delivery_minutes"] is None
    assert kpi["p90_delivery_minutes"] is None


def test_branch_load_exact_values() -> None:
    load = branch_load(make_df(), {1: "Центр", 2: "Север", 3: "Юг"}, include_ids=[3])
    assert load.attrs["mean_orders"] == 2.33
    items = to_records(load)
    assert items == [
        {
            "branch_id": 1,
            "branch_name": "Центр",
            "orders": 3,
            "share_pct": 42.86,
            "delivered": 2,
            "canceled": 1,
            "cancel_rate": 0.3333,
            "avg_delivery_minutes": 25.0,
            "deviation_from_mean": 0.67,
            "deviation_pct": 28.57,
        },
        {
            "branch_id": 2,
            "branch_name": "Север",
            "orders": 4,
            "share_pct": 57.14,
            "delivered": 3,
            "canceled": 0,
            "cancel_rate": 0.0,
            "avg_delivery_minutes": 45.0,
            "deviation_from_mean": 1.67,
            "deviation_pct": 71.43,
        },
        {
            "branch_id": 3,
            "branch_name": "Юг",
            "orders": 0,
            "share_pct": 0.0,
            "delivered": 0,
            "canceled": 0,
            "cancel_rate": 0.0,
            "avg_delivery_minutes": None,
            "deviation_from_mean": -2.33,
            "deviation_pct": -100.0,
        },
    ]
    json.dumps(items)  # без NaN — сериализуется


def test_branch_load_empty() -> None:
    assert to_records(branch_load(make_df([]))) == []
    items = to_records(branch_load(make_df([]), {1: "Центр"}, include_ids=[1]))
    assert items[0]["orders"] == 0
    assert items[0]["share_pct"] == 0.0
    assert items[0]["deviation_pct"] is None


def test_timeseries_day_fills_gaps() -> None:
    points = to_records(timeseries(make_df(), "day"))
    assert [p["period_start"].day for p in points] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert [p["orders"] for p in points] == [3, 1, 0, 0, 0, 0, 0, 3]
    assert points[0]["period_start"] == datetime(2024, 1, 1, tzinfo=UTC)
    assert points[0]["cancel_rate"] == 0.3333
    assert points[0]["avg_delivery_minutes"] == 25.0
    assert points[3]["avg_delivery_minutes"] is None
    assert points[3]["cancel_rate"] == 0.0
    assert points[7]["avg_delivery_minutes"] == 50.0
    json.dumps(points, default=str)


def test_timeseries_week_and_hour() -> None:
    weeks = to_records(timeseries(make_df(), "week"))
    assert [(p["period_start"], p["orders"]) for p in weeks] == [
        (datetime(2024, 1, 1, tzinfo=UTC), 4),
        (datetime(2024, 1, 8, tzinfo=UTC), 3),
    ]
    hours = to_records(timeseries(make_df(), "hour"))
    # с 2024-01-01 10:00 по 2024-01-08 11:00 включительно
    assert len(hours) == 7 * 24 + 2
    assert hours[0]["orders"] == 2
    assert hours[0]["avg_delivery_minutes"] == 25.0
    assert hours[-1]["period_start"] == datetime(2024, 1, 8, 11, tzinfo=UTC)
    assert hours[-1]["orders"] == 3


def test_timeseries_empty_and_bad_granularity() -> None:
    assert to_records(timeseries(make_df([]), "day")) == []
    with pytest.raises(ValueError):
        timeseries(make_df(), "month")  # type: ignore[arg-type]


def test_aggregate_by_driver_and_hour_of_day() -> None:
    by_driver = to_records(aggregate(make_df(), "driver", ["orders", "avg_delivery_minutes"]))
    assert by_driver == [
        {"driver_id": 1, "orders": 2, "avg_delivery_minutes": 25.0},
        {"driver_id": 2, "orders": 3, "avg_delivery_minutes": 45.0},
        {"driver_id": None, "orders": 2, "avg_delivery_minutes": None},
    ]
    by_branch_day = aggregate(make_df(), ["branch", "day"], ["orders"])
    assert list(by_branch_day.columns) == ["branch_id", "day", "orders"]
    assert by_branch_day["orders"].tolist() == [3, 1, 3]
    by_hour = to_records(aggregate(make_df(), "hour_of_day", ["orders"]))
    assert by_hour == [
        {"hour_of_day": 9, "orders": 1},
        {"hour_of_day": 10, "orders": 2},
        {"hour_of_day": 11, "orders": 3},
        {"hour_of_day": 12, "orders": 1},
    ]


def test_aggregate_empty_and_unknown_names() -> None:
    empty = aggregate(make_df([]), ["branch", "week"], ["orders", "p90_delivery_minutes"])
    assert empty.empty
    assert list(empty.columns) == ["branch_id", "week", "orders", "p90_delivery_minutes"]
    with pytest.raises(ValueError):
        aggregate(make_df(), "city")
    with pytest.raises(ValueError):
        aggregate(make_df(), "branch", ["revenue"])


# --- эндпоинты ---


@pytest.fixture
def seeded(db_session: Session) -> Session:
    db_session.add_all(
        [
            Branch(id=1, name="Центр", lat=56.32, lon=44.03),
            Branch(id=2, name="Север", lat=56.35, lon=43.9),
            Branch(id=3, name="Юг", lat=56.25, lon=43.95),
            Branch(id=4, name="Закрытый", lat=56.2, lon=43.8, is_active=False),
        ]
    )
    db_session.flush()
    for i, (branch, _driver, order_time, minutes, status) in enumerate(ROWS, start=1):
        db_session.add(
            Order(
                external_id=f"ORD-{i:04d}",
                client_lat=56.3,
                client_lon=44.0,
                branch_id=branch,
                order_time=order_time,
                delivery_time_minutes=minutes,
                status=status,
            )
        )
    db_session.commit()
    return db_session


def _headers(session: Session, role: UserRole) -> dict[str, str]:
    user = User(username=f"user_{role.value}", password_hash="x", role=role.value)
    session.add(user)
    session.commit()
    token = create_access_token(user.id, user.role, settings=make_test_settings())
    return {"Authorization": f"Bearer {token}"}


def test_fetch_df_matches_hand_built_frame(seeded: Session) -> None:
    """Данные из БД дают те же KPI, что и DataFrame, собранный вручную."""
    assert summary_kpi(OrderRepository(seeded).fetch_df()) == summary_kpi(make_df())


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.MANAGER, UserRole.EXECUTIVE])
def test_kpi_endpoint(client: TestClient, seeded: Session, role: UserRole) -> None:
    response = client.get("/api/v1/stats/kpi", headers=_headers(seeded, role))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_orders"] == 7
    assert body["cancel_rate"] == 0.1429
    assert body["p90_delivery_minutes"] == 47.0
    assert body["period"] == {"date_from": None, "date_to": None, "branch_ids": None}


@pytest.mark.parametrize("path", ["kpi", "branch-load", "timeseries"])
def test_stats_roles(client: TestClient, seeded: Session, path: str) -> None:
    assert client.get(f"/api/v1/stats/{path}").status_code == 401
    driver = _headers(seeded, UserRole.DRIVER)
    assert client.get(f"/api/v1/stats/{path}", headers=driver).status_code == 403


def test_kpi_date_filter_and_empty_period(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.MANAGER)
    # Период полуоткрытый: заказы 2024-01-08 не попадают
    response = client.get(
        "/api/v1/stats/kpi",
        params={"date_from": "2024-01-01T00:00:00Z", "date_to": "2024-01-08T00:00:00Z"},
        headers=headers,
    )
    body = response.json()
    assert body["total_orders"] == 4
    assert body["p90_delivery_minutes"] == 38.0  # percentile([20, 30, 40], 90)
    assert body["period"]["date_from"].startswith("2024-01-01T00:00:00")

    # Время без пояса трактуется как UTC
    naive = client.get(
        "/api/v1/stats/kpi",
        params={"date_from": "2024-01-08T11:00:00", "date_to": "2024-01-08T11:31:00"},
        headers=headers,
    ).json()
    assert naive["total_orders"] == 2

    empty = client.get(
        "/api/v1/stats/kpi",
        params={"date_from": "2030-01-01T00:00:00Z", "date_to": "2030-02-01T00:00:00Z"},
        headers=headers,
    ).json()
    assert empty["total_orders"] == 0
    assert empty["avg_delivery_minutes"] is None


def test_date_validation(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.ADMIN)
    for path in ("kpi", "branch-load", "timeseries"):
        response = client.get(
            f"/api/v1/stats/{path}",
            params={"date_from": "2024-02-01T00:00:00Z", "date_to": "2024-01-01T00:00:00Z"},
            headers=headers,
        )
        assert response.status_code == 422
    bad = client.get("/api/v1/stats/kpi", params={"date_from": "вчера"}, headers=headers)
    assert bad.status_code == 422


def test_branch_load_endpoint(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.EXECUTIVE)
    body = client.get("/api/v1/stats/branch-load", headers=headers).json()
    # Закрытый филиал без заказов не показывается, активный «Юг» — показывается
    assert [item["branch_name"] for item in body["items"]] == ["Центр", "Север", "Юг"]
    assert body["total_orders"] == 7
    assert body["mean_orders"] == 2.33
    assert body["items"][2]["avg_delivery_minutes"] is None

    filtered = client.get(
        "/api/v1/stats/branch-load", params={"branch_id": [2, 3]}, headers=headers
    ).json()
    assert [item["branch_id"] for item in filtered["items"]] == [2, 3]
    assert filtered["items"][0]["share_pct"] == 100.0
    assert filtered["period"]["branch_ids"] == [2, 3]


def test_kpi_branch_filter(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.ADMIN)
    body = client.get("/api/v1/stats/kpi", params={"branch_id": 1}, headers=headers).json()
    assert body["total_orders"] == 3
    assert body["canceled"] == 1
    assert body["avg_delivery_minutes"] == 25.0


def test_timeseries_endpoint(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.MANAGER)
    body = client.get(
        "/api/v1/stats/timeseries", params={"granularity": "week"}, headers=headers
    ).json()
    assert body["granularity"] == "week"
    assert [p["orders"] for p in body["points"]] == [4, 3]
    assert body["points"][0]["period_start"].startswith("2024-01-01T00:00:00")

    day = client.get("/api/v1/stats/timeseries", params={"branch_id": 2}, headers=headers).json()
    assert body["points"] and day["granularity"] == "day"
    assert [p["orders"] for p in day["points"]] == [1, 0, 0, 0, 0, 0, 3]

    bad = client.get("/api/v1/stats/timeseries", params={"granularity": "month"}, headers=headers)
    assert bad.status_code == 422


def test_openapi_documents_utc(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    kpi = schema["paths"]["/api/v1/stats/kpi"]["get"]
    assert "UTC" in kpi["description"]
