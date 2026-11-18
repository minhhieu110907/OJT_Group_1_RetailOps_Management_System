"""Single-instance polling publisher for committed Outbox events."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.outbox.broker import EventPublisher
from app.modules.outbox.contracts import PublishBatchResult
from app.modules.outbox.errors import BrokerPublishError
from app.modules.outbox.repository import OutboxRepository

LOGGER = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(
        self,
        broker: EventPublisher,
        repository: OutboxRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.broker = broker
        self.repository = repository or OutboxRepository()
        self.clock = clock or (lambda: datetime.now(UTC).replace(tzinfo=None))

    def publish_due(
        self,
        session_factory: Callable[[], Session],
        *,
        batch_size: int,
    ) -> PublishBatchResult:
        if not 1 <= batch_size <= 25:
            raise ValueError("Outbox batch_size must be between 1 and 25")

        now = self.clock()
        with session_factory() as session:
            event_ids = self.repository.due_event_ids(
                session, now=now, batch_size=batch_size
            )
            # Security hygiene for disabled secret events happens without publishing.
            self.repository.skip_expired_disabled_secrets(session, now=now)
            session.commit()

        published = 0
        failed = 0
        for event_id in event_ids:
            if not self._start_attempt(session_factory, event_id):
                failed += 1
                continue
            try:
                self.broker.publish(event_id)
            except BrokerPublishError:
                self._best_effort_publish_error(
                    session_factory, event_id, "BROKER_PUBLISH_FAILED"
                )
                self._log_failure(event_id, "BROKER_PUBLISH_FAILED")
                failed += 1
                continue
            if self._mark_confirmed(session_factory, event_id):
                published += 1
            else:
                failed += 1

        return PublishBatchResult(
            scanned=len(event_ids), published=published, failed=failed
        )

    def _start_attempt(
        self, session_factory: Callable[[], Session], event_id: bytes
    ) -> bool:
        try:
            with session_factory() as session:
                changed = self.repository.increment_publish_attempt(session, event_id)
                session.commit()
                if not changed:
                    self._log_failure(event_id, "DB_PUBLISH_ATTEMPT_NOT_APPLIED")
                return changed
        except SQLAlchemyError:
            self._log_failure(event_id, "DB_PUBLISH_ATTEMPT_FAILED")
            return False

    def _mark_confirmed(
        self, session_factory: Callable[[], Session], event_id: bytes
    ) -> bool:
        try:
            with session_factory() as session:
                changed = self.repository.mark_published(
                    session, event_id=event_id, published_at=self.clock()
                )
                session.commit()
                if not changed:
                    self._log_failure(event_id, "DB_PUBLISH_CONFIRM_NOT_APPLIED")
                return changed
        except SQLAlchemyError:
            # Commit acknowledgement can be ambiguous. Read back using a new session.
            try:
                with session_factory() as verification:
                    return (
                        self.repository.published_at(verification, event_id) is not None
                    )
            except SQLAlchemyError:
                self._log_failure(event_id, "DB_PUBLISH_CONFIRM_UNKNOWN")
                return False

    def _best_effort_publish_error(
        self,
        session_factory: Callable[[], Session],
        event_id: bytes,
        error_code: str,
    ) -> None:
        try:
            with session_factory() as session:
                self.repository.record_publish_error(
                    session, event_id=event_id, error_code=error_code
                )
                session.commit()
        except SQLAlchemyError:
            self._log_failure(event_id, "DB_PUBLISH_ERROR_RECORD_FAILED")
            return

    @staticmethod
    def _log_failure(event_id: bytes, error_code: str) -> None:
        LOGGER.warning(
            "Outbox publish operation failed",
            extra={
                "event_id": str(UUID(bytes=event_id)),
                "error_code": error_code,
            },
        )
