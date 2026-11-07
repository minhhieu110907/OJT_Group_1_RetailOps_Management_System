"""Create categories and suppliers tables.

Revision ID: 20261107_02
Revises: 20261106_01
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261107_02"
down_revision: str | None = "20261106_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create categories and suppliers tables according to ERD V1.0."""
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name="ck_categories_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name="ck_suppliers_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
    )


def downgrade() -> None:
    """Drop suppliers and categories tables."""
    op.drop_table("suppliers")
    op.drop_table("categories")
