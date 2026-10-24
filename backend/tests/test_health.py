"""Тесты эндпоинтов состояния и документации API."""

from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.session import get_db
from backend.app.main import create_app


def test_health_liveness(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "NewFastPizza Analytics API"


def test_health_ready_with_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert set(body["components"]) == {"database", "graph"}
    assert body["components"]["database"]["status"] == "ok"
    assert body["components"]["graph"]["status"] == "not_configured"


def test_health_ready_database_unavailable(tmp_path: Path) -> None:
    """Недоступная БД: компонент database в ошибке, ответ 503."""
    broken_engine = create_engine(f"sqlite:///{tmp_path / 'missing' / 'db.sqlite'}")

    def _broken_db() -> Iterator[Session]:
        with Session(broken_engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = _broken_db
    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/health/ready")
    broken_engine.dispose()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["components"]["database"]["status"] == "error"


def test_openapi_schema(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "NewFastPizza Analytics API"
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/health/ready" in schema["paths"]


def test_docs_pages(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_settings_parse_cors_and_graph_path() -> None:
    settings = Settings(CORS_ORIGINS="http://a.local, http://b.local", _env_file=None)
    assert settings.CORS_ORIGINS == ["http://a.local", "http://b.local"]
    assert settings.GRAPH_PATH == settings.DATA_DIR / "nn_graph.pkl"
