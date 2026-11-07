"""Stateless SQLAlchemy repository for AdminNotification persistence."""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.modules.notifications.models import AdminNotification


class NotificationRepository:
    """Execute owner-scoped SQL queries for Admin notifications without committing."""

    def add_if_absent(
        self,
        session: Session,
        admin_user_id: int,
        approval_request_id: int,
        created_at: datetime,
    ) -> AdminNotification:

        stmt = (
            mysql_insert(AdminNotification)
            .values(
                admin_user_id=admin_user_id,
                approval_request_id=approval_request_id,
                created_at=created_at,
                read_at=None,
            )
            .on_duplicate_key_update(id=AdminNotification.id)
        )
        session.execute(stmt)
        session.flush()
        record = self.find_by_approval_request_id(session, approval_request_id)
        if record is None:
            raise RuntimeError(
                "AdminNotification row missing after atomic upsert flush"
            )
        return record

    def find_by_approval_request_id(
        self,
        session: Session,
        approval_request_id: int,
    ) -> AdminNotification | None:
        """Return the notification linked to a staff approval request, if any."""
        stmt = select(AdminNotification).where(
            AdminNotification.approval_request_id == approval_request_id
        )
        return session.scalar(stmt)

    def get_owned(
        self,
        session: Session,
        notification_id: int,
        admin_user_id: int,
    ) -> AdminNotification | None:
        """Return a notification only when owned by ``admin_user_id``."""
        stmt = select(AdminNotification).where(
            AdminNotification.id == notification_id,
            AdminNotification.admin_user_id == admin_user_id,
        )
        return session.scalar(stmt)

    def list_for_admin(
        self,
        session: Session,
        admin_user_id: int,
        *,
        unread_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AdminNotification], int]:
        """List notifications owned by ``admin_user_id`` ordered by newest first."""
        predicates = [AdminNotification.admin_user_id == admin_user_id]
        if unread_only:
            predicates.append(AdminNotification.read_at.is_(None))

        total_stmt = (
            select(func.count()).select_from(AdminNotification).where(*predicates)
        )
        total = int(session.scalar(total_stmt) or 0)

        items_stmt = (
            select(AdminNotification)
            .where(*predicates)
            .order_by(
                AdminNotification.created_at.desc(),
                AdminNotification.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = list(session.scalars(items_stmt))
        return items, total

    def count_unread(
        self,
        session: Session,
        admin_user_id: int,
    ) -> int:

        stmt = (
            select(func.count())
            .select_from(AdminNotification)
            .where(
                AdminNotification.admin_user_id == admin_user_id,
                AdminNotification.read_at.is_(None),
            )
        )
        return int(session.scalar(stmt) or 0)

    def mark_read(
        self,
        session: Session,
        notification_id: int,
        admin_user_id: int,
        read_at: datetime,
    ) -> int:

        stmt = (
            update(AdminNotification)
            .where(
                AdminNotification.id == notification_id,
                AdminNotification.admin_user_id == admin_user_id,
                AdminNotification.read_at.is_(None),
            )
            .values(read_at=read_at)
        )
        result = session.execute(stmt)
        session.flush()
        return int(result.rowcount or 0)

    def mark_all_read(
        self,
        session: Session,
        admin_user_id: int,
        read_at: datetime,
    ) -> int:

        stmt = (
            update(AdminNotification)
            .where(
                AdminNotification.admin_user_id == admin_user_id,
                AdminNotification.read_at.is_(None),
            )
            .values(read_at=read_at)
        )
        result = session.execute(stmt)
        session.flush()
        return int(result.rowcount or 0)
