"""Репозиторий шаблонов отчётов."""

from collections.abc import Sequence

from sqlalchemy import or_, select

from backend.app.db.models import ReportTemplate
from backend.app.repositories.base import BaseRepository


class ReportTemplateRepository(BaseRepository[ReportTemplate]):
    model = ReportTemplate

    def list_available(self, owner_id: int) -> Sequence[ReportTemplate]:
        """Системные шаблоны и личные шаблоны пользователя."""
        stmt = (
            select(ReportTemplate)
            .where(or_(ReportTemplate.is_system.is_(True), ReportTemplate.owner_id == owner_id))
            .order_by(ReportTemplate.is_system.desc(), ReportTemplate.name)
        )
        return self.session.scalars(stmt).all()

    def get_system_by_name(self, name: str) -> ReportTemplate | None:
        stmt = select(ReportTemplate).where(
            ReportTemplate.is_system.is_(True), ReportTemplate.name == name
        )
        return self.session.scalar(stmt)

    def list_all(self) -> Sequence[ReportTemplate]:
        """Все шаблоны (для администратора): сначала системные, затем по имени."""
        stmt = select(ReportTemplate).order_by(
            ReportTemplate.is_system.desc(), ReportTemplate.name, ReportTemplate.id
        )
        return self.session.scalars(stmt).all()

    def get_by_owner_and_name(self, owner_id: int, name: str) -> ReportTemplate | None:
        stmt = select(ReportTemplate).where(
            ReportTemplate.owner_id == owner_id, ReportTemplate.name == name
        )
        return self.session.scalar(stmt)
