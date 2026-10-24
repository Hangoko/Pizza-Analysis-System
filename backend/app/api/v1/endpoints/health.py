"""
Эндпоинты проверки состояния сервиса.

- `/health`       — liveness: процесс жив и отвечает.
- `/health/ready` — readiness: готовность зависимостей (БД, граф дорог).
  Проверка БД добавляется на этапе 2, статус графа — на этапе 6.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

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


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness-проверка")
def ready() -> ReadinessResponse:
    """Состояние зависимостей сервиса."""
    # Заготовки: реальные проверки подключаются на следующих этапах
    components = {
        "database": ComponentStatus(
            status="not_configured", detail="Проверка БД будет добавлена на этапе 2"
        ),
        "graph": ComponentStatus(
            status="not_configured", detail="Загрузка графа будет добавлена на этапе 6"
        ),
    }
    # Сервис не готов, если хотя бы один компонент в ошибке или ещё загружается
    not_ready = any(c.status in ("error", "loading") for c in components.values())
    return ReadinessResponse(status="not_ready" if not_ready else "ready", components=components)
