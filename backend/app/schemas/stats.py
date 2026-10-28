"""Схемы ответов /stats. Все даты-время — в UTC; отсутствующие значения — `null`."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Granularity = Literal["hour", "day", "week"]


class StatsPeriod(BaseModel):
    """Фильтр ответа. Период полуоткрытый: `date_from <= order_time < date_to`."""

    date_from: datetime | None = Field(description="Начало периода (UTC), включительно")
    date_to: datetime | None = Field(description="Конец периода (UTC), не включительно")
    branch_ids: list[int] | None = Field(description="Филиалы; `null` — все")


class KpiSummary(BaseModel):
    total_orders: int = Field(description="Всего заказов за период")
    delivered: int = Field(description="Доставлено")
    canceled: int = Field(description="Отменено")
    cancel_rate: float = Field(description="Доля отменённых от всех заказов, 0..1")
    avg_delivery_minutes: float | None = Field(
        description="Среднее время доставки, мин (по доставленным); `null`, если доставок нет"
    )
    median_delivery_minutes: float | None = Field(description="Медиана времени доставки, мин")
    p90_delivery_minutes: float | None = Field(description="90-й перцентиль времени доставки, мин")


class KpiResponse(KpiSummary):
    period: StatsPeriod


class BranchLoadItem(BaseModel):
    branch_id: int
    branch_name: str | None
    orders: int
    share_pct: float = Field(description="Доля заказов филиала от всех, %")
    delivered: int
    canceled: int
    cancel_rate: float = Field(description="Доля отменённых, 0..1")
    avg_delivery_minutes: float | None
    deviation_from_mean: float = Field(
        description="Отклонение числа заказов от средней нагрузки на филиал, заказов"
    )
    deviation_pct: float | None = Field(
        description="Отклонение от средней нагрузки, %; `null`, если средняя равна 0"
    )


class BranchLoadResponse(BaseModel):
    period: StatsPeriod
    total_orders: int
    mean_orders: float = Field(description="Средняя нагрузка на филиал, заказов")
    items: list[BranchLoadItem]


class TimeseriesPoint(BaseModel):
    period_start: datetime = Field(description="Начало интервала (UTC); неделя — с понедельника")
    orders: int
    delivered: int
    canceled: int
    cancel_rate: float
    avg_delivery_minutes: float | None


class TimeseriesResponse(BaseModel):
    period: StatsPeriod
    granularity: Granularity
    points: list[TimeseriesPoint]
