"""Шаблоны отчётов: системные и пользовательские."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAtMixin, IdMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from backend.app.db.models.user import User


class ReportTemplate(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "report_templates"
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(default=False, server_default=false())
    # NULL — системный шаблон без владельца
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Конфигурация конструктора отчёта (метрики, группировки, фильтры).
    # Переносимый JSON (не JSONB), чтобы тесты работали на SQLite
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    owner: Mapped["User | None"] = relationship(back_populates="report_templates")

    def __repr__(self) -> str:
        return f"ReportTemplate(id={self.id!r}, name={self.name!r})"
