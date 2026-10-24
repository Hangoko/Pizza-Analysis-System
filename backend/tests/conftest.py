"""Общие фикстуры тестов."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """HTTP-клиент для приложения (с запуском lifespan)."""
    with TestClient(create_app()) as test_client:
        yield test_client
