"""Repository for sales analytics queries."""

from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.modules.sales.models import Order, OrderStatus


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
