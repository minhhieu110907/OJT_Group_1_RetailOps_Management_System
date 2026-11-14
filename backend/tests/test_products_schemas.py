"""Unit tests for Product Pydantic schemas and input normalization."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.products.models import CatalogStatus
from app.modules.products.schemas import (
    MAX_PRODUCT_SEARCH_LENGTH,
    ProductCreateRequest,
    ProductRead,
    ProductSortOrder,
    ProductStatusUpdateRequest,
    ProductUpdateRequest,
    normalize_search_query,
)


def test_product_create_request_normalizes_and_validates_fields() -> None:
    payload = ProductCreateRequest(
        sku="  SKU-001  ",
        name="  Nước khoáng thiên nhiên  ",
        category_id=2,
        sale_price_vnd=15_000,
    )
    assert payload.sku == "SKU-001"
    assert payload.name == "Nước khoáng thiên nhiên"
    assert payload.category_id == 2
    assert payload.sale_price_vnd == 15_000


@pytest.mark.parametrize(
    "bad_payload",
    [
        {
            "sku": "",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "   ",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "SKU CÓ DẤU",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "SKU WITH SPACE",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "A" * 65,
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "SKU-01",
            "name": "   ",
            "category_id": 1,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "SKU-01",
            "name": "N" * 161,
            "category_id": 1,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "SKU-01",
            "name": "Sản phẩm A",
            "category_id": 0,
            "sale_price_vnd": 10_000,
        },
        {
            "sku": "SKU-01",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 0,
        },
        {
            "sku": "SKU-01",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": -5_000,
        },
        {
            "sku": "SKU-01",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000.5,
        },
        {
            "sku": "SKU-01",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000,
            "quantity": 10,
        },
        {
            "sku": "SKU-01",
            "name": "Sản phẩm A",
            "category_id": 1,
            "sale_price_vnd": 10_000,
            "stock_version": 1,
        },
    ],
)
def test_product_create_request_rejects_invalid_or_extra_fields(
    bad_payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProductCreateRequest(**bad_payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "forbidden_field",
    ["quantity", "stock_version", "status", "unit_cost_vnd", "cost"],
)
def test_product_update_request_forbids_stock_and_cost_fields(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError):
        ProductUpdateRequest(**{forbidden_field: 1})  # type: ignore[arg-type]


def test_product_status_update_request_accepts_only_active_or_inactive() -> None:
    req = ProductStatusUpdateRequest(status=CatalogStatus.INACTIVE)
    assert req.status == CatalogStatus.INACTIVE

    with pytest.raises(ValidationError):
        ProductStatusUpdateRequest(status="DELETED")  # type: ignore[arg-type]


def test_product_read_whitelists_exact_10_fields_without_cost() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    dto = ProductRead(
        id=1,
        category_id=2,
        sku="SKU-001",
        name="Trà xanh",
        status=CatalogStatus.ACTIVE,
        sale_price_vnd=12_000,
        quantity=0,
        stock_version=0,
        created_at=now,
        updated_at=now,
    )
    dumped = dto.model_dump()
    assert set(dumped.keys()) == {
        "id",
        "category_id",
        "sku",
        "name",
        "status",
        "sale_price_vnd",
        "quantity",
        "stock_version",
        "created_at",
        "updated_at",
    }
    assert "unit_cost_vnd" not in dumped
    assert "cost" not in dumped


def test_product_sort_order_whitelist_and_rejection() -> None:
    assert [member.value for member in ProductSortOrder] == [
        "quantity_asc",
        "restock_first",
        "name_asc",
        "name_desc",
        "sku_asc",
        "sku_desc",
        "created_desc",
    ]
    for bad_sort in (
        "id_asc",
        "price_asc",
        "created_asc",
        "quantity_desc",
        "name; DROP TABLE products",
        "",
    ):
        with pytest.raises(ValueError):
            ProductSortOrder(bad_sort)


def test_normalize_search_query_trims_and_enforces_max_length() -> None:
    assert normalize_search_query(None) is None
    assert normalize_search_query("") is None
    assert normalize_search_query("   ") is None
    assert normalize_search_query("  Cà phê sữa  ") == "Cà phê sữa"
    assert (
        normalize_search_query("a" * MAX_PRODUCT_SEARCH_LENGTH)
        == "a" * MAX_PRODUCT_SEARCH_LENGTH
    )

    with pytest.raises(ValueError, match="must not exceed 100 characters"):
        normalize_search_query("a" * (MAX_PRODUCT_SEARCH_LENGTH + 1))
