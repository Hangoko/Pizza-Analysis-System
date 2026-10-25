"""
Зоны спроса K-Means поверх `KMeansAnalyzer` (ML, Ахметов) для REST API.

`KMeansAnalyzer` уже читает филиалы и доставленные заказы из БД. Здесь — только:
- `PeriodKMeansAnalyzer`: тонкий подкласс, у которого `load_data()` без аргументов
  использует заданный период (так `ClustersMapGenerator` строит карту за тот же период);
- проверка «заказов достаточно для кластеризации» до запуска K-Means.
"""

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.app.ml.services.kmeans_service import KMeansAnalyzer


class NotEnoughOrdersError(ValueError):
    """Доставленных заказов за период меньше, чем запрошено кластеров."""

    def __init__(self, orders: int, n_clusters: int) -> None:
        self.orders = orders
        self.n_clusters = n_clusters
        super().__init__(
            f"Недостаточно доставленных заказов для кластеризации: {orders} "
            f"при n_clusters={n_clusters}. Расширьте период или уменьшите n_clusters."
        )


class PeriodKMeansAnalyzer(KMeansAnalyzer):
    """`KMeansAnalyzer` с периодом по умолчанию для `load_data()`."""

    def __init__(
        self,
        session: Session,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        **kwargs: Any,
    ) -> None:
        self.date_from = date_from
        self.date_to = date_to
        super().__init__(session=session, **kwargs)

    def load_data(
        self,
        session: Session | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> pd.DataFrame:
        return super().load_data(
            session=session,
            date_from=date_from if date_from is not None else self.date_from,
            date_to=date_to if date_to is not None else self.date_to,
        )

    def load_checked_data(self) -> pd.DataFrame:
        """Заказы за период; если их меньше, чем кластеров, — `NotEnoughOrdersError`."""
        df = self.load_data()
        if len(df) < self.n_clusters:
            raise NotEnoughOrdersError(len(df), self.n_clusters)
        return df
