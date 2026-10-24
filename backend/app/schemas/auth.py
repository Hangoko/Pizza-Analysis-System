"""Схемы аутентификации."""

from typing import Literal

from pydantic import BaseModel


class Token(BaseModel):
    """Ответ `/auth/login` в формате OAuth2 (совместим со Swagger Authorize)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # секунды
