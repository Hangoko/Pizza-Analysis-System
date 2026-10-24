"""Филиалы пиццерии."""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAtMixin, IdMixin

if TYPE_CHECKING:
    from backend.app.db.models.driver import Driver
    from backend.app.db.models.order import Order


class Branch(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (CheckConstraint("current_queue >= 0", name="current_queue_non_negative"),)

    name: Mapped[str] = mapped_column(String(255), unique=True)
    lat: Mapped[float]
    lon: Mapped[float]
    # Текущая очередь заказов — учитывается в рекомендациях водителям
    current_queue: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    drivers: Mapped[list["Driver"]] = relationship(back_populates="branch")
    orders: Mapped[list["Order"]] = relationship(back_populates="branch")

    def __repr__(self) -> str:
        return f"Branch(id={self.id!r}, name={self.name!r})"
