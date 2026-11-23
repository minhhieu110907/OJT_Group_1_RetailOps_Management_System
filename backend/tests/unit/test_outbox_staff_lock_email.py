"""Unit tests for STAFF_LOCKED and STAFF_UNLOCKED outbox emails."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.repository import ENABLED_EMAIL_EVENTS
from app.modules.outbox.templates import EmailTemplateRegistry
from app.modules.outbox.writer import (
    PAYLOAD_FIELDS,
    SUPPORTED_EVENT_TYPES,
    OutboxWriter,
)


def test_staff_lock_events_registered_in_outbox() -> None:
    assert "STAFF_LOCKED" in SUPPORTED_EVENT_TYPES
    assert "STAFF_UNLOCKED" in SUPPORTED_EVENT_TYPES
    assert "STAFF_LOCKED" in ENABLED_EMAIL_EVENTS
    assert "STAFF_UNLOCKED" in ENABLED_EMAIL_EVENTS
    assert PAYLOAD_FIELDS["STAFF_LOCKED"] == frozenset({"schema_version", "actor_id"})
    assert PAYLOAD_FIELDS["STAFF_UNLOCKED"] == frozenset({"schema_version", "actor_id"})


def test_staff_lock_and_unlock_email_templates_render() -> None:
    registry = EmailTemplateRegistry()
    now = datetime.now(UTC).replace(tzinfo=None)

    locked_event = OutboxEvent(
        id=b"\x01" * 16,
        subject_user_id=10,
        event_type="STAFF_LOCKED",
        payload={"schema_version": 1, "actor_id": 1},
        created_at=now,
        available_at=now,
    )
    rendered_locked = registry.render(locked_event)
    assert "khóa" in rendered_locked.subject.lower()
    assert "tạm khóa" in rendered_locked.text.lower()

    unlocked_event = OutboxEvent(
        id=b"\x02" * 16,
        subject_user_id=10,
        event_type="STAFF_UNLOCKED",
        payload={"schema_version": 1, "actor_id": 1},
        created_at=now,
        available_at=now,
    )
    rendered_unlocked = registry.render(unlocked_event)
    assert "mở khóa" in rendered_unlocked.subject.lower()
    assert "mở khóa" in rendered_unlocked.text.lower()


def test_outbox_writer_appends_staff_lock_events() -> None:
    writer = OutboxWriter()
    session = MagicMock()
    now = datetime.now(UTC)

    locked = writer.append(
        session,
        subject_user_id=42,
        event_type="STAFF_LOCKED",
        payload={"schema_version": 1, "actor_id": 1},
        available_at_utc=now,
    )
    unlocked = writer.append(
        session,
        subject_user_id=42,
        event_type="STAFF_UNLOCKED",
        payload={"schema_version": 1, "actor_id": 1},
        available_at_utc=now,
    )

    assert locked.event_type == "STAFF_LOCKED"
    assert unlocked.event_type == "STAFF_UNLOCKED"
    assert session.add.call_count == 2
