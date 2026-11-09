"""SQLAlchemy ORM models for Product and Inventory."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductStatus(StrEnum):
    """Supported lifecycle states for products."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


# Alias preserved for internal module compatibility
CatalogStatus = ProductStatus


class Product(Base):
    """Product master data with current selling price in integer VND."""

    __tablename__ = "products"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_products"),
        UniqueConstraint("sku", name="uq_products_sku"),
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE') AND sale_price_vnd > 0",
            name="ck_products_status_and_price",
        ),
        Index(
            "ix_products_category_id_status_id",
            "category_id",
            "status",
            "id",
        ),
        Index(
            "ix_products_status_id",
            "status",
            "id",
        ),
        Index(
            "ix_products_name_id",
            "name",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "categories.id",
            name="fk_products_category_id_categories",
        ),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(
        String(64, collation="ascii_bin"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=ProductStatus.ACTIVE.value,
        server_default=text("'ACTIVE'"),
    )
    sale_price_vnd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )

    inventory: Mapped[Inventory | None] = relationship(
        back_populates="product",
        uselist=False,
    )


class Inventory(Base):
    """Current inventory balance and optimistic version for a product."""

    __tablename__ = "inventory"
    __table_args__ = (
        PrimaryKeyConstraint("product_id", name="pk_inventory"),
        CheckConstraint(
            "quantity >= 0 AND stock_version >= 0 "
            "AND (quantity = 0 OR first_stocked_at IS NOT NULL)",
            name="ck_inventory_qty_version_first_stocked",
        ),
        Index(
            "ix_inventory_quantity_product_id",
            "quantity",
            "product_id",
        ),
    )

    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "products.id",
            name="fk_inventory_product_id_products",
        ),
        primary_key=True,
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    stock_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    first_stocked_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )

    product: Mapped[Product] = relationship(back_populates="inventory")
