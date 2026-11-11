"""Create purchase receipts and purchase receipt items tables.

Revision ID: 20261111_02
Revises: 20261111_01
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261111_02"
down_revision: str | None = "20261111_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create purchase_receipts and purchase_receipt_items tables."""
    op.create_table(
        "purchase_receipts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "supplier_name_snapshot",
            sa.String(length=160),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=9),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column(
            "draft_version",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "total_vnd",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("closed_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("closed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "draft_version >= 1 AND total_vnd >= 0",
            name="ck_purchase_receipts_version_and_total",
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND closed_by IS NULL AND closed_at IS NULL) "
            "OR (status IN ('CONFIRMED','CANCELLED') "
            "AND closed_by IS NOT NULL "
            "AND closed_at IS NOT NULL "
            "AND supplier_name_snapshot IS NOT NULL)",
            name="ck_purchase_receipts_status_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by"],
            ["users.id"],
            name="fk_purchase_receipts_closed_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_purchase_receipts_created_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_purchase_receipts_supplier_id_suppliers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_receipts"),
    )
    op.create_index(
        "ix_purchase_receipts_created_at_id",
        "purchase_receipts",
        ["created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_receipts_status_created_at_id",
        "purchase_receipts",
        ["status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_receipts_supplier_id_created_at_id",
        "purchase_receipts",
        ["supplier_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "purchase_receipt_items",
        sa.Column("receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "sku_snapshot",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "product_name_snapshot",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost_vnd", sa.BigInteger(), nullable=False),
        sa.Column("line_total_vnd", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "quantity > 0 AND unit_cost_vnd >= 0 "
            "AND line_total_vnd = CAST(quantity AS DECIMAL(30,0)) * unit_cost_vnd",
            name="ck_purchase_receipt_items_qty_cost_line_total",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_purchase_receipt_items_product_id_products",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["purchase_receipts.id"],
            name="fk_purchase_receipt_items_receipt_id_purchase_receipts",
        ),
        sa.PrimaryKeyConstraint(
            "receipt_id", "product_id", name="pk_purchase_receipt_items"
        ),
    )


def downgrade() -> None:
    """Drop purchase_receipt_items and purchase_receipts tables."""
    op.drop_table("purchase_receipt_items")
    op.drop_index(
        "ix_purchase_receipts_supplier_id_created_at_id",
        table_name="purchase_receipts",
    )
    op.drop_index(
        "ix_purchase_receipts_status_created_at_id",
        table_name="purchase_receipts",
    )
    op.drop_index(
        "ix_purchase_receipts_created_at_id",
        table_name="purchase_receipts",
    )
    op.drop_table("purchase_receipts")
