import os
import pickle
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox
from sqlalchemy.orm import Session

from backend.app.repositories.branch import BranchRepository

# Резервный словарь филиалов для автономного запуска без БД
DEFAULT_BRANCHES_DICT: dict[int, dict[str, Any]] = {
    1: {"name": "Филиал Нижегородский", "lat": 56.322974, "lon": 44.034741, "queue": 5},
    2: {"name": "Филиал Автозавод", "lat": 56.241094, "lon": 43.861618, "queue": 1},
    3: {"name": "Филиал Сормово", "lat": 56.364246, "lon": 43.816756, "queue": 4},
    4: {"name": "Филиал Приокский", "lat": 56.245525, "lon": 43.985747, "queue": 2},
    5: {"name": "Филиал Московский", "lat": 56.326492, "lon": 43.871275, "queue": 3},
    6: {"name": "Филиал Канавинский", "lat": 56.312834, "lon": 43.937238, "queue": 6},
    7: {"name": "Филиал Советский", "lat": 56.293337, "lon": 44.013856, "queue": 0},
}


class RoutingService:
    def __init__(
        self,
        session: Session | None = None,
        graph: nx.MultiDiGraph | None = None,
        graph_path: str | Path | None = None,
        branches: dict[int, dict[str, Any]] | None = None,
    ):
        self.session = session
        self.graph_path = Path(graph_path) if graph_path is not None else None
        self._explicit_branches = branches

        if branches is not None:
            self.branches = dict(branches)
        elif session is not None:
            self.branches = self.load_branches_from_db(session)
        else:
            self.branches = {k: dict(v) for k, v in DEFAULT_BRANCHES_DICT.items()}

        self.graph = graph if graph is not None else self._load_or_download_graph()

    @staticmethod
    def load_branches_from_db(session: Session) -> dict[int, dict[str, Any]]:
        """Загружает активные филиалы и их текущие очереди из PostgreSQL / SQLite."""
        active_branches = BranchRepository(session).list_active()
        return {
            branch.id: {
                "name": branch.name,
                "lat": float(branch.lat),
                "lon": float(branch.lon),
                "queue": int(branch.current_queue),
            }
            for branch in active_branches
        }

    def refresh_branches(self, session: Session | None = None) -> dict[int, dict[str, Any]]:
        """Обновляет список филиалов и очередей из БД, если доступна сессия."""
        if self._explicit_branches is not None:
            return self.branches

        active_session = session or self.session
        if active_session is not None:
            self.branches = self.load_branches_from_db(active_session)
        return self.branches

    def _load_or_download_graph(self) -> nx.MultiDiGraph:
        if self.graph_path is not None:
            target_path = self.graph_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            base_dir = os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                )
            )
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            target_path = Path(os.path.join(data_dir, "nn_graph.pkl"))

        if target_path.exists():
            print("Загрузка графа из кэша...")
            with open(target_path, "rb") as f:
                return pickle.load(f)
        else:
            print("Скачивание графа дорог Нижнего Новгорода (это займет пару минут)...")
            G = ox.graph_from_point((56.32, 44.00), dist=15000, network_type="drive")
            G = ox.add_edge_speeds(G)
            G = ox.add_edge_travel_times(G)

            with open(target_path, "wb") as f:
                pickle.dump(G, f)
            return G

    def get_driver_recommendation(
        self,
        driver_lat: float,
        driver_lon: float,
        session: Session | None = None,
    ) -> dict[str, Any] | None:
        """
        Рассчитывает оптимальный филиал для водителя по алгоритму Дейкстры
        с учетом времени проезда по графу дорог и текущей очереди заказов в филиалах.
        """
        self.refresh_branches(session=session)
        if not self.branches:
            return None

        driver_node = ox.distance.nearest_nodes(self.graph, X=driver_lon, Y=driver_lat)
        best_branch = None
        best_score = float("inf")

        for branch_id, info in self.branches.items():
            branch_node = ox.distance.nearest_nodes(self.graph, X=info["lon"], Y=info["lat"])

            try:
                travel_time = nx.shortest_path_length(
                    self.graph,
                    source=driver_node,
                    target=branch_node,
                    weight="travel_time",
                )
                travel_time_min = travel_time / 60.0
                score = travel_time_min - (info["queue"] * 2)

                if score < best_score:
                    best_score = score
                    best_branch = {
                        "branch_id": branch_id,
                        "branch_name": info["name"],
                        "travel_time_minutes": round(travel_time_min, 1),
                        "queue_size": info["queue"],
                        "driver_node": driver_node,
                        "branch_node": branch_node,
                        "route_nodes": nx.shortest_path(
                            self.graph,
                            source=driver_node,
                            target=branch_node,
                            weight="travel_time",
                        ),
                    }
            except nx.NetworkXNoPath:
                continue

        return best_branch
