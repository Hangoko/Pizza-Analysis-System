"""KPI и агрегированная статистика заказов (роли: admin, manager, executive)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.deps import DbSession, require_roles
from backend.app.db.models.user import UserRole
from backend.app.schemas.stats import (
    BranchLoadResponse,
    Granularity,
    KpiResponse,
    StatsPeriod,
    TimeseriesResponse,
)
from backend.app.services.stats_service import StatsService

STATS_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.EXECUTIVE)

_TZ_NOTE = (
    "Все даты-время — в UTC. Значение без часового пояса трактуется как UTC. "
    "Период полуоткрытый: `date_from <= order_time < date_to`."
)

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(require_roles(*STATS_ROLES))],
    responses={
        401: {"description": "Нет или неверный токен"},
        403: {"description": "Недостаточно прав (нужна роль admin, manager или executive)"},
        422: {"description": "Некорректные параметры, в т.ч. `date_from` позже `date_to`"},
    },
)


@dataclass(frozen=True)
class StatsFilters:
    date_from: datetime | None
    date_to: datetime | None
    branch_ids: list[int] | None

    @property
    def period(self) -> StatsPeriod:
        return StatsPeriod(
            date_from=self.date_from, date_to=self.date_to, branch_ids=self.branch_ids
        )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def stats_filters(
    date_from: Annotated[
        datetime | None,
        Query(description="Начало периода, включительно (ISO 8601, UTC)"),
    ] = None,
    date_to: Annotated[
        datetime | None,
        Query(description="Конец периода, не включительно (ISO 8601, UTC)"),
    ] = None,
    branch_id: Annotated[
        list[int] | None,
        Query(
            description="Фильтр по филиалам; параметр можно повторять: `?branch_id=1&branch_id=2`"
        ),
    ] = None,
) -> StatsFilters:
    start, end = _as_utc(date_from), _as_utc(date_to)
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_from должен быть не позже date_to",
        )
    branch_ids = sorted(set(branch_id)) if branch_id else None
    return StatsFilters(date_from=start, date_to=end, branch_ids=branch_ids)


Filters = Annotated[StatsFilters, Depends(stats_filters)]


@router.get(
    "/kpi",
    response_model=KpiResponse,
    summary="Сводные KPI за период",
    description=f"Количество заказов, доставки, отмены, среднее/медиана/p90 времени доставки. "
    f"{_TZ_NOTE}",
)
def get_kpi(filters: Filters, db: DbSession) -> KpiResponse:
    data = StatsService(db).kpi(filters.date_from, filters.date_to, filters.branch_ids)
    return KpiResponse(period=filters.period, **data)


@router.get(
    "/branch-load",
    response_model=BranchLoadResponse,
    summary="Нагрузка по филиалам",
    description=f"Заказы, доля %, среднее время доставки и отклонение от средней нагрузки "
    f"по каждому филиалу. Активные филиалы показываются и без заказов. {_TZ_NOTE}",
)
def get_branch_load(filters: Filters, db: DbSession) -> BranchLoadResponse:
    data = StatsService(db).branch_load(filters.date_from, filters.date_to, filters.branch_ids)
    return BranchLoadResponse(period=filters.period, **data)


@router.get(
    "/timeseries",
    response_model=TimeseriesResponse,
    summary="Временной ряд заказов",
    description=f"Агрегация по часам, дням или неделям (с понедельника); `period_start` — "
    f"начало интервала. Пропуски между первым и последним заказом заполняются нулями. "
    f"{_TZ_NOTE}",
)
def get_timeseries(
    filters: Filters,
    db: DbSession,
    granularity: Annotated[Granularity, Query(description="Шаг: hour, day или week")] = "day",
) -> TimeseriesResponse:
    points = StatsService(db).timeseries(
        granularity, filters.date_from, filters.date_to, filters.branch_ids
    )
    return TimeseriesResponse(period=filters.period, granularity=granularity, points=points)
