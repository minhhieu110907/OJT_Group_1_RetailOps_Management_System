"""Create inventory_adjustments and stock_movements tables.

Revision ID: 20261111_04
Revises: 20261111_03
Create Date: 2026-11-11

Depends on ``purchase_receipt_items`` (20261111_02) for the composite FK
``stock_movements(receipt_id, product_id) -> purchase_receipt_items``. The
ERD reference to ``order_items(order_id, product_id)`` is deferred until the
``order_items`` table is created by the Checkout/Order task.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261111_04"
down_revision: str | None = "20261111_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create inventory_adjustments and stock_movements tables according to ERD V1.0."""
    op.create_table(
        "inventory_adjustments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("counted_quantity", sa.Integer(), nullable=False),
        sa.Column("version_before", sa.BigInteger(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "quantity_before >= 0 AND counted_quantity >= 0 "
            "AND version_before >= 0 AND CHAR_LENGTH(TRIM(reason)) > 0",
            name="ck_inventory_adjustments_nonnegative_and_reason",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_inventory_adjustments_actor_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["inventory.product_id"],
            name="fk_inventory_adjustments_product_id_inventory",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_adjustments"),
        sa.UniqueConstraint(
            "id",
            "product_id",
            name="uq_inventory_adjustments_id_product_id",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_inventory_adjustments_product_id_created_at_id",
        "inventory_adjustments",
        ["product_id", "created_at", "id"],
        unique=False,
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("receipt_id", sa.BigInteger(), nullable=True),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("adjustment_id", sa.BigInteger(), nullable=True),
        sa.Column("sku_snapshot", sa.String(length=64), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("stock_version_after", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "quantity_before >= 0 AND quantity_after >= 0 "
            "AND quantity_before <> quantity_after AND stock_version_after > 0",
            name="ck_stock_movements_quantities_and_version",
        ),
        sa.CheckConstraint(
            "(kind = 'PURCHASE_CONFIRM' AND receipt_id IS NOT NULL "
            "AND order_id IS NULL AND adjustment_id IS NULL "
            "AND quantity_after > quantity_before) "
            "OR (kind IN ('SALE','ORDER_CANCEL') AND order_id IS NOT NULL "
            "AND receipt_id IS NULL AND adjustment_id IS NULL "
            "AND ((kind = 'SALE' AND quantity_after < quantity_before) "
            "OR (kind = 'ORDER_CANCEL' AND quantity_after > quantity_before))) "
            "OR (kind = 'ADJUSTMENT' AND adjustment_id IS NOT NULL "
            "AND receipt_id IS NULL AND order_id IS NULL)",
            name="ck_stock_movements_kind_source_and_direction",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_stock_movements_actor_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["adjustment_id", "product_id"],
            ["inventory_adjustments.id", "inventory_adjustments.product_id"],
            name="fk_stock_movements_adjustment_product",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "product_id"],
            ["purchase_receipt_items.receipt_id", "purchase_receipt_items.product_id"],
            name="fk_stock_movements_receipt_item",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["inventory.product_id"],
            name="fk_stock_movements_product_id_inventory",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stock_movements"),
        sa.UniqueConstraint(
            "product_id",
            "stock_version_after",
            name="uq_stock_movements_product_version_after",
        ),
        sa.UniqueConstraint(
            "receipt_id",
            "product_id",
            name="uq_stock_movements_receipt_product",
        ),
        sa.UniqueConstraint(
            "order_id",
            "product_id",
            "kind",
            name="uq_stock_movements_order_product_kind",
        ),
        sa.UniqueConstraint(
            "adjustment_id",
            "product_id",
            name="uq_stock_movements_adjustment_product",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_stock_movements_product_id_occurred_at_id",
        "stock_movements",
        ["product_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_stock_movements_occurred_at_id",
        "stock_movements",
        ["occurred_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop stock_movements and inventory_adjustments tables in reverse order."""
    op.drop_index("ix_stock_movements_occurred_at_id", table_name="stock_movements")
    op.drop_index(
        "ix_stock_movements_product_id_occurred_at_id",
        table_name="stock_movements",
    )
    op.drop_table("stock_movements")
    op.drop_index(
        "ix_inventory_adjustments_product_id_created_at_id",
        table_name="inventory_adjustments",
    )
    op.drop_table("inventory_adjustments")
