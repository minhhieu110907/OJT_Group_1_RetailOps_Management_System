"""Unit tests for Inventory schemas validation and constraints."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.modules.inventory.schemas import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    InventoryPage,
    InventoryRead,
    LowStockItem,
    LowStockPage,
    StockMovementAdminPage,
    StockMovementAdminRead,
    StockMovementPage,
    StockMovementRead,
)


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


# ---------------------------------------------------------------------------
# Low-stock warning schema tests
# ---------------------------------------------------------------------------


def test_low_stock_item_valid() -> None:
    """Test LowStockItem initialization and default threshold."""
    item = LowStockItem(
        product_id=1,
        sku="SKU-001",
        name="Cà phê Robusta",
        quantity=3,
    )
    assert item.product_id == 1
    assert item.sku == "SKU-001"
    assert item.name == "Cà phê Robusta"
    assert item.quantity == 3
    assert item.threshold == DEFAULT_LOW_STOCK_THRESHOLD
    assert item.threshold == 5


def test_low_stock_item_extra_fields_forbidden() -> None:
    """Test LowStockItem strictly forbids unexpected/cost fields."""
    data = {
        "product_id": 1,
        "sku": "SKU-001",
        "name": "Cà phê Robusta",
        "quantity": 3,
        "cost_price": 20000,
    }
    with pytest.raises(ValidationError) as exc_info:
        LowStockItem.model_validate(data)
    assert "Extra inputs are not permitted" in str(exc_info.value)


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
def test_low_stock_page_invalid_bounds(
    invalid_field: str, invalid_value: object
) -> None:
    """Test LowStockPage pagination bounds."""
    data = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }
    data[invalid_field] = invalid_value
    with pytest.raises(ValidationError):
        LowStockPage.model_validate(data)


# ---------------------------------------------------------------------------
# Stock movement schemas tests
# ---------------------------------------------------------------------------


def test_stock_movement_read_valid() -> None:
    """Test safe STAFF StockMovementRead initialization."""
    now = datetime(2026, 11, 11, 10, 0, 0)
    data = {
        "id": 100,
        "product_id": 5,
        "sku": "SKU-TEA-001",
        "kind": "PURCHASE_CONFIRM",
        "quantity_before": 10,
        "quantity_after": 50,
        "stock_version_after": 2,
        "reference_id": 12,
        "occurred_at": now,
    }
    item = StockMovementRead.model_validate(data)
    assert item.id == 100
    assert item.product_id == 5
    assert item.kind == "PURCHASE_CONFIRM"
    assert item.reference_id == 12
    assert not hasattr(item, "actor_id")
    assert not hasattr(item, "adjustment_reason")


def test_stock_movement_read_forbids_actor_and_prices() -> None:
    """Test StockMovementRead forbids actor_id, adjustment_reason, and prices."""
    now = datetime(2026, 11, 11, 10, 0, 0)
    base_data = {
        "id": 100,
        "product_id": 5,
        "sku": "SKU-TEA-001",
        "kind": "ADJUSTMENT",
        "quantity_before": 10,
        "quantity_after": 8,
        "stock_version_after": 3,
        "reference_id": 5,
        "occurred_at": now,
    }

    # Forbids actor_id
    with pytest.raises(ValidationError) as exc_actor:
        StockMovementRead.model_validate({**base_data, "actor_id": 1})
    assert "Extra inputs are not permitted" in str(exc_actor.value)

    # Forbids unit_cost_vnd
    with pytest.raises(ValidationError) as exc_cost:
        StockMovementRead.model_validate({**base_data, "unit_cost_vnd": 25000})
    assert "Extra inputs are not permitted" in str(exc_cost.value)


def test_stock_movement_admin_read_valid() -> None:
    """Test audited ADMIN StockMovementAdminRead initialization."""
    now = datetime(2026, 11, 11, 10, 0, 0)
    data = {
        "id": 101,
        "product_id": 5,
        "sku": "SKU-TEA-001",
        "kind": "ADJUSTMENT",
        "quantity_before": 10,
        "quantity_after": 8,
        "stock_version_after": 3,
        "reference_id": 5,
        "occurred_at": now,
        "actor_id": 42,
        "adjustment_reason": "Vỡ bao bì khi sắp xếp kho",
    }
    item = StockMovementAdminRead.model_validate(data)
    assert item.actor_id == 42
    assert item.adjustment_reason == "Vỡ bao bì khi sắp xếp kho"


def test_stock_movement_admin_read_forbids_cost_prices() -> None:
    """Test StockMovementAdminRead strictly forbids cost prices."""
    now = datetime(2026, 11, 11, 10, 0, 0)
    data = {
        "id": 101,
        "product_id": 5,
        "sku": "SKU-TEA-001",
        "kind": "ADJUSTMENT",
        "quantity_before": 10,
        "quantity_after": 8,
        "stock_version_after": 3,
        "reference_id": 5,
        "occurred_at": now,
        "actor_id": 42,
        "adjustment_reason": "Vỡ bao bì khi sắp xếp kho",
        "cost_price": 50000,
    }
    with pytest.raises(ValidationError) as exc_info:
        StockMovementAdminRead.model_validate(data)
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_stock_movement_pages_valid() -> None:
    """Test pagination bounds for both STAFF and ADMIN movement pages."""
    staff_page = StockMovementPage(items=[], total=0, page=1, page_size=20)
    assert staff_page.items == []
    assert staff_page.total == 0

    admin_page = StockMovementAdminPage(items=[], total=0, page=1, page_size=20)
    assert admin_page.items == []
    assert admin_page.total == 0
