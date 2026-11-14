"""HTTP contract and schema tests for order history and detail endpoints."""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi import FastAPI
from pydantic import ValidationError

from app.modules.auth.models import User
from app.modules.sales.models import OrderStatus
from app.modules.sales.router import get_order, list_orders, router as sales_router
from app.modules.sales.schemas import OrderLineRead, OrderPage, OrderRead
from app.modules.sales.service import OrderQuery, OrderReadService


def test_generated_openapi_matches_frozen_order_contract() -> None:
    """Validate that sales router OpenAPI definition matches contracts/openapi.yaml."""
    app = FastAPI()
    app.include_router(sales_router)
    runtime_openapi = app.openapi()

    openapi_path = (
        Path(__file__).parents[4] / "contracts" / "openapi.yaml"
    ).resolve()
    frozen = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))

    # 1. Check path /orders (GET)
    assert "/orders" in runtime_openapi["paths"]
    assert "get" in runtime_openapi["paths"]["/orders"]
    get_orders_op = runtime_openapi["paths"]["/orders"]["get"]
    assert "200" in get_orders_op["responses"]
    schema_ref = get_orders_op["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert schema_ref == "#/components/schemas/OrderPage"

    # Check query params on /orders
    runtime_param_names = {p["name"] for p in get_orders_op["parameters"]}
    expected_params = {
        "page",
        "page_size",
        "status",
        "from_date",
        "to_date",
        "search",
    }
    assert expected_params.issubset(runtime_param_names)

    # 2. Check path /orders/{order_id} (GET)
    assert "/orders/{order_id}" in runtime_openapi["paths"]
    assert "get" in runtime_openapi["paths"]["/orders/{order_id}"]
    get_order_op = runtime_openapi["paths"]["/orders/{order_id}"]["get"]
    assert "200" in get_order_op["responses"]
    order_ref = get_order_op["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert order_ref == "#/components/schemas/OrderRead"

    # 3. Check Schemas: OrderPage, OrderRead, OrderLineRead
    schemas = runtime_openapi["components"]["schemas"]
    assert "OrderPage" in schemas
    assert "OrderRead" in schemas
    assert "OrderLineRead" in schemas

    # OrderPage required fields
    frozen_page = frozen["components"]["schemas"]["OrderPage"]
    assert set(schemas["OrderPage"]["required"]) == set(frozen_page["required"])

    # OrderRead required fields
    frozen_order = frozen["components"]["schemas"]["OrderRead"]
    assert set(schemas["OrderRead"]["required"]) == set(frozen_order["required"])


def test_list_orders_router_delegates_to_service() -> None:
    """Verify list_orders route translates queries and calls OrderReadService."""
    mock_service = MagicMock(spec=OrderReadService)
    mock_session = MagicMock()
    mock_user = User(
        id=7,
        email_normalized="staff@example.com",
        password_hash="hash",
        role="STAFF",
        status="ACTIVE",
    )

    expected_page = OrderPage(items=[], total=0, page=2, page_size=15)
    mock_service.list.return_value = expected_page

    result = list_orders(
        current_user=mock_user,
        session=mock_session,
        service=mock_service,
        page=2,
        page_size=15,
        status_filter=OrderStatus.COMPLETED,
        from_date=date(2026, 11, 10),
        to_date=date(2026, 11, 14),
        search="SKU-TEST",
    )

    assert result == expected_page
    mock_service.list.assert_called_once_with(
        mock_session,
        actor_id=7,
        actor_role="STAFF",
        filters=OrderQuery(
            page=2,
            page_size=15,
            status="COMPLETED",
            from_date=date(2026, 11, 10),
            to_date=date(2026, 11, 14),
            search="SKU-TEST",
        ),
    )


def test_get_order_router_delegates_to_service() -> None:
    """Verify get_order route passes order_id to OrderReadService."""
    mock_service = MagicMock(spec=OrderReadService)
    mock_session = MagicMock()
    mock_user = User(
        id=1,
        email_normalized="admin@example.com",
        password_hash="hash",
        role="ADMIN",
        status="ACTIVE",
    )

    expected_order = OrderRead(
        id=88,
        status="COMPLETED",
        total_vnd=50_000,
        created_by=7,
        sold_at=datetime(2026, 11, 14, 3, 0, tzinfo=UTC),
        cancelled_by=None,
        cancelled_at=None,
        cancel_reason=None,
        items=(),
    )
    mock_service.get.return_value = expected_order

    result = get_order(
        order_id=88,
        current_user=mock_user,
        session=mock_session,
        service=mock_service,
    )

    assert result == expected_order
    mock_service.get.assert_called_once_with(
        mock_session,
        actor_id=1,
        actor_role="ADMIN",
        order_id=88,
    )


def test_order_schemas_extra_forbid() -> None:
    """Verify extra='forbid' is enforced on OrderPage, OrderRead, OrderLineRead."""
    # Extra field on OrderLineRead
    with pytest.raises(ValidationError):
        OrderLineRead(
            product_id=1,
            sku_snapshot="SKU-01",
            product_name_snapshot="Prod",
            quantity=1,
            unit_price_vnd=10_000,
            line_total_vnd=10_000,
            extra_field="disallowed",
        )

    # Extra field on OrderRead
    with pytest.raises(ValidationError):
        OrderRead(
            id=1,
            status="COMPLETED",
            total_vnd=10_000,
            created_by=1,
            sold_at=datetime(2026, 11, 14, tzinfo=UTC),
            cancelled_by=None,
            cancelled_at=None,
            cancel_reason=None,
            items=(),
            cost_price_vnd=5_000,  # Disallowed extra field
        )

    # Extra field on OrderPage
    with pytest.raises(ValidationError):
        OrderPage(
            items=[],
            total=0,
            page=1,
            page_size=20,
            extra_info="disallowed",
        )


def test_order_status_enum_values() -> None:
    assert OrderStatus.COMPLETED == "COMPLETED"
    assert OrderStatus.CANCELLED == "CANCELLED"
