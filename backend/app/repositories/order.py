"""Репозиторий заказов, включая выгрузку в pandas для KPI и ML."""

from collections.abc import Iterable
from datetime import datetime

import pandas as pd
from sqlalchemy import select

from backend.app.db.models import Order
from backend.app.repositories.base import BaseRepository

# Колонки DataFrame совпадают с CSV генератора (order_id, client_lat, ...),
# чтобы ML-код (KMeansAnalyzer) мог работать с данными из БД без изменений
ORDER_DF_COLUMNS = [
    "order_id",
    "client_lat",
    "client_lon",
    "branch_id",
    "driver_id",
    "order_time",
    "delivered_at",
    "delivery_time_minutes",
    "status",
]


class OrderRepository(BaseRepository[Order]):
    model = Order

    def get_by_external_id(self, external_id: str) -> Order | None:
        return self.session.scalar(select(Order).where(Order.external_id == external_id))

    def existing_external_ids(self) -> set[str]:
        return set(self.session.scalars(select(Order.external_id)))

    def fetch_df(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        branch_ids: Iterable[int] | None = None,
        status: str | Iterable[str] | None = None,
    ) -> pd.DataFrame:
        """
        Заказы в виде DataFrame с фильтрами.

        Период полуоткрытый: `date_from <= order_time < date_to`.
        Даты — timezone-aware; `order_time`/`delivered_at` в результате — в UTC.
        """
        stmt = select(
            Order.external_id.label("order_id"),
            Order.client_lat,
            Order.client_lon,
            Order.branch_id,
            Order.driver_id,
            Order.order_time,
            Order.delivered_at,
            Order.delivery_time_minutes,
            Order.status,
        ).order_by(Order.order_time, Order.id)

        if date_from is not None:
            stmt = stmt.where(Order.order_time >= date_from)
        if date_to is not None:
            stmt = stmt.where(Order.order_time < date_to)
        if branch_ids is not None:
            stmt = stmt.where(Order.branch_id.in_(list(branch_ids)))
        if status is not None:
            statuses = [status] if isinstance(status, str) else list(status)
            stmt = stmt.where(Order.status.in_(statuses))

        rows = self.session.execute(stmt).all()
        df = pd.DataFrame([tuple(row) for row in rows], columns=ORDER_DF_COLUMNS)
        for column in ("order_time", "delivered_at"):
            df[column] = pd.to_datetime(df[column], utc=True)
        # Nullable-целые, чтобы NULL не превращал колонку во float
        for column in ("branch_id", "driver_id", "delivery_time_minutes"):
            df[column] = df[column].astype("Int64")
        return df
