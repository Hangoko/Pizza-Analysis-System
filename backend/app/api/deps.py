"""Общие зависимости FastAPI для эндпоинтов."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db

# Сессия БД на время запроса; в тестах подменяется через dependency_overrides[get_db]
DbSession = Annotated[Session, Depends(get_db)]

__all__ = ["DbSession", "get_db"]
