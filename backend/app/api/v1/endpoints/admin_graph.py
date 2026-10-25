"""
Администрирование графа дорог (только admin).

Эндпоинты синхронные: разбор файлов, копирование графа и pickle выполняются в пуле потоков,
изменения сериализуются `GraphRegistry.mutation_lock`.
"""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.app.api.deps import AppSettings, require_roles
from backend.app.api.v1.endpoints.recommendations import get_graph_registry
from backend.app.core.graph_state import GraphRegistry
from backend.app.db.models.user import UserRole
from backend.app.schemas.graph import GraphChangeResult, GraphInfo, WeightsUpdateReport
from backend.app.services.graph_service import GraphAdminError, GraphService

router = APIRouter(
    prefix="/admin/graph",
    tags=["admin"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
    responses={
        401: {"description": "Нет или неверный токен"},
        403: {"description": "Недостаточно прав (нужна роль admin)"},
    },
)

_UPLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"description": "Граф ещё загружается при старте"},
    413: {"description": "Файл больше GRAPH_UPLOAD_MAX_MB"},
    415: {"description": "Неподдерживаемый формат (в т.ч. pickle)"},
    422: {"description": "Файл не разобран или не прошёл проверку"},
}


def get_graph_service(
    registry: Annotated[GraphRegistry, Depends(get_graph_registry)], settings: AppSettings
) -> GraphService:
    return GraphService(registry, settings)


Service = Annotated[GraphService, Depends(get_graph_service)]


def _run(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return action()
    except GraphAdminError as exc:
        detail: Any = {"message": str(exc), "errors": exc.errors} if exc.errors else str(exc)
        raise HTTPException(exc.status_code, detail=detail) from None


@router.get("/info", response_model=GraphInfo, summary="Состояние графа дорог")
def graph_info(service: Service) -> dict[str, Any]:
    """Узлы, рёбра, источник, версия, время загрузки, статус, файл `GRAPH_PATH`."""
    return service.info()


@router.post(
    "/weights",
    response_model=WeightsUpdateReport,
    summary="Обновить веса рёбер (пробки)",
    responses={**_UPLOAD_RESPONSES, 503: {"description": "Граф не загружен"}},
)
def update_weights(
    service: Service,
    file: Annotated[
        UploadFile, File(description="CSV или JSON: u, v[, key], travel_time|multiplier")
    ],
) -> dict[str, Any]:
    """
    Каждая строка: `u`, `v`, необязательный `key` (без него — все параллельные рёбра u→v) и
    ровно одно из `travel_time` (секунды) или `multiplier` (к исходному времени без пробок).
    Некорректные строки пропускаются с причиной; граф заменяется, если обновлено хоть одно ребро.
    """
    return _run(lambda: service.update_weights(file.file, file.filename))


@router.post(
    "/upload",
    response_model=GraphChangeResult,
    summary="Загрузить новый граф (GraphML / JSON node-link)",
    responses=_UPLOAD_RESPONSES,
)
def upload_graph(
    service: Service,
    file: Annotated[UploadFile, File(description="GraphML (.graphml) или JSON node-link (.json)")],
) -> dict[str, Any]:
    """Узлы — `x` (долгота), `y` (широта); рёбра — `travel_time` > 0. Pickle не принимается."""
    return _run(lambda: service.upload(file.file, file.filename))


@router.post(
    "/reload",
    response_model=GraphChangeResult,
    summary="Перечитать граф из GRAPH_PATH",
    responses={
        404: {"description": "Файла графа нет"},
        409: {"description": "Граф ещё загружается при старте"},
        422: {"description": "Файл повреждён — остаётся прежний граф"},
    },
)
def reload_graph(service: Service) -> dict[str, Any]:
    return _run(service.reload)
