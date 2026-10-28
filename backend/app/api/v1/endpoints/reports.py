"""Шаблоны отчётов, конструктор и экспорт CSV (роли: admin, manager, executive)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.app.api.deps import CurrentUser, DbSession, require_roles
from backend.app.db.models import ReportTemplate
from backend.app.db.models.user import UserRole
from backend.app.schemas.reports import (
    CsvDelimiter,
    ReportConfig,
    ReportPeriod,
    ReportPreview,
    ReportRequest,
    ReportTemplateCreate,
    ReportTemplateRead,
    ReportTemplateUpdate,
    as_utc,
)
from backend.app.services.report_service import (
    ReportPermissionError,
    ReportService,
    TemplateNameConflictError,
    TemplateNotFoundError,
    content_disposition,
    report_columns,
    report_filename,
    resolve_period,
    to_csv,
)
from backend.app.services.stats_service import to_records

REPORT_ROLES = (UserRole.ADMIN, UserRole.MANAGER, UserRole.EXECUTIVE)

_PERIOD_NOTE = (
    "Даты — в UTC (значение без пояса трактуется как UTC), период полуоткрытый: "
    "`date_from <= order_time < date_to`. Если даты не переданы — последние "
    "`config.default_period_days` дней."
)
_CSV_NOTE = (
    "CSV: UTF-8 с BOM, русские заголовки. Разделитель `;` (Excel RU, дробная часть через "
    "запятую) или `,` (дробная часть через точку)."
)
_CSV_RESPONSE = {200: {"content": {"text/csv": {}}, "description": "Файл CSV"}}

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_roles(*REPORT_ROLES))],
    responses={
        401: {"description": "Нет или неверный токен"},
        403: {"description": "Недостаточно прав"},
        422: {"description": "Некорректная конфигурация или период"},
    },
)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Ошибки сервиса -> HTTP."""
    try:
        yield
    except TemplateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Шаблон не найден") from None
    except ReportPermissionError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Недостаточно прав") from None
    except TemplateNameConflictError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Шаблон с таким названием уже существует"
        ) from None


def report_period(
    date_from: Annotated[
        datetime | None, Query(description="Начало периода, включительно (ISO 8601, UTC)")
    ] = None,
    date_to: Annotated[
        datetime | None, Query(description="Конец периода, не включительно (ISO 8601, UTC)")
    ] = None,
) -> ReportPeriod:
    start, end = as_utc(date_from), as_utc(date_to)
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_from должен быть не позже date_to",
        )
    return ReportPeriod(date_from=start, date_to=end)


Period = Annotated[ReportPeriod, Depends(report_period)]
Delimiter = Annotated[
    CsvDelimiter, Query(description="Разделитель CSV: `;` (по умолчанию) или `,`")
]


def _csv_response(
    service: ReportService,
    config: ReportConfig,
    period: ReportPeriod,
    name: str,
    sep: CsvDelimiter,
) -> Response:
    resolved = resolve_period(config, period)
    df = service.build_report(config, resolved)
    return Response(
        content=to_csv(df, sep),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": content_disposition(report_filename(name, resolved))},
    )


# --- шаблоны ---


@router.get(
    "/templates",
    response_model=list[ReportTemplateRead],
    summary="Список шаблонов",
    description="Системные и свои шаблоны; администратор видит все.",
)
def list_templates(user: CurrentUser, db: DbSession) -> list[ReportTemplate]:
    with _service_errors():
        return list(ReportService(db).list_templates(user))


@router.post(
    "/templates",
    response_model=ReportTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать шаблон",
    description="admin и manager; системный шаблон (`is_system=true`) — только admin.",
    responses={409: {"description": "Шаблон с таким названием уже существует"}},
)
def create_template(data: ReportTemplateCreate, user: CurrentUser, db: DbSession) -> ReportTemplate:
    with _service_errors():
        return ReportService(db).create_template(user, data)


@router.get(
    "/templates/{template_id}",
    response_model=ReportTemplateRead,
    summary="Шаблон по id",
    responses={404: {"description": "Шаблон не найден"}},
)
def get_template(template_id: int, user: CurrentUser, db: DbSession) -> ReportTemplate:
    with _service_errors():
        return ReportService(db).get_template(user, template_id)


@router.put(
    "/templates/{template_id}",
    response_model=ReportTemplateRead,
    summary="Изменить шаблон",
    description="Свой шаблон — владелец или admin; системный — только admin.",
    responses={
        404: {"description": "Шаблон не найден"},
        409: {"description": "Шаблон с таким названием уже существует"},
    },
)
def update_template(
    template_id: int, data: ReportTemplateUpdate, user: CurrentUser, db: DbSession
) -> ReportTemplate:
    with _service_errors():
        return ReportService(db).update_template(user, template_id, data)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить шаблон",
    description="Свой шаблон — владелец или admin; системный — только admin.",
    responses={404: {"description": "Шаблон не найден"}},
)
def delete_template(template_id: int, user: CurrentUser, db: DbSession) -> Response:
    with _service_errors():
        ReportService(db).delete_template(user, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/templates/{template_id}/export.csv",
    response_class=Response,
    responses={**_CSV_RESPONSE, 404: {"description": "Шаблон не найден"}},
    summary="Экспорт отчёта по шаблону в CSV",
    description=f"{_PERIOD_NOTE} {_CSV_NOTE}",
)
def export_template_csv(
    template_id: int,
    user: CurrentUser,
    db: DbSession,
    period: Period,
    delimiter: Delimiter = ";",
) -> Response:
    service = ReportService(db)
    with _service_errors():
        template = service.get_template(user, template_id)
    config = ReportConfig.model_validate(template.config)
    return _csv_response(service, config, period, template.name, delimiter)


# --- конструктор ---


@router.post(
    "/preview",
    response_model=ReportPreview,
    summary="Предпросмотр отчёта (конструктор)",
    description=f"Конфигурация + период → строки отчёта в JSON. {_PERIOD_NOTE}",
)
def preview_report(request: ReportRequest, db: DbSession) -> ReportPreview:
    period = resolve_period(request.config, request)
    df = ReportService(db).build_report(request.config, period)
    return ReportPreview(
        period=ReportPeriod(date_from=period.date_from, date_to=period.date_to),
        columns=report_columns(df),
        rows=to_records(df),
    )


@router.post(
    "/export.csv",
    response_class=Response,
    responses=_CSV_RESPONSE,
    summary="Экспорт ad-hoc отчёта в CSV",
    description=f"Конфигурация + период из тела запроса. {_PERIOD_NOTE} {_CSV_NOTE}",
)
def export_adhoc_csv(request: ReportRequest, db: DbSession, delimiter: Delimiter = ";") -> Response:
    period = ReportPeriod(date_from=request.date_from, date_to=request.date_to)
    return _csv_response(ReportService(db), request.config, period, request.name, delimiter)
