"""Репозиторий пользователей."""

from sqlalchemy import func, select

from backend.app.db.models import User
from backend.app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def count_by_role(self, role: str) -> int:
        return (
            self.session.scalar(select(func.count()).select_from(User).where(User.role == role))
            or 0
        )
