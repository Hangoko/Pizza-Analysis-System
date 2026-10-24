"""
Безопасность: хеширование паролей (bcrypt) и JWT-токены доступа (PyJWT).

Токен содержит `sub` (id пользователя строкой), `role`, `iat` и `exp`.
Роль в токене — справочная: права всегда проверяются по пользователю из БД.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from backend.app.core.config import Settings, get_settings

# bcrypt учитывает только первые 72 байта пароля; более длинные пароли отклоняем
BCRYPT_MAX_PASSWORD_BYTES = 72

# Хеш заведомо неверного пароля: проверяется, когда пользователь не найден,
# чтобы время ответа «нет такого пользователя» и «неверный пароль» было сопоставимым
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt()).decode()


class InvalidTokenError(Exception):
    """Токен повреждён, подписан другим ключом, просрочен или без нужных полей."""


@dataclass(frozen=True, slots=True)
class TokenPayload:
    user_id: int
    role: str | None
    expires_at: datetime


def password_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES


def hash_password(password: str) -> str:
    if password_too_long(password):
        raise ValueError(f"Пароль длиннее {BCRYPT_MAX_PASSWORD_BYTES} байт")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Проверка пароля. При `password_hash=None` сверяет с фиктивным хешем и даёт False."""
    if password_too_long(password):
        return False
    target = password_hash or _DUMMY_PASSWORD_HASH
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), target.encode("ascii"))
    except ValueError:
        # Повреждённый хеш в БД
        return False
    return ok and password_hash is not None


def create_access_token(
    user_id: int,
    role: str,
    *,
    expires_delta: timedelta | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    claims = {"sub": str(user_id), "role": role, "iat": now, "exp": now + expires_delta}
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, *, settings: Settings | None = None) -> TokenPayload:
    settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError(str(exc)) from exc
    return TokenPayload(
        user_id=user_id,
        role=claims.get("role"),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
    )
