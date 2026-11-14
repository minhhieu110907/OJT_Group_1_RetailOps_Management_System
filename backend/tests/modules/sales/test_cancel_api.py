from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    IdempotencyKeyReusedError,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User
from app.modules.sales.router import get_order_service
from app.modules.sales.schemas import OrderRead


class FakeOrderService:
    def __init__(self) -> None:
        self.arguments: dict[str, object] | None = None

    def cancel(self, session: object, **kwargs: object) -> OrderRead:
        del session
        self.arguments = kwargs
        return OrderRead(
            id=kwargs["order_id"],
            status="CANCELLED",
            total_vnd=20_000,
            created_by=7,
            sold_at=datetime(2026, 11, 14, 3, 0, tzinfo=UTC),
            cancelled_by=kwargs["actor_id"],
            cancelled_at=datetime(2026, 11, 14, 3, 10, tzinfo=UTC),
            cancel_reason=kwargs["reason"],
            items=[],
        )


class ErrorOrderService(FakeOrderService):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def cancel(self, session: object, **kwargs: object) -> OrderRead:
        del session, kwargs
        raise self.error


def application(
    service: FakeOrderService, *, authenticated: bool = True, status="ACTIVE"
):
    settings = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        idempotency_secret=SecretStr("i" * 32),
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = lambda: object()
    app.dependency_overrides[get_order_service] = lambda: service
    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=User(
                id=7,
                email_normalized="staff@example.com",
                password_hash="hash",
                role="STAFF",
                status=status,
                admin_slot=None,
                last_reapplied_at=None,
                created_at=datetime(2026, 11, 14),
                updated_at=datetime(2026, 11, 14),
            ),
            session_id=uuid4(),
        )
    return app


@pytest.mark.anyio
async def test_cancel_uses_authenticated_actor_and_normalized_reason() -> None:
    service = FakeOrderService()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(service)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/91/cancel",
            headers={"Idempotency-Key": "cancel-order-key-0001"},
            json={"reason": "  Customer mistake  "},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert service.arguments == {
        "actor_id": 7,
        "actor_role": "STAFF",
        "order_id": 91,
        "reason": "Customer mistake",
        "idempotency_key": "cancel-order-key-0001",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("authenticated", "user_status", "expected"),
    [(False, "ACTIVE", 401), (True, "PENDING_APPROVAL", 403)],
)
async def test_cancel_requires_active_authentication(
    authenticated: bool, user_status: str, expected: int
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=application(
                FakeOrderService(), authenticated=authenticated, status=user_status
            )
        ),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/91/cancel",
            headers={"Idempotency-Key": "cancel-order-key-0002"},
            json={"reason": "Reason"},
        )
    assert response.status_code == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [{"reason": "   "}, {"reason": "x" * 501}, {"reason": "ok", "actor_id": 9}],
)
async def test_cancel_rejects_invalid_reason_or_client_actor(body) -> None:
    service = FakeOrderService()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(service)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/91/cancel",
            headers={"Idempotency-Key": "cancel-order-key-0003"},
            json=body,
        )
    assert response.status_code == 422
    assert service.arguments is None


@pytest.mark.anyio
async def test_static_checkout_route_is_not_captured_as_order_id() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(FakeOrderService())),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/checkout",
            headers={"Idempotency-Key": "checkout-route-key-0001"},
            json={"reason": "not checkout payload"},
        )
    assert response.status_code == 422
    details = response.json()["details"]
    assert not any(item["field"] == "path.order_id" for item in details)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ResourceNotFoundError(), 404, "RESOURCE_NOT_FOUND"),
        (InvalidStateError(), 409, "INVALID_STATE"),
        (IdempotencyKeyReusedError(), 409, "IDEMPOTENCY_KEY_REUSED"),
    ],
)
async def test_cancel_returns_sanitized_business_error_envelope(
    error: Exception, status_code: int, code: str
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(ErrorOrderService(error))),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/orders/91/cancel",
            headers={"Idempotency-Key": "cancel-order-key-0004"},
            json={"reason": "Reason"},
        )
    assert response.status_code == status_code
    assert response.json().keys() == {"code", "message", "details"}
    assert response.json()["code"] == code
