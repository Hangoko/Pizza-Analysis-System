"""Общие фикстуры тестов: SQLite in-memory вместо PostgreSQL и HTTP-клиент."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.db.models  # noqa: F401  (регистрация таблиц в metadata)
from backend.app.core.config import Settings
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import create_app


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Отдельная in-memory БД на каждый тест; StaticPool — одно соединение на все сессии."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


TEST_JWT_SECRET = "test-only-jwt-secret-key-with-enough-length-0123456789"


def make_test_settings(**overrides: Any) -> Settings:
    """Настройки тестов: без чтения `.env`, с тестовым JWT-секретом и без загрузки графа."""
    values: dict[str, Any] = {
        "JWT_SECRET_KEY": TEST_JWT_SECRET,
        "LOAD_GRAPH_ON_STARTUP": False,
        "ALLOW_PUBLIC_REGISTRATION": True,
        "FIRST_ADMIN_USERNAME": None,
        "FIRST_ADMIN_PASSWORD": None,
        "FIRST_ADMIN_EMAIL": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def test_settings() -> Settings:
    return make_test_settings()


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def make_client(session_factory: sessionmaker[Session]) -> Iterator[ClientFactory]:
    """Фабрика HTTP-клиентов: `make_client(settings=..., setup=lambda app: ...)`."""
    clients: list[TestClient] = []

    def _get_test_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    def _make(settings: Settings | None = None, setup: Callable[[Any], None] | None = None):
        app = create_app(settings or make_test_settings())
        app.dependency_overrides[get_db] = _get_test_db
        if setup is not None:
            setup(app)
        test_client = TestClient(app)
        test_client.__enter__()
        clients.append(test_client)
        return test_client

    yield _make
    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    """HTTP-клиент для приложения (с запуском lifespan) и подменённой сессией БД."""
    return make_client()
