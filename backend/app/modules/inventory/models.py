"""SQLAlchemy ORM models for Inventory adjustments and Stock movements."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.products.models import Inventory, Product, ProductStatus


class MovementKind(StrEnum):
    """Canonical stock movement kinds persisted in MySQL per ERD V1.0."""

    PURCHASE_CONFIRM = "PURCHASE_CONFIRM"
    SALE = "SALE"
    ORDER_CANCEL = "ORDER_CANCEL"
    ADJUSTMENT = "ADJUSTMENT"


class MovementType(StrEnum):
    """High-level movement type aliases for the unified InventoryService entry point."""

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    RETURN = "RETURN"
    ADJUST = "ADJUST"


class ReferenceType(StrEnum):
    """Supported business document reference types for stock mutations."""

    RECEIPT = "RECEIPT"
    ORDER = "ORDER"
    ADJUSTMENT = "ADJUSTMENT"


class InventoryAdjustment(Base):
    """Audit record for an Admin physical inventory count adjustment."""

    __tablename__ = "inventory_adjustments"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_inventory_adjustments"),
        UniqueConstraint(
            "id",
            "product_id",
            name="uq_inventory_adjustments_id_product_id",
        ),
        Index(
            "ix_inventory_adjustments_product_id_created_at_id",
            "product_id",
            "created_at",
            "id",
        ),
        CheckConstraint(
            "quantity_before >= 0 AND counted_quantity >= 0 "
            "AND version_before >= 0 AND CHAR_LENGTH(TRIM(reason)) > 0",
            name="ck_inventory_adjustments_nonnegative_and_reason",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "inventory.product_id",
            name="fk_inventory_adjustments_product_id_inventory",
        ),
        nullable=False,
    )
    actor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_inventory_adjustments_actor_id_users",
        ),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    quantity_before: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    counted_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    version_before: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )


class StockMovement(Base):
    """Immutable append-only ledger entry for every non-zero stock balance change."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_stock_movements"),
        ForeignKeyConstraint(
            ["adjustment_id", "product_id"],
            ["inventory_adjustments.id", "inventory_adjustments.product_id"],
            name="fk_stock_movements_adjustment_product",
        ),
        # ERD V1.0: stock_movements.(receipt_id, product_id) > purchase_receipt_items.
        # The order_items reference is added once the order_items table exists.
        ForeignKeyConstraint(
            ["receipt_id", "product_id"],
            ["purchase_receipt_items.receipt_id", "purchase_receipt_items.product_id"],
            name="fk_stock_movements_receipt_item",
        ),
        ForeignKeyConstraint(
            ["order_id", "product_id"],
            ["order_items.order_id", "order_items.product_id"],
            name="fk_stock_movements_order_item",
        ),
        UniqueConstraint(
            "product_id",
            "stock_version_after",
            name="uq_stock_movements_product_version_after",
        ),
        UniqueConstraint(
            "receipt_id",
            "product_id",
            name="uq_stock_movements_receipt_product",
        ),
        UniqueConstraint(
            "order_id",
            "product_id",
            "kind",
            name="uq_stock_movements_order_product_kind",
        ),
        UniqueConstraint(
            "adjustment_id",
            "product_id",
            name="uq_stock_movements_adjustment_product",
        ),
        Index(
            "ix_stock_movements_product_id_occurred_at_id",
            "product_id",
            "occurred_at",
            "id",
        ),
        Index(
            "ix_stock_movements_occurred_at_id",
            "occurred_at",
            "id",
        ),
        CheckConstraint(
            "quantity_before >= 0 AND quantity_after >= 0 "
            "AND quantity_before <> quantity_after AND stock_version_after > 0",
            name="ck_stock_movements_quantities_and_version",
        ),
        CheckConstraint(
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
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "inventory.product_id",
            name="fk_stock_movements_product_id_inventory",
        ),
        nullable=False,
    )
    actor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_stock_movements_actor_id_users",
        ),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    receipt_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    adjustment_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    sku_snapshot: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    quantity_before: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    quantity_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    stock_version_after: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )

    @property
    def delta(self) -> int:
        """Signed quantity change represented by this movement."""
        return self.quantity_after - self.quantity_before


__all__ = [
    "Inventory",
    "InventoryAdjustment",
    "MovementKind",
    "MovementType",
    "Product",
    "ProductStatus",
    "ReferenceType",
    "StockMovement",
]
