"""Order persistence sharing caller-owned transactions and read operations."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, lazyload, selectinload

from app.modules.sales.models import Order, OrderItem


def _escape_like(value: str) -> str:
    """Escape LIKE pattern special characters % and _ using backslash."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class OrderRepository:
    def lock_by_id(self, session: Session, order_id: int) -> Order | None:
        return session.scalar(
            select(Order)
            .options(lazyload(Order.items))
            .where(Order.id == order_id)
            .with_for_update()
        )

    def get_by_id(self, session: Session, order_id: int) -> Order | None:
        """Fetch a single order by ID with eagerly loaded items."""
        return session.scalar(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )

    def list_orders(
        self,
        session: Session,
        *,
        status: str | None = None,
        sold_from_utc: datetime | None = None,
        sold_to_utc_exclusive: datetime | None = None,
        order_id_exact: int | None = None,
        sku_search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Order], int]:
        """Query paginated orders with date range, status, and search filters."""
        conditions = []
        if status is not None:
            conditions.append(Order.status == status)
        if sold_from_utc is not None:
            conditions.append(Order.sold_at >= sold_from_utc)
        if sold_to_utc_exclusive is not None:
            conditions.append(Order.sold_at < sold_to_utc_exclusive)

        if sku_search is not None:
            escaped_sku = _escape_like(sku_search.lower())
            sku_exists_clause = exists(
                select(1).where(
                    OrderItem.order_id == Order.id,
                    func.lower(OrderItem.sku_snapshot).like(
                        f"%{escaped_sku}%", escape="\\"
                    ),
                )
            )
            if order_id_exact is not None:
                conditions.append(or_(Order.id == order_id_exact, sku_exists_clause))
            else:
                conditions.append(sku_exists_clause)
        elif order_id_exact is not None:
            conditions.append(Order.id == order_id_exact)

        count_stmt = select(func.count(Order.id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total = session.scalar(count_stmt) or 0

        if total == 0:
            return [], 0

        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(*conditions)
            .order_by(Order.sold_at.desc(), Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        orders = list(session.scalars(stmt))
        return orders, total

    def list_items(self, session: Session, order_id: int) -> list[OrderItem]:
        return list(
            session.scalars(
                select(OrderItem)
                .where(OrderItem.order_id == order_id)
                .order_by(OrderItem.product_id)
            )
        )

    def create_completed(
        self,
        session: Session,
        *,
        actor_id: int,
        sold_at: datetime,
        total_vnd: int,
        items: Sequence[dict[str, object]],
    ) -> Order:
        order = Order(
            status="COMPLETED",
            total_vnd=total_vnd,
            created_by=actor_id,
            sold_at=sold_at,
        )
        session.add(order)
        session.flush()
        for item in items:
            session.add(OrderItem(order_id=order.id, **item))
        session.flush()
        return order
