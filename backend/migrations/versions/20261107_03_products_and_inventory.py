"""Create products and inventory tables.

Revision ID: 20261107_03
Revises: 20261107_02
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261107_03"
down_revision: str | None = "20261107_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create products and inventory tables according to ERD V1.0."""
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "sku",
            sa.String(length=64, collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("sale_price_vnd", sa.BigInteger(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE') AND sale_price_vnd > 0",
            name="ck_products_status_and_price",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_products_category_id_categories",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_index(
        "ix_products_category_id_status_id",
        "products",
        ["category_id", "status", "id"],
        unique=False,
    )
    op.create_index(
        "ix_products_name_id",
        "products",
        ["name", "id"],
        unique=False,
    )
    op.create_index(
        "ix_products_status_id",
        "products",
        ["status", "id"],
        unique=False,
    )
    op.create_table(
        "inventory",
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "quantity",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "stock_version",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("first_stocked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "quantity >= 0 AND stock_version >= 0 "
            "AND (quantity = 0 OR first_stocked_at IS NOT NULL)",
            name="ck_inventory_qty_version_first_stocked",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_inventory_product_id_products",
        ),
        sa.PrimaryKeyConstraint("product_id", name="pk_inventory"),
    )
    op.create_index(
        "ix_inventory_quantity_product_id",
        "inventory",
        ["quantity", "product_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove inventory and products tables in reverse dependency order."""
    op.drop_index("ix_inventory_quantity_product_id", table_name="inventory")
    op.drop_table("inventory")
    op.drop_index("ix_products_status_id", table_name="products")
    op.drop_index("ix_products_name_id", table_name="products")
    op.drop_index("ix_products_category_id_status_id", table_name="products")
    op.drop_table("products")

