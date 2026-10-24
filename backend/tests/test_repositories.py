"""Тесты моделей и репозиториев на SQLite."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import Branch, Driver, Order, OrderStatus, ReportTemplate, User
from backend.app.repositories.branch import BranchRepository
from backend.app.repositories.driver import DriverRepository
from backend.app.repositories.order import ORDER_DF_COLUMNS, OrderRepository
from backend.app.repositories.report_template import ReportTemplateRepository
from backend.app.repositories.user import UserRepository

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def sample(db_session: Session) -> dict[str, list]:
    """Два филиала (один неактивный), водитель и три заказа в разные дни."""
    branches = [
        Branch(name="Центр", lat=56.32, lon=44.03, current_queue=2),
        Branch(name="Закрытый", lat=56.24, lon=43.86, is_active=False),
    ]
    db_session.add_all(branches)
    db_session.flush()
    driver = Driver(full_name="Иван Петров", branch_id=branches[0].id)
    db_session.add(driver)
    db_session.flush()
    orders = [
        Order(
            external_id="ORD-0001",
            client_lat=56.3,
            client_lon=44.0,
            branch_id=branches[0].id,
            driver_id=driver.id,
            order_time=T0,
            delivered_at=T0 + timedelta(minutes=30),
            delivery_time_minutes=30,
            status=OrderStatus.DELIVERED,
        ),
        Order(
            external_id="ORD-0002",
            client_lat=56.31,
            client_lon=44.01,
            branch_id=branches[0].id,
            order_time=T0 + timedelta(days=1),
            status=OrderStatus.CANCELED,
        ),
        Order(
            external_id="ORD-0003",
            client_lat=56.25,
            client_lon=43.87,
            branch_id=branches[1].id,
            order_time=T0 + timedelta(days=2),
            status=OrderStatus.PENDING,
        ),
    ]
    db_session.add_all(orders)
    db_session.commit()
    return {"branches": branches, "drivers": [driver], "orders": orders}


def test_user_repository(db_session: Session) -> None:
    repo = UserRepository(db_session)
    user = repo.add(User(username="boss", password_hash="x", role="executive"))
    repo.commit()

    assert repo.get(user.id) is user
    assert repo.get_by_username("boss") is user
    assert repo.get_by_username("nobody") is None
    assert repo.count_by_role("executive") == 1
    assert user.is_active is True
    assert user.created_at.tzinfo is not None


def test_user_unique_username(db_session: Session) -> None:
    repo = UserRepository(db_session)
    repo.add(User(username="dup", password_hash="x", role="manager"))
    with pytest.raises(IntegrityError):
        repo.add(User(username="dup", password_hash="y", role="manager"))


def test_user_role_check_constraint(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        UserRepository(db_session).add(User(username="x", password_hash="x", role="superuser"))


def test_branch_list_active(sample: dict, db_session: Session) -> None:
    repo = BranchRepository(db_session)
    assert [b.name for b in repo.list_active()] == ["Центр"]
    assert len(repo.list()) == 2
    assert repo.get_by_name("Закрытый") is not None


def test_branch_queue_non_negative(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        BranchRepository(db_session).add(Branch(name="Bad", lat=0, lon=0, current_queue=-1))


def test_driver_repository(sample: dict, db_session: Session) -> None:
    repo = DriverRepository(db_session)
    branch_id = sample["branches"][0].id
    assert [d.full_name for d in repo.list_by_branch(branch_id)] == ["Иван Петров"]
    assert repo.get_by_full_name("Иван Петров") is not None


def test_base_repository_delete_and_paging(sample: dict, db_session: Session) -> None:
    repo = OrderRepository(db_session)
    assert [o.external_id for o in repo.list(offset=1, limit=1)] == ["ORD-0002"]
    repo.delete(repo.get_by_external_id("ORD-0003"))
    repo.commit()
    assert repo.existing_external_ids() == {"ORD-0001", "ORD-0002"}


def test_datetime_is_utc_aware(sample: dict, db_session: Session) -> None:
    db_session.expire_all()
    order = OrderRepository(db_session).get_by_external_id("ORD-0001")
    assert order is not None
    assert order.order_time == T0
    assert order.order_time.tzinfo is not None


def test_naive_datetime_rejected(sample: dict, db_session: Session) -> None:
    order = sample["orders"][1]
    order.order_time = datetime(2026, 10, 1, 12, 0)
    with pytest.raises(Exception, match="timezone-aware"):
        db_session.flush()


def test_fetch_df_columns_and_types(sample: dict, db_session: Session) -> None:
    df = OrderRepository(db_session).fetch_df()
    assert list(df.columns) == ORDER_DF_COLUMNS
    assert list(df["order_id"]) == ["ORD-0001", "ORD-0002", "ORD-0003"]
    assert str(df["order_time"].dt.tz) == "UTC"
    assert df["driver_id"].isna().sum() == 2
    assert df.loc[0, "delivery_time_minutes"] == 30


def test_fetch_df_filters(sample: dict, db_session: Session) -> None:
    repo = OrderRepository(db_session)
    first_branch = sample["branches"][0].id

    by_period = repo.fetch_df(date_from=T0 + timedelta(hours=1), date_to=T0 + timedelta(days=2))
    assert list(by_period["order_id"]) == ["ORD-0002"]

    by_branch = repo.fetch_df(branch_ids=[first_branch])
    assert set(by_branch["order_id"]) == {"ORD-0001", "ORD-0002"}

    by_status = repo.fetch_df(status=OrderStatus.DELIVERED)
    assert list(by_status["order_id"]) == ["ORD-0001"]

    by_statuses = repo.fetch_df(status=[OrderStatus.CANCELED, OrderStatus.PENDING])
    assert len(by_statuses) == 2


def test_fetch_df_empty_keeps_columns(db_session: Session) -> None:
    df = OrderRepository(db_session).fetch_df()
    assert df.empty
    assert list(df.columns) == ORDER_DF_COLUMNS


def test_report_templates(db_session: Session) -> None:
    users = UserRepository(db_session)
    owner = users.add(User(username="m", password_hash="x", role="manager"))
    other = users.add(User(username="o", password_hash="x", role="manager"))
    repo = ReportTemplateRepository(db_session)
    repo.add(ReportTemplate(name="Системный", is_system=True, config={"metrics": ["count"]}))
    repo.add(ReportTemplate(name="Мой", owner_id=owner.id))
    repo.add(ReportTemplate(name="Чужой", owner_id=other.id))
    repo.commit()

    assert [t.name for t in repo.list_available(owner.id)] == ["Системный", "Мой"]
    system = repo.get_system_by_name("Системный")
    assert system is not None
    assert system.config == {"metrics": ["count"]}

    with pytest.raises(IntegrityError):
        repo.add(ReportTemplate(name="Мой", owner_id=owner.id))
