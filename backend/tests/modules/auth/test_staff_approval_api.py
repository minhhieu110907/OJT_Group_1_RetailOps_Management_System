"""HTTP contract tests for ADMIN Staff approval endpoints."""

from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidStateError, ResourceNotFoundError
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.approval_router import get_staff_approval_service
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User
from app.modules.auth.schemas import ApprovalPage, ApprovalRead


def settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
    )


def principal(role: str) -> CurrentPrincipal:
    now = datetime(2026, 11, 11, 8, 0)
    return CurrentPrincipal(
        user=User(
            id=1 if role == "ADMIN" else 2,
            email_normalized=f"{role.lower()}@example.com",
            password_hash="hash",
            role=role,
            status="ACTIVE",
            admin_slot=1 if role == "ADMIN" else None,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        ),
        session_id=uuid4(),
    )


class FakeApprovalService:
    def list(
        self, _session: object, *, status: str | None, page: int, page_size: int
    ) -> ApprovalPage:
        item = ApprovalRead(
            id=10,
            user_id=2,
            attempt_no=1,
            status=status or "PENDING",
            requested_at=datetime(2026, 11, 11, 8, 0),
            decided_by=None,
            decided_at=None,
            decision_reason=None,
        )
        return ApprovalPage(items=[item], total=1, page=page, page_size=page_size)

    def decide(
        self,
        _session: object,
        *,
        actor_id: int,
        approval_id: int,
        decision: str,
        reason: str | None,
    ) -> ApprovalRead:
        if approval_id == 404:
            raise ResourceNotFoundError()
        if approval_id == 409:
            raise InvalidStateError()
        return ApprovalRead(
            id=approval_id,
            user_id=2,
            attempt_no=1,
            status=decision,
            requested_at=datetime(2026, 11, 11, 8, 0),
            decided_by=actor_id,
            decided_at=datetime(2026, 11, 11, 9, 0),
            decision_reason=reason,
        )


def application(role: str | None = "ADMIN") -> object:
    config = settings()
    app = create_app(config)
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[get_db_session] = lambda: object()
    app.dependency_overrides[get_staff_approval_service] = FakeApprovalService
    if role is not None:
        app.dependency_overrides[get_current_principal] = lambda: principal(role)
    return app


@pytest.mark.anyio
async def test_approval_endpoints_enforce_authentication_and_admin_role() -> None:
    for role, expected in ((None, 401), ("STAFF", 403)):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application(role)),
            base_url="http://test",
        ) as client:
            for method, path, kwargs in (
                ("GET", "/api/v1/staff-approvals", {}),
                ("POST", "/api/v1/staff-approvals/10/approve", {}),
                (
                    "POST",
                    "/api/v1/staff-approvals/10/reject",
                    {"json": {"reason": "Không đạt"}},
                ),
            ):
                response = await client.request(method, path, **kwargs)
                assert response.status_code == expected


@pytest.mark.anyio
async def test_approval_api_success_errors_filter_and_validation() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application()), base_url="http://test"
    ) as client:
        listed = await client.get(
            "/api/v1/staff-approvals?status=APPROVED&page=2&page_size=5"
        )
        approved = await client.post("/api/v1/staff-approvals/10/approve")
        rejected = await client.post(
            "/api/v1/staff-approvals/11/reject", json={"reason": " Không đạt "}
        )
        missing = await client.post("/api/v1/staff-approvals/404/approve")
        stale = await client.post("/api/v1/staff-approvals/409/approve")
        bad_extra = await client.post(
            "/api/v1/staff-approvals/10/reject",
            json={"reason": "x", "unexpected": True},
        )
        bad_blank = await client.post(
            "/api/v1/staff-approvals/10/reject", json={"reason": "   "}
        )

    assert listed.status_code == 200
    assert listed.json()["page"] == 2
    assert listed.json()["items"][0]["status"] == "APPROVED"
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert rejected.status_code == 200
    assert rejected.json()["decision_reason"] == "Không đạt"
    assert missing.status_code == 404
    assert stale.status_code == 409
    assert stale.json()["code"] == "INVALID_STATE"
    assert bad_extra.status_code == bad_blank.status_code == 422
