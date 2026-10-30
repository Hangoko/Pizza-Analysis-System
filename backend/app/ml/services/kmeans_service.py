import math
import os
from datetime import datetime
from typing import Any

import pandas as pd
from sklearn.cluster import KMeans
from sqlalchemy.orm import Session

from backend.app.db.models.order import OrderStatus
from backend.app.repositories.branch import BranchRepository
from backend.app.repositories.order import OrderRepository

# Резервный список филиалов для автономного запуска без подключения к БД
DEFAULT_BRANCHES: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Филиал Нижегородский",
        "lat": 56.322974,
        "lon": 44.034741,
        "current_queue": 5,
        "is_active": True,
    },
    {
        "id": 2,
        "name": "Филиал Автозавод",
        "lat": 56.241094,
        "lon": 43.861618,
        "current_queue": 1,
        "is_active": True,
    },
    {
        "id": 3,
        "name": "Филиал Сормово",
        "lat": 56.364246,
        "lon": 43.816756,
        "current_queue": 4,
        "is_active": True,
    },
    {
        "id": 4,
        "name": "Филиал Приокский",
        "lat": 56.245525,
        "lon": 43.985747,
        "current_queue": 2,
        "is_active": True,
    },
    {
        "id": 5,
        "name": "Филиал Московский",
        "lat": 56.326492,
        "lon": 43.871275,
        "current_queue": 3,
        "is_active": True,
    },
    {
        "id": 6,
        "name": "Филиал Канавинский",
        "lat": 56.312834,
        "lon": 43.937238,
        "current_queue": 6,
        "is_active": True,
    },
    {
        "id": 7,
        "name": "Филиал Советский",
        "lat": 56.293337,
        "lon": 44.013856,
        "current_queue": 0,
        "is_active": True,
    },
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние в километрах между двумя точками (lat, lon) по формуле гаверсинуса."""
    earth_radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_km * c


class KMeansAnalyzer:
    def __init__(
        self,
        n_clusters: int = 7,
        session: Session | None = None,
        branches: list[dict[str, Any]] | None = None,
        coverage_radius_km: float = 2.0,
        high_demand_threshold: int = 130,
        low_demand_threshold: int = 80,
    ):
        self.n_clusters = n_clusters
        self.session = session
        self.coverage_radius_km = coverage_radius_km
        self.high_demand_threshold = high_demand_threshold
        self.low_demand_threshold = low_demand_threshold
        self._explicit_branches = branches
        self.branches = self.load_branches(session=session)
        self.model = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)

    def load_branches(self, session: Session | None = None) -> list[dict[str, Any]]:
        """Загружает список активных филиалов из БД (или возвращает резервный список)."""
        if self._explicit_branches is not None:
            return [b for b in self._explicit_branches if b.get("is_active", True)]

        active_session = session or self.session
        if active_session is not None:
            db_branches = BranchRepository(active_session).list_active()
            return [
                {
                    "id": b.id,
                    "name": b.name,
                    "lat": float(b.lat),
                    "lon": float(b.lon),
                    "current_queue": int(b.current_queue),
                    "is_active": bool(b.is_active),
                }
                for b in db_branches
            ]

        return [dict(b) for b in DEFAULT_BRANCHES if b.get("is_active", True)]

    def load_data(
        self,
        session: Session | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Загружает доставленные заказы из БД через OrderRepository.fetch_df().
        Если сессия БД не передана — читает локальный файл data/synthetic_orders.csv.
        """
        active_session = session or self.session
        if active_session is not None:
            return OrderRepository(active_session).fetch_df(
                date_from=date_from,
                date_to=date_to,
                status=OrderStatus.DELIVERED,
            )

        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            )
        )
        file_path = os.path.join(base_dir, "data", "synthetic_orders.csv")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл данных не найден: {file_path}")

        df = pd.read_csv(file_path)
        df = df[df["status"] == OrderStatus.DELIVERED.value].copy()
        return df

    def _find_nearest_branch(self, lat: float, lon: float) -> tuple[dict[str, Any] | None, float]:
        """Находит ближайший действующий филиал и расстояние до него в км."""
        if not self.branches:
            return None, float("inf")

        nearest_branch = None
        min_dist = float("inf")
        for branch in self.branches:
            dist = haversine_km(lat, lon, float(branch["lat"]), float(branch["lon"]))
            if dist < min_dist:
                min_dist = dist
                nearest_branch = branch
        return nearest_branch, min_dist

    def analyze_demand(
        self,
        df: pd.DataFrame | None = None,
        session: Session | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Выполняет кластеризацию K-Means по доставленным заказам и сопоставляет
        центроиды кластеров с координатами действующих филиалов.
        """
        active_session = session or self.session
        if active_session is not None or self._explicit_branches is not None:
            self.branches = self.load_branches(session=active_session)

        if df is None:
            df = self.load_data(session=active_session, date_from=date_from, date_to=date_to)
        else:
            df = df[df["status"] == OrderStatus.DELIVERED.value].copy()

        if df.empty:
            return []

        actual_clusters = min(self.n_clusters, len(df))
        model = (
            self.model
            if actual_clusters == self.n_clusters
            else KMeans(n_clusters=actual_clusters, random_state=42, n_init=10)
        )

        coords = df[["client_lat", "client_lon"]].astype(float).values
        model.fit(coords)

        centroids = model.cluster_centers_
        df["cluster"] = model.labels_
        cluster_counts = df["cluster"].value_counts().sort_index()

        recommendations: list[dict[str, Any]] = []
        for i, (lat, lon) in enumerate(centroids):
            order_count = int(cluster_counts.get(i, 0))
            nearest_branch, dist_km = self._find_nearest_branch(float(lat), float(lon))
            has_branch_nearby = nearest_branch is not None and dist_km <= self.coverage_radius_km

            if not has_branch_nearby:
                if order_count >= self.high_demand_threshold:
                    recommendation = "Открыть филиал"
                else:
                    recommendation = "Спрос низкий"
            else:
                if order_count < self.low_demand_threshold:
                    recommendation = "Закрыть филиал"
                else:
                    recommendation = "Филиал рентабелен"

            recommendations.append(
                {
                    "zone_id": i,
                    "center_lat": round(float(lat), 6),
                    "center_lon": round(float(lon), 6),
                    "order_count": order_count,
                    "recommendation": recommendation,
                    "nearest_branch_id": nearest_branch["id"] if nearest_branch else None,
                    "nearest_branch_name": nearest_branch["name"] if nearest_branch else None,
                    "distance_to_branch_km": (
                        round(dist_km, 2) if math.isfinite(dist_km) else None
                    ),
                }
            )

        return recommendations


if __name__ == "__main__":
    analyzer = KMeansAnalyzer(n_clusters=7)
    results = analyzer.analyze_demand()
    print("Результаты кластеризации (Топ зон спроса):")
    for res in results:
        print(res)
