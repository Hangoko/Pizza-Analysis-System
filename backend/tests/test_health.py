"""Тесты эндпоинтов состояния и документации API."""

from fastapi.testclient import TestClient

from backend.app.core.config import Settings


def test_health_liveness(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "NewFastPizza Analytics API"


def test_health_ready_structure(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ready", "not_ready")
    assert set(body["components"]) == {"database", "graph"}


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
