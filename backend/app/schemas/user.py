"""Схемы пользователя. Хеш пароля наружу не отдаётся никогда."""

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from backend.app.core.security import BCRYPT_MAX_PASSWORD_BYTES, password_too_long
from backend.app.db.models.user import UserRole

PASSWORD_MIN_LENGTH = 8
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"
# Простая проверка формата email (без зависимости email-validator)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_password(value: str | None) -> str | None:
    if value is not None and password_too_long(value):
        raise ValueError(f"Пароль не должен превышать {BCRYPT_MAX_PASSWORD_BYTES} байт")
    return value


def normalize_email(value: str | None) -> str | None:
    """Пустая строка → None; email приводится к нижнему регистру и проверяется."""
    if value is None or not value.strip():
        return None
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Некорректный email")
    return value


Password = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH), AfterValidator(check_password)]
Email = Annotated[str | None, Field(max_length=255), AfterValidator(normalize_email)]


class UserRegister(BaseModel):
    """Данные саморегистрации. Роль не передаётся: всегда `driver`."""

    username: str = Field(min_length=3, max_length=64, pattern=USERNAME_PATTERN)
    password: Password
    email: Email = None
    full_name: str | None = Field(default=None, max_length=255)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime


# --- администрирование пользователей (/admin/users) ---


class UserCreate(UserRegister):
    """Создание сотрудника администратором: роль любая."""

    role: UserRole
    is_active: bool = True
    driver_id: int | None = Field(
        default=None, description="Привязать к записи водителя (только для роли driver)"
    )


class UserUpdate(BaseModel):
    """Частичное изменение. Передаются только меняемые поля; `driver_id: null` — отвязать."""

    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    full_name: str | None = Field(default=None, max_length=255)
    email: Email = None
    is_active: bool | None = None
    password: Password | None = Field(default=None, description="Новый пароль (сброс)")
    driver_id: int | None = None


class UserAdminRead(UserRead):
    updated_at: datetime | None = None
    driver_id: int | None = Field(default=None, description="Связанная запись водителя")


class UserList(BaseModel):
    items: list[UserAdminRead]
    total: int
    limit: int
    offset: int
