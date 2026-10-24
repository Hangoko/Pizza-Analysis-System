"""ORM-модели. Импорт пакета регистрирует все таблицы в `Base.metadata` (нужно Alembic)."""

from backend.app.db.models.branch import Branch
from backend.app.db.models.driver import Driver
from backend.app.db.models.order import Order, OrderStatus
from backend.app.db.models.report_template import ReportTemplate
from backend.app.db.models.user import User, UserRole

__all__ = [
    "Branch",
    "Driver",
    "Order",
    "OrderStatus",
    "ReportTemplate",
    "User",
    "UserRole",
]
