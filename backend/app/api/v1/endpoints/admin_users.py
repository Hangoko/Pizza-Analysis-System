"""Администрирование пользователей (только admin)."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.deps import DbSession, require_roles
from backend.app.db.models import User
from backend.app.db.models.user import UserRole
from backend.app.schemas.user import UserAdminRead, UserCreate, UserList, UserUpdate
from backend.app.services.auth_service import UserAlreadyExistsError
from backend.app.services.user_admin_service import (
    AdminProtectionError,
    DriverLinkError,
    UserAdminError,
    UserAdminService,
    UserNotFoundError,
    to_admin_read,
)

require_admin = require_roles(UserRole.ADMIN)
Admin = Annotated[User, Depends(require_admin)]

router = APIRouter(
    prefix="/admin/users",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
    responses={
        401: {"description": "Нет или неверный токен"},
        403: {"description": "Недостаточно прав (нужна роль admin)"},
    },
)

_FIELD_NAMES = {"username": "логином", "email": "email"}
_NOT_FOUND = {404: {"description": "Пользователь или водитель не найден"}}
_CONFLICT = {409: {"description": "Логин/email заняты, защита администратора, водитель занят"}}


def _raise_http(exc: UserAdminError | UserAlreadyExistsError) -> NoReturn:
    if isinstance(exc, UserAlreadyExistsError):
        detail = f"Пользователь с таким {_FIELD_NAMES.get(exc.field, exc.field)} уже существует"
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail) from None
    kind = exc.kind if isinstance(exc, DriverLinkError) else None
    if isinstance(exc, UserNotFoundError) or kind == "not_found":
        code = status.HTTP_404_NOT_FOUND
    elif kind == "invalid":
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(exc, AdminProtectionError | DriverLinkError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(code, detail=str(exc)) from None


@router.get("", response_model=UserList, summary="Список пользователей")
def list_users(
    db: DbSession,
    role: Annotated[UserRole | None, Query(description="Фильтр по роли")] = None,
    is_active: Annotated[bool | None, Query(description="Фильтр по активности")] = None,
    search: Annotated[
        str | None, Query(max_length=100, description="Подстрока логина или ФИО")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserList:
    users, total = UserAdminService(db).list(
        role=role, is_active=is_active, query=search, offset=offset, limit=limit
    )
    return UserList(
        items=[to_admin_read(user) for user in users], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    response_model=UserAdminRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать сотрудника",
    responses={**_NOT_FOUND, **_CONFLICT},
)
def create_user(data: UserCreate, db: DbSession) -> UserAdminRead:
    """Сотрудник с любой ролью; для роли `driver` можно сразу указать `driver_id`."""
    try:
        return to_admin_read(UserAdminService(db).create(data))
    except (UserAdminError, UserAlreadyExistsError) as exc:
        _raise_http(exc)


@router.get(
    "/{user_id}", response_model=UserAdminRead, summary="Пользователь", responses=_NOT_FOUND
)
def get_user(user_id: int, db: DbSession) -> UserAdminRead:
    try:
        return to_admin_read(UserAdminService(db).get(user_id))
    except UserAdminError as exc:
        _raise_http(exc)


@router.patch(
    "/{user_id}",
    response_model=UserAdminRead,
    summary="Изменить пользователя",
    responses={**_NOT_FOUND, **_CONFLICT},
)
def update_user(user_id: int, data: UserUpdate, db: DbSession, admin: Admin) -> UserAdminRead:
    """Роль, ФИО, email, активность, сброс пароля (`password`), привязка `driver_id`."""
    try:
        return to_admin_read(UserAdminService(db).update(user_id, data, actor=admin))
    except (UserAdminError, UserAlreadyExistsError) as exc:
        _raise_http(exc)


@router.delete(
    "/{user_id}",
    response_model=UserAdminRead,
    summary="Деактивировать пользователя",
    responses={**_NOT_FOUND, **_CONFLICT},
)
def deactivate_user(user_id: int, db: DbSession, admin: Admin) -> UserAdminRead:
    """Мягкое удаление: `is_active=false`, данные и история заказов сохраняются."""
    try:
        return to_admin_read(UserAdminService(db).deactivate(user_id, actor=admin))
    except UserAdminError as exc:
        _raise_http(exc)
