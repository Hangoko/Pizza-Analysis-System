"""Тесты скрипта наполнения БД."""

from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import Branch, Driver, Order
from backend.app.scripts.seed import BRANCHES, DRIVERS_COUNT, seed


def _write_csv(path: Path) -> Path:
    pd.DataFrame(
        [
            ["ORD-0001", 56.3, 44.0, 2, 7, "2026-10-07 19:10:00", 43.0, "Delivered"],
            ["ORD-0002", 56.2, 43.9, 5, 20, "2026-10-08 10:00:00", None, "Canceled"],
        ],
        columns=[
            "order_id",
            "client_lat",
            "client_lon",
            "branch_id",
            "driver_id",
            "order_time",
            "delivery_time_minutes",
            "status",
        ],
    ).to_csv(path, index=False)
    return path


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_is_idempotent(db_session: Session, tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path / "orders.csv")

    first = seed(db_session, csv_path)
    assert first == {"branches": len(BRANCHES), "drivers": DRIVERS_COUNT, "new_orders": 2}

    second = seed(db_session, csv_path)
    assert second["new_orders"] == 0
    assert _count(db_session, Branch) == len(BRANCHES)
    assert _count(db_session, Driver) == DRIVERS_COUNT
    assert _count(db_session, Order) == 2


def test_seed_maps_csv_fields(db_session: Session, tmp_path: Path) -> None:
    seed(db_session, _write_csv(tmp_path / "orders.csv"))

    delivered = db_session.scalar(select(Order).where(Order.external_id == "ORD-0001"))
    assert delivered is not None
    assert delivered.branch.name == BRANCHES[2].name
    assert delivered.driver is not None and delivered.driver.full_name == "Водитель 07"
    # 19:10 по Нижнему Новгороду (UTC+3) = 16:10 UTC
    assert delivered.order_time.isoformat() == "2026-10-07T16:10:00+00:00"
    assert delivered.delivery_time_minutes == 43
    assert delivered.delivered_at is not None
    assert (delivered.delivered_at - delivered.order_time).total_seconds() == 43 * 60

    canceled = db_session.scalar(select(Order).where(Order.external_id == "ORD-0002"))
    assert canceled is not None
    assert canceled.delivery_time_minutes is None
    assert canceled.delivered_at is None
