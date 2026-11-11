"""Append-only transactional outbox writer."""

import json
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
PAYLOAD_FIELDS = {
    "STAFF_REGISTERED": frozenset({"schema_version", "approval_request_id"}),
    "STAFF_APPROVED": frozenset({"schema_version", "approval_request_id", "actor_id"}),
    "STAFF_REJECTED": frozenset({"schema_version", "approval_request_id", "actor_id"}),
    "PASSWORD_RESET": frozenset({"schema_version"}),
    "STAFF_REAPPLY_PROOF": frozenset({"schema_version"}),
}
SECRET_EVENT_TYPES = frozenset({"PASSWORD_RESET", "STAFF_REAPPLY_PROOF"})
MAX_SECRET_CIPHERTEXT_BYTES = 2048


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Outbox timestamps must be timezone-aware")
    return value.astimezone(UTC).replace(tzinfo=None)


def _validated_payload(
    event_type: str, payload: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    normalized = dict(payload)
    expected_fields = PAYLOAD_FIELDS[event_type]
    if set(normalized) != expected_fields:
        raise ValueError("Outbox payload fields do not match the event schema")
    if (
        type(normalized["schema_version"]) is not int
        or normalized["schema_version"] != 1
    ):
        raise ValueError("Outbox payload schema_version must be integer 1")
    for field in expected_fields - {"schema_version"}:
        value = normalized[field]
        if type(value) is not int or value <= 0:
            raise ValueError(f"Outbox payload {field} must be a positive integer")
    try:
        json.dumps(normalized, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Outbox payload must be valid JSON") from error
    return normalized


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
        if type(subject_user_id) is not int or subject_user_id <= 0:
            raise ValueError("Outbox subject_user_id must be a positive integer")

        normalized_payload = _validated_payload(event_type, payload)
        has_ciphertext = secret_ciphertext is not None
        has_expiry = secret_expires_at_utc is not None
        if has_ciphertext != has_expiry:
            raise ValueError(
                "Encrypted event secret and expiry must be provided together"
            )
        if event_type in SECRET_EVENT_TYPES and not has_ciphertext:
            raise ValueError(
                "Secret-bearing event requires encrypted secret and expiry"
            )
        if event_type not in SECRET_EVENT_TYPES and has_ciphertext:
            raise ValueError("This event type does not accept an encrypted secret")
        if (
            secret_ciphertext is not None
            and not 1 <= len(secret_ciphertext) <= MAX_SECRET_CIPHERTEXT_BYTES
        ):
            raise ValueError("Encrypted event secret has an invalid length")

        event_id = uuid4().bytes
        appended_at = datetime.now(UTC).replace(tzinfo=None)
        available_at = max(_utc_naive(available_at_utc), appended_at)
        secret_expires_at = (
            _utc_naive(secret_expires_at_utc)
            if secret_expires_at_utc is not None
            else None
        )
        if secret_expires_at is not None and secret_expires_at <= appended_at:
            raise ValueError("Encrypted event secret expiry must be in the future")
        session.add(
            OutboxEvent(
                id=event_id,
                subject_user_id=subject_user_id,
                event_type=event_type,
                payload=normalized_payload,
                secret_expires_at=secret_expires_at,
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
