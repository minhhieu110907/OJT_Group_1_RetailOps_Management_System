"""HTTP API tests for Admin notification endpoints (401, 403, pagination, mark read)."""

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
from app.modules.notifications.dependencies import get_notification_service
from app.modules.notifications.service import NotificationService
from tests.modules.notifications.test_service_unit import (
    AdvancingClock,
    FakeNotificationRepository,
    GuardedFakeSession,
)

ORIGIN = "http://127.0.0.1:5173"


def _test_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )


def _principal(user_id: int, role: str) -> CurrentPrincipal:
    now = datetime(2026, 11, 7, 8, 0, 0)
    user = User(
        id=user_id,
        email_normalized=f"{role.lower()}_{user_id}@example.com",
        password_hash="hash",
        role=role,
        status="ACTIVE",
        admin_slot=1 if role == "ADMIN" else None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    return CurrentPrincipal(user=user, session_id=uuid4())


@pytest.mark.anyio
async def test_all_four_notification_endpoints_reject_unauthenticated_with_401() -> (
    None
):
    settings = _test_settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = GuardedFakeSession

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for method, path, kwargs in (
            ("GET", "/api/v1/admin/notifications", {}),
            ("GET", "/api/v1/admin/notifications/unread-count", {}),
            ("PATCH", "/api/v1/admin/notifications/1/read", {"json": {}}),
            ("PATCH", "/api/v1/admin/notifications/read-all", {"json": {}}),
        ):
            response = await client.request(method, path, **kwargs)
            assert response.status_code == 401
            assert response.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
async def test_all_four_notification_endpoints_reject_staff_with_403() -> None:
    settings = _test_settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = GuardedFakeSession
    app.dependency_overrides[get_current_principal] = lambda: _principal(2, "STAFF")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        for method, path, kwargs in (
            ("GET", "/api/v1/admin/notifications", {}),
            ("GET", "/api/v1/admin/notifications/unread-count", {}),
            ("PATCH", "/api/v1/admin/notifications/1/read", {"json": {}}),
            ("PATCH", "/api/v1/admin/notifications/read-all", {"json": {}}),
        ):
            response = await client.request(method, path, **kwargs)
            assert response.status_code == 403
            assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_admin_notification_endpoints_full_lifecycle_and_validation() -> None:
    settings = _test_settings()
    repo = FakeNotificationRepository()
    clock = AdvancingClock(datetime(2026, 11, 7, 9, 0, 0, tzinfo=UTC))
    service = NotificationService(repository=repo, clock=clock)
    fake_session = GuardedFakeSession()

    n1 = service.create_for_approval(
        fake_session,  # type: ignore[arg-type]
        admin_user_id=1,
        approval_request_id=101,
    )
    n2 = service.create_for_approval(
        fake_session,  # type: ignore[arg-type]
        admin_user_id=1,
        approval_request_id=102,
    )
    other = service.create_for_approval(
        fake_session,  # type: ignore[arg-type]
        admin_user_id=99,
        approval_request_id=999,
    )

    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = lambda: fake_session
    app.dependency_overrides[get_notification_service] = lambda: service
    app.dependency_overrides[get_current_principal] = lambda: _principal(1, "ADMIN")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        list_resp = await client.get("/api/v1/admin/notifications?page=1&page_size=20")
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["total"] == 2
        assert body["page"] == 1
        assert body["page_size"] == 20
        assert [item["id"] for item in body["items"]] == [n2.id, n1.id]
        assert [item["approval_request_id"] for item in body["items"]] == [102, 101]
        for item in body["items"]:
            assert set(item.keys()) == {
                "id",
                "approval_request_id",
                "created_at",
                "read_at",
            }

        count_resp = await client.get("/api/v1/admin/notifications/unread-count")
        assert count_resp.status_code == 200
        assert count_resp.json() == {"count": 2}

        read1 = await client.patch(
            f"/api/v1/admin/notifications/{n1.id}/read",
            json={},
        )
        read2 = await client.patch(
            f"/api/v1/admin/notifications/{n1.id}/read",
            json={},
        )
        assert read1.status_code == 200
        assert read2.status_code == 200
        assert read1.json()["read_at"] is not None
        assert read2.json()["read_at"] == read1.json()["read_at"]

        unread_list = await client.get("/api/v1/admin/notifications?unread_only=true")
        assert unread_list.status_code == 200
        assert [item["id"] for item in unread_list.json()["items"]] == [n2.id]
        assert unread_list.json()["total"] == 1

        for forbidden_id in (other.id, 999999):
            not_found = await client.patch(
                f"/api/v1/admin/notifications/{forbidden_id}/read",
                json={},
            )
            assert not_found.status_code == 404
            assert not_found.json()["code"] == "RESOURCE_NOT_FOUND"

        all1 = await client.patch("/api/v1/admin/notifications/read-all", json={})
        all2 = await client.patch("/api/v1/admin/notifications/read-all", json={})
        assert all1.status_code == 200
        assert all1.json() == {"updated_count": 1}
        assert all2.status_code == 200
        assert all2.json() == {"updated_count": 0}

        bad_page = await client.get("/api/v1/admin/notifications?page_size=101")
        bad_id = await client.patch("/api/v1/admin/notifications/0/read", json={})
        bad_body = await client.patch(
            f"/api/v1/admin/notifications/{n1.id}/read",
            json={"extra": 1},
        )
        assert bad_page.status_code == 422
        assert bad_id.status_code == 422
        assert bad_body.status_code == 422
