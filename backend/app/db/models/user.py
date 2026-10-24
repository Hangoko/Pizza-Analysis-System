"""Пользователи системы и их роли."""

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAtMixin, IdMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from backend.app.db.models.driver import Driver
    from backend.app.db.models.report_template import ReportTemplate


class UserRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    EXECUTIVE = "executive"  # руководство
    DRIVER = "driver"


# Роль хранится строкой + CHECK: переносимо между PostgreSQL и SQLite
_ROLES_SQL = ", ".join(f"'{role.value}'" for role in UserRole)


class User(IdMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role IN ({_ROLES_SQL})", name="role"),)

    username: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.MANAGER.value)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    driver: Mapped["Driver | None"] = relationship(back_populates="user")
    report_templates: Mapped[list["ReportTemplate"]] = relationship(back_populates="owner")

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, username={self.username!r}, role={self.role!r})"
