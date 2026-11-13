"""Order header and immutable sale snapshots."""

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
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderStatus(StrEnum):
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_orders"),
        CheckConstraint("total_vnd > 0", name="ck_orders_total_positive"),
        CheckConstraint(
            "(status = 'COMPLETED' AND cancelled_by IS NULL "
            "AND cancelled_at IS NULL AND cancel_reason IS NULL) OR "
            "(status = 'CANCELLED' AND cancelled_by IS NOT NULL "
            "AND cancelled_at IS NOT NULL AND cancelled_at >= sold_at "
            "AND cancel_reason IS NOT NULL "
            "AND CHAR_LENGTH(TRIM(cancel_reason)) > 0)",
            name="ck_orders_status_lifecycle",
        ),
        Index("ix_orders_sold_at_id", "sold_at", "id"),
        Index("ix_orders_status_sold_at_id", "status", "sold_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        String(9),
        nullable=False,
        default="COMPLETED",
        server_default=text("'COMPLETED'"),
    )
    total_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", name="fk_orders_created_by_users"),
        nullable=False,
    )
    sold_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", name="fk_orders_cancelled_by_users")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        PrimaryKeyConstraint("order_id", "product_id", name="pk_order_items"),
        CheckConstraint(
            "quantity > 0 AND unit_price_vnd > 0 "
            "AND line_total_vnd = CAST(quantity AS DECIMAL(30,0)) * unit_price_vnd",
            name="ck_order_items_qty_price_total",
        ),
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", name="fk_order_items_order_id_orders"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.id", name="fk_order_items_product_id_products"),
        nullable=False,
    )
    sku_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_total_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")
