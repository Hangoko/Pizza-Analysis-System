"""Окружение Alembic: URL из настроек приложения, метаданные — из ORM-моделей."""

from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy.engine import Connection

import backend.app.db.models  # noqa: F401  (регистрация всех таблиц в metadata)
from backend.app.core.config import get_settings
from backend.app.db.base import Base, UTCDateTime
from backend.app.db.session import make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """URL можно переопределить параметром `-x db_url=...`, иначе — DATABASE_URL."""
    return context.get_x_argument(as_dictionary=True).get("db_url") or get_settings().DATABASE_URL


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | bool:
    """Миграции не зависят от кода приложения: UTCDateTime пишем как sa.DateTime(tz)."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=False,
        render_item=render_item,
        # SQLite не умеет ALTER для большинства операций — batch-режим
        render_as_batch=(connection is not None and connection.dialect.name == "sqlite"),
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else {},
    )


def run_migrations_offline() -> None:
    """Генерация SQL без подключения к БД (`alembic upgrade head --sql`)."""
    _configure(url=get_url())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(get_url())
    with engine.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
