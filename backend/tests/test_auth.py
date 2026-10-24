"""Тесты аутентификации и RBAC: регистрация, вход, /me, токены, роли, бутстрап админа."""

import base64
import json
import logging
from datetime import timedelta
from typing import Annotated

import jwt
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.api.deps import require_roles
from backend.app.core.config import Settings
from backend.app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.app.db.models import User
from backend.app.db.models.user import UserRole
from backend.app.repositories.user import UserRepository
from backend.app.services.auth_service import ensure_first_admin
from backend.tests.conftest import TEST_JWT_SECRET, ClientFactory, make_test_settings

PASSWORD = "s3cret-pass"


def _register(client: TestClient, username: str = "ivan", **extra: str) -> dict:
    response = client.post(
        "/api/v1/auth/register", json={"username": username, "password": PASSWORD, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(client: TestClient, username: str = "ivan", password: str = PASSWORD):
    return client.post("/api/v1/auth/login", data={"username": username, "password": password})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user(session: Session, username: str, role: UserRole, *, active: bool = True) -> User:
    user = UserRepository(session).add(
        User(
            username=username,
            password_hash=hash_password(PASSWORD),
            role=role.value,
            is_active=active,
        )
    )
    session.commit()
    return user


# --- security ---


def test_password_hashing() -> None:
    hashed = hash_password(PASSWORD)
    assert hashed != PASSWORD
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("wrong-password", hashed)
    assert not verify_password(PASSWORD, None)


def test_password_over_72_bytes_rejected() -> None:
    long_password = "я" * 37  # 74 байта в UTF-8
    with pytest.raises(ValueError):
        hash_password(long_password)
    assert not verify_password(long_password, hash_password("я" * 36))


def test_token_roundtrip(test_settings: Settings) -> None:
    token = create_access_token(42, "manager", settings=test_settings)
    payload = decode_token(token, settings=test_settings)
    assert payload.user_id == 42
    assert payload.role == "manager"


def test_token_requires_exp(test_settings: Settings) -> None:
    token = jwt.encode({"sub": "1"}, TEST_JWT_SECRET, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_token(token, settings=test_settings)


# --- регистрация ---


def test_register_returns_driver_without_password_hash(client: TestClient) -> None:
    body = _register(client, email="Ivan@Example.com", full_name="Иван")
    assert body["username"] == "ivan"
    assert body["email"] == "ivan@example.com"
    assert body["role"] == "driver"
    assert body["is_active"] is True
    assert "password" not in body and "password_hash" not in body


def test_register_ignores_role_field(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "hacker", "password": PASSWORD, "role": "admin"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "driver"


def test_register_duplicate_username_conflict(client: TestClient) -> None:
    _register(client)
    response = client.post("/api/v1/auth/register", json={"username": "ivan", "password": PASSWORD})
    assert response.status_code == 409


def test_register_duplicate_email_conflict(client: TestClient) -> None:
    _register(client, "ivan", email="a@b.ru")
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "petr", "password": PASSWORD, "email": "a@b.ru"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ivan", "password": "short"},
        {"username": "ivan", "password": "я" * 40},
        {"username": "ivan", "password": PASSWORD, "email": "not-an-email"},
        {"username": "a b", "password": PASSWORD},
    ],
)
def test_register_validation(client: TestClient, payload: dict) -> None:
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422


def test_register_disabled(make_client: ClientFactory) -> None:
    client = make_client(make_test_settings(ALLOW_PUBLIC_REGISTRATION=False))
    response = client.post("/api/v1/auth/register", json={"username": "ivan", "password": PASSWORD})
    assert response.status_code == 403


# --- вход и /me ---


def test_login_and_me(client: TestClient) -> None:
    _register(client)
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 60 * 60

    me = client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "ivan"
    assert "password_hash" not in me.json()


def test_wrong_password_and_unknown_user_same_401(client: TestClient) -> None:
    _register(client)
    wrong = _login(client, password="wrong-password")
    unknown = _login(client, username="nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_without_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_token(client: TestClient, test_settings: Settings) -> None:
    user_id = _register(client)["id"]
    token = create_access_token(
        user_id, "driver", expires_delta=timedelta(seconds=-10), settings=test_settings
    )
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 401


def test_tampered_token(client: TestClient, test_settings: Settings) -> None:
    user_id = _register(client)["id"]
    token = create_access_token(user_id, "driver", settings=test_settings)
    header, payload, signature = token.split(".")
    # Подменяем роль в payload, сохраняя исходную подпись
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["role"] = "admin"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    tampered = f"{header}.{forged}.{signature}"
    assert client.get("/api/v1/auth/me", headers=_auth(tampered)).status_code == 401

    foreign = jwt.encode(
        {"sub": str(user_id), "role": "admin", "exp": 9999999999},
        "another-secret-key-of-sufficient-length-0123456789",
        algorithm="HS256",
    )
    assert client.get("/api/v1/auth/me", headers=_auth(foreign)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=_auth("garbage")).status_code == 401


def test_token_of_deleted_user(client: TestClient, test_settings: Settings) -> None:
    token = create_access_token(999, "admin", settings=test_settings)
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 401


def test_inactive_user(client: TestClient, db_session: Session) -> None:
    _register(client)
    token = _login(client).json()["access_token"]

    user = UserRepository(db_session).get_by_username("ivan")
    assert user is not None
    user.is_active = False
    db_session.commit()

    # Блокировка действует сразу, даже для уже выданного токена
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 403
    assert _login(client).status_code == 403


# --- RBAC ---


def _add_protected_route(app: FastAPI) -> None:
    """Тестовый маршрут, доступный только admin и manager."""
    router = APIRouter()

    @router.get("/test-only/managers")
    def managers_only(
        user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
    ) -> dict[str, str]:
        return {"role": user.role}

    app.include_router(router)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.ADMIN, 200),
        (UserRole.MANAGER, 200),
        (UserRole.EXECUTIVE, 403),
        (UserRole.DRIVER, 403),
    ],
)
def test_require_roles(
    make_client: ClientFactory, db_session: Session, role: UserRole, expected: int
) -> None:
    client = make_client(setup=_add_protected_route)
    _create_user(db_session, f"user_{role.value}", role)
    token = _login(client, f"user_{role.value}").json()["access_token"]
    response = client.get("/test-only/managers", headers=_auth(token))
    assert response.status_code == expected


def test_require_roles_without_token(make_client: ClientFactory) -> None:
    client = make_client(setup=_add_protected_route)
    assert client.get("/test-only/managers").status_code == 401


def test_role_change_applies_immediately(make_client: ClientFactory, db_session: Session) -> None:
    client = make_client(setup=_add_protected_route)
    user = _create_user(db_session, "boss", UserRole.MANAGER)
    token = _login(client, "boss").json()["access_token"]
    assert client.get("/test-only/managers", headers=_auth(token)).status_code == 200

    user.role = UserRole.DRIVER.value
    db_session.commit()
    assert client.get("/test-only/managers", headers=_auth(token)).status_code == 403


def test_openapi_token_url_matches_login(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    flows = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]
    token_url = flows["password"]["tokenUrl"]
    assert token_url == "/api/v1/auth/login"
    assert token_url in schema["paths"]


# --- бутстрап администратора ---


def test_first_admin_bootstrap_idempotent(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    settings = make_test_settings(
        FIRST_ADMIN_USERNAME="root", FIRST_ADMIN_PASSWORD="admin-password-1"
    )
    with caplog.at_level(logging.DEBUG):
        admin = ensure_first_admin(db_session, settings)
        again = ensure_first_admin(db_session, settings)

    assert admin is not None and admin.role == "admin"
    assert again is None
    repo = UserRepository(db_session)
    assert repo.count_by_role("admin") == 1
    assert verify_password("admin-password-1", admin.password_hash)
    assert "admin-password-1" not in caplog.text


def test_first_admin_not_configured(db_session: Session) -> None:
    assert ensure_first_admin(db_session, make_test_settings()) is None
    assert UserRepository(db_session).count_by_role("admin") == 0


def test_first_admin_skipped_when_admin_exists(db_session: Session) -> None:
    _create_user(db_session, "existing_admin", UserRole.ADMIN)
    settings = make_test_settings(FIRST_ADMIN_USERNAME="root", FIRST_ADMIN_PASSWORD="pwd-123456")
    assert ensure_first_admin(db_session, settings) is None
    assert UserRepository(db_session).get_by_username("root") is None


def test_first_admin_can_login(make_client: ClientFactory, db_session: Session) -> None:
    settings = make_test_settings(FIRST_ADMIN_USERNAME="root", FIRST_ADMIN_PASSWORD="pwd-123456")
    ensure_first_admin(db_session, settings)
    client = make_client(settings)
    token = _login(client, "root", "pwd-123456").json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=_auth(token)).json()["role"] == "admin"
