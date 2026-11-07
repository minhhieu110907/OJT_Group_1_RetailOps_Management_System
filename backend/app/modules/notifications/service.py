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

    return datetime.now(UTC).replace(tzinfo=None)


class NotificationService:
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

        count = self._repository.count_unread(session, admin_user_id)
        return UnreadCountResponse(count=count)

    def mark_read(
        self,
        session: Session,
        admin_user_id: int,
        notification_id: int,
    ) -> NotificationRead:

        now = self._normalize_timestamp(self._clock())
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
            raise AppException(
                code="RESOURCE_NOT_FOUND",
                message="Notification was not found",
                status_code=404,
            )
        return NotificationRead.model_validate(notification)

    def mark_all_read(
        self,
        session: Session,
        admin_user_id: int,
    ) -> MarkAllReadResponse:

        now = self._normalize_timestamp(self._clock())
        updated_count = self._repository.mark_all_read(
            session,
            admin_user_id=admin_user_id,
            read_at=now,
        )
        return MarkAllReadResponse(updated_count=updated_count)

    @staticmethod
    def _normalize_timestamp(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value
