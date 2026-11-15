"""Repository for sales analytics queries."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.inventory.models import Inventory
from app.modules.sales.models import Order, OrderItem, OrderStatus


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

    def get_top_products(
        self,
        session: Session,
        *,
        start_utc: datetime,
        end_utc_exclusive: datetime,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve top performing products by sold units in COMPLETED orders.

        Orders strictly filtered by sold_at within [start_utc, end_utc_exclusive).
        Ties broken by revenue_vnd DESC and product_id ASC.
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

        stmt = (
            select(
                OrderItem.product_id,
                OrderItem.sku_snapshot.label("sku"),
                OrderItem.product_name_snapshot.label("name"),
                sold_units_col,
                revenue_col,
                Inventory.quantity.label("quantity"),
                Inventory.first_stocked_at.label("first_stocked_at"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(Inventory, Inventory.product_id == OrderItem.product_id)
            .where(
                Order.status == OrderStatus.COMPLETED,
                Order.sold_at >= start_utc_naive,
                Order.sold_at < end_utc_exclusive_naive,
            )
            .group_by(
                OrderItem.product_id,
                OrderItem.sku_snapshot,
                OrderItem.product_name_snapshot,
                Inventory.quantity,
                Inventory.first_stocked_at,
            )
            .order_by(
                sold_units_col.desc(),
                revenue_col.desc(),
                OrderItem.product_id.asc(),
            )
            .limit(limit)
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
