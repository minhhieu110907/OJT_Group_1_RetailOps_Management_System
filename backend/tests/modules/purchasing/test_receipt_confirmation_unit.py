"""Unit tests for Purchase Receipt confirmation schemas and validation (T04A7DF)."""

import inspect
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.exceptions import DomainValidationError
from app.modules.purchasing import (
    ReceiptConfirmService as ExportedReceiptConfirmService,
)
from app.modules.purchasing.confirm_service import ReceiptConfirmService
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
    service = ReceiptConfirmService()
    dummy_session = SimpleNamespace()
    with pytest.raises(DomainValidationError):
        service.confirm(
            dummy_session,  # type: ignore[arg-type]
            actor_id=1,
            receipt_id=1,
            expected_draft_version=1,
            idempotency_key=bad_key,
        )


def test_receipt_confirm_service_matches_frozen_contract() -> None:
    assert ExportedReceiptConfirmService is ReceiptConfirmService
    sig = inspect.signature(ReceiptConfirmService.confirm)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == [
        "self",
        "session",
        "actor_id",
        "receipt_id",
        "expected_draft_version",
        "idempotency_key",
    ]
    assert params[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for kw_param in params[2:]:
        assert kw_param.kind is inspect.Parameter.KEYWORD_ONLY
