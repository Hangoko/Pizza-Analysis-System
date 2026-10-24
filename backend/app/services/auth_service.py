"""
Сервис аутентификации: регистрация, вход, бутстрап первого администратора.

Сервис не знает про HTTP: ошибки — доменные исключения, их переводит в коды слой API.
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.core.security import hash_password, verify_password
from backend.app.db.models import User
from backend.app.db.models.user import UserRole
from backend.app.repositories.user import UserRepository
from backend.app.schemas.user import UserRegister

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Базовая ошибка аутентификации."""


class RegistrationDisabledError(AuthError):
    pass


class UserAlreadyExistsError(AuthError):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class InvalidCredentialsError(AuthError):
    pass


class InactiveUserError(AuthError):
    pass


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)

    def register(self, data: UserRegister) -> User:
        """Саморегистрация. Роль всегда `driver` — повысить её может только администратор."""
        if not self.settings.ALLOW_PUBLIC_REGISTRATION:
            raise RegistrationDisabledError
        if self.users.get_by_username(data.username) is not None:
            raise UserAlreadyExistsError("username")
        if data.email is not None and self.users.get_by_email(data.email) is not None:
            raise UserAlreadyExistsError("email")

        user = User(
            username=data.username,
            email=data.email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=UserRole.DRIVER.value,
            is_active=True,
        )
        try:
            self.users.add(user)
            self.session.commit()
        except IntegrityError as exc:
            # Гонка двух одновременных регистраций с одинаковыми данными
            self.session.rollback()
            raise UserAlreadyExistsError("username") from exc
        return user

    def authenticate(self, username: str, password: str) -> User:
        """Проверка логина/пароля. Неизвестный пользователь и неверный пароль неразличимы."""
        user = self.users.get_by_username(username)
        password_ok = verify_password(password, user.password_hash if user else None)
        if user is None or not password_ok:
            raise InvalidCredentialsError
        if not user.is_active:
            raise InactiveUserError
        return user


def ensure_first_admin(session: Session, settings: Settings) -> User | None:
    """
    Создаёт первого администратора из `FIRST_ADMIN_*`, если админов в БД ещё нет.

    Идемпотентно: при наличии хотя бы одного админа ничего не делает.
    Возвращает созданного пользователя или None. Пароль в лог не пишется.
    """
    username = settings.FIRST_ADMIN_USERNAME
    password = settings.FIRST_ADMIN_PASSWORD
    if not username or not password:
        return None

    users = UserRepository(session)
    if users.count_by_role(UserRole.ADMIN.value) > 0:
        return None
    if users.get_by_username(username) is not None:
        logger.warning(
            "Пользователь %r уже существует и не является администратором — "
            "бутстрап администратора пропущен",
            username,
        )
        return None

    admin = users.add(
        User(
            username=username,
            email=settings.FIRST_ADMIN_EMAIL or None,
            full_name="Администратор",
            password_hash=hash_password(password),
            role=UserRole.ADMIN.value,
            is_active=True,
        )
    )
    session.commit()
    logger.info("Создан первый администратор %r", username)
    return admin
