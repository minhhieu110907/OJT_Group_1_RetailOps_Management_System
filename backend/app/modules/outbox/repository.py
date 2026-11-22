"""Short-lived database operations for Outbox publishing and delivery."""

from datetime import datetime

from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session

from app.modules.auth.models import PasswordResetToken, User
from app.modules.outbox.contracts import StuckEventCandidate
from app.modules.outbox.models import OutboxEvent

ENABLED_EMAIL_EVENTS = (
    "STAFF_REGISTERED",
    "STAFF_APPROVED",
    "STAFF_REJECTED",
    "PASSWORD_RESET",
    "PURCHASE_DRAFT_CREATED",
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

    def find_stuck_events(
        self,
        session: Session,
        *,
        stuck_before: datetime,
        batch_size: int,
    ) -> tuple[StuckEventCandidate, ...]:
        """Return bounded, deterministically ordered stuck-event candidates."""
        statement = (
            select(
                OutboxEvent.id,
                OutboxEvent.event_type,
                OutboxEvent.published_at,
                OutboxEvent.publish_attempts,
                OutboxEvent.delivery_attempts,
                OutboxEvent.last_error_code,
            )
            .where(
                OutboxEvent.outcome.is_(None),
                OutboxEvent.published_at.is_not(None),
                OutboxEvent.published_at <= stuck_before,
                OutboxEvent.event_type.in_(ENABLED_EMAIL_EVENTS),
            )
            .order_by(OutboxEvent.published_at, OutboxEvent.id)
            .limit(batch_size)
        )
        rows = session.execute(statement).all()
        return tuple(
            StuckEventCandidate(
                event_id=row[0],
                event_type=row[1],
                published_at=row[2],
                publish_attempts=row[3],
                delivery_attempts=row[4],
                last_error_code=row[5],
            )
            for row in rows
        )

    @staticmethod
    def _replay_guard_reason(
        event: OutboxEvent | None, *, max_attempts: int
    ) -> str | None:
        if event is None:
            return "EVENT_NOT_FOUND"
        if event.outcome is not None or event.finished_at is not None:
            return f"TERMINAL_OUTCOME_{event.outcome or 'FINISHED'}"
        if event.event_type not in ENABLED_EMAIL_EVENTS:
            return "EVENT_TYPE_DISABLED"
        if event.published_at is None:
            return "EVENT_NOT_PUBLISHED"
        if event.delivery_attempts >= max_attempts:
            return "DELIVERY_ATTEMPT_BUDGET_EXHAUSTED"
        return None

    def check_replay_eligibility(
        self,
        session: Session,
        *,
        event_id: bytes,
        max_attempts: int = 4,
    ) -> tuple[str, int | None]:
        """Read-only eligibility check for dry-run operator inspection."""
        event = session.get(OutboxEvent, event_id)
        reason = self._replay_guard_reason(event, max_attempts=max_attempts)
        if reason is not None:
            return reason, event.delivery_attempts if event is not None else None
        assert event is not None
        return "ELIGIBLE", event.delivery_attempts

    def requeue_for_operator_replay(
        self,
        session: Session,
        *,
        event_id: bytes,
        now: datetime,
        max_attempts: int = 4,
    ) -> tuple[str, int | None]:
        """Re-open an eligible stuck event under row lock without resetting budget."""
        event = session.get(OutboxEvent, event_id, with_for_update=True)
        reason = self._replay_guard_reason(event, max_attempts=max_attempts)
        if reason is not None:
            return reason, event.delivery_attempts if event is not None else None
        assert event is not None
        event.published_at = None
        event.available_at = now
        event.last_error_code = "OPERATOR_REPLAY_QUEUED"
        session.flush()
        return "REPLAY_QUEUED", event.delivery_attempts
