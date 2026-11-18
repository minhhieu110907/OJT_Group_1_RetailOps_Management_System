"""Short-lived database operations for Outbox publishing and delivery."""

from datetime import datetime

from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session

from app.modules.auth.models import PasswordResetToken, User
from app.modules.outbox.models import OutboxEvent

ENABLED_EMAIL_EVENTS = (
    "STAFF_REGISTERED",
    "STAFF_APPROVED",
    "STAFF_REJECTED",
    "PASSWORD_RESET",
)
SECRET_EMAIL_EVENTS = ("PASSWORD_RESET", "STAFF_REAPPLY_PROOF")


class OutboxRepository:
    def due_event_ids(
        self, session: Session, *, now: datetime, batch_size: int
    ) -> tuple[bytes, ...]:
        statement: Select[tuple[bytes]] = (
            select(OutboxEvent.id)
            .where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.outcome.is_(None),
                OutboxEvent.available_at <= now,
                OutboxEvent.event_type.in_(ENABLED_EMAIL_EVENTS),
            )
            .order_by(OutboxEvent.available_at, OutboxEvent.id)
            .limit(batch_size)
        )
        return tuple(session.scalars(statement))

    def increment_publish_attempt(self, session: Session, event_id: bytes) -> bool:
        result = session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.published_at.is_(None))
            .values(
                publish_attempts=OutboxEvent.publish_attempts + 1,
                last_error_code=None,
            )
        )
        return result.rowcount == 1

    def mark_published(
        self, session: Session, *, event_id: bytes, published_at: datetime
    ) -> bool:
        result = session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.published_at.is_(None))
            .values(published_at=published_at, last_error_code=None)
        )
        return result.rowcount == 1

    def record_publish_error(
        self, session: Session, *, event_id: bytes, error_code: str
    ) -> None:
        session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.published_at.is_(None))
            .values(last_error_code=error_code[:64])
        )

    def published_at(self, session: Session, event_id: bytes) -> datetime | None:
        return session.scalar(
            select(OutboxEvent.published_at).where(OutboxEvent.id == event_id)
        )

    def load_event_and_user(
        self, session: Session, event_id: bytes
    ) -> tuple[OutboxEvent, User] | None:
        row = session.execute(
            select(OutboxEvent, User)
            .join(User, User.id == OutboxEvent.subject_user_id)
            .where(OutboxEvent.id == event_id)
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    def begin_delivery_attempt(
        self,
        session: Session,
        event_id: bytes,
        *,
        max_attempts: int,
        exhausted_at: datetime,
    ) -> int | None:
        event = session.get(OutboxEvent, event_id, with_for_update=True)
        if event is None or event.outcome is not None:
            return None
        if event.delivery_attempts >= max_attempts:
            event.outcome = "FAILED"
            event.finished_at = exhausted_at
            event.last_error_code = "DELIVERY_ATTEMPT_BUDGET_EXHAUSTED"
            event.secret_ciphertext = None
            session.flush()
            return 0
        event.delivery_attempts += 1
        event.last_error_code = None
        session.flush()
        return event.delivery_attempts

    def delivery_state(
        self, session: Session, event_id: bytes
    ) -> tuple[int, str | None, str | None] | None:
        row = session.execute(
            select(
                OutboxEvent.delivery_attempts,
                OutboxEvent.outcome,
                OutboxEvent.last_error_code,
            ).where(OutboxEvent.id == event_id)
        ).one_or_none()
        return (row[0], row[1], row[2]) if row is not None else None

    def finish_delivery(
        self,
        session: Session,
        *,
        event_id: bytes,
        outcome: str,
        finished_at: datetime,
        error_code: str | None,
    ) -> bool:
        result = session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.outcome.is_(None))
            .values(
                outcome=outcome,
                finished_at=finished_at,
                last_error_code=error_code[:64] if error_code else None,
                secret_ciphertext=None,
            )
        )
        return result.rowcount == 1

    def record_transient_delivery_error(
        self, session: Session, *, event_id: bytes, error_code: str
    ) -> bool:
        result = session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.outcome.is_(None))
            .values(last_error_code=error_code[:64])
        )
        return result.rowcount == 1

    def skip_expired_disabled_secrets(self, session: Session, *, now: datetime) -> int:
        result = session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.event_type.in_(SECRET_EMAIL_EVENTS),
                OutboxEvent.outcome.is_(None),
                OutboxEvent.secret_expires_at.is_not(None),
                OutboxEvent.secret_expires_at <= now,
            )
            .values(
                outcome="SKIPPED",
                finished_at=now,
                secret_ciphertext=None,
                last_error_code="SECRET_EXPIRED_BEFORE_ENABLEMENT",
            )
        )
        return result.rowcount

    def is_password_reset_token_active(
        self,
        session: Session,
        *,
        user_id: int,
        token_hash: str,
        now: datetime,
    ) -> bool:
        """Return True iff the reset token exists, is unused, and has not expired."""
        found = session.scalar(
            select(PasswordResetToken.id).where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
        )
        return found is not None
