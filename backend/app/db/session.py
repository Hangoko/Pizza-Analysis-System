"""Подключение к БД: engine, фабрика сессий и зависимость FastAPI `get_db`."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


def make_engine(url: str) -> Engine:
    """Создаёт engine; для PostgreSQL ограничиваем время ожидания подключения."""
    connect_args: dict[str, object] = {}
    if url.startswith("postgresql"):
        connect_args["connect_timeout"] = 5
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


# Engine не подключается к БД при создании — соединение открывается при первом запросе
engine = make_engine(get_settings().DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Сессия БД на время обработки запроса."""
    with SessionLocal() as session:
        yield session
