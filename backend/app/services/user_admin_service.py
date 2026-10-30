"""
Администрирование пользователей: создание сотрудников, изменение роли/ФИО/email/пароля,
мягкая деактивация, привязка учётной записи водителя к записи `drivers`.

Защита: администратор не может деактивировать или понизить себя; нельзя оставить систему
без активного администратора (строки активных админов блокируются на время проверки).
"""

from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.security import hash_password
from backend.app.db.models import Driver, User
from backend.app.db.models.user import UserRole
from backend.app.repositories.driver import DriverRepository
from backend.app.repositories.user import UserRepository
from backend.app.schemas.user import UserAdminRead, UserCreate, UserUpdate
from backend.app.services.auth_service import UserAlreadyExistsError


class UserAdminError(Exception):
    """Базовая ошибка администрирования пользователей (сообщение — для клиента)."""


class UserNotFoundError(UserAdminError):
    pass


class AdminProtectionError(UserAdminError):
    """Операция лишила бы систему администратора или админа — собственных прав."""


class DriverLinkError(UserAdminError):
    """Некорректная привязка к записи водителя."""

    def __init__(self, message: str, *, kind: str = "conflict") -> None:
        super().__init__(message)
        # "not_found" | "invalid" | "conflict"
        self.kind = kind


def to_admin_read(user: User) -> UserAdminRead:
    read = UserAdminRead.model_validate(user)
    read.driver_id = user.driver.id if user.driver is not None else None
    return read


class UserAdminService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.drivers = DriverRepository(session)

    # --- чтение ---

    def list(
        self,
        *,
        role: UserRole | None,
        is_active: bool | None,
        query: str | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[User], int]:
        return self.users.search(
            role=role.value if role else None,
            is_active=is_active,
            query=query.strip() if query else None,
            offset=offset,
            limit=limit,
        )

    def get(self, user_id: int) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise UserNotFoundError("Пользователь не найден")
        return user

    # --- изменение ---

    def create(self, data: UserCreate) -> User:
        if self.users.get_by_username(data.username) is not None:
            raise UserAlreadyExistsError("username")
        if data.email is not None and self.users.get_by_email(data.email) is not None:
            raise UserAlreadyExistsError("email")
        user = User(
            username=data.username,
            email=data.email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=data.role.value,
            is_active=data.is_active,
        )
        self.users.add(user)
        if data.driver_id is not None:
            self._link_driver(user, data.driver_id)
        self._commit()
        return user

    def update(self, user_id: int, data: UserUpdate, *, actor: User) -> User:
        user = self.get(user_id)
        changes = data.model_dump(exclude_unset=True)
        # null у не-nullable полей означает «не менять»
        for field in ("role", "is_active", "password"):
            if field in changes and changes[field] is None:
                del changes[field]

        new_role = changes.get("role", UserRole(user.role))
        new_active = changes.get("is_active", user.is_active)
        self._check_admin_protection(user, actor, new_role=new_role, new_active=new_active)

        if "email" in changes and changes["email"] is not None:
            other = self.users.get_by_email(changes["email"])
            if other is not None and other.id != user.id:
                raise UserAlreadyExistsError("email")

        if "role" in changes:
            user.role = new_role.value
        if "is_active" in changes:
            user.is_active = new_active
        if "full_name" in changes:
            user.full_name = changes["full_name"]
        if "email" in changes:
            user.email = changes["email"]
        if "password" in changes:
            user.password_hash = hash_password(changes["password"])

        if "driver_id" in changes:
            if changes["driver_id"] is None:
                self._unlink_driver(user)
            else:
                self._link_driver(user, changes["driver_id"])
        elif new_role != UserRole.DRIVER:
            # Сменили роль с driver — запись водителя отвязывается
            self._unlink_driver(user)
        self._commit()
        return user

    def deactivate(self, user_id: int, *, actor: User) -> User:
        user = self.get(user_id)
        self._check_admin_protection(user, actor, new_role=UserRole(user.role), new_active=False)
        user.is_active = False
        self._commit()
        return user

    # --- внутреннее ---

    def _check_admin_protection(
        self, user: User, actor: User, *, new_role: UserRole, new_active: bool
    ) -> None:
        loses_admin = (
            user.role == UserRole.ADMIN.value
            and user.is_active
            and (new_role != UserRole.ADMIN or not new_active)
        )
        if not loses_admin:
            return
        if user.id == actor.id:
            raise AdminProtectionError(
                "Нельзя деактивировать или понизить собственную учётную запись"
            )
        others = [admin for admin in self.users.lock_active_admins() if admin.id != user.id]
        if not others:
            raise AdminProtectionError(
                "Нельзя деактивировать или понизить последнего администратора"
            )

    def _link_driver(self, user: User, driver_id: int) -> None:
        if user.role != UserRole.DRIVER.value:
            raise DriverLinkError(
                "Привязать запись водителя можно только к роли driver", kind="invalid"
            )
        driver = self.drivers.get(driver_id)
        if driver is None:
            raise DriverLinkError("Водитель не найден", kind="not_found")
        if driver.user_id is not None and driver.user_id != user.id:
            raise DriverLinkError("Водитель уже привязан к другой учётной записи")
        current: Driver | None = user.driver
        if current is not None and current.id != driver.id:
            current.user = None
        driver.user = user

    def _unlink_driver(self, user: User) -> None:
        if user.driver is not None:
            user.driver.user = None

    def _commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            # Гонка параллельных запросов с одинаковым логином/email
            self.session.rollback()
            raise UserAlreadyExistsError("username") from exc
