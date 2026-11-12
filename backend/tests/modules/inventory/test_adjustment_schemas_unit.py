"""Unit tests for Inventory Adjustment Pydantic schemas (T04A758)."""

import pytest
from pydantic import ValidationError

from app.modules.inventory.schemas import (
    MAX_STOCK_QUANTITY,
    AdjustRequest,
    AdjustResponse,
)


def test_adjust_request_valid() -> None:
    req = AdjustRequest(
        counted_quantity=10,
        expected_stock_version=2,
        reason="Đếm thực tế định kỳ",
    )
    assert req.counted_quantity == 10
    assert req.expected_stock_version == 2
    assert req.reason == "Đếm thực tế định kỳ"


def test_adjust_request_trims_whitespace_reason() -> None:
    req = AdjustRequest(
        counted_quantity=0,
        expected_stock_version=0,
        reason="   Hàng bị vỡ toàn bộ   ",
    )
    assert req.reason == "Hàng bị vỡ toàn bộ"


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {
            "counted_quantity": -1,
            "expected_stock_version": 0,
            "reason": "Valid",
        },
        {
            "counted_quantity": MAX_STOCK_QUANTITY + 1,
            "expected_stock_version": 0,
            "reason": "Valid",
        },
        {
            "counted_quantity": 10,
            "expected_stock_version": -1,
            "reason": "Valid",
        },
        {"counted_quantity": 10, "expected_stock_version": 0, "reason": ""},
        {"counted_quantity": 10, "expected_stock_version": 0, "reason": "   "},
        {
            "counted_quantity": 10,
            "expected_stock_version": 0,
            "reason": "Valid",
            "extra": "forbidden",
        },
    ],
)
def test_adjust_request_invalid_inputs(invalid_payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AdjustRequest.model_validate(invalid_payload)


def test_adjust_response_valid() -> None:
    resp = AdjustResponse(
        product_id=1,
        quantity=5,
        stock_version=2,
        audit_id=10,
        movement_created=True,
    )
    assert resp.product_id == 1
    assert resp.quantity == 5
    assert resp.stock_version == 2
    assert resp.audit_id == 10
    assert resp.movement_created is True


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {
            "product_id": 0,
            "quantity": 5,
            "stock_version": 1,
            "audit_id": 1,
            "movement_created": True,
        },
        {
            "product_id": 1,
            "quantity": -1,
            "stock_version": 1,
            "audit_id": 1,
            "movement_created": True,
        },
        {
            "product_id": 1,
            "quantity": 5,
            "stock_version": -1,
            "audit_id": 1,
            "movement_created": True,
        },
        {
            "product_id": 1,
            "quantity": 5,
            "stock_version": 1,
            "audit_id": 0,
            "movement_created": True,
        },
        {
            "product_id": 1,
            "quantity": 5,
            "stock_version": 1,
            "audit_id": 1,
            "movement_created": "not-bool",
        },
    ],
)
def test_adjust_response_invalid_inputs(invalid_payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AdjustResponse.model_validate(invalid_payload)
