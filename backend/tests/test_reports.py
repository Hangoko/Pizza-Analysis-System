"""Тесты отчётов: схема конфигурации, права, CRUD шаблонов, конструктор, CSV, seed, миграция."""

import argparse
import csv
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args
from urllib.parse import unquote

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import BASE_DIR
from backend.app.core.security import create_access_token
from backend.app.db.models import Branch, Driver, Order, ReportTemplate, User
from backend.app.db.models.user import UserRole
from backend.app.schemas.reports import (
    ReportConfig,
    ReportGroupBy,
    ReportMetric,
    ReportPeriod,
)
from backend.app.services.report_service import (
    SYSTEM_TEMPLATES,
    build_report_frame,
    report_filename,
    resolve_period,
    seed_system_templates,
    to_csv,
)
from backend.app.services.stats_service import GROUP_KEYS, METRICS, aggregate, to_records
from backend.tests.conftest import make_test_settings
from backend.tests.test_stats import ROWS, make_df

API = "/api/v1/reports"
ALL_METRICS = list(METRICS)


def _cfg(**overrides: Any) -> dict[str, Any]:
    return {"metrics": ["orders", "avg_delivery_minutes"], "group_by": "branch"} | overrides


# --- фикстуры ---


@pytest.fixture
def seeded(db_session: Session) -> Session:
    """Те же заказы, что в test_stats (с водителями), и системные шаблоны."""
    db_session.add_all(
        [
            Branch(id=1, name="Центр", lat=56.32, lon=44.03),
            Branch(id=2, name="Север", lat=56.35, lon=43.9),
            Driver(id=1, full_name="Иванов", branch_id=1),
            Driver(id=2, full_name="Петров", branch_id=2),
        ]
    )
    db_session.flush()
    for i, (branch, driver, order_time, minutes, status) in enumerate(ROWS, start=1):
        db_session.add(
            Order(
                external_id=f"ORD-{i:04d}",
                client_lat=56.3,
                client_lon=44.0,
                branch_id=branch,
                driver_id=driver,
                order_time=order_time,
                delivery_time_minutes=minutes,
                status=status,
            )
        )
    seed_system_templates(db_session)
    db_session.commit()
    return db_session


def _headers(session: Session, role: UserRole, name: str | None = None) -> dict[str, str]:
    user = User(username=name or f"user_{role.value}", password_hash="x", role=role.value)
    session.add(user)
    session.commit()
    token = create_access_token(user.id, user.role, settings=make_test_settings())
    return {"Authorization": f"Bearer {token}"}


def _system_id(session: Session, name: str = "Нагрузка филиалов") -> int:
    template = session.query(ReportTemplate).filter_by(is_system=True, name=name).one()
    return template.id


def _create(client: TestClient, headers: dict[str, str], name: str = "Мой отчёт") -> dict:
    response = client.post(
        f"{API}/templates", json={"name": name, "config": _cfg()}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


ALL_TIME = {"date_from": "2024-01-01T00:00:00Z", "date_to": "2024-02-01T00:00:00Z"}


# --- схема конфигурации ---


def test_schema_names_match_stats_service() -> None:
    assert set(get_args(ReportMetric)) == set(METRICS)
    assert set(get_args(ReportGroupBy)) == set(GROUP_KEYS)


def test_config_validation() -> None:
    config = ReportConfig.model_validate(
        {"metrics": ["orders", "orders", "canceled"], "filters": {"branch_ids": [2, 1, 2]}}
    )
    assert config.metrics == ["orders", "canceled"]
    assert config.filters.branch_ids == [1, 2]
    assert config.group_by is None
    assert config.default_period_days == 30
    for bad in (
        {"metrics": ["revenue"]},
        {"metrics": []},
        {"metrics": ["orders"], "group_by": "city"},
        {"metrics": ["orders"], "filters": {"statuses": ["Lost"]}},
        {"metrics": ["orders"], "default_period_days": 0},
        {"metrics": ["orders"], "unknown": 1},
    ):
        with pytest.raises(ValidationError):
            ReportConfig.model_validate(bad)
    with pytest.raises(ValidationError):
        ReportPeriod(date_from=datetime(2024, 2, 1), date_to=datetime(2024, 1, 1))


def test_api_rejects_invalid_config(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.MANAGER)
    bad = client.post(
        f"{API}/templates",
        json={"name": "x", "config": {"metrics": ["revenue"]}},
        headers=headers,
    )
    assert bad.status_code == 422
    assert "revenue" in bad.text
    preview = client.post(f"{API}/preview", json={"config": _cfg(group_by="city")}, headers=headers)
    assert preview.status_code == 422
    period = client.post(
        f"{API}/preview",
        json={"config": _cfg(), "date_from": "2024-02-01", "date_to": "2024-01-01"},
        headers=headers,
    )
    assert period.status_code == 422
    template_id = _system_id(seeded)
    export = client.get(
        f"{API}/templates/{template_id}/export.csv",
        params={"date_from": "2024-02-01", "date_to": "2024-01-01"},
        headers=headers,
    )
    assert export.status_code == 422
    sep = client.get(
        f"{API}/templates/{template_id}/export.csv", params={"delimiter": "|"}, headers=headers
    )
    assert sep.status_code == 422


# --- права ---


def test_driver_and_anonymous_have_no_access(client: TestClient, seeded: Session) -> None:
    driver = _headers(seeded, UserRole.DRIVER)
    template_id = _system_id(seeded)
    assert client.get(f"{API}/templates").status_code == 401
    assert client.get(f"{API}/templates", headers=driver).status_code == 403
    assert client.get(f"{API}/templates/{template_id}", headers=driver).status_code == 403
    export = client.get(f"{API}/templates/{template_id}/export.csv", headers=driver)
    assert export.status_code == 403
    preview = client.post(f"{API}/preview", json={"config": _cfg()}, headers=driver)
    assert preview.status_code == 403


def test_other_users_template_is_forbidden(client: TestClient, seeded: Session) -> None:
    owner = _headers(seeded, UserRole.MANAGER, "owner")
    other = _headers(seeded, UserRole.MANAGER, "other")
    executive = _headers(seeded, UserRole.EXECUTIVE)
    template_id = _create(client, owner)["id"]
    url = f"{API}/templates/{template_id}"
    body = {"name": "Чужой", "config": _cfg()}
    for headers in (other, executive):
        assert client.get(url, headers=headers).status_code == 403
        assert client.put(url, json=body, headers=headers).status_code == 403
        assert client.delete(url, headers=headers).status_code == 403
        assert client.get(f"{url}/export.csv", headers=headers).status_code == 403
    names = [t["name"] for t in client.get(f"{API}/templates", headers=other).json()]
    assert "Мой отчёт" not in names
    assert client.get(url, headers=owner).status_code == 200


def test_executive_reads_and_exports_only(client: TestClient, seeded: Session) -> None:
    executive = _headers(seeded, UserRole.EXECUTIVE)
    template_id = _system_id(seeded)
    created = client.post(
        f"{API}/templates", json={"name": "x", "config": _cfg()}, headers=executive
    )
    assert created.status_code == 403
    listed = client.get(f"{API}/templates", headers=executive).json()
    assert {t["name"] for t in listed} == {name for name, _, _ in SYSTEM_TEMPLATES}
    url = f"{API}/templates/{template_id}"
    assert client.get(url, headers=executive).status_code == 200
    assert (
        client.put(url, json={"name": "x", "config": _cfg()}, headers=executive).status_code == 403
    )
    assert client.delete(url, headers=executive).status_code == 403
    assert client.get(f"{url}/export.csv", headers=executive).status_code == 200
    preview = client.post(f"{API}/preview", json={"config": _cfg()}, headers=executive)
    assert preview.status_code == 200


def test_system_templates_editable_only_by_admin(client: TestClient, seeded: Session) -> None:
    manager = _headers(seeded, UserRole.MANAGER)
    admin = _headers(seeded, UserRole.ADMIN)
    template_id = _system_id(seeded)
    url = f"{API}/templates/{template_id}"
    body = {"name": "Нагрузка филиалов", "description": "v2", "config": _cfg(group_by="week")}
    assert client.put(url, json=body, headers=manager).status_code == 403
    assert client.delete(url, headers=manager).status_code == 403
    system = client.post(
        f"{API}/templates", json={"name": "S", "config": _cfg(), "is_system": True}, headers=manager
    )
    assert system.status_code == 403

    updated = client.put(url, json=body, headers=admin)
    assert updated.status_code == 200, updated.text
    assert updated.json()["config"]["group_by"] == "week"
    assert updated.json()["is_system"] is True and updated.json()["owner_id"] is None

    created = client.post(
        f"{API}/templates", json={"name": "S", "config": _cfg(), "is_system": True}, headers=admin
    )
    assert created.status_code == 201
    assert created.json()["owner_id"] is None
    # Видят все роли с доступом к отчётам
    assert client.get(f"{API}/templates/{created.json()['id']}", headers=manager).status_code == 200
    assert client.delete(url, headers=admin).status_code == 204


def test_admin_manages_user_templates(client: TestClient, seeded: Session) -> None:
    manager = _headers(seeded, UserRole.MANAGER)
    admin = _headers(seeded, UserRole.ADMIN)
    template_id = _create(client, manager)["id"]
    names = [t["name"] for t in client.get(f"{API}/templates", headers=admin).json()]
    assert "Мой отчёт" in names
    url = f"{API}/templates/{template_id}"
    updated = client.put(url, json={"name": "Правка", "config": _cfg()}, headers=admin)
    assert updated.status_code == 200
    assert client.delete(url, headers=admin).status_code == 204


# --- CRUD ---


def test_template_crud(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.MANAGER)
    created = _create(client, headers)
    assert created["is_system"] is False
    assert created["config"] == {
        "metrics": ["orders", "avg_delivery_minutes"],
        "group_by": "branch",
        "filters": {"branch_ids": None, "driver_ids": None, "statuses": None},
        "default_period_days": 30,
    }
    listed = client.get(f"{API}/templates", headers=headers).json()
    # Сначала системные, затем свои
    assert len(listed) == len(SYSTEM_TEMPLATES) + 1
    assert listed[-1]["id"] == created["id"]

    url = f"{API}/templates/{created['id']}"
    assert client.get(url, headers=headers).json()["name"] == "Мой отчёт"
    body = {
        "name": "По дням",
        "description": "описание",
        "config": {"metrics": ["delivered"], "group_by": "day", "default_period_days": None},
    }
    updated = client.put(url, json=body, headers=headers).json()
    assert updated["name"] == "По дням"
    assert updated["description"] == "описание"
    assert updated["config"]["default_period_days"] is None

    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(url, headers=headers).status_code == 404
    assert client.get(f"{API}/templates/9999", headers=headers).status_code == 404


def test_template_name_conflict(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.MANAGER)
    admin = _headers(seeded, UserRole.ADMIN)
    _create(client, headers, "Дубль")
    again = client.post(
        f"{API}/templates", json={"name": "Дубль", "config": _cfg()}, headers=headers
    )
    assert again.status_code == 409
    # У другого пользователя то же имя допустимо
    _create(client, admin, "Дубль")
    system = client.post(
        f"{API}/templates",
        json={"name": "Сводка по сети", "config": _cfg(), "is_system": True},
        headers=admin,
    )
    assert system.status_code == 409


# --- построение отчёта ---


def test_build_report_frame_reuses_aggregate() -> None:
    df = make_df()
    config = ReportConfig(metrics=ALL_METRICS, group_by="branch")
    frame = build_report_frame(df, config, {1: "Центр", 2: "Север"})
    expected = aggregate(df, "branch", ALL_METRICS)
    assert list(frame.columns) == ["branch_id", "branch_name", *ALL_METRICS]
    assert frame.drop(columns="branch_name").equals(expected)
    assert frame["branch_name"].tolist() == ["Центр", "Север"]

    by_driver = build_report_frame(
        df,
        ReportConfig.model_validate(
            {"metrics": ["orders"], "group_by": "driver", "filters": {"driver_ids": [2]}}
        ),
        driver_names={2: "Петров"},
    )
    assert to_records(by_driver) == [{"driver_id": 2, "driver_name": "Петров", "orders": 3}]

    statuses = build_report_frame(
        df,
        ReportConfig.model_validate({"metrics": ["orders"], "filters": {"statuses": ["Canceled"]}}),
    )
    assert to_records(statuses) == [{"orders": 1}]


def test_resolve_period_default_days() -> None:
    now = datetime(2026, 10, 25, 12, tzinfo=UTC)
    config = ReportConfig(metrics=["orders"], default_period_days=7)
    period = resolve_period(config, ReportPeriod(), now=now)
    assert period.date_from == datetime(2026, 10, 18, 12, tzinfo=UTC)
    assert period.date_to == now
    explicit = ReportPeriod(date_from=datetime(2024, 1, 1, tzinfo=UTC))
    assert resolve_period(config, explicit, now=now) == explicit
    unlimited = ReportConfig(metrics=["orders"], default_period_days=None)
    assert resolve_period(unlimited, ReportPeriod(), now=now) == ReportPeriod()


def test_preview_matches_stats_service(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.MANAGER)
    response = client.post(
        f"{API}/preview",
        json={"config": {"metrics": ALL_METRICS, "group_by": "branch"}, **ALL_TIME},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    expected = to_records(aggregate(make_df(), "branch", ALL_METRICS))
    rows = [{k: v for k, v in row.items() if k != "branch_name"} for row in body["rows"]]
    assert rows == expected
    assert [row["branch_name"] for row in body["rows"]] == ["Центр", "Север"]
    assert body["columns"][0] == {"key": "branch_id", "label": "ID филиала"}
    assert body["period"]["date_from"].startswith("2024-01-01T00:00:00")

    summary = client.post(
        f"{API}/preview",
        json={"config": {"metrics": ALL_METRICS, "default_period_days": None}},
        headers=headers,
    ).json()
    assert summary["rows"] == to_records(aggregate(make_df(), (), ALL_METRICS))
    assert summary["period"] == {"date_from": None, "date_to": None}

    # Период по умолчанию (30 дней до текущего момента) — данных 2024 года нет
    recent = client.post(f"{API}/preview", json={"config": _cfg()}, headers=headers).json()
    assert recent["rows"] == []
    assert recent["period"]["date_from"] is not None


# --- CSV ---


def _parse_csv(content: bytes, delimiter: str = ";") -> list[list[str]]:
    assert content.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=delimiter))


def test_template_export_csv(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.EXECUTIVE)
    template_id = _system_id(seeded)
    response = client.get(
        f"{API}/templates/{template_id}/export.csv", params=ALL_TIME, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    rows = _parse_csv(response.content)
    assert rows[0] == [
        "ID филиала",
        "Филиал",
        "Заказов",
        "Доставлено",
        "Отменено",
        "Доля отмен",
        "Среднее время доставки, мин",
    ]
    assert len(rows) == 1 + 2
    assert rows[1] == ["1", "Центр", "3", "2", "1", "0,3333", "25,0"]
    assert b"\r\n" in response.content

    disposition = response.headers["content-disposition"]
    expected = "report_нагрузка_филиалов_2024-01-01_2024-02-01.csv"
    assert disposition.startswith('attachment; filename="report_')
    assert "filename*=UTF-8''" in disposition
    assert unquote(disposition.split("filename*=UTF-8''")[1]) == expected
    disposition.encode("latin-1")  # заголовок — только ASCII


def test_adhoc_export_csv_comma(client: TestClient, seeded: Session) -> None:
    headers = _headers(seeded, UserRole.MANAGER)
    response = client.post(
        f"{API}/export.csv",
        params={"delimiter": ","},
        json={
            "name": "Weekly",
            "config": {"metrics": ["orders", "cancel_rate"], "group_by": "week"},
            **ALL_TIME,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    rows = _parse_csv(response.content, ",")
    assert rows == [
        ["Неделя с (UTC)", "Заказов", "Доля отмен"],
        ["2024-01-01", "4", "0.25"],
        ["2024-01-08", "3", "0.0"],
    ]
    assert (
        'filename="report_weekly_2024-01-01_2024-02-01.csv"'
        in (response.headers["content-disposition"])
    )


def test_csv_helpers() -> None:
    empty = build_report_frame(make_df([]), ReportConfig(metrics=["orders"], group_by="day"))
    rows = _parse_csv(to_csv(empty))
    assert rows == [["День (UTC)", "Заказов"]]
    period = ReportPeriod(date_from=datetime(2024, 1, 1, tzinfo=UTC))
    assert report_filename("Сводка / сеть!", period) == "report_сводка_сеть_2024-01-01_now.csv"


# --- seed и миграция ---


def test_seed_system_templates_idempotent(db_session: Session) -> None:
    assert seed_system_templates(db_session) == len(SYSTEM_TEMPLATES)
    db_session.commit()
    assert seed_system_templates(db_session) == 0
    templates = db_session.query(ReportTemplate).all()
    assert len(templates) == len(SYSTEM_TEMPLATES)
    assert all(t.is_system and t.owner_id is None for t in templates)
    for template in templates:
        ReportConfig.model_validate(template.config)


def test_system_name_unique_in_model(db_session: Session) -> None:
    db_session.add(ReportTemplate(name="X", is_system=True, config={}))
    db_session.commit()
    db_session.add(ReportTemplate(name="X", is_system=True, config={}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_migration_system_name_unique(tmp_path: Path) -> None:
    """Частичный индекс из миграции 0002: системные имена уникальны, пользовательские — нет."""
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    cfg = Config(str(BASE_DIR / "backend" / "alembic.ini"))
    cfg.cmd_opts = argparse.Namespace(x=[f"db_url={url}"])
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    insert = text(
        "INSERT INTO report_templates (name, is_system, owner_id, config, created_at, updated_at) "
        "VALUES (:name, :is_system, NULL, '{}', '2024-01-01', '2024-01-01')"
    )
    try:
        with engine.begin() as conn:
            conn.execute(insert, {"name": "Сводка", "is_system": True})
            # Несистемные шаблоны без владельца под индекс не попадают
            conn.execute(insert, {"name": "Сводка", "is_system": False})
            conn.execute(insert, {"name": "Сводка", "is_system": False})
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(insert, {"name": "Сводка", "is_system": True})

        command.downgrade(cfg, "0001")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM report_templates"))
            conn.execute(insert, {"name": "Сводка", "is_system": True})
            conn.execute(insert, {"name": "Сводка", "is_system": True})
    finally:
        engine.dispose()
