"""HTTP contract regression for Bonus Staff account routes."""

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidStateError
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.account_router import get_staff_account_service
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal


def _settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins="http://127.0.0.1:5173",
    )


class StubStaffAccounts:
    def transition(self, *_args, **_kwargs):
        raise InvalidStateError("Transition already applied.")


@pytest.mark.anyio
async def test_admin_account_endpoints_enforce_auth_and_role() -> None:
    app = create_app(_settings())
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_db_session] = lambda: object()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        unauthenticated = await client.post("/api/v1/admin/staff/1/lock")
        assert unauthenticated.status_code == 401
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=SimpleNamespace(id=2, status="ACTIVE", role="STAFF"),
            session_id=uuid4(),
        )
        staff_request = await client.post("/api/v1/admin/staff/1/lock")
        assert staff_request.status_code == 403


@pytest.mark.anyio
async def test_admin_account_conflicts_and_query_schema() -> None:
    app = create_app(_settings())
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_db_session] = lambda: object()
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user=SimpleNamespace(id=1, status="ACTIVE", role="ADMIN"),
        session_id=uuid4(),
    )
    app.dependency_overrides[get_staff_account_service] = StubStaffAccounts
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        conflict = await client.post("/api/v1/admin/staff/2/lock")
        assert conflict.status_code == 409
        invalid_status = await client.get("/api/v1/admin/staff?status=REJECTED")
        assert invalid_status.status_code == 422
        invalid_id = await client.post("/api/v1/admin/staff/0/lock")
        assert invalid_id.status_code == 422
