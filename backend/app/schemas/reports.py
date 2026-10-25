"""
Схемы шаблонов отчётов и конструктора.

`ReportConfig` — конфигурация отчёта, хранится в `report_templates.config` (JSON)
и валидируется при каждом сохранении. Имена метрик и группировок совпадают
с `stats_service.METRICS` / `stats_service.GROUP_KEYS`.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from backend.app.db.models.order import OrderStatus

ReportMetric = Literal[
    "orders",
    "delivered",
    "canceled",
    "cancel_rate",
    "avg_delivery_minutes",
    "median_delivery_minutes",
    "p90_delivery_minutes",
]
ReportGroupBy = Literal[
    "branch", "driver", "status", "hour", "day", "week", "hour_of_day", "weekday"
]
OrderStatusName = Literal["Pending", "InDelivery", "Delivered", "Canceled"]
CsvDelimiter = Literal[";", ","]

MAX_PERIOD_DAYS = 3650


def as_utc(value: datetime | None) -> datetime | None:
    """Время без часового пояса трактуется как UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime | None, AfterValidator(as_utc)]


def _unique_sorted(values: list[Any] | None) -> list[Any] | None:
    return sorted(set(values)) if values else None


class ReportFilters(BaseModel):
    """Фильтры заказов; `null` или пустой список — без ограничения."""

    model_config = ConfigDict(extra="forbid")

    branch_ids: Annotated[list[int] | None, AfterValidator(_unique_sorted)] = None
    driver_ids: Annotated[list[int] | None, AfterValidator(_unique_sorted)] = None
    statuses: Annotated[list[OrderStatusName] | None, AfterValidator(_unique_sorted)] = Field(
        default=None, description=f"Статусы заказов: {', '.join(s.value for s in OrderStatus)}"
    )


class ReportConfig(BaseModel):
    """Конфигурация конструктора отчёта."""

    model_config = ConfigDict(extra="forbid")

    metrics: list[ReportMetric] = Field(
        min_length=1, description="Метрики в порядке колонок отчёта (дубликаты удаляются)"
    )
    group_by: ReportGroupBy | None = Field(
        default=None, description="Ключ группировки; `null` — одна итоговая строка"
    )
    filters: ReportFilters = Field(default_factory=ReportFilters)
    default_period_days: int | None = Field(
        default=30,
        ge=1,
        le=MAX_PERIOD_DAYS,
        description="Период по умолчанию (последние N дней), если даты не переданы; "
        "`null` — вся история",
    )

    @model_validator(mode="after")
    def _dedupe_metrics(self) -> "ReportConfig":
        self.metrics = list(dict.fromkeys(self.metrics))
        return self


class ReportPeriod(BaseModel):
    """Период отчёта (UTC), полуоткрытый: `date_from <= order_time < date_to`."""

    date_from: UtcDateTime = None
    date_to: UtcDateTime = None

    @model_validator(mode="after")
    def _check_order(self) -> "ReportPeriod":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from должен быть не позже date_to")
        return self


# --- шаблоны ---


class ReportTemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    config: ReportConfig


class ReportTemplateCreate(ReportTemplateBase):
    is_system: bool = Field(
        default=False, description="Системный шаблон (без владельца) — только для admin"
    )


class ReportTemplateUpdate(ReportTemplateBase):
    """Полная замена названия, описания и конфигурации."""


class ReportTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_system: bool
    owner_id: int | None
    config: ReportConfig
    created_at: datetime
    updated_at: datetime


# --- конструктор ---


class ReportRequest(ReportPeriod):
    """Ad-hoc отчёт: конфигурация + период."""

    config: ReportConfig
    name: str = Field(default="adhoc", min_length=1, max_length=255, description="Имя для файла")


class ReportColumn(BaseModel):
    key: str
    label: str = Field(description="Заголовок колонки (рус.), как в CSV")


class ReportPreview(BaseModel):
    period: ReportPeriod = Field(description="Фактический период (с учётом default_period_days)")
    columns: list[ReportColumn]
    rows: list[dict[str, Any]]
