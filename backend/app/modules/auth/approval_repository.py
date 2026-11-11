"""Queries and row locks for Staff approval workflows."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import StaffApprovalRequest, User


class StaffApprovalRepository:
    def list_page(
        self,
        session: Session,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[StaffApprovalRequest], int]:
        predicate = (
            StaffApprovalRequest.status == status if status is not None else None
        )
        count_query = select(func.count()).select_from(StaffApprovalRequest)
        item_query = select(StaffApprovalRequest)
        if predicate is not None:
            count_query = count_query.where(predicate)
            item_query = item_query.where(predicate)
        total = int(session.scalar(count_query) or 0)
        items = list(
            session.scalars(
                item_query.order_by(
                    StaffApprovalRequest.requested_at.desc(),
                    StaffApprovalRequest.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def find_actor(self, session: Session, actor_id: int) -> User | None:
        return session.scalar(
            select(User)
            .where(User.id == actor_id)
            .execution_options(populate_existing=True)
        )

    def lock_approval(
        self, session: Session, approval_id: int
    ) -> StaffApprovalRequest | None:
        return session.scalar(
            select(StaffApprovalRequest)
            .where(StaffApprovalRequest.id == approval_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def lock_user(self, session: Session, user_id: int) -> User | None:
        return session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
