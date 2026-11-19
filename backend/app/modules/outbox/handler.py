"""Idempotent email handler for a single sequential Celery worker."""

from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.auth.security import decrypt_reset_secret, hash_reset_token
from app.modules.outbox.contracts import EmailOutcome
from app.modules.outbox.errors import (
    DatabaseUnavailableError,
    PermanentEmailError,
    TransientEmailError,
    UnknownEventError,
)
from app.modules.outbox.repository import ENABLED_EMAIL_EVENTS, OutboxRepository
from app.modules.outbox.smtp import EmailTransport
from app.modules.outbox.templates import EmailTemplateRegistry


class EmailEventHandler:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        transport: EmailTransport,
        repository: OutboxRepository | None = None,
        templates: EmailTemplateRegistry | None = None,
        clock: Callable[[], datetime] | None = None,
        secret_key: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.transport = transport
        self.repository = repository or OutboxRepository()
        self.templates = templates or EmailTemplateRegistry()
        self.clock = clock or (lambda: datetime.now(UTC).replace(tzinfo=None))
        self.secret_key = secret_key

    def handle(self, *, event_id: bytes) -> EmailOutcome:
        if not isinstance(event_id, bytes) or len(event_id) != 16:
            raise ValueError("Outbox event ID must contain exactly 16 bytes")
        is_password_reset = False
        reset_user_id: int | None = None
        reset_secret_expires_at: datetime | None = None
        reset_token_hash: str | None = None
        try:
            with self.session_factory() as session:
                loaded = self.repository.load_event_and_user(session, event_id)
                if loaded is None:
                    raise UnknownEventError("Outbox event does not exist")
                event, user = loaded
                if event.outcome is not None:
                    return EmailOutcome(event_id=event_id, status="SKIPPED")
                if event.event_type not in ENABLED_EMAIL_EVENTS:
                    raise PermanentEmailError("Secret email event is disabled")
                recipient = user.email_normalized
                if event.event_type == "PASSWORD_RESET":
                    is_password_reset = True
                    reset_user_id = user.id
                    reset_secret_expires_at = event.secret_expires_at
                    now = self.clock()
                    if (
                        event.secret_expires_at is None
                        or event.secret_expires_at <= now
                        or event.secret_ciphertext is None
                    ):
                        self._finish(
                            event_id, outcome="FAILED", error_code="SECRET_EXPIRED"
                        )
                        return EmailOutcome(event_id=event_id, status="FAILED")
                    if self.secret_key is None:
                        self._finish(
                            event_id,
                            outcome="FAILED",
                            error_code="SECRET_DECRYPT_FAILED",
                        )
                        return EmailOutcome(event_id=event_id, status="FAILED")
                    try:
                        reset_link = decrypt_reset_secret(
                            event.secret_ciphertext, self.secret_key
                        )
                    except ValueError:
                        self._finish(
                            event_id,
                            outcome="FAILED",
                            error_code="SECRET_DECRYPT_FAILED",
                        )
                        return EmailOutcome(event_id=event_id, status="FAILED")
                    raw_token = parse_qs(urlsplit(reset_link).query).get("token", [""])[
                        0
                    ]
                    if not raw_token:
                        self._finish(
                            event_id, outcome="FAILED", error_code="TOKEN_INACTIVE"
                        )
                        return EmailOutcome(event_id=event_id, status="FAILED")
                    reset_token_hash = hash_reset_token(raw_token)
                    if not self.repository.is_password_reset_token_active(
                        session,
                        user_id=user.id,
                        token_hash=reset_token_hash,
                        now=now,
                    ):
                        self._finish(
                            event_id, outcome="FAILED", error_code="TOKEN_INACTIVE"
                        )
                        return EmailOutcome(event_id=event_id, status="FAILED")
                    rendered = self.templates.render_password_reset(
                        reset_link=reset_link
                    )
                else:
                    rendered = self.templates.render(event)

            attempt = self._begin_attempt(event_id)
            if attempt is None:
                return EmailOutcome(event_id=event_id, status="SKIPPED")
            if attempt == 0:
                return EmailOutcome(event_id=event_id, status="FAILED")

            # Re-verify token state right before SMTP dispatch (closing the short
            # session before network I/O so no MySQL lock is held during SMTP).
            if is_password_reset:
                assert reset_user_id is not None
                assert reset_token_hash is not None
                dispatch_now = self.clock()
                if (
                    reset_secret_expires_at is None
                    or reset_secret_expires_at <= dispatch_now
                ):
                    self._finish(
                        event_id, outcome="FAILED", error_code="SECRET_EXPIRED"
                    )
                    return EmailOutcome(event_id=event_id, status="FAILED")
                with self.session_factory() as session:
                    still_active = self.repository.is_password_reset_token_active(
                        session,
                        user_id=reset_user_id,
                        token_hash=reset_token_hash,
                        now=dispatch_now,
                    )
                if not still_active:
                    self._finish(
                        event_id, outcome="FAILED", error_code="TOKEN_INACTIVE"
                    )
                    return EmailOutcome(event_id=event_id, status="FAILED")
        except (UnknownEventError, PermanentEmailError):
            raise
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("Outbox database unavailable") from error

        try:
            self.transport.send(recipient=recipient, email=rendered)
        except TransientEmailError as error:
            if attempt >= 4:
                self._finish(
                    event_id,
                    outcome="FAILED",
                    error_code="SMTP_RETRIES_EXHAUSTED",
                )
                return EmailOutcome(event_id=event_id, status="FAILED")
            self._record_transient(event_id, error.code)
            return EmailOutcome(event_id=event_id, status="RETRY")
        except PermanentEmailError as error:
            self._finish(event_id, outcome="FAILED", error_code=error.code)
            return EmailOutcome(event_id=event_id, status="FAILED")

        self._finish(event_id, outcome="SENT", error_code=None)
        return EmailOutcome(event_id=event_id, status="SENT")

    def _begin_attempt(self, event_id: bytes) -> int | None:
        attempt: int | None = None
        try:
            with self.session_factory() as session:
                attempt = self.repository.begin_delivery_attempt(
                    session,
                    event_id,
                    max_attempts=4,
                    exhausted_at=self.clock(),
                )
                session.commit()
                return attempt
        except SQLAlchemyError as error:
            # Commit acknowledgement may be ambiguous. Only continue when a new
            # session proves the attempt/budget transition is durable.
            state = self._read_delivery_state(event_id)
            if state is not None and attempt is not None:
                attempts, outcome, _error_code = state
                if attempt == 0 and outcome == "FAILED":
                    return 0
                if attempt > 0 and attempts >= attempt and outcome is None:
                    return attempt
                if outcome is not None:
                    return None
            raise DatabaseUnavailableError(
                "Delivery attempt was not durably persisted"
            ) from error

    def _finish(self, event_id: bytes, *, outcome: str, error_code: str | None) -> None:
        changed = False
        try:
            with self.session_factory() as session:
                changed = self.repository.finish_delivery(
                    session,
                    event_id=event_id,
                    outcome=outcome,
                    finished_at=self.clock(),
                    error_code=error_code,
                )
                session.commit()
        except SQLAlchemyError as error:
            state = self._read_delivery_state(event_id)
            if state is not None and state[1] == outcome:
                return
            raise DatabaseUnavailableError(
                "Terminal Outbox state was not persisted"
            ) from error
        if not changed:
            state = self._read_delivery_state(event_id)
            if state is None or state[1] != outcome:
                raise DatabaseUnavailableError(
                    "Terminal Outbox state was not persisted"
                )

    def _record_transient(self, event_id: bytes, error_code: str) -> None:
        try:
            with self.session_factory() as session:
                if not self.repository.record_transient_delivery_error(
                    session, event_id=event_id, error_code=error_code
                ):
                    raise DatabaseUnavailableError(
                        "Transient Outbox state was not persisted"
                    )
                session.commit()
        except SQLAlchemyError as error:
            state = self._read_delivery_state(event_id)
            if state is not None and state[1] is None and state[2] == error_code:
                return
            raise DatabaseUnavailableError(
                "Transient Outbox state was not persisted"
            ) from error

    def _read_delivery_state(
        self, event_id: bytes
    ) -> tuple[int, str | None, str | None] | None:
        try:
            with self.session_factory() as session:
                return self.repository.delivery_state(session, event_id)
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError(
                "Outbox delivery state could not be verified"
            ) from error
