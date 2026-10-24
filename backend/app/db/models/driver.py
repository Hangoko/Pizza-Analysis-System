"""Водители (курьеры)."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAtMixin, IdMixin

if TYPE_CHECKING:
    from backend.app.db.models.branch import Branch
    from backend.app.db.models.order import Order
    from backend.app.db.models.user import User


class Driver(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "drivers"

    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), index=True
    )
    # Учётная запись водителя (роль driver) — не более одной на водителя
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    branch: Mapped["Branch | None"] = relationship(back_populates="drivers")
    user: Mapped["User | None"] = relationship(back_populates="driver")
    orders: Mapped[list["Order"]] = relationship(back_populates="driver")

    def __repr__(self) -> str:
        return f"Driver(id={self.id!r}, full_name={self.full_name!r})"
