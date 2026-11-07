"""Application service for Admin in-app notifications."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.notifications.models import AdminNotification
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)


def utc_now() -> datetime:
    """Return naive UTC datetime matching MySQL DATETIME(6) storage convention."""
    return datetime.now(UTC).replace(tzinfo=None)


class NotificationService:
    """Coordinate Admin notification use cases and transaction boundaries.

    Transaction invariants:
    - ``create_for_approval`` is a sub-operation called inside ``AuthService``'s
      registration transaction; it NEVER calls ``commit()``, ``rollback()``,
      ``close()``, ``begin()``, or ``begin_nested()``.
    - ``mark_read`` and ``mark_all_read`` are top-level HTTP use cases; each owns
      its transaction boundary, committing once on success and rolling back on error.
    """

    def __init__(
        self,
        repository: NotificationRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def create_for_approval(
        self,
        session: Session,
        admin_user_id: int,
        approval_request_id: int,
    ) -> AdminNotification:
        """Create or return the notification for a staff approval request.

        Transaction & ownership contract:
        - ``session`` is passed from ``AuthService`` during Staff registration.
        - The caller (``AuthService``) is the sole transaction owner.
        - This method NEVER calls ``commit()``, ``rollback()``, ``close()``,
          ``begin()``, or ``begin_nested()``.
        - Database errors (such as FK constraint violations) propagate untouched
          so ``AuthService`` can roll back ``User``, ``StaffApprovalRequest``, and
          ``AdminNotification`` together.
        - If called again with the same ``approval_request_id`` (including with a
          different ``admin_user_id``), the existing notification is returned without
          modifying ``admin_user_id``, ``created_at``, or ``read_at``.
        """
        now = self._normalize_timestamp(self._clock())
        return self._repository.add_if_absent(
            session,
            admin_user_id=admin_user_id,
            approval_request_id=approval_request_id,
            created_at=now,
        )

    def list_for_admin(
        self,
        session: Session,
        admin_user_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> NotificationListResponse:
        """Return a paginated list of notifications owned by ``admin_user_id``."""
        offset = (page - 1) * page_size
        items, total = self._repository.list_for_admin(
            session,
            admin_user_id,
            unread_only=unread_only,
            offset=offset,
            limit=page_size,
        )
        return NotificationListResponse(
            items=[NotificationRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def count_unread(
        self,
        session: Session,
        admin_user_id: int,
    ) -> UnreadCountResponse:
        """Return the unread notification count for ``admin_user_id``."""
        count = self._repository.count_unread(session, admin_user_id)
        return UnreadCountResponse(count=count)

    def mark_read(
        self,
        session: Session,
        admin_user_id: int,
        notification_id: int,
    ) -> NotificationRead:
        """Idempotently mark an owned notification as read and commit once."""
        now = self._normalize_timestamp(self._clock())
        try:
            self._repository.mark_read(
                session,
                notification_id=notification_id,
                admin_user_id=admin_user_id,
                read_at=now,
            )
            notification = self._repository.get_owned(
                session,
                notification_id=notification_id,
                admin_user_id=admin_user_id,
            )
            if notification is None:
                session.rollback()
                raise AppException(
                    code="RESOURCE_NOT_FOUND",
                    message="Notification was not found",
                    status_code=404,
                )
            result = NotificationRead.model_validate(notification)
            session.commit()
            return result
        except AppException:
            raise
        except Exception:
            session.rollback()
            raise

    def mark_all_read(
        self,
        session: Session,
        admin_user_id: int,
    ) -> MarkAllReadResponse:
        """Mark all unread owned notifications as read and commit once."""
        now = self._normalize_timestamp(self._clock())
        try:
            updated_count = self._repository.mark_all_read(
                session,
                admin_user_id=admin_user_id,
                read_at=now,
            )
            session.commit()
            return MarkAllReadResponse(updated_count=updated_count)
        except Exception:
            session.rollback()
            raise

    @staticmethod
    def _normalize_timestamp(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value
