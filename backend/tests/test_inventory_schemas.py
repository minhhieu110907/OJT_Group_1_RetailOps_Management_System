"""Unit tests for Inventory schemas validation and constraints."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.modules.inventory.schemas import InventoryPage, InventoryRead


def test_inventory_read_valid() -> None:
    """Test valid InventoryRead instantiation."""
    now = datetime(2026, 11, 11, 10, 0, 0)
    data = {
        "product_id": 1,
        "sku": "SKU-001",
        "name": "Cà phê Robusta",
        "category_id": 2,
        "status": "ACTIVE",
        "quantity": 100,
        "stock_version": 1,
        "first_stocked_at": now,
    }
    item = InventoryRead.model_validate(data)
    assert item.product_id == 1
    assert item.sku == "SKU-001"
    assert item.name == "Cà phê Robusta"
    assert item.category_id == 2
    assert item.status == "ACTIVE"
    assert item.quantity == 100
    assert item.stock_version == 1
    assert item.first_stocked_at == now


def test_inventory_read_null_first_stocked_at() -> None:
    """Test first_stocked_at can be None for items never stocked."""
    data = {
        "product_id": 10,
        "sku": "SKU-010",
        "name": "Sản phẩm chưa có tồn",
        "category_id": 1,
        "status": "ACTIVE",
        "quantity": 0,
        "stock_version": 0,
        "first_stocked_at": None,
    }
    item = InventoryRead.model_validate(data)
    assert item.first_stocked_at is None
    assert item.quantity == 0
    assert item.stock_version == 0


@pytest.mark.parametrize(
    "invalid_field,invalid_value",
    [
        ("product_id", 0),
        ("product_id", -1),
        ("category_id", 0),
        ("category_id", -5),
        ("quantity", -1),
        ("stock_version", -1),
        ("status", "DELETED"),
        ("status", "ARCHIVED"),
    ],
)
def test_inventory_read_invalid_bounds(
    invalid_field: str, invalid_value: object
) -> None:
    """Test boundary validation rejects invalid numeric ranges or status enums."""
    valid_data = {
        "product_id": 1,
        "sku": "SKU-001",
        "name": "Test Product",
        "category_id": 1,
        "status": "ACTIVE",
        "quantity": 10,
        "stock_version": 0,
        "first_stocked_at": None,
    }
    invalid_data = {**valid_data, invalid_field: invalid_value}
    with pytest.raises(ValidationError):
        InventoryRead.model_validate(invalid_data)


def test_inventory_read_extra_fields_forbidden() -> None:
    """Test that extra fields like cost_price or sale_price are strictly forbidden."""
    data = {
        "product_id": 1,
        "sku": "SKU-001",
        "name": "Test Product",
        "category_id": 1,
        "status": "ACTIVE",
        "quantity": 10,
        "stock_version": 0,
        "first_stocked_at": None,
        "cost_price": 50000,
    }
    with pytest.raises(ValidationError) as exc_info:
        InventoryRead.model_validate(data)
    assert "Extra inputs are not permitted" in str(exc_info.value)

    data_sale = {
        "product_id": 1,
        "sku": "SKU-001",
        "name": "Test Product",
        "category_id": 1,
        "status": "ACTIVE",
        "quantity": 10,
        "stock_version": 0,
        "first_stocked_at": None,
        "sale_price_vnd": 80000,
    }
    with pytest.raises(ValidationError) as exc_info:
        InventoryRead.model_validate(data_sale)
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_inventory_page_valid() -> None:
    """Test valid InventoryPage creation."""
    item = InventoryRead(
        product_id=1,
        sku="SKU-001",
        name="Test Product",
        category_id=1,
        status="ACTIVE",
        quantity=5,
        stock_version=1,
        first_stocked_at=None,
    )
    page = InventoryPage(items=[item], total=1, page=1, page_size=20)
    assert len(page.items) == 1
    assert page.total == 1
    assert page.page == 1
    assert page.page_size == 20


@pytest.mark.parametrize(
    "invalid_field,invalid_value",
    [
        ("total", -1),
        ("page", 0),
        ("page", -1),
        ("page_size", 0),
        ("page_size", 101),
    ],
)
def test_inventory_page_invalid_bounds(
    invalid_field: str, invalid_value: object
) -> None:
    """Test InventoryPage pagination boundary constraints."""
    data = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }
    data[invalid_field] = invalid_value
    with pytest.raises(ValidationError):
        InventoryPage.model_validate(data)


def test_inventory_page_extra_fields_forbidden() -> None:
    """Test InventoryPage rejects unexpected attributes."""
    data = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "unexpected": "value",
    }
    with pytest.raises(ValidationError):
        InventoryPage.model_validate(data)
