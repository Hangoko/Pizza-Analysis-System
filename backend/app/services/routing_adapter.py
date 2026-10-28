"""
Быстрая рекомендация филиала водителю поверх `RoutingService` (ML, Ахметов).

Исходный `RoutingService.get_driver_recommendation` на каждый запрос строит BallTree по
всем узлам графа (1 + N раз, N — число филиалов) и запускает Дейкстру 2N раз.
`FastRoutingService` — тонкий подкласс без изменения ML-кода:
- граф передаётся готовым (`graph=` из `GraphSnapshot`), ничего не читается с диска;
- ближайшие узлы ищутся по BallTree, построенному один раз при загрузке графа,
  узлы филиалов кэшируются в снимке;
- **один** проход Дейкстры от узла водителя с остановкой, как только достигнуты все
  узлы филиалов, и восстановлением маршрута по предкам.
Формула (`score = минуты в пути - очередь * 2`), порядок обхода филиалов и формат
результата совпадают с исходным методом, поэтому `MapGenerator` работает без изменений.
"""

from heapq import heappop, heappush
from itertools import count
from typing import Any

import networkx as nx
from sqlalchemy.orm import Session

from backend.app.core.graph_state import GraphSnapshot
from backend.app.ml.services.routing_service import RoutingService

# Как в networkx: ребро без атрибута веса стоит 1
_DEFAULT_WEIGHT = 1


class PointOutsideGraphError(ValueError):
    """Точка слишком далеко от ближайшего узла графа (вне зоны покрытия)."""

    def __init__(self, distance_km: float, max_distance_km: float) -> None:
        self.distance_km = distance_km
        self.max_distance_km = max_distance_km
        super().__init__(
            f"Точка в {distance_km:.1f} км от ближайшей дороги графа "
            f"(допустимо не более {max_distance_km:g} км)"
        )


def dijkstra_to_targets(
    graph: nx.MultiDiGraph,
    source: Any,
    targets: set[Any],
    weight: str = "travel_time",
) -> tuple[dict[Any, float], dict[Any, Any]]:
    """
    Дейкстра от `source` до момента, когда все `targets` получили окончательное расстояние.
    Возвращает (расстояния, предки). Для мультиграфа берётся минимальный вес среди
    параллельных рёбер — так же, как в `networkx.shortest_path_length`.
    """
    remaining = set(targets)
    dist: dict[Any, float] = {}
    pred: dict[Any, Any] = {source: None}
    best: dict[Any, float] = {source: 0}
    tie = count()
    heap: list[tuple[float, int, Any]] = [(0, next(tie), source)]
    succ = graph.succ
    while heap and remaining:
        d, _, node = heappop(heap)
        if node in dist:
            continue
        dist[node] = d
        remaining.discard(node)
        if not remaining:
            break
        for neighbour, edges in succ[node].items():
            if neighbour in dist:
                continue
            cost = min(attrs.get(weight, _DEFAULT_WEIGHT) for attrs in edges.values())
            candidate = d + cost
            if neighbour not in best or candidate < best[neighbour]:
                best[neighbour] = candidate
                pred[neighbour] = node
                heappush(heap, (candidate, next(tie), neighbour))
    return dist, pred


def _path_to(pred: dict[Any, Any], target: Any) -> list[Any]:
    path = [target]
    while (parent := pred[path[-1]]) is not None:
        path.append(parent)
    path.reverse()
    return path


class FastRoutingService(RoutingService):
    """`RoutingService` на графе из `GraphSnapshot` с одним проходом Дейкстры."""

    def __init__(
        self,
        snapshot: GraphSnapshot,
        session: Session | None = None,
        branches: dict[int, dict[str, Any]] | None = None,
        max_snap_distance_km: float | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.max_snap_distance_km = max_snap_distance_km
        super().__init__(session=session, graph=snapshot.graph, branches=branches)

    def get_driver_recommendation(
        self,
        driver_lat: float,
        driver_lon: float,
        session: Session | None = None,
    ) -> dict[str, Any] | None:
        self.refresh_branches(session=session)
        if not self.branches:
            return None

        driver_node, distance_km = self.snapshot.nearest_node(driver_lat, driver_lon)
        if self.max_snap_distance_km is not None and distance_km > self.max_snap_distance_km:
            raise PointOutsideGraphError(distance_km, self.max_snap_distance_km)

        branch_nodes = {
            branch_id: self.snapshot.branch_node(info["lat"], info["lon"])
            for branch_id, info in self.branches.items()
        }
        dist, pred = dijkstra_to_targets(self.graph, driver_node, set(branch_nodes.values()))

        best_branch: dict[str, Any] | None = None
        best_score = float("inf")
        for branch_id, info in self.branches.items():
            branch_node = branch_nodes[branch_id]
            if branch_node not in dist:
                continue  # недостижим — как NetworkXNoPath в исходном методе
            travel_time_min = dist[branch_node] / 60.0
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
                    "route_nodes": _path_to(pred, branch_node),
                }
        return best_branch

    def route_coords(self, recommendation: dict[str, Any]) -> list[list[float]]:
        """Маршрут как список `[lat, lon]`."""
        nodes = self.graph.nodes
        return [[nodes[n]["y"], nodes[n]["x"]] for n in recommendation["route_nodes"]]
