"""Репозиторий филиалов."""

from collections.abc import Sequence

from sqlalchemy import select

from backend.app.db.models import Branch
from backend.app.repositories.base import BaseRepository


class BranchRepository(BaseRepository[Branch]):
    model = Branch

    def get_by_name(self, name: str) -> Branch | None:
        return self.session.scalar(select(Branch).where(Branch.name == name))

    def list_active(self) -> Sequence[Branch]:
        stmt = select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)
        return self.session.scalars(stmt).all()
