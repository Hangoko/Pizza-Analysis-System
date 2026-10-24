"""Общие зависимости FastAPI для эндпоинтов: сессия БД, настройки, текущий пользователь, роли."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import InvalidTokenError, decode_token
from backend.app.db.models import User
from backend.app.db.models.user import UserRole
from backend.app.db.session import get_db
from backend.app.repositories.user import UserRepository

# Сессия БД на время запроса; в тестах подменяется через dependency_overrides[get_db]
DbSession = Annotated[Session, Depends(get_db)]


def get_app_settings(request: Request) -> Settings:
    """Настройки, с которыми создано приложение (create_app(settings))."""
    return getattr(request.app.state, "settings", None) or get_settings()


AppSettings = Annotated[Settings, Depends(get_app_settings)]

# tokenUrl должен совпадать с реальным путём эндпоинта входа — его использует Swagger Authorize
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{get_settings().API_V1_PREFIX}/auth/login")


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
    settings: AppSettings,
) -> User:
    """
    Пользователь по JWT. Читается из БД на каждый запрос, поэтому блокировка
    и смена роли действуют сразу, без ожидания истечения токена.
    """
    try:
        payload = decode_token(token, settings=settings)
    except InvalidTokenError:
        raise _credentials_error() from None
    user = UserRepository(db).get(payload.user_id)
    if user is None:
        raise _credentials_error()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись заблокирована"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole | str) -> Callable[[User], User]:
    """
    Зависимость «пользователь с одной из ролей»:
        `Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))`
    Без токена — 401, с неподходящей ролью — 403.
    """
    if not roles:
        raise ValueError("require_roles: нужно указать хотя бы одну роль")
    allowed = frozenset(str(role) for role in roles)

    def _check_role(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user

    return _check_role


__all__ = [
    "AppSettings",
    "CurrentUser",
    "DbSession",
    "get_app_settings",
    "get_current_user",
    "get_db",
    "oauth2_scheme",
    "require_roles",
]
