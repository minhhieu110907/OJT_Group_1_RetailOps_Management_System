"""Frozen JSON application envelope carried inside the Celery task protocol."""

from collections.abc import Mapping
from uuid import UUID


def build_envelope(event_id: bytes) -> Mapping[str, object]:
    if not isinstance(event_id, bytes) or len(event_id) != 16:
        raise ValueError("Outbox event ID must contain exactly 16 bytes")
    return {"event_id": str(UUID(bytes=event_id)), "schema_version": 1}


def parse_envelope(envelope: object) -> bytes:
    if not isinstance(envelope, Mapping) or set(envelope) != {
        "event_id",
        "schema_version",
    }:
        raise ValueError("Invalid Outbox task envelope")
    event_id = envelope["event_id"]
    if envelope["schema_version"] != 1 or not isinstance(event_id, str):
        raise ValueError("Unsupported Outbox task envelope")
    try:
        parsed = UUID(event_id)
    except ValueError as error:
        raise ValueError("Invalid Outbox event UUID") from error
    if str(parsed) != event_id:
        raise ValueError("Outbox event UUID must use canonical lowercase form")
    return parsed.bytes
