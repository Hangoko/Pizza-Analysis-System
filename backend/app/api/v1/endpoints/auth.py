"""Эндпоинты аутентификации: регистрация, вход (OAuth2 password flow), текущий пользователь."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.app.api.deps import AppSettings, CurrentUser, DbSession
from backend.app.core.security import create_access_token
from backend.app.db.models import User
from backend.app.schemas.auth import Token
from backend.app.schemas.user import UserRead, UserRegister
from backend.app.services.auth_service import (
    AuthService,
    InactiveUserError,
    InvalidCredentialsError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_FIELD_NAMES = {"username": "логином", "email": "email"}


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация (роль driver)",
    responses={
        403: {"description": "Публичная регистрация отключена"},
        409: {"description": "Логин или email уже заняты"},
    },
)
def register(data: UserRegister, db: DbSession, settings: AppSettings) -> User:
    """Создаёт пользователя с ролью `driver`. Повысить роль может только администратор."""
    try:
        return AuthService(db, settings).register(data)
    except RegistrationDisabledError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Публичная регистрация отключена"
        ) from None
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Пользователь с таким {_FIELD_NAMES.get(exc.field, exc.field)} уже существует",
        ) from None


@router.post(
    "/login",
    response_model=Token,
    summary="Вход: получить JWT",
    responses={
        401: {"description": "Неверный логин или пароль"},
        403: {"description": "Учётная запись заблокирована"},
    },
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    settings: AppSettings,
) -> Token:
    """OAuth2 password flow (form-data `username`/`password`) — работает с Swagger Authorize."""
    try:
        user = AuthService(db, settings).authenticate(form.username, form.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись заблокирована"
        ) from None
    token = create_access_token(user.id, user.role, settings=settings)
    return Token(access_token=token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@router.get("/me", response_model=UserRead, summary="Текущий пользователь")
def me(user: CurrentUser) -> User:
    return user
