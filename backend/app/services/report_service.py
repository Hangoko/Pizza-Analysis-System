"""
Отчёты: шаблоны (CRUD с проверкой прав), конструктор и экспорт в CSV.

Расчёт метрик не дублируется — `build_report_frame` вызывает `stats_service.aggregate`.

Права (матрица из README):
- системные шаблоны читают admin/manager/executive, изменяет и удаляет только admin;
- пользовательские шаблоны — только владелец или admin;
- executive — только чтение и экспорт; driver — нет доступа.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import ReportTemplate, User
from backend.app.db.models.user import UserRole
from backend.app.repositories.branch import BranchRepository
from backend.app.repositories.driver import DriverRepository
from backend.app.repositories.order import OrderRepository
from backend.app.repositories.report_template import ReportTemplateRepository
from backend.app.schemas.reports import (
    CsvDelimiter,
    ReportConfig,
    ReportPeriod,
    ReportTemplateCreate,
    ReportTemplateUpdate,
)
from backend.app.services.stats_service import aggregate

REPORT_ROLES = frozenset({UserRole.ADMIN.value, UserRole.MANAGER.value, UserRole.EXECUTIVE.value})
EDITOR_ROLES = frozenset({UserRole.ADMIN.value, UserRole.MANAGER.value})

# Заголовки CSV (ключи JSON остаются английскими)
COLUMN_LABELS: dict[str, str] = {
    "branch_id": "ID филиала",
    "branch_name": "Филиал",
    "driver_id": "ID водителя",
    "driver_name": "Водитель",
    "status": "Статус",
    "hour": "Час (UTC)",
    "day": "День (UTC)",
    "week": "Неделя с (UTC)",
    "hour_of_day": "Час суток (UTC)",
    "weekday": "День недели (0 = пн)",
    "orders": "Заказов",
    "delivered": "Доставлено",
    "canceled": "Отменено",
    "cancel_rate": "Доля отмен",
    "avg_delivery_minutes": "Среднее время доставки, мин",
    "median_delivery_minutes": "Медиана времени доставки, мин",
    "p90_delivery_minutes": "90-й перцентиль времени доставки, мин",
}
_TIME_FORMATS = {"hour": "%Y-%m-%d %H:%M", "day": "%Y-%m-%d", "week": "%Y-%m-%d"}

# Системные шаблоны (создаются seed-скриптом)
SYSTEM_TEMPLATES: tuple[tuple[str, str, dict], ...] = (
    (
        "Сводка по сети",
        "Итоговые KPI по всем филиалам за период",
        {
            "metrics": [
                "orders",
                "delivered",
                "canceled",
                "cancel_rate",
                "avg_delivery_minutes",
                "median_delivery_minutes",
                "p90_delivery_minutes",
            ],
            "group_by": None,
        },
    ),
    (
        "Нагрузка филиалов",
        "Заказы, доставки, отмены и среднее время доставки по каждому филиалу",
        {
            "metrics": ["orders", "delivered", "canceled", "cancel_rate", "avg_delivery_minutes"],
            "group_by": "branch",
        },
    ),
    (
        "Динамика заказов по дням",
        "Количество заказов и время доставки по дням",
        {
            "metrics": ["orders", "delivered", "canceled", "cancel_rate", "avg_delivery_minutes"],
            "group_by": "day",
        },
    ),
    (
        "Эффективность водителей",
        "Доставки и время доставки по каждому водителю",
        {
            "metrics": [
                "orders",
                "delivered",
                "cancel_rate",
                "avg_delivery_minutes",
                "median_delivery_minutes",
                "p90_delivery_minutes",
            ],
            "group_by": "driver",
        },
    ),
)


class ReportError(Exception):
    """Базовая ошибка сервиса отчётов."""


class TemplateNotFoundError(ReportError):
    pass


class ReportPermissionError(ReportError):
    pass


class TemplateNameConflictError(ReportError):
    pass


# --- права ---


def can_read(user: User, template: ReportTemplate) -> bool:
    if user.role not in REPORT_ROLES:
        return False
    return template.is_system or user.role == UserRole.ADMIN or template.owner_id == user.id


def can_modify(user: User, template: ReportTemplate) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role not in EDITOR_ROLES or template.is_system:
        return False
    return template.owner_id == user.id


def can_create(user: User, is_system: bool) -> bool:
    if is_system:
        return user.role == UserRole.ADMIN
    return user.role in EDITOR_ROLES


# --- построение отчёта (чистые функции) ---


def resolve_period(
    config: ReportConfig, period: ReportPeriod, now: datetime | None = None
) -> ReportPeriod:
    """Если даты не переданы — последние `default_period_days` дней до текущего момента."""
    if period.date_from or period.date_to or config.default_period_days is None:
        return period
    end = now or datetime.now(UTC)
    return ReportPeriod(date_from=end - timedelta(days=config.default_period_days), date_to=end)


def build_report_frame(
    df: pd.DataFrame,
    config: ReportConfig,
    branch_names: Mapping[int, str] | None = None,
    driver_names: Mapping[int, str] | None = None,
) -> pd.DataFrame:
    """
    Отчёт по DataFrame формата `OrderRepository.fetch_df`.
    Фильтры филиалов и статусов применяются здесь же (на случай данных не из БД),
    затем — `aggregate`. При группировке по филиалу/водителю добавляется колонка с названием.
    """
    filters = config.filters
    if filters.branch_ids:
        df = df[df["branch_id"].isin(filters.branch_ids).fillna(False).astype(bool)]
    if filters.driver_ids:
        df = df[df["driver_id"].isin(filters.driver_ids).fillna(False).astype(bool)]
    if filters.statuses:
        df = df[df["status"].isin(filters.statuses)]

    result = aggregate(df, config.group_by or (), config.metrics)
    for id_column, name_column, names in (
        ("branch_id", "branch_name", branch_names),
        ("driver_id", "driver_name", driver_names),
    ):
        if id_column in result.columns and names is not None:
            position = result.columns.get_loc(id_column) + 1
            values = [None if pd.isna(i) else names.get(int(i)) for i in result[id_column]]
            result.insert(position, name_column, values)
    return result


def report_columns(df: pd.DataFrame) -> list[dict[str, str]]:
    return [{"key": str(c), "label": COLUMN_LABELS.get(str(c), str(c))} for c in df.columns]


def to_csv(df: pd.DataFrame, delimiter: CsvDelimiter = ";") -> bytes:
    """
    CSV для Excel: UTF-8 с BOM, русские заголовки, строки через CRLF.
    С разделителем `;` (Excel RU) дробная часть отделяется запятой, с `,` — точкой.
    """
    out = df.copy()
    for column, fmt in _TIME_FORMATS.items():
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], utc=True).dt.strftime(fmt)
    out = out.rename(columns=COLUMN_LABELS)
    text = out.to_csv(
        index=False,
        sep=delimiter,
        decimal="," if delimiter == ";" else ".",
        lineterminator="\r\n",
    )
    return text.encode("utf-8-sig")


def _slug(value: str) -> str:
    return re.sub(r"[^\w-]+", "_", value.strip().lower()).strip("_")


def report_filename(name: str, period: ReportPeriod) -> str:
    """`report_<slug>_<from>_<to>.csv`; открытые границы — `start` / `now`."""
    start = period.date_from.date().isoformat() if period.date_from else "start"
    end = period.date_to.date().isoformat() if period.date_to else "now"
    parts = ["report", _slug(name), start, end]
    return "_".join(p for p in parts if p) + ".csv"


def content_disposition(filename: str) -> str:
    """Заголовок с ASCII-запасным именем и `filename*` по RFC 5987 (для кириллицы)."""
    fallback = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in "._-") else "_" for ch in filename
    )
    fallback = re.sub(r"_+", "_", fallback)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


# --- сервис ---


class ReportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.templates = ReportTemplateRepository(session)
        self.orders = OrderRepository(session)
        self.branches = BranchRepository(session)
        self.drivers = DriverRepository(session)

    # шаблоны

    def list_templates(self, user: User) -> Sequence[ReportTemplate]:
        if user.role not in REPORT_ROLES:
            raise ReportPermissionError
        if user.role == UserRole.ADMIN:
            return self.templates.list_all()
        return self.templates.list_available(user.id)

    def get_template(self, user: User, template_id: int) -> ReportTemplate:
        template = self.templates.get(template_id)
        if template is None:
            raise TemplateNotFoundError
        if not can_read(user, template):
            raise ReportPermissionError
        return template

    def _ensure_unique_name(
        self, name: str, is_system: bool, owner_id: int | None, exclude_id: int | None = None
    ) -> None:
        if is_system:
            existing = self.templates.get_system_by_name(name)
        else:
            existing = self.templates.get_by_owner_and_name(owner_id, name)
        if existing is not None and existing.id != exclude_id:
            raise TemplateNameConflictError

    def _commit(self, template: ReportTemplate) -> ReportTemplate:
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise TemplateNameConflictError from None
        self.session.refresh(template)
        return template

    def create_template(self, user: User, data: ReportTemplateCreate) -> ReportTemplate:
        if not can_create(user, data.is_system):
            raise ReportPermissionError
        owner_id = None if data.is_system else user.id
        self._ensure_unique_name(data.name, data.is_system, owner_id)
        template = ReportTemplate(
            name=data.name,
            description=data.description,
            is_system=data.is_system,
            owner_id=owner_id,
            config=data.config.model_dump(mode="json"),
        )
        self.session.add(template)
        return self._commit(template)

    def update_template(
        self, user: User, template_id: int, data: ReportTemplateUpdate
    ) -> ReportTemplate:
        template = self.get_template(user, template_id)
        if not can_modify(user, template):
            raise ReportPermissionError
        self._ensure_unique_name(data.name, template.is_system, template.owner_id, template.id)
        template.name = data.name
        template.description = data.description
        template.config = data.config.model_dump(mode="json")
        return self._commit(template)

    def delete_template(self, user: User, template_id: int) -> None:
        template = self.get_template(user, template_id)
        if not can_modify(user, template):
            raise ReportPermissionError
        self.session.delete(template)
        self.session.commit()

    # отчёты

    def build_report(self, config: ReportConfig, period: ReportPeriod) -> pd.DataFrame:
        """Отчёт за период (границы уже разрешены через `resolve_period`)."""
        filters = config.filters
        df = self.orders.fetch_df(
            date_from=period.date_from,
            date_to=period.date_to,
            branch_ids=filters.branch_ids,
            status=filters.statuses,
        )
        branch_names = driver_names = None
        if config.group_by == "branch":
            branch_names = {b.id: b.name for b in self.branches.list()}
        elif config.group_by == "driver":
            driver_names = {d.id: d.full_name for d in self.drivers.list()}
        return build_report_frame(df, config, branch_names, driver_names)


def seed_system_templates(session: Session) -> int:
    """Создаёт недостающие системные шаблоны (по имени). Возвращает число новых."""
    repo = ReportTemplateRepository(session)
    created = 0
    for name, description, config in SYSTEM_TEMPLATES:
        if repo.get_system_by_name(name) is not None:
            continue
        repo.add(
            ReportTemplate(
                name=name,
                description=description,
                is_system=True,
                owner_id=None,
                config=ReportConfig.model_validate(config).model_dump(mode="json"),
            )
        )
        created += 1
    return created
