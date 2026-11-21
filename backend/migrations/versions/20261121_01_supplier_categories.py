"""Add optional supplier_categories link table.

Revision ID: 20261121_01
Revises: 20261119_01
Create Date: 2026-11-21

Purely additive: creates a new link table and touches no existing table or
row, so it is safe to apply to a populated database and to roll back.
Downgrade drops only supplier_categories (supplier/category rows are kept).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_01"
down_revision: str | None = "20261119_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create supplier_categories (supplier <-> category, many-to-many)."""
    op.create_table(
        "supplier_categories",
        sa.Column("supplier_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("category_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_supplier_categories_supplier_id_suppliers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_supplier_categories_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "supplier_id", "category_id", name="pk_supplier_categories"
        ),
        # Declared inline so MySQL uses it to back the category_id foreign key
        # (no duplicate implicit index) and it is dropped with the table.
        sa.Index("ix_supplier_categories_category_id", "category_id"),
    )


def downgrade() -> None:
    """Drop supplier_categories only; suppliers and categories are untouched.

    The category_id index backs a foreign key on MySQL and cannot be dropped on
    its own, so it is removed together with the table.
    """
    op.drop_table("supplier_categories")
