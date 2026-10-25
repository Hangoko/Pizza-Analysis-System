"""
Состояние графа дорог в памяти процесса.

`GraphRegistry` хранится в `app.state.graph_registry`. Граф загружается один раз
(в фоне при старте приложения) и дальше только читается. Эндпоинты берут
неизменяемый снимок `GraphSnapshot` и работают с ним до конца запроса, поэтому
замена графа (`replace_graph`, этап 7) не ломает запросы, которые уже выполняются.
"""

import logging
import pickle
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from sklearn.neighbors import BallTree

logger = logging.getLogger(__name__)

# Тот же радиус Земли, что использует osmnx.distance.nearest_nodes
EARTH_RADIUS_KM = 6371.009


class GraphStatus(StrEnum):
    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class BBox:
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


@dataclass(frozen=True, eq=False)
class GraphSnapshot:
    """Загруженный граф + индекс ближайших узлов + кэш узлов филиалов."""

    graph: nx.MultiDiGraph
    version: int
    source: str
    loaded_at: datetime
    bbox: BBox
    _node_ids: np.ndarray = field(repr=False)
    _tree: BallTree = field(repr=False)
    # (lat, lon) филиала -> ближайший узел; словарь мутирует только этот снимок
    _branch_nodes: dict[tuple[float, float], Any] = field(default_factory=dict, repr=False)

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def nearest_node(self, lat: float, lon: float) -> tuple[Any, float]:
        """Ближайший узел графа и расстояние до него в км (haversine, как в osmnx)."""
        dist, pos = self._tree.query(np.deg2rad([[lat, lon]]), k=1)
        return self._node_ids[pos[0, 0]].item(), float(dist[0, 0]) * EARTH_RADIUS_KM

    def branch_node(self, lat: float, lon: float) -> Any:
        """Ближайший узел для филиала; считается один раз на координаты и версию графа."""
        key = (float(lat), float(lon))
        node = self._branch_nodes.get(key)
        if node is None:
            node = self.nearest_node(*key)[0]
            self._branch_nodes[key] = node
        return node

    @property
    def cached_branch_coords(self) -> list[tuple[float, float]]:
        return list(self._branch_nodes)


def build_snapshot(
    graph: nx.MultiDiGraph,
    *,
    version: int,
    source: str,
    branch_coords: list[tuple[float, float]] | None = None,
) -> GraphSnapshot:
    """Проверяет граф, строит BallTree по узлам и заранее считает узлы филиалов."""
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError(f"Ожидался networkx.MultiDiGraph, получен {type(graph).__name__}")
    if graph.number_of_nodes() == 0:
        raise ValueError("Граф дорог пуст")

    node_ids = np.empty(graph.number_of_nodes(), dtype=object)
    coords = np.empty((graph.number_of_nodes(), 2), dtype=float)
    for i, (node, data) in enumerate(graph.nodes(data=True)):
        if "x" not in data or "y" not in data:
            raise ValueError(f"У узла {node!r} нет координат x/y")
        node_ids[i] = node
        coords[i] = (data["y"], data["x"])

    # Узлы — целые числа OSM: храним в int-массиве, чтобы .item() отдавал обычный int
    if all(isinstance(n, int | np.integer) for n in node_ids):
        node_ids = node_ids.astype(np.int64)

    snapshot = GraphSnapshot(
        graph=graph,
        version=version,
        source=source,
        loaded_at=datetime.now(UTC),
        bbox=BBox(
            min_lat=float(coords[:, 0].min()),
            min_lon=float(coords[:, 1].min()),
            max_lat=float(coords[:, 0].max()),
            max_lon=float(coords[:, 1].max()),
        ),
        _node_ids=node_ids,
        _tree=BallTree(np.deg2rad(coords), metric="haversine"),
    )
    for lat, lon in branch_coords or []:
        snapshot.branch_node(lat, lon)
    return snapshot


def read_graph_file(path: Path, *, allow_download: bool) -> nx.MultiDiGraph:
    """
    Читает граф из pickle. Если файла нет и скачивание разрешено — скачивает граф OSM
    штатным загрузчиком `RoutingService` (несколько минут) и сохраняет его в `path`.
    """
    if path.exists():
        with path.open("rb") as file:
            return pickle.load(file)  # noqa: S301 — файл создаёт само приложение
    if not allow_download:
        raise FileNotFoundError(f"Файл графа не найден: {path}")

    from backend.app.ml.services.routing_service import RoutingService

    logger.info("Файл графа %s не найден — скачивание из OpenStreetMap", path)
    return RoutingService(graph_path=path, branches={}).graph


class GraphRegistry:
    """Потокобезопасный реестр текущего графа: статус, ошибка, снимок, замена."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: GraphSnapshot | None = None
        self._status = GraphStatus.NOT_LOADED
        self._error: str | None = None
        self._version = 0

    @property
    def status(self) -> GraphStatus:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    def snapshot(self) -> GraphSnapshot | None:
        """Текущий граф (чтение ссылки атомарно, блокировка не нужна)."""
        return self._snapshot

    def mark_loading(self) -> None:
        with self._lock:
            self._status = GraphStatus.LOADING
            self._error = None

    def mark_failed(self, error: BaseException | str) -> None:
        with self._lock:
            self._error = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
            # Если раньше граф уже был загружен, продолжаем работать на нём
            self._status = GraphStatus.READY if self._snapshot else GraphStatus.FAILED

    def replace_graph(self, graph: nx.MultiDiGraph, *, source: str = "memory") -> GraphSnapshot:
        """
        Атомарно заменяет граф. Индекс узлов и кэш узлов филиалов (для тех же координат,
        что были в старом кэше) строятся до захвата блокировки — читатели не ждут.
        """
        with self._lock:
            old = self._snapshot
            version = self._version + 1
            self._version = version
        coords = old.cached_branch_coords if old else None
        snapshot = build_snapshot(graph, version=version, source=source, branch_coords=coords)
        with self._lock:
            # Параллельная замена с большей версией уже выиграла — старую не ставим
            if self._snapshot is None or self._snapshot.version < version:
                self._snapshot = snapshot
            self._status = GraphStatus.READY
            self._error = None
        logger.info(
            "Граф дорог v%s загружен (%s): %s узлов, %s рёбер",
            version,
            source,
            snapshot.node_count,
            snapshot.edge_count,
        )
        return snapshot

    def load_from_file(self, path: Path, *, allow_download: bool = False) -> None:
        """Синхронная загрузка (вызывается в отдельном потоке); ошибки — в статус."""
        self.mark_loading()
        try:
            graph = read_graph_file(path, allow_download=allow_download)
            self.replace_graph(graph, source=str(path))
        except Exception as exc:  # noqa: BLE001 — любая ошибка загрузки → статус failed
            logger.exception("Не удалось загрузить граф дорог из %s", path)
            self.mark_failed(exc)

    def info(self) -> dict[str, Any]:
        """Сводка для health/админки."""
        snapshot = self._snapshot
        return {
            "status": self._status.value,
            "error": self._error,
            "version": snapshot.version if snapshot else None,
            "source": snapshot.source if snapshot else None,
            "nodes": snapshot.node_count if snapshot else None,
            "edges": snapshot.edge_count if snapshot else None,
            "loaded_at": snapshot.loaded_at if snapshot else None,
        }
