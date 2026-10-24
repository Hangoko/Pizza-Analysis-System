"""Начальная схема: users, branches, drivers, orders, report_templates.

Revision ID: 0001
Revises:
Create Date: 2026-10-24 14:23:20.626167+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("current_queue", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "current_queue >= 0", name=op.f("ck_branches_current_queue_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branches")),
        sa.UniqueConstraint("name", name=op.f("uq_branches_name")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'manager', 'executive', 'driver')", name=op.f("ck_users_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_drivers_branch_id_branches"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_drivers_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drivers")),
        sa.UniqueConstraint("user_id", name=op.f("uq_drivers_user_id")),
    )
    op.create_index(op.f("ix_drivers_branch_id"), "drivers", ["branch_id"], unique=False)
    op.create_table(
        "report_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_report_templates_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_templates")),
        sa.UniqueConstraint("owner_id", "name", name=op.f("uq_report_templates_owner_id_name")),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=32), nullable=False),
        sa.Column("client_lat", sa.Double(), nullable=False),
        sa.Column("client_lon", sa.Double(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.Integer(), nullable=True),
        sa.Column("order_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_time_minutes", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('Pending', 'InDelivery', 'Delivered', 'Canceled')",
            name=op.f("ck_orders_status"),
        ),
        sa.CheckConstraint(
            "delivery_time_minutes IS NULL OR delivery_time_minutes >= 0",
            name=op.f("ck_orders_delivery_time_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            name=op.f("fk_orders_branch_id_branches"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"],
            ["drivers.id"],
            name=op.f("fk_orders_driver_id_drivers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("external_id", name=op.f("uq_orders_external_id")),
    )
    op.create_index(
        "ix_orders_branch_id_order_time", "orders", ["branch_id", "order_time"], unique=False
    )
    op.create_index(op.f("ix_orders_driver_id"), "orders", ["driver_id"], unique=False)
    op.create_index("ix_orders_order_time", "orders", ["order_time"], unique=False)
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_order_time", table_name="orders")
    op.drop_index(op.f("ix_orders_driver_id"), table_name="orders")
    op.drop_index("ix_orders_branch_id_order_time", table_name="orders")
    op.drop_table("orders")
    op.drop_table("report_templates")
    op.drop_index(op.f("ix_drivers_branch_id"), table_name="drivers")
    op.drop_table("drivers")
    op.drop_table("users")
    op.drop_table("branches")
