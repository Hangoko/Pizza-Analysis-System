"""Тесты /admin/users: CRUD, фильтры, защита администратора, привязка водителя."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.db.models import Driver, User
from backend.app.db.models.user import UserRole
from backend.app.schemas.user import UserUpdate
from backend.app.services.user_admin_service import AdminProtectionError, UserAdminService
from backend.tests.conftest import make_test_settings

URL = "/api/v1/admin/users"


def _user(session: Session, username: str, role: UserRole, **kwargs) -> User:
    user = User(username=username, password_hash=hash_password("password1"), role=role, **kwargs)
    session.add(user)
    session.commit()
    return user


def _auth(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role, settings=make_test_settings())
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(db_session: Session) -> User:
    return _user(db_session, "root", UserRole.ADMIN, full_name="Главный Админ")


@pytest.fixture
def headers(admin: User) -> dict[str, str]:
    return _auth(admin)


def test_non_admin_forbidden(client: TestClient, db_session: Session) -> None:
    for role in (UserRole.MANAGER, UserRole.EXECUTIVE, UserRole.DRIVER):
        user = _user(db_session, f"u_{role.value}", role)
        assert client.get(URL, headers=_auth(user)).status_code == 403
        assert client.post(URL, json={}, headers=_auth(user)).status_code == 403
    assert client.get(URL).status_code == 401


def test_create_and_login(client: TestClient, headers) -> None:
    body = {
        "username": "manager1",
        "password": "secret123",
        "email": "Manager@Example.com",
        "full_name": "Иван Петров",
        "role": "manager",
    }
    response = client.post(URL, json=body, headers=headers)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["role"] == "manager" and created["is_active"] is True
    assert created["email"] == "manager@example.com"
    assert "password_hash" not in created and created["driver_id"] is None

    login = client.post(
        "/api/v1/auth/login", data={"username": "manager1", "password": "secret123"}
    )
    assert login.status_code == 200

    assert client.post(URL, json=body, headers=headers).status_code == 409
    other = {**body, "username": "manager2"}
    assert client.post(URL, json=other, headers=headers).status_code == 409  # email занят
    bad = {**body, "username": "x", "role": "boss"}
    assert client.post(URL, json=bad, headers=headers).status_code == 422


def test_list_filters_and_pagination(client: TestClient, db_session: Session, headers) -> None:
    for i in range(5):
        _user(db_session, f"driver{i}", UserRole.DRIVER, full_name=f"Водитель {i}")
    _user(db_session, "old_manager", UserRole.MANAGER, is_active=False, full_name="Сидоров")

    body = client.get(URL, params={"limit": 2, "offset": 1}, headers=headers).json()
    assert body["total"] == 7 and body["limit"] == 2 and body["offset"] == 1
    assert [u["username"] for u in body["items"]] == ["driver0", "driver1"]

    body = client.get(URL, params={"role": "driver", "limit": 100}, headers=headers).json()
    assert body["total"] == 5

    body = client.get(URL, params={"is_active": False}, headers=headers).json()
    assert [u["username"] for u in body["items"]] == ["old_manager"]

    body = client.get(URL, params={"search": "Сидор"}, headers=headers).json()
    assert [u["username"] for u in body["items"]] == ["old_manager"]
    body = client.get(URL, params={"search": "DRIVER3"}, headers=headers).json()
    assert [u["username"] for u in body["items"]] == ["driver3"]
    # % и _ ищутся буквально
    assert client.get(URL, params={"search": "%"}, headers=headers).json()["total"] == 0
    body = client.get(URL, params={"search": "_"}, headers=headers).json()
    assert [u["username"] for u in body["items"]] == ["old_manager"]

    assert client.get(URL, params={"limit": 0}, headers=headers).status_code == 422


def test_get_patch_and_password_reset(client: TestClient, db_session: Session, headers) -> None:
    user = _user(db_session, "worker", UserRole.DRIVER)
    assert client.get(f"{URL}/{user.id}", headers=headers).json()["username"] == "worker"
    assert client.get(f"{URL}/99999", headers=headers).status_code == 404

    patch = {"role": "manager", "full_name": "Новое ФИО", "email": "w@example.com"}
    response = client.patch(f"{URL}/{user.id}", json=patch, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "manager" and response.json()["full_name"] == "Новое ФИО"

    response = client.patch(f"{URL}/{user.id}", json={"password": "brand-new-1"}, headers=headers)
    assert response.status_code == 200
    db_session.expire_all()
    assert verify_password("brand-new-1", db_session.get(User, user.id).password_hash)

    assert (
        client.patch(f"{URL}/{user.id}", json={"password": "short"}, headers=headers).status_code
        == 422
    )
    assert (
        client.patch(f"{URL}/{user.id}", json={"username": "x"}, headers=headers).status_code == 422
    )
    assert client.patch(f"{URL}/99999", json={}, headers=headers).status_code == 404


def test_deactivate_blocks_access(client: TestClient, db_session: Session, headers) -> None:
    user = _user(db_session, "leaver", UserRole.MANAGER)
    user_headers = _auth(user)
    assert client.get("/api/v1/auth/me", headers=user_headers).status_code == 200

    response = client.delete(f"{URL}/{user.id}", headers=headers)
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=user_headers).status_code == 403
    # Мягкое удаление: запись осталась, можно вернуть
    response = client.patch(f"{URL}/{user.id}", json={"is_active": True}, headers=headers)
    assert response.json()["is_active"] is True


def test_admin_cannot_demote_or_deactivate_self(client: TestClient, admin, headers) -> None:
    for request in (
        lambda: client.delete(f"{URL}/{admin.id}", headers=headers),
        lambda: client.patch(f"{URL}/{admin.id}", json={"role": "manager"}, headers=headers),
        lambda: client.patch(f"{URL}/{admin.id}", json={"is_active": False}, headers=headers),
    ):
        response = request()
        assert response.status_code == 409
        assert "собственную" in response.json()["detail"]
    # Остальные поля себе менять можно
    response = client.patch(f"{URL}/{admin.id}", json={"full_name": "Я"}, headers=headers)
    assert response.status_code == 200


def test_admin_can_demote_another_admin(client: TestClient, db_session: Session, headers) -> None:
    other = _user(db_session, "admin2", UserRole.ADMIN)
    response = client.patch(f"{URL}/{other.id}", json={"role": "executive"}, headers=headers)
    assert response.status_code == 200 and response.json()["role"] == "executive"
    # Бывший админ сразу теряет доступ к админке
    assert client.get(URL, headers=_auth(other)).status_code == 403


def test_last_active_admin_protected(db_session: Session, admin: User) -> None:
    """
    Через HTTP действующий админ всегда сам активный админ, поэтому «последнего» защищает
    проверка «себя»; на уровне сервиса (например, при гонке запросов) — отдельная проверка.
    """
    manager = _user(db_session, "boss", UserRole.MANAGER)
    service = UserAdminService(db_session)
    with pytest.raises(AdminProtectionError, match="последнего"):
        service.deactivate(admin.id, actor=manager)
    with pytest.raises(AdminProtectionError, match="последнего"):
        service.update(admin.id, UserUpdate(role=UserRole.DRIVER), actor=manager)

    # Неактивный второй админ не считается
    _user(db_session, "sleeping", UserRole.ADMIN, is_active=False)
    with pytest.raises(AdminProtectionError):
        service.deactivate(admin.id, actor=manager)

    _user(db_session, "spare", UserRole.ADMIN)
    assert service.deactivate(admin.id, actor=manager).is_active is False


def test_driver_link(client: TestClient, db_session: Session, headers) -> None:
    free = Driver(full_name="Свободный водитель")
    taken_owner = _user(db_session, "taken_owner", UserRole.DRIVER)
    taken = Driver(full_name="Занятый водитель", user_id=taken_owner.id)
    db_session.add_all([free, taken])
    db_session.commit()

    body = {"username": "drv", "password": "password1", "role": "driver", "driver_id": free.id}
    response = client.post(URL, json=body, headers=headers)
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    assert response.json()["driver_id"] == free.id

    response = client.patch(f"{URL}/{user_id}", json={"driver_id": taken.id}, headers=headers)
    assert response.status_code == 409
    response = client.patch(f"{URL}/{user_id}", json={"driver_id": 99999}, headers=headers)
    assert response.status_code == 404
    bad = {**body, "username": "mgr", "role": "manager"}
    assert client.post(URL, json=bad, headers=headers).status_code == 422

    # Смена роли с driver отвязывает запись водителя
    response = client.patch(f"{URL}/{user_id}", json={"role": "manager"}, headers=headers)
    assert response.json()["driver_id"] is None
    db_session.expire_all()
    assert db_session.get(Driver, free.id).user_id is None

    response = client.patch(
        f"{URL}/{user_id}", json={"role": "driver", "driver_id": free.id}, headers=headers
    )
    assert response.json()["driver_id"] == free.id
    response = client.patch(f"{URL}/{user_id}", json={"driver_id": None}, headers=headers)
    assert response.json()["driver_id"] is None
