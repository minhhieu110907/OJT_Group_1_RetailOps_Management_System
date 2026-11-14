"""HTTP contract and schema tests for order history and detail endpoints."""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
import yaml
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceNotFoundError
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User
from app.modules.sales.models import OrderStatus
from app.modules.sales.repository import OrderRepository
from app.modules.sales.router import get_order, get_order_read_service, list_orders
from app.modules.sales.router import router as sales_router
from app.modules.sales.schemas import OrderLineRead, OrderPage, OrderRead
from app.modules.sales.service import OrderQuery, OrderReadService


def test_generated_openapi_matches_frozen_order_contract() -> None:
    """Validate that sales router OpenAPI definition matches contracts/openapi.yaml."""
    app = FastAPI()
    app.include_router(sales_router)
    runtime_openapi = app.openapi()

    openapi_path = (Path(__file__).parents[4] / "contracts" / "openapi.yaml").resolve()
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


class FakeOrderReadService:
    def __init__(self, raise_error: Exception | None = None) -> None:
        self.raise_error = raise_error
        self.last_filters: OrderQuery | None = None

    def list(
        self,
        session: object,
        *,
        actor_id: int,
        actor_role: str,
        filters: OrderQuery,
    ) -> OrderPage:
        del session, actor_id, actor_role
        if self.raise_error:
            raise self.raise_error
        self.last_filters = filters
        return OrderPage(
            items=[
                OrderRead(
                    id=10,
                    status=filters.status or "COMPLETED",
                    total_vnd=50_000,
                    created_by=1,
                    sold_at=datetime(2026, 11, 14, 3, 0, tzinfo=UTC),
                    cancelled_by=None,
                    cancelled_at=None,
                    cancel_reason=None,
                    items=(
                        OrderLineRead(
                            product_id=5,
                            sku_snapshot="SKU-005",
                            product_name_snapshot="Cà phê",
                            quantity=2,
                            unit_price_vnd=25_000,
                            line_total_vnd=50_000,
                        ),
                    ),
                )
            ],
            total=1,
            page=filters.page,
            page_size=filters.page_size,
        )

    def get(
        self,
        session: object,
        *,
        actor_id: int,
        actor_role: str,
        order_id: int,
    ) -> OrderRead:
        del session, actor_id, actor_role
        if self.raise_error:
            raise self.raise_error
        if order_id == 999:
            raise ResourceNotFoundError("Không tìm thấy đơn hàng.")
        return OrderRead(
            id=order_id,
            status="COMPLETED",
            total_vnd=50_000,
            created_by=1,
            sold_at=datetime(2026, 11, 14, 3, 0, tzinfo=UTC),
            cancelled_by=None,
            cancelled_at=None,
            cancel_reason=None,
            items=(
                OrderLineRead(
                    product_id=5,
                    sku_snapshot="SKU-005",
                    product_name_snapshot="Cà phê",
                    quantity=2,
                    unit_price_vnd=25_000,
                    line_total_vnd=50_000,
                ),
            ),
        )


def make_test_app(
    service: object | None = None,
    *,
    authenticated: bool = True,
    user_status: str = "ACTIVE",
    user_role: str = "STAFF",
) -> FastAPI:
    config = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        idempotency_secret=SecretStr("i" * 32),
    )
    app = create_app(config)
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    if service is not None:
        app.dependency_overrides[get_order_read_service] = lambda: service
    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=User(
                id=1,
                email_normalized="tester@example.com",
                password_hash="hash",
                role=user_role,
                status=user_status,
                admin_slot=1 if user_role == "ADMIN" else None,
                last_reapplied_at=None,
                created_at=datetime(2026, 11, 14),
                updated_at=datetime(2026, 11, 14),
            ),
            session_id=uuid4(),
        )
    return app


@pytest.mark.anyio
async def test_list_orders_http_unauthenticated_returns_401() -> None:
    app = make_test_app(FakeOrderReadService(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders")
    assert res.status_code == 401


@pytest.mark.anyio
async def test_list_orders_http_inactive_user_returns_403() -> None:
    app = make_test_app(FakeOrderReadService(), user_status="PENDING")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders")
    assert res.status_code == 403


@pytest.mark.anyio
async def test_list_orders_http_real_service_date_overflow_422() -> None:
    """Verify real OrderReadService catches date.max and returns 422 without repo."""
    mock_repo = MagicMock(spec=OrderRepository)
    real_service = OrderReadService(repository=mock_repo)
    app = make_test_app(service=real_service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders?to_date=9999-12-31")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "vượt giới hạn" in body["message"]
    mock_repo.list_orders.assert_not_called()


@pytest.mark.anyio
async def test_list_orders_http_real_service_from_date_greater_than_to_date_422() -> (
    None
):
    """Verify real OrderReadService catches from_date > to_date without repo."""
    mock_repo = MagicMock(spec=OrderRepository)
    real_service = OrderReadService(repository=mock_repo)
    app = make_test_app(service=real_service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders?from_date=2026-11-20&to_date=2026-11-10")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "from_date must not be greater than to_date" in body["message"]
    mock_repo.list_orders.assert_not_called()


@pytest.mark.anyio
async def test_list_orders_http_real_service_valid_query_delegates_to_repo() -> None:
    """Verify real OrderReadService translates dates to UTC and calls repository."""
    mock_repo = MagicMock(spec=OrderRepository)
    mock_repo.list_orders.return_value = ([], 0)
    real_service = OrderReadService(repository=mock_repo)
    app = make_test_app(service=real_service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/orders?page=2&page_size=15&status=COMPLETED&from_date=2026-11-10&to_date=2026-11-14&search=SKU-TEST"
        )

    assert res.status_code == 200
    body = res.json()
    assert body == {"items": [], "total": 0, "page": 2, "page_size": 15}
    mock_repo.list_orders.assert_called_once()
    call_kwargs = mock_repo.list_orders.call_args.kwargs
    assert call_kwargs["status"] == "COMPLETED"
    # Vietnam (+07) 2026-11-10 00:00:00 -> 2026-11-09 17:00:00 UTC
    assert call_kwargs["sold_from_utc"] == datetime(2026, 11, 9, 17, 0, 0)
    # Vietnam (+07) 2026-11-15 00:00:00 -> 2026-11-14 17:00:00 UTC
    assert call_kwargs["sold_to_utc_exclusive"] == datetime(2026, 11, 14, 17, 0, 0)
    assert call_kwargs["offset"] == 15
    assert call_kwargs["limit"] == 15
    assert call_kwargs["sku_search"] == "SKU-TEST"


@pytest.mark.anyio
async def test_list_orders_http_schema_validations_rejected_before_service() -> None:
    """Verify schema-level invalid parameters are rejected before repository."""
    mock_repo = MagicMock(spec=OrderRepository)
    real_service = OrderReadService(repository=mock_repo)
    app = make_test_app(service=real_service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for bad_url in [
            "/api/v1/orders?page=0",
            "/api/v1/orders?page_size=101",
            "/api/v1/orders?status=PENDING",
        ]:
            res = await client.get(bad_url)
            assert res.status_code == 422
    mock_repo.list_orders.assert_not_called()


@pytest.mark.anyio
async def test_list_orders_http_success_200() -> None:
    service = FakeOrderReadService()
    app = make_test_app(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders?page=1&page_size=10&status=COMPLETED")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == 10
    assert body["items"][0]["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_get_order_http_unauthenticated_returns_401() -> None:
    app = make_test_app(FakeOrderReadService(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders/10")
    assert res.status_code == 401


@pytest.mark.anyio
async def test_get_order_http_inactive_user_returns_403() -> None:
    app = make_test_app(FakeOrderReadService(), user_status="INACTIVE")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders/10")
    assert res.status_code == 403


@pytest.mark.anyio
async def test_get_order_http_validation_error_422() -> None:
    app = make_test_app(FakeOrderReadService())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders/0")
    assert res.status_code == 422


@pytest.mark.anyio
async def test_get_order_http_not_found_404() -> None:
    app = make_test_app(FakeOrderReadService())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders/999")
    assert res.status_code == 404
    assert res.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.anyio
async def test_get_order_http_success_200() -> None:
    app = make_test_app(FakeOrderReadService())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders/10")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == 10
    assert body["status"] == "COMPLETED"
    assert body["total_vnd"] == 50_000
    # Verify ISO-8601 UTC timestamp format
    assert body["sold_at"].endswith("Z") or "+00:00" in body["sold_at"]
    assert len(body["items"]) == 1
    assert body["items"][0]["sku_snapshot"] == "SKU-005"
