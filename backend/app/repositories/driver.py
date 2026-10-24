"""Репозиторий водителей."""

from collections.abc import Sequence

from sqlalchemy import select

from backend.app.db.models import Driver
from backend.app.repositories.base import BaseRepository


class DriverRepository(BaseRepository[Driver]):
    model = Driver

    def get_by_full_name(self, full_name: str) -> Driver | None:
        return self.session.scalar(select(Driver).where(Driver.full_name == full_name))

    def get_by_user_id(self, user_id: int) -> Driver | None:
        return self.session.scalar(select(Driver).where(Driver.user_id == user_id))

    def list_by_branch(self, branch_id: int, *, only_active: bool = True) -> Sequence[Driver]:
        stmt = select(Driver).where(Driver.branch_id == branch_id)
        if only_active:
            stmt = stmt.where(Driver.is_active.is_(True))
        return self.session.scalars(stmt.order_by(Driver.id)).all()
