"""Append-only transactional outbox writer."""

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.modules.outbox.models import OutboxEvent

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
SUPPORTED_EVENT_TYPES = frozenset(
    {
        "STAFF_REGISTERED",
        "STAFF_APPROVED",
        "STAFF_REJECTED",
        "PASSWORD_RESET",
        "STAFF_REAPPLY_PROOF",
    }
)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class OutboxWriter:
    """Add an event to the caller's Session without ending its transaction."""

    def append(
        self,
        session: Session,
        *,
        subject_user_id: int,
        event_type: str,
        payload: Mapping[str, JsonValue],
        available_at_utc: datetime,
        secret_ciphertext: bytes | None = None,
        secret_expires_at_utc: datetime | None = None,
    ) -> bytes:
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise ValueError("Unsupported outbox event type")
        if secret_ciphertext is not None and secret_expires_at_utc is None:
            raise ValueError("Encrypted event secret requires an expiry")

        event_id = uuid4().bytes
        appended_at = datetime.now(UTC).replace(tzinfo=None)
        available_at = max(_utc_naive(available_at_utc), appended_at)
        session.add(
            OutboxEvent(
                id=event_id,
                subject_user_id=subject_user_id,
                event_type=event_type,
                payload=dict(payload),
                secret_expires_at=(
                    _utc_naive(secret_expires_at_utc)
                    if secret_expires_at_utc is not None
                    else None
                ),
                secret_ciphertext=secret_ciphertext,
                created_at=appended_at,
                available_at=available_at,
                published_at=None,
                publish_attempts=0,
                delivery_attempts=0,
                outcome=None,
                finished_at=None,
                last_error_code=None,
            )
        )
        return event_id
