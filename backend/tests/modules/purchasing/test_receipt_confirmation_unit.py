"""Unit tests for Purchase Receipt confirmation schemas and validation (T04A7DF)."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.exceptions import DomainValidationError
from app.modules.purchasing.confirmation_service import ReceiptConfirmationService
from app.modules.purchasing.schemas import MAX_SQL_BIGINT, ReceiptVersionRequest


def test_receipt_version_request_valid() -> None:
    req = ReceiptVersionRequest(expected_draft_version=1)
    assert req.expected_draft_version == 1

    req_max = ReceiptVersionRequest(expected_draft_version=MAX_SQL_BIGINT)
    assert req_max.expected_draft_version == MAX_SQL_BIGINT


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"expected_draft_version": 0},
        {"expected_draft_version": -1},
        {"expected_draft_version": "1"},
        {"expected_draft_version": True},
        {"expected_draft_version": MAX_SQL_BIGINT + 1},
        {"expected_draft_version": 1, "extra_field": "forbidden"},
    ],
)
def test_receipt_version_request_invalid(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReceiptVersionRequest.model_validate(payload)


@pytest.mark.parametrize(
    "bad_key",
    [
        "",
        "   ",
        "too-short-key",
        "a" * 129,
        "invalid key with spaces!",
    ],
)
def test_confirm_receipt_rejects_invalid_idempotency_key(bad_key: str) -> None:
    service = ReceiptConfirmationService()
    dummy_session = SimpleNamespace()
    with pytest.raises(DomainValidationError):
        service.confirm_receipt(
            dummy_session,  # type: ignore[arg-type]
            actor_id=1,
            receipt_id=1,
            expected_draft_version=1,
            idempotency_key=bad_key,
        )
