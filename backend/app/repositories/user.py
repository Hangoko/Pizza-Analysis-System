"""Репозиторий пользователей."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select

from backend.app.db.models import User
from backend.app.db.models.user import UserRole
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

    def search(
        self,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[User], int]:
        """Фильтр по роли/активности и подстроке логина или ФИО; возвращает (страница, всего)."""
        conditions = []
        if role is not None:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active.is_(is_active))
        if query:
            # ILIKE в PostgreSQL; символы % и _ ищутся буквально
            escaped = "".join("\\" + ch if ch in "\\%_" else ch for ch in query)
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    User.username.ilike(pattern, escape="\\"),
                    User.full_name.ilike(pattern, escape="\\"),
                )
            )
        total = self.session.scalar(select(func.count()).select_from(User).where(*conditions))
        stmt = select(User).where(*conditions).order_by(User.id).offset(offset).limit(limit)
        return self.session.scalars(stmt).all(), total or 0

    def lock_active_admins(self) -> Sequence[User]:
        """
        Активные администраторы с блокировкой строк (SELECT ... FOR UPDATE в PostgreSQL):
        два параллельных запроса не смогут одновременно убрать двух последних админов.
        """
        stmt = (
            select(User)
            .where(User.role == UserRole.ADMIN.value, User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        )
        return self.session.scalars(stmt).all()
