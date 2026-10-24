import math
import os
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

# Дефолтные координаты действующих филиалов (совпадают с RoutingService и seed.py)
DEFAULT_BRANCHES: list[dict[str, Any]] = [
    {"id": 1, "name": "Филиал Нижегородский", "lat": 56.322974, "lon": 44.034741, "is_active": True},
    {"id": 2, "name": "Филиал Автозавод", "lat": 56.241094, "lon": 43.861618, "is_active": True},
    {"id": 3, "name": "Филиал Сормово", "lat": 56.364246, "lon": 43.816756, "is_active": True},
    {"id": 4, "name": "Филиал Приокский", "lat": 56.245525, "lon": 43.985747, "is_active": True},
    {"id": 5, "name": "Филиал Московский", "lat": 56.326492, "lon": 43.871275, "is_active": True},
    {"id": 6, "name": "Филиал Канавинский", "lat": 56.312834, "lon": 43.937238, "is_active": True},
    {"id": 7, "name": "Филиал Советский", "lat": 56.293337, "lon": 44.013856, "is_active": True},
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
        branches: list[dict[str, Any]] | None = None,
        coverage_radius_km: float = 2.0,
        high_demand_threshold: int = 130,
        low_demand_threshold: int = 80,
    ):
        self.n_clusters = n_clusters
        self.coverage_radius_km = coverage_radius_km
        self.high_demand_threshold = high_demand_threshold
        self.low_demand_threshold = low_demand_threshold
        self.branches = (
            [b for b in branches if b.get("is_active", True)]
            if branches is not None
            else [dict(b) for b in DEFAULT_BRANCHES]
        )
        self.model = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)

    def load_data(self) -> pd.DataFrame:
        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
        )
        file_path = os.path.join(base_dir, "data", "synthetic_orders.csv")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл данных не найден: {file_path}")

        df = pd.read_csv(file_path)
        df = df[df["status"] == "Delivered"].copy()
        return df

    def _find_nearest_branch(
        self, lat: float, lon: float
    ) -> tuple[dict[str, Any] | None, float]:
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

    def analyze_demand(self, df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
        """
        Выполняет кластеризацию K-Means и сопоставляет центроиды с координатами филиалов.

        Правила рекомендаций:
        - В зоне нет филиала (дистанция > coverage_radius_km) и высокий спрос -> "Открыть филиал"
        - В зоне есть филиал (дистанция <= coverage_radius_km), но низкий спрос -> "Закрыть филиал"
        - В зоне есть филиал и достаточный спрос -> "Филиал рентабелен"
        - В зоне нет филиала и низкий/умеренный спрос -> "Спрос низкий"
        """
        if df is None:
            df = self.load_data()
        else:
            df = df[df["status"] == "Delivered"].copy()

        if df.empty:
            return []

        actual_clusters = min(self.n_clusters, len(df))
        model = (
            self.model
            if actual_clusters == self.n_clusters
            else KMeans(n_clusters=actual_clusters, random_state=42, n_init=10)
        )

        coords = df[["client_lat", "client_lon"]].values
        model.fit(coords)

        centroids = model.cluster_centers_
        df["cluster"] = model.labels_
        cluster_counts = df["cluster"].value_counts().sort_index()

        recommendations: list[dict[str, Any]] = []
        for i, (lat, lon) in enumerate(centroids):
            order_count = int(cluster_counts.get(i, 0))
            nearest_branch, dist_km = self._find_nearest_branch(float(lat), float(lon))
            has_branch_nearby = (
                nearest_branch is not None and dist_km <= self.coverage_radius_km
            )

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
    print("Результаты кластеризации (с учетом действующих филиалов):")
    for res in results:
        print(res)