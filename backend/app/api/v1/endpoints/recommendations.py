"""
Рекомендации: филиал для водителя (граф дорог + очереди) и зоны спроса K-Means.

Эндпоинты синхронные (`def`): FastAPI выполняет их в пуле потоков, поэтому Дейкстра,
K-Means и генерация карт не блокируют event loop.
"""

import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from backend.app.api.deps import AppSettings, DbSession, require_roles
from backend.app.core.graph_state import GraphRegistry, GraphSnapshot, GraphStatus
from backend.app.db.models.user import UserRole
from backend.app.ml.visualization.clusters_map_generator import ClustersMapGenerator
from backend.app.ml.visualization.route_map_generator import MapGenerator
from backend.app.schemas.recommendations import (
    DemandZone,
    DemandZonesResponse,
    DriverRecommendation,
)
from backend.app.schemas.reports import as_utc
from backend.app.services.demand_adapter import NotEnoughOrdersError, PeriodKMeansAnalyzer
from backend.app.services.routing_adapter import FastRoutingService, PointOutsideGraphError

DRIVER_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.DRIVER)
DEMAND_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.EXECUTIVE)

# Через сколько секунд имеет смысл повторить запрос, пока граф не готов
RETRY_AFTER_LOADING_S = 30
RETRY_AFTER_UNAVAILABLE_S = 300

MAX_CLUSTERS = 50

router = APIRouter(
    prefix="/recommendations",
    tags=["recommendations"],
    responses={
        401: {"description": "Нет или неверный токен"},
        403: {"description": "Недостаточно прав"},
    },
)

_GRAPH_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "От точки водителя не достижим ни один активный филиал"},
    422: {"description": "Некорректные координаты или точка вне зоны графа дорог"},
    503: {"description": "Граф дорог ещё не загружен (заголовок `Retry-After`)"},
}


# --- зависимости ---


def get_graph_registry(request: Request) -> GraphRegistry:
    return request.app.state.graph_registry


def get_graph_snapshot(
    registry: Annotated[GraphRegistry, Depends(get_graph_registry)],
) -> GraphSnapshot:
    """Текущий граф; пока его нет — 503 с `Retry-After`."""
    snapshot = registry.snapshot()
    if snapshot is not None:
        return snapshot
    if registry.status == GraphStatus.LOADING:
        detail, retry = "Граф дорог загружается, повторите позже", RETRY_AFTER_LOADING_S
    elif registry.status == GraphStatus.FAILED:
        detail = f"Граф дорог не загружен: {registry.error}"
        retry = RETRY_AFTER_UNAVAILABLE_S
    else:
        detail, retry = "Граф дорог не загружен", RETRY_AFTER_UNAVAILABLE_S
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
        headers={"Retry-After": str(retry)},
    )


Snapshot = Annotated[GraphSnapshot, Depends(get_graph_snapshot)]
Latitude = Annotated[float, Query(ge=-90, le=90, description="Широта водителя")]
Longitude = Annotated[float, Query(ge=-180, le=180, description="Долгота водителя")]


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _recommend(
    snapshot: GraphSnapshot, db: DbSession, settings: AppSettings, lat: float, lon: float
) -> tuple[FastRoutingService, dict[str, Any]]:
    router_service = FastRoutingService(
        snapshot, session=db, max_snap_distance_km=settings.ROUTE_MAX_SNAP_DISTANCE_KM
    )
    try:
        recommendation = router_service.get_driver_recommendation(lat, lon)
    except PointOutsideGraphError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    if recommendation is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Нет маршрута ни к одному активному филиалу"
        )
    return router_service, recommendation


def _render_html(generate: Callable[[str], str | None]) -> HTMLResponse:
    """
    Генераторы карт сохраняют HTML в `data/<имя>`; абсолютный путь в `os.path.join`
    заменяет каталог, поэтому файл пишется во временную папку и удаляется после чтения.
    """
    with tempfile.TemporaryDirectory(prefix="pizza-map-") as tmp:
        target = Path(tmp) / f"map_{uuid.uuid4().hex}.html"
        path = generate(str(target))
        if not path:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Карта не построена")
        html = Path(path).read_text(encoding="utf-8")
    return HTMLResponse(html)


# --- водитель ---


@router.get(
    "/driver",
    response_model=DriverRecommendation,
    summary="Лучший филиал для водителя",
    dependencies=[Depends(require_roles(*DRIVER_ROLES))],
    responses=_GRAPH_RESPONSES,
)
def driver_recommendation(
    lat: Latitude, lon: Longitude, snapshot: Snapshot, db: DbSession, settings: AppSettings
) -> DriverRecommendation:
    """
    Один проход Дейкстры по графу дорог от ближайшего к водителю узла; выбирается филиал
    с минимальной оценкой `минуты в пути - очередь * 2`. Роли: admin, manager, driver.
    """
    started = time.perf_counter()
    router_service, rec = _recommend(snapshot, db, settings, lat, lon)
    return DriverRecommendation(
        branch_id=rec["branch_id"],
        branch_name=rec["branch_name"],
        travel_time_minutes=rec["travel_time_minutes"],
        queue_size=rec["queue_size"],
        score=round(rec["travel_time_minutes"] - rec["queue_size"] * 2, 1),
        driver_node=rec["driver_node"],
        branch_node=rec["branch_node"],
        route=router_service.route_coords(rec),
        graph_version=snapshot.version,
        elapsed_ms=_elapsed_ms(started),
    )


@router.get(
    "/driver/map",
    response_class=HTMLResponse,
    summary="Карта маршрута водителя (HTML, folium)",
    dependencies=[Depends(require_roles(*DRIVER_ROLES))],
    responses=_GRAPH_RESPONSES,
)
def driver_route_map(
    lat: Latitude, lon: Longitude, snapshot: Snapshot, db: DbSession, settings: AppSettings
) -> HTMLResponse:
    """Карта с маршрутом, всеми филиалами и заказами (через `MapGenerator`)."""
    router_service, rec = _recommend(snapshot, db, settings, lat, lon)
    generator = MapGenerator(router_service, session=db)
    return _render_html(lambda filename: generator.generate_route_map(rec, filename))


# --- зоны спроса (K-Means) ---


def demand_analyzer(
    db: DbSession,
    n_clusters: Annotated[int, Query(ge=1, le=MAX_CLUSTERS, description="Число кластеров")] = 7,
    date_from: Annotated[datetime | None, Query(description="Начало периода (UTC)")] = None,
    date_to: Annotated[datetime | None, Query(description="Конец периода (UTC), искл.")] = None,
    coverage_radius_km: Annotated[float, Query(gt=0, le=50)] = 2.0,
    high_demand_threshold: Annotated[int, Query(ge=0)] = 130,
    low_demand_threshold: Annotated[int, Query(ge=0)] = 80,
) -> PeriodKMeansAnalyzer:
    date_from, date_to = as_utc(date_from), as_utc(date_to)
    if date_from is not None and date_to is not None and date_from >= date_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="date_from должен быть раньше date_to"
        )
    return PeriodKMeansAnalyzer(
        session=db,
        date_from=date_from,
        date_to=date_to,
        n_clusters=n_clusters,
        coverage_radius_km=coverage_radius_km,
        high_demand_threshold=high_demand_threshold,
        low_demand_threshold=low_demand_threshold,
    )


Analyzer = Annotated[PeriodKMeansAnalyzer, Depends(demand_analyzer)]

_DEMAND_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"description": "Некорректные параметры или заказов меньше, чем кластеров"},
}


def _checked_orders(analyzer: PeriodKMeansAnalyzer) -> pd.DataFrame:
    try:
        return analyzer.load_checked_data()
    except NotEnoughOrdersError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None


@router.get(
    "/branches",
    response_model=DemandZonesResponse,
    summary="Зоны спроса и рекомендации по филиалам (K-Means)",
    dependencies=[Depends(require_roles(*DEMAND_ROLES))],
    responses=_DEMAND_RESPONSES,
)
def branch_recommendations(analyzer: Analyzer) -> DemandZonesResponse:
    """Кластеризация доставленных заказов за период. Роли: admin, manager, executive."""
    started = time.perf_counter()
    df = _checked_orders(analyzer)
    zones = analyzer.analyze_demand(df=df)
    return DemandZonesResponse(
        n_clusters=analyzer.n_clusters,
        date_from=analyzer.date_from,
        date_to=analyzer.date_to,
        orders_count=len(df),
        zones=[DemandZone(**zone) for zone in zones],
        elapsed_ms=_elapsed_ms(started),
    )


@router.get(
    "/branches/map",
    response_class=HTMLResponse,
    summary="Карта зон спроса (HTML, folium)",
    dependencies=[Depends(require_roles(*DEMAND_ROLES))],
    responses=_DEMAND_RESPONSES,
)
def branch_recommendations_map(analyzer: Analyzer) -> HTMLResponse:
    """Тепловая карта заказов, филиалы и центроиды K-Means (через `ClustersMapGenerator`)."""
    _checked_orders(analyzer)
    generator = ClustersMapGenerator(analyzer)
    return _render_html(generator.generate_clusters_map)
