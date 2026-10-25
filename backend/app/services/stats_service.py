"""
KPI и агрегация заказов (pandas/NumPy).

Чистые функции принимают DataFrame в формате `OrderRepository.fetch_df`
(колонки `branch_id`, `driver_id`, `order_time` (UTC), `delivery_time_minutes`, `status`, ...)
и ничего не знают о БД — их переиспользует сервис отчётов.
`StatsService` — тонкая обёртка: выгружает данные через репозитории и вызывает функции.

Соглашения:
- время доставки считается только по доставленным заказам с известным `delivery_time_minutes`;
- `cancel_rate` — доля отменённых от всех заказов периода (0..1);
- пустой период: счётчики и доли — 0, средние/перцентили — `None`;
- в результатах `to_records` NaN/NA заменяются на `None` (в JSON — `null`).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.db.models.order import OrderStatus
from backend.app.repositories.branch import BranchRepository
from backend.app.repositories.order import OrderRepository

Granularity = Literal["hour", "day", "week"]

MINUTES_DIGITS = 2
RATE_DIGITS = 4
PCT_DIGITS = 2

# --- ключи группировки ---


def _week_start(ts: pd.Series) -> pd.Series:
    """Начало недели (понедельник 00:00) с сохранением часового пояса."""
    day = ts.dt.floor("D")
    return day - pd.to_timedelta(day.dt.day_of_week, unit="D")


# Ключ группировки -> (имя колонки в результате, функция df -> Series)
GROUP_KEYS: dict[str, tuple[str, Callable[[pd.DataFrame], pd.Series]]] = {
    "branch": ("branch_id", lambda df: df["branch_id"]),
    "driver": ("driver_id", lambda df: df["driver_id"]),
    "status": ("status", lambda df: df["status"]),
    "hour": ("hour", lambda df: df["order_time"].dt.floor("h")),
    "day": ("day", lambda df: df["order_time"].dt.floor("D")),
    "week": ("week", lambda df: _week_start(df["order_time"])),
    "hour_of_day": ("hour_of_day", lambda df: df["order_time"].dt.hour),
    "weekday": ("weekday", lambda df: df["order_time"].dt.day_of_week),
}

TIME_KEYS = ("hour", "day", "week")
_FREQ: dict[str, str] = {"hour": "h", "day": "D", "week": "7D"}

# --- метрики ---

COUNT_METRICS = ("orders", "delivered", "canceled")
MINUTES_METRICS = ("avg_delivery_minutes", "median_delivery_minutes", "p90_delivery_minutes")
METRICS: tuple[str, ...] = (*COUNT_METRICS, "cancel_rate", *MINUTES_METRICS)

SUMMARY_FIELDS = {
    "total_orders": "orders",
    "delivered": "delivered",
    "canceled": "canceled",
    "cancel_rate": "cancel_rate",
    "avg_delivery_minutes": "avg_delivery_minutes",
    "median_delivery_minutes": "median_delivery_minutes",
    "p90_delivery_minutes": "p90_delivery_minutes",
}


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Вспомогательные колонки для векторного расчёта метрик."""
    status = df["status"].astype(object)
    delivered = (status == OrderStatus.DELIVERED.value).to_numpy(dtype=bool)
    minutes = pd.to_numeric(df["delivery_time_minutes"], errors="coerce").to_numpy(
        dtype="float64", na_value=np.nan
    )
    return pd.DataFrame(
        {
            "_delivered": delivered.astype("int64"),
            "_canceled": (status == OrderStatus.CANCELED.value).to_numpy(dtype="int64"),
            "_minutes": np.where(delivered, minutes, np.nan),
        },
        index=df.index,
    )


def _validate_metrics(metrics: Sequence[str] | None) -> list[str]:
    if metrics is None:
        return list(METRICS)
    unknown = [m for m in metrics if m not in METRICS]
    if unknown:
        raise ValueError(f"Неизвестные метрики: {unknown}; доступны: {list(METRICS)}")
    return list(dict.fromkeys(metrics))


def _round(result: pd.DataFrame) -> pd.DataFrame:
    for column in result.columns:
        if column in MINUTES_METRICS:
            result[column] = result[column].astype("float64").round(MINUTES_DIGITS)
        elif column == "cancel_rate":
            result[column] = result[column].astype("float64").round(RATE_DIGITS)
    return result


def aggregate(
    df: pd.DataFrame,
    group_by: str | Sequence[str] = (),
    metrics: Sequence[str] | None = None,
) -> pd.DataFrame:
    """
    Универсальная агрегация: группировка по ключам из `GROUP_KEYS`
    (`branch`, `driver`, `status`, `hour`, `day`, `week`, `hour_of_day`, `weekday`)
    и набор метрик из `METRICS`. Без ключей — одна строка по всему DataFrame.

    Возвращает DataFrame: колонки ключей (`branch_id`, `day`, ...) + метрики,
    строки отсортированы по ключам. Заказы без водителя попадают в группу `driver_id = NA`.
    """
    keys = [group_by] if isinstance(group_by, str) else list(group_by)
    unknown = [k for k in keys if k not in GROUP_KEYS]
    if unknown:
        raise ValueError(f"Неизвестные ключи группировки: {unknown}; доступны: {list(GROUP_KEYS)}")
    metric_names = _validate_metrics(metrics)
    key_columns = [GROUP_KEYS[k][0] for k in keys]

    if not keys:
        return _round(pd.DataFrame([_overall(df)], columns=METRICS)[metric_names])
    if df.empty:
        return pd.DataFrame(columns=[*key_columns, *metric_names])

    prepared = _prepare(df)
    for key, column in zip(keys, key_columns, strict=True):
        prepared[column] = GROUP_KEYS[key][1](df)
    grouped = prepared.groupby(key_columns, sort=True, dropna=False)
    result = pd.DataFrame(
        {
            "orders": grouped.size(),
            "delivered": grouped["_delivered"].sum(),
            "canceled": grouped["_canceled"].sum(),
            "avg_delivery_minutes": grouped["_minutes"].mean(),
            "median_delivery_minutes": grouped["_minutes"].median(),
            "p90_delivery_minutes": grouped["_minutes"].quantile(0.9),
        }
    )
    result["cancel_rate"] = result["canceled"] / result["orders"]
    result = result.reset_index()[[*key_columns, *metric_names]]
    return _round(result)


def _overall(df: pd.DataFrame) -> dict[str, Any]:
    """Метрики по всему DataFrame (без группировки)."""
    total = len(df)
    if total == 0:
        return {name: (0 if name in COUNT_METRICS else None) for name in METRICS} | {
            "cancel_rate": 0.0
        }
    prepared = _prepare(df)
    minutes = prepared["_minutes"].dropna().to_numpy()
    canceled = int(prepared["_canceled"].sum())
    has_minutes = minutes.size > 0
    return {
        "orders": total,
        "delivered": int(prepared["_delivered"].sum()),
        "canceled": canceled,
        "cancel_rate": canceled / total,
        "avg_delivery_minutes": float(np.mean(minutes)) if has_minutes else None,
        "median_delivery_minutes": float(np.median(minutes)) if has_minutes else None,
        "p90_delivery_minutes": float(np.percentile(minutes, 90)) if has_minutes else None,
    }


# --- готовые расчёты для эндпоинтов /stats ---


def summary_kpi(df: pd.DataFrame) -> dict[str, Any]:
    """Сводные KPI периода: количество, доставлено, отменено, доля отмен, среднее/медиана/p90."""
    row = to_records(aggregate(df))[0]
    return {field: row[metric] for field, metric in SUMMARY_FIELDS.items()}


def branch_load(
    df: pd.DataFrame,
    branch_names: Mapping[int, str] | None = None,
    include_ids: Iterable[int] = (),
) -> pd.DataFrame:
    """
    Нагрузка по филиалам: заказы, доля % от всех, доставлено/отменено, среднее время доставки,
    отклонение от средней нагрузки на филиал (в заказах и в %).

    `include_ids` — филиалы, которые надо показать даже без заказов (они участвуют в средней).
    `branch_names` — названия филиалов (id -> name), неизвестные — `None`.
    """
    metrics = ["orders", "delivered", "canceled", "cancel_rate", "avg_delivery_minutes"]
    load = aggregate(df, "branch", metrics).set_index("branch_id")
    ids = sorted({int(i) for i in load.index} | {int(i) for i in include_ids})
    load = load.reindex(pd.Index(ids, dtype="int64"))
    for column in COUNT_METRICS:
        load[column] = load[column].fillna(0).astype("int64")
    load["cancel_rate"] = load["cancel_rate"].astype("float64").fillna(0.0)
    load["avg_delivery_minutes"] = load["avg_delivery_minutes"].astype("float64")

    total = int(load["orders"].sum())
    mean_orders = float(load["orders"].mean()) if len(load) else 0.0
    orders = load["orders"].astype("float64")
    load["share_pct"] = (orders / total * 100).round(PCT_DIGITS) if total else 0.0
    load["deviation_from_mean"] = (orders - mean_orders).round(PCT_DIGITS)
    if mean_orders:
        load["deviation_pct"] = ((orders / mean_orders - 1) * 100).round(PCT_DIGITS)
    else:
        load["deviation_pct"] = np.nan

    names = branch_names or {}
    load.index.name = "branch_id"
    load = load.reset_index()
    load.insert(1, "branch_name", [names.get(int(i)) for i in load["branch_id"]])
    columns = [
        "branch_id",
        "branch_name",
        "orders",
        "share_pct",
        "delivered",
        "canceled",
        "cancel_rate",
        "avg_delivery_minutes",
        "deviation_from_mean",
        "deviation_pct",
    ]
    load = load[columns]
    load.attrs["mean_orders"] = round(mean_orders, PCT_DIGITS)
    return load


def timeseries(
    df: pd.DataFrame,
    granularity: Granularity = "day",
    metrics: Sequence[str] | None = None,
    fill_gaps: bool = True,
) -> pd.DataFrame:
    """
    Временной ряд по началу интервала (`period_start`, UTC): час / день / неделя (с понедельника).
    `fill_gaps` — пропущенные интервалы между первым и последним заказом заполняются
    нулевыми счётчиками (средние — `NaN`), чтобы график был непрерывным.
    """
    if granularity not in TIME_KEYS:
        raise ValueError(f"granularity должен быть одним из {TIME_KEYS}")
    metric_names = _validate_metrics(
        metrics or ["orders", "delivered", "canceled", "cancel_rate", "avg_delivery_minutes"]
    )
    series = aggregate(df, granularity, metric_names).rename(columns={granularity: "period_start"})
    if series.empty or not fill_gaps:
        return series
    series = series.set_index("period_start")
    full_range = pd.date_range(series.index.min(), series.index.max(), freq=_FREQ[granularity])
    series = series.reindex(full_range)
    for column in series.columns:
        if column in COUNT_METRICS:
            series[column] = series[column].fillna(0).astype("int64")
        elif column == "cancel_rate":
            series[column] = series[column].astype("float64").fillna(0.0)
    series.index.name = "period_start"
    return series.reset_index()


# --- сериализация ---


def _to_python(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, float | np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Строки DataFrame как список dict с типами Python; NaN/NA -> None."""
    return [
        {column: _to_python(value) for column, value in zip(df.columns, row, strict=True)}
        for row in df.itertuples(index=False, name=None)
    ]


# --- сервис ---


class StatsService:
    """Выгружает заказы через репозитории и считает KPI чистыми функциями выше."""

    def __init__(self, session: Session) -> None:
        self.orders = OrderRepository(session)
        self.branches = BranchRepository(session)

    def _fetch(
        self,
        date_from: datetime | None,
        date_to: datetime | None,
        branch_ids: Sequence[int] | None,
    ) -> pd.DataFrame:
        return self.orders.fetch_df(
            date_from=date_from, date_to=date_to, branch_ids=branch_ids or None
        )

    def kpi(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        branch_ids: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        return summary_kpi(self._fetch(date_from, date_to, branch_ids))

    def branch_load(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        branch_ids: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        df = self._fetch(date_from, date_to, branch_ids)
        branches = self.branches.list()
        # Активные филиалы показываются и без заказов; закрытые — только если есть заказы
        include = [b.id for b in branches if b.is_active and (not branch_ids or b.id in branch_ids)]
        load = branch_load(df, {b.id: b.name for b in branches}, include)
        return {
            "total_orders": int(load["orders"].sum()),
            "mean_orders": load.attrs["mean_orders"],
            "items": to_records(load),
        }

    def timeseries(
        self,
        granularity: Granularity = "day",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        branch_ids: Sequence[int] | None = None,
    ) -> list[dict[str, Any]]:
        return to_records(timeseries(self._fetch(date_from, date_to, branch_ids), granularity))
