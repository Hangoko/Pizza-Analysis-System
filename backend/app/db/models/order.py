"""Заказы — основной источник данных для KPI, отчётов и ML."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, CreatedAtMixin, IdMixin, UTCDateTime

if TYPE_CHECKING:
    from backend.app.db.models.branch import Branch
    from backend.app.db.models.driver import Driver


class OrderStatus(StrEnum):
    PENDING = "Pending"
    IN_DELIVERY = "InDelivery"
    DELIVERED = "Delivered"
    CANCELED = "Canceled"


_STATUSES_SQL = ", ".join(f"'{status.value}'" for status in OrderStatus)


class Order(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES_SQL})", name="status"),
        CheckConstraint(
            "delivery_time_minutes IS NULL OR delivery_time_minutes >= 0",
            name="delivery_time_non_negative",
        ),
        Index("ix_orders_order_time", "order_time"),
        Index("ix_orders_branch_id_order_time", "branch_id", "order_time"),
        Index("ix_orders_status", "status"),
    )

    # Внешний идентификатор заказа, например ORD-0001
    external_id: Mapped[str] = mapped_column(String(32), unique=True)
    client_lat: Mapped[float]
    client_lon: Mapped[float]
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="RESTRICT"))
    driver_id: Mapped[int | None] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL"), index=True
    )
    order_time: Mapped[datetime] = mapped_column(UTCDateTime())
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    delivery_time_minutes: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PENDING.value)

    branch: Mapped["Branch"] = relationship(back_populates="orders")
    driver: Mapped["Driver | None"] = relationship(back_populates="orders")

    def __repr__(self) -> str:
        return f"Order(id={self.id!r}, external_id={self.external_id!r}, status={self.status!r})"
