"""
Эндпоинты проверки состояния сервиса.

- `/health`       — liveness: процесс жив и отвечает.
- `/health/ready` — readiness: готовность зависимостей (БД, граф дорог).
  Если сервис не готов, возвращается HTTP 503. Статус графа добавляется на этапе 6.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.core.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])

ComponentState = Literal["ok", "error", "loading", "not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    version: str


class ComponentStatus(BaseModel):
    status: ComponentState
    detail: str | None = None


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


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness-проверка",
    responses={503: {"model": ReadinessResponse, "description": "Сервис не готов"}},
)
def ready(response: Response, db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse:
    """Состояние зависимостей сервиса: БД и граф дорог."""
    components = {
        "database": check_database(db),
        # Заготовка: загрузка графа подключается на этапе 6
        "graph": ComponentStatus(
            status="not_configured", detail="Загрузка графа будет добавлена на этапе 6"
        ),
    }
    # Сервис не готов, если хотя бы один компонент в ошибке или ещё загружается
    not_ready = any(c.status in ("error", "loading") for c in components.values())
    if not_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="not_ready" if not_ready else "ready", components=components)
