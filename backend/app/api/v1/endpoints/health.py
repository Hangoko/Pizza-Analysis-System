"""
Эндпоинты проверки состояния сервиса.

- `/health`       — liveness: процесс жив и отвечает.
- `/health/ready` — readiness: готовность зависимостей (БД, граф дорог).
  Если сервис не готов, возвращается HTTP 503.

Граф дорог влияет на готовность, только если он обязателен (`LOAD_GRAPH_ON_STARTUP=true`):
пока он грузится — `loading`, при ошибке — `error` (оба дают 503). При
`LOAD_GRAPH_ON_STARTUP=false` граф необязателен: незагруженный граф — `not_configured`,
сервис готов, а эндпоинты маршрутов сами отвечают 503.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.deps import AppSettings, get_db
from backend.app.core.config import get_settings
from backend.app.core.graph_state import GraphRegistry, GraphStatus

router = APIRouter(prefix="/health", tags=["health"])

ComponentState = Literal["ok", "error", "loading", "not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    version: str


class ComponentStatus(BaseModel):
    status: ComponentState
    detail: str | None = None
    required: bool = True


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    components: dict[str, ComponentStatus]


@router.get("", response_model=HealthResponse, summary="Liveness-проверка")
def health() -> HealthResponse:
    """Сервис запущен и обрабатывает запросы."""
    settings = get_settings()
    return HealthResponse(app=settings.APP_NAME, version=settings.APP_VERSION)


def check_database(db: Session) -> ComponentStatus:
    """Простейший запрос к БД: соединение установлено и СУБД отвечает."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return ComponentStatus(status="error", detail=type(exc).__name__)
    return ComponentStatus(status="ok")


def check_graph(registry: GraphRegistry, required: bool) -> ComponentStatus:
    """Состояние графа дорог в памяти процесса."""
    snapshot = registry.snapshot()
    if snapshot is not None:
        detail = f"v{snapshot.version}: {snapshot.node_count} узлов, {snapshot.edge_count} рёбер"
        if registry.status == GraphStatus.LOADING:
            detail += "; идёт перезагрузка"
        return ComponentStatus(status="ok", detail=detail, required=required)
    if registry.status == GraphStatus.FAILED:
        return ComponentStatus(status="error", detail=registry.error, required=required)
    if registry.status == GraphStatus.LOADING:
        return ComponentStatus(status="loading", detail="Граф загружается", required=required)
    return ComponentStatus(
        status="not_configured",
        detail="Загрузка графа при старте отключена (LOAD_GRAPH_ON_STARTUP=false)",
        required=required,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness-проверка",
    responses={503: {"model": ReadinessResponse, "description": "Сервис не готов"}},
)
def ready(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: AppSettings,
) -> ReadinessResponse:
    """Состояние зависимостей сервиса: БД и граф дорог."""
    components = {
        "database": check_database(db),
        "graph": check_graph(
            request.app.state.graph_registry, required=settings.LOAD_GRAPH_ON_STARTUP
        ),
    }
    # Не готов, если обязательный компонент в ошибке или ещё загружается
    not_ready = any(c.required and c.status in ("error", "loading") for c in components.values())
    if not_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="not_ready" if not_ready else "ready", components=components)
