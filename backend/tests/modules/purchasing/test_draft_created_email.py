"""Unit tests for the PURCHASE_DRAFT_CREATED outbox email flow."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import InvalidStateError, ResourceNotFoundError
from app.modules.outbox.repository import ENABLED_EMAIL_EVENTS
from app.modules.outbox.templates import EmailTemplateRegistry
from app.modules.outbox.writer import OutboxWriter
from app.modules.purchasing.draft_service import ReceiptDraftService


def test_event_type_is_enabled_for_delivery() -> None:
    assert "PURCHASE_DRAFT_CREATED" in ENABLED_EMAIL_EVENTS


def test_writer_accepts_only_receipt_id_payload() -> None:
    session = MagicMock()
    writer = OutboxWriter()
    event_id = writer.append(
        session,
        subject_user_id=1,
        event_type="PURCHASE_DRAFT_CREATED",
        payload={"schema_version": 1, "receipt_id": 7},
        available_at_utc=datetime.now(UTC),
    )
    assert len(event_id) == 16
    session.add.assert_called_once()

    with pytest.raises(ValueError):
        writer.append(
            session,
            subject_user_id=1,
            event_type="PURCHASE_DRAFT_CREATED",
            payload={"schema_version": 1},
            available_at_utc=datetime.now(UTC),
        )


def test_template_renders_receipt_id_without_sensitive_data() -> None:
    event = SimpleNamespace(
        event_type="PURCHASE_DRAFT_CREATED",
        payload={"schema_version": 1, "receipt_id": 42},
    )
    rendered = EmailTemplateRegistry().render(event)  # type: ignore[arg-type]
    assert "#42" in rendered.text
    assert "DRAFT" in rendered.text
    assert rendered.subject == "RetailOps đã tạo phiếu nhập nháp"


def test_template_rejects_invalid_receipt_id() -> None:
    event = SimpleNamespace(
        event_type="PURCHASE_DRAFT_CREATED", payload={"receipt_id": "x"}
    )
    with pytest.raises(ValueError):
        EmailTemplateRegistry().render(event)  # type: ignore[arg-type]


def test_create_draft_appends_outbox_event_in_same_session() -> None:
    writer = MagicMock()
    service = ReceiptDraftService(outbox_writer=writer)

    session = MagicMock()
    supplier = SimpleNamespace(id=3, name="NCC A", status="ACTIVE")
    session.get.return_value = supplier
    service._process_items = MagicMock(return_value=([], 0))  # type: ignore[method-assign]

    def _flush() -> None:
        for call in session.add.call_args_list:
            obj = call.args[0]
            if getattr(obj, "id", None) is None:
                obj.id = 99

    session.flush.side_effect = _flush

    service.create_draft(
        session, actor_id=5, supplier_id=3, items=[], notify_email=True
    )

    writer.append.assert_called_once()
    kwargs = writer.append.call_args.kwargs
    assert kwargs["subject_user_id"] == 5
    assert kwargs["event_type"] == "PURCHASE_DRAFT_CREATED"
    assert kwargs["payload"] == {"schema_version": 1, "receipt_id": 99}
    session.commit.assert_not_called()


def test_notify_draft_created_validates_draft_status_and_queues_outbox() -> None:
    writer = MagicMock()
    service = ReceiptDraftService(outbox_writer=writer)
    session = MagicMock()

    # Not found -> ResourceNotFoundError
    session.get.return_value = None
    with pytest.raises(ResourceNotFoundError):
        service.notify_draft_created(session, actor_id=2, receipt_id=404)

    # Non-DRAFT -> InvalidStateError
    session.get.return_value = SimpleNamespace(id=10, status="CONFIRMED")
    with pytest.raises(InvalidStateError):
        service.notify_draft_created(session, actor_id=2, receipt_id=10)
    writer.append.assert_not_called()

    # Valid DRAFT -> appends outbox event
    draft_obj = SimpleNamespace(id=15, status="DRAFT")
    session.get.return_value = draft_obj
    service.get_receipt = MagicMock(return_value=draft_obj)  # type: ignore[method-assign]
    res = service.notify_draft_created(session, actor_id=2, receipt_id=15)
    assert res is draft_obj
    writer.append.assert_called_once()
    assert writer.append.call_args.kwargs["payload"] == {
        "schema_version": 1,
        "receipt_id": 15,
    }
