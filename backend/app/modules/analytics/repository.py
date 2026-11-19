"""Repository for sales analytics queries."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.inventory.models import Inventory
from app.modules.products.models import CatalogStatus, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus


def _to_utc_naive(dt: datetime) -> datetime:
    """Convert timezone-aware or naive datetime into UTC-naive for MySQL DATETIME."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class SalesAnalyticsRepository:
    """Read-only repository aggregating sales metrics from committed orders."""

    def aggregate_sales(
        self,
        session: Session,
        *,
        start_utc: datetime,
        end_utc_exclusive: datetime,
    ) -> dict[str, int]:
        """Aggregate revenue, completed, and cancelled order count for the period.

        Filters strictly by Order.sold_at within [start_utc, end_utc_exclusive)
        to leverage ix_orders_sold_at_id and ix_orders_status_sold_at_id indexes.
        """
        start_utc_naive = (
            start_utc.astimezone(UTC).replace(tzinfo=None)
            if start_utc.tzinfo is not None
            else start_utc
        )
        end_utc_exclusive_naive = (
            end_utc_exclusive.astimezone(UTC).replace(tzinfo=None)
            if end_utc_exclusive.tzinfo is not None
            else end_utc_exclusive
        )

        completed_cond = Order.status == OrderStatus.COMPLETED
        cancelled_cond = Order.status == OrderStatus.CANCELLED

        stmt = select(
            func.coalesce(
                func.sum(
                    case(
                        (completed_cond, Order.total_vnd),
                        else_=0,
                    )
                ),
                0,
            ).label("revenue_vnd"),
            func.coalesce(
                func.sum(
                    case(
                        (completed_cond, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("completed_orders"),
            func.coalesce(
                func.sum(
                    case(
                        (cancelled_cond, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("cancelled_orders"),
        ).where(
            Order.sold_at >= start_utc_naive,
            Order.sold_at < end_utc_exclusive_naive,
        )

        row = session.execute(stmt).one()
        return {
            "revenue_vnd": int(row.revenue_vnd or 0),
            "completed_orders": int(row.completed_orders or 0),
            "cancelled_orders": int(row.cancelled_orders or 0),
        }

    def get_daily_sales_orders(
        self,
        session: Session,
        *,
        start_utc: datetime,
        end_utc_exclusive: datetime,
    ) -> list[tuple[datetime, str, int]]:
        """Fetch sold_at, status, and total_vnd for completed and cancelled orders."""
        start_utc_naive = (
            start_utc.astimezone(UTC).replace(tzinfo=None)
            if start_utc.tzinfo is not None
            else start_utc
        )
        end_utc_exclusive_naive = (
            end_utc_exclusive.astimezone(UTC).replace(tzinfo=None)
            if end_utc_exclusive.tzinfo is not None
            else end_utc_exclusive
        )
        stmt = (
            select(Order.sold_at, Order.status, Order.total_vnd)
            .where(
                Order.sold_at >= start_utc_naive,
                Order.sold_at < end_utc_exclusive_naive,
                Order.status.in_(
                    [OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value]
                ),
            )
            .order_by(Order.sold_at.asc())
        )
        return list(session.execute(stmt).tuples().all())

    def get_top_products(
        self,
        session: Session,
        *,
        start_utc: datetime,
        end_utc_exclusive: datetime,
        limit: int = 5,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Retrieve top performing products by sold units in COMPLETED orders.

        Snapshot policy:
        - sold_units, revenue_vnd: aggregated from historical OrderItem snapshots
          for COMPLETED orders within [start_utc, end_utc_exclusive).
        - sku, name: current product master record from Product.
        - quantity, first_stocked_at: current inventory level from Inventory.

        Aggregation is grouped strictly by OrderItem.product_id (each product appears
        at most once). Ties broken by revenue_vnd DESC and product_id ASC.
        """
        start_utc_naive = (
            start_utc.astimezone(UTC).replace(tzinfo=None)
            if start_utc.tzinfo is not None
            else start_utc
        )
        end_utc_exclusive_naive = (
            end_utc_exclusive.astimezone(UTC).replace(tzinfo=None)
            if end_utc_exclusive.tzinfo is not None
            else end_utc_exclusive
        )

        sold_units_col = func.coalesce(func.sum(OrderItem.quantity), 0).label(
            "sold_units"
        )
        revenue_col = func.coalesce(func.sum(OrderItem.line_total_vnd), 0).label(
            "revenue_vnd"
        )

        # Subquery: aggregate sales per unique product_id for COMPLETED orders in period
        sales_subq = (
            select(
                OrderItem.product_id.label("product_id"),
                sold_units_col,
                revenue_col,
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.status == OrderStatus.COMPLETED,
                Order.sold_at >= start_utc_naive,
                Order.sold_at < end_utc_exclusive_naive,
            )
            .group_by(OrderItem.product_id)
            .order_by(
                sold_units_col.desc(),
                revenue_col.desc(),
                OrderItem.product_id.asc(),
            )
        )
        if offset > 0:
            sales_subq = sales_subq.offset(offset)
        if limit > 0:
            sales_subq = sales_subq.limit(limit)

        sales_subq = sales_subq.subquery("top_sales")

        # Outer query: join current Product catalog and Inventory state
        stmt = (
            select(
                sales_subq.c.product_id,
                Product.sku.label("sku"),
                Product.name.label("name"),
                sales_subq.c.sold_units,
                sales_subq.c.revenue_vnd,
                Inventory.quantity.label("quantity"),
                Inventory.first_stocked_at.label("first_stocked_at"),
            )
            .join(Product, Product.id == sales_subq.c.product_id)
            .outerjoin(Inventory, Inventory.product_id == sales_subq.c.product_id)
            .order_by(
                sales_subq.c.sold_units.desc(),
                sales_subq.c.revenue_vnd.desc(),
                sales_subq.c.product_id.asc(),
            )
        )

        rows = session.execute(stmt).all()
        return [
            {
                "product_id": int(r.product_id),
                "sku": str(r.sku),
                "name": str(r.name),
                "sold_units": int(r.sold_units),
                "revenue_vnd": int(r.revenue_vnd),
                "quantity": int(r.quantity) if r.quantity is not None else None,
                "first_stocked_at": r.first_stocked_at,
            }
            for r in rows
        ]

    def count_top_products(
        self,
        session: Session,
        *,
        start_utc: datetime,
        end_utc_exclusive: datetime,
    ) -> int:
        """Count distinct products sold in COMPLETED orders in the period."""
        start_utc_naive = _to_utc_naive(start_utc)
        end_utc_exclusive_naive = _to_utc_naive(end_utc_exclusive)

        stmt = (
            select(func.count(func.distinct(OrderItem.product_id)))
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.status == OrderStatus.COMPLETED,
                Order.sold_at >= start_utc_naive,
                Order.sold_at < end_utc_exclusive_naive,
            )
        )
        return int(session.scalar(stmt) or 0)

    def list_slow_products(
        self,
        session: Session,
        *,
        as_of_utc: datetime,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List slow-moving ACTIVE products (stock > 0, stocked > 7d, sold <= 2 in 30d).

        Only COMPLETED orders in [as_of_utc - 30 days, as_of_utc) are counted.
        CANCELLED orders are excluded; products with zero orders have sold_units = 0.
        """
        as_of_naive = _to_utc_naive(as_of_utc)
        stocked_before = as_of_naive - timedelta(days=7)
        sales_window_start = as_of_naive - timedelta(days=30)

        sales_subq = (
            select(
                OrderItem.product_id.label("product_id"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("sold_units"),
                func.coalesce(func.sum(OrderItem.line_total_vnd), 0).label(
                    "revenue_vnd"
                ),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.status == OrderStatus.COMPLETED,
                Order.sold_at >= sales_window_start,
                Order.sold_at < as_of_naive,
            )
            .group_by(OrderItem.product_id)
            .subquery("slow_sales_30d")
        )

        sold_units_expr = func.coalesce(sales_subq.c.sold_units, 0).label("sold_units")
        revenue_expr = func.coalesce(sales_subq.c.revenue_vnd, 0).label("revenue_vnd")

        base_stmt = (
            select(
                Product.id.label("product_id"),
                Product.sku.label("sku"),
                Product.name.label("name"),
                sold_units_expr,
                revenue_expr,
                Inventory.quantity.label("quantity"),
                Inventory.first_stocked_at.label("first_stocked_at"),
            )
            .join(Inventory, Inventory.product_id == Product.id)
            .outerjoin(sales_subq, sales_subq.c.product_id == Product.id)
            .where(
                Product.status == CatalogStatus.ACTIVE.value,
                Inventory.quantity > 0,
                Inventory.first_stocked_at.is_not(None),
                Inventory.first_stocked_at < stocked_before,
                func.coalesce(sales_subq.c.sold_units, 0) <= 2,
            )
        )

        count_stmt = select(func.count()).select_from(base_stmt.subquery("slow_base"))
        total = int(session.scalar(count_stmt) or 0)

        ordered_stmt = base_stmt.order_by(
            sold_units_expr.asc(),
            Inventory.quantity.desc(),
            Inventory.first_stocked_at.asc(),
            Product.id.asc(),
        )
        if offset > 0:
            ordered_stmt = ordered_stmt.offset(offset)
        if limit > 0:
            ordered_stmt = ordered_stmt.limit(limit)

        rows = session.execute(ordered_stmt).all()
        items = [
            {
                "product_id": int(r.product_id),
                "sku": str(r.sku),
                "name": str(r.name),
                "sold_units": int(r.sold_units),
                "revenue_vnd": int(r.revenue_vnd),
                "quantity": int(r.quantity),
                "first_stocked_at": r.first_stocked_at,
            }
            for r in rows
        ]
        return items, total
