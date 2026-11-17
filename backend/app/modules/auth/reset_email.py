"""Email delivery port and adapters for STAFF password reset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DependencyUnavailableError
from app.modules.auth.security import encrypt_reset_secret
from app.modules.outbox.writer import OutboxWriter


@dataclass(frozen=True)
class SentResetEmail:
    """In-memory captured reset email record for test environments only."""

    user_id: int
    recipient_email: str
    reset_link: str
    expires_at_utc: datetime


class PasswordResetEmailPort(Protocol):
    """Port abstracting how password reset emails are dispatched."""

    def send_reset_email(
        self,
        session: Session,
        *,
        user_id: int,
        recipient_email: str,
        reset_link: str,
        expires_at_utc: datetime,
    ) -> None: ...


class FakeInMemoryPasswordResetEmailAdapter:
    """In-memory fake adapter for tests/local dev; never logs plaintext secrets."""

    def __init__(self) -> None:
        self.sent_emails: list[SentResetEmail] = []

    def send_reset_email(
        self,
        session: Session,
        *,
        user_id: int,
        recipient_email: str,
        reset_link: str,
        expires_at_utc: datetime,
    ) -> None:
        del session
        self.sent_emails.append(
            SentResetEmail(
                user_id=user_id,
                recipient_email=recipient_email,
                reset_link=reset_link,
                expires_at_utc=expires_at_utc,
            )
        )


class OutboxPasswordResetEmailAdapter:
    """Transactional outbox adapter writing encrypted PASSWORD_RESET events."""

    def __init__(
        self,
        *,
        secret_key: str,
        outbox_writer: OutboxWriter | None = None,
    ) -> None:
        self._secret_key = secret_key
        self._outbox_writer = outbox_writer or OutboxWriter()

    def send_reset_email(
        self,
        session: Session,
        *,
        user_id: int,
        recipient_email: str,
        reset_link: str,
        expires_at_utc: datetime,
    ) -> None:
        del recipient_email
        ciphertext = encrypt_reset_secret(reset_link, self._secret_key)
        now_utc = datetime.now(UTC)
        aware_expires = (
            expires_at_utc.replace(tzinfo=UTC)
            if expires_at_utc.tzinfo is None
            else expires_at_utc.astimezone(UTC)
        )
        self._outbox_writer.append(
            session,
            subject_user_id=user_id,
            event_type="PASSWORD_RESET",
            payload={"schema_version": 1},
            available_at_utc=now_utc,
            secret_ciphertext=ciphertext,
            secret_expires_at_utc=aware_expires,
        )


def build_password_reset_email_adapter(
    settings: Settings,
) -> PasswordResetEmailPort:
    """Construct the configured reset email adapter, failing closed in production."""
    if settings.password_reset_email_adapter == "memory":
        if settings.environment.strip().lower() == "production":
            raise DependencyUnavailableError(
                "Adapter email giả lập không được phép chạy ở môi trường production."
            )
        return FakeInMemoryPasswordResetEmailAdapter()

    secret = settings.jwt_secret
    if secret is None:
        raise DependencyUnavailableError("Thiếu khóa mã hóa cho outbox reset email.")
    return OutboxPasswordResetEmailAdapter(secret_key=secret.get_secret_value())
