from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User
from app.modules.sales.router import get_checkout_service
from app.modules.sales.schemas import OrderLineRead, OrderRead


def settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        idempotency_secret=SecretStr("i" * 32),
    )


def principal(*, status: str = "ACTIVE", role: str = "STAFF") -> CurrentPrincipal:
    now = datetime(2026, 11, 12, 9, 0)
    return CurrentPrincipal(
        user=User(
            id=7,
            email_normalized="staff@example.com",
            password_hash="hash",
            role=role,
            status=status,
            admin_slot=1 if role == "ADMIN" else None,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        ),
        session_id=uuid4(),
    )


class FakeCheckoutService:
    def __init__(self) -> None:
        self.actor_id: int | None = None
        self.key: str | None = None

    def checkout(self, session: object, **kwargs: object) -> OrderRead:
        del session
        self.actor_id = kwargs["actor_id"]  # type: ignore[assignment]
        self.key = kwargs["idempotency_key"]  # type: ignore[assignment]
        item = kwargs["items"][0]  # type: ignore[index]
        return OrderRead(
            id=91,
            status="COMPLETED",
            total_vnd=item.quantity * 12_000,
            created_by=self.actor_id,
            sold_at=datetime(2026, 11, 12, 9, 30, tzinfo=UTC),
            cancelled_by=None,
            cancelled_at=None,
            cancel_reason=None,
            items=[
                OrderLineRead(
                    product_id=item.product_id,
                    sku_snapshot="SKU-1",
                    product_name_snapshot="Product 1",
                    quantity=item.quantity,
                    unit_price_vnd=12_000,
                    line_total_vnd=item.quantity * 12_000,
                )
            ],
        )


def application(
    service: FakeCheckoutService,
    *,
    user_status: str = "ACTIVE",
    authenticated: bool = True,
):
    config = settings()
    app = create_app(config)
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[get_db_session] = lambda: object()
    app.dependency_overrides[get_checkout_service] = lambda: service
    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: principal(
            status=user_status
        )
    return app


def payload(**line_overrides: object) -> dict[str, object]:
    item = {"product_id": 1, "quantity": 2, "viewed_unit_price_vnd": 12_000}
    item.update(line_overrides)
    return {"items": [item]}


@pytest.mark.anyio
async def test_checkout_accepts_active_staff_and_uses_authenticated_actor() -> None:
    service = FakeCheckoutService()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(service)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json=payload(),
        )

    assert response.status_code == 201
    assert response.json()["id"] == 91
    assert service.actor_id == 7
    assert service.key == "checkout-key-0001"


@pytest.mark.anyio
async def test_checkout_requires_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=application(FakeCheckoutService(), authenticated=False)
        ),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json=payload(),
        )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_checkout_rejects_inactive_user() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=application(FakeCheckoutService(), user_status="PENDING")
        ),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json=payload(),
        )

    assert response.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [payload(quantity=0), payload(quantity=1.5), {**payload(), "actor_id": 99}],
)
async def test_checkout_rejects_invalid_or_extra_input(body: dict[str, object]) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(FakeCheckoutService())),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/checkout",
            headers={"Idempotency-Key": "checkout-key-0001"},
            json=body,
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_checkout_requires_valid_idempotency_key() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(FakeCheckoutService())),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/orders/checkout", json=payload())

    assert response.status_code == 422
