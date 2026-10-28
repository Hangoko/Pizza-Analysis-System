"""Уникальность названий системных шаблонов отчётов (частичный индекс).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 12:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_report_templates_system_name",
        "report_templates",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_system"),
        sqlite_where=sa.text("is_system"),
    )


def downgrade() -> None:
    op.drop_index("uq_report_templates_system_name", table_name="report_templates")
