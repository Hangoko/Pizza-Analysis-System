"""Схемы пользователя. Хеш пароля наружу не отдаётся никогда."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.security import BCRYPT_MAX_PASSWORD_BYTES, password_too_long
from backend.app.db.models.user import UserRole

PASSWORD_MIN_LENGTH = 8
# Простая проверка формата email (без зависимости email-validator)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserRegister(BaseModel):
    """Данные саморегистрации. Роль не передаётся: всегда `driver`."""

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def _password_fits_bcrypt(cls, value: str) -> str:
        if password_too_long(value):
            raise ValueError(f"Пароль не должен превышать {BCRYPT_MAX_PASSWORD_BYTES} байт")
        return value

    @field_validator("email")
    @classmethod
    def _email_format(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("Некорректный email")
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
