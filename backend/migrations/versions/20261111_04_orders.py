"""Create orders and immutable order item snapshots.

Revision ID: 20261111_04
Revises: 20261111_03
Create Date: 2026-11-12
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
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "status",
            sa.String(9),
            server_default=sa.text("'COMPLETED'"),
            nullable=False,
        ),
        sa.Column("total_vnd", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("sold_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("cancelled_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.CheckConstraint("total_vnd > 0", name="ck_orders_total_positive"),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND cancelled_by IS NULL AND cancelled_at IS NULL "
            "AND cancel_reason IS NULL) OR (status = 'CANCELLED' "
            "AND cancelled_by IS NOT NULL AND cancelled_at IS NOT NULL "
            "AND cancelled_at >= sold_at AND cancel_reason IS NOT NULL "
            "AND CHAR_LENGTH(TRIM(cancel_reason)) > 0)",
            name="ck_orders_status_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"], ["users.id"], name="fk_orders_cancelled_by_users"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_orders_created_by_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
    )
    op.create_index("ix_orders_sold_at_id", "orders", ["sold_at", "id"])
    op.create_index(
        "ix_orders_status_sold_at_id", "orders", ["status", "sold_at", "id"]
    )
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_snapshot", sa.String(64), nullable=False),
        sa.Column("product_name_snapshot", sa.String(160), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_vnd", sa.BigInteger(), nullable=False),
        sa.Column("line_total_vnd", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "quantity > 0 AND unit_price_vnd > 0 "
            "AND line_total_vnd = CAST(quantity AS DECIMAL(30,0)) * unit_price_vnd",
            name="ck_order_items_qty_price_total",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name="fk_order_items_order_id_orders"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name="fk_order_items_product_id_products"
        ),
        sa.PrimaryKeyConstraint("order_id", "product_id", name="pk_order_items"),
    )


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_index("ix_orders_status_sold_at_id", table_name="orders")
    op.drop_index("ix_orders_sold_at_id", table_name="orders")
    op.drop_table("orders")
