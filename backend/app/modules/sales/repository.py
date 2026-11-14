"""Order writes that share the caller-owned transaction."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.modules.sales.models import Order, OrderItem


class OrderRepository:
    def lock_by_id(self, session: Session, order_id: int) -> Order | None:
        return session.scalar(
            select(Order)
            .options(lazyload(Order.items))
            .where(Order.id == order_id)
            .with_for_update()
        )

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
