"""End-to-end Nginx/Uvicorn/Redis/MySQL registration verification."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.auth.models import AuthSession, StaffApprovalRequest, User
from app.modules.auth.service import REGISTER_ACCEPTED_MESSAGE
from app.modules.notifications.models import AdminNotification

pytestmark = [pytest.mark.integration, pytest.mark.proxy_integration]
EMAIL_PREFIX = "t3c9a33_proxy_registration_"


def _ensure_admin(engine: Engine) -> None:
    with Session(engine) as session:
        if session.scalar(select(User).where(User.admin_slot == 1)) is not None:
            return
        now = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            User(
                email_normalized=f"{EMAIL_PREFIX}admin@example.com",
                password_hash="proxy-test-only-hash",
                role="ADMIN",
                status="ACTIVE",
                admin_slot=1,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def _cleanup_registrations(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        user_ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if not user_ids:
            return
        approval_ids = list(
            session.scalars(
                select(StaffApprovalRequest.id).where(
                    StaffApprovalRequest.user_id.in_(user_ids)
                )
            )
        )
        if approval_ids:
            session.execute(
                delete(AdminNotification).where(
                    AdminNotification.approval_request_id.in_(approval_ids)
                )
            )
        session.execute(
            delete(StaffApprovalRequest).where(
                StaffApprovalRequest.user_id.in_(user_ids)
            )
        )
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        session.execute(delete(User).where(User.id.in_(user_ids)))


@pytest.mark.anyio
async def test_forged_forwarded_headers_share_real_proxy_client_bucket(
    migrated_integration_engine: Engine,
) -> None:
    base_url = os.getenv("RETAILOPS_PROXY_BASE_URL")
    redis_url = os.getenv("RETAILOPS_PROXY_REDIS_URL")
    if not base_url or not redis_url:
        pytest.skip("Proxy topology URLs are required")
    _cleanup_registrations(migrated_integration_engine)
    _ensure_admin(migrated_integration_engine)
    redis = Redis.from_url(redis_url, decode_responses=False)
    existing_keys = [
        key
        async for key in redis.scan_iter(
            match="retailops:rate-limit:staff-registration:*"
        )
    ]
    if existing_keys:
        await redis.delete(*existing_keys)

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as client:
            responses = []
            for index in range(6):
                responses.append(
                    await client.post(
                        "/api/v1/auth/register",
                        headers={
                            "X-Real-IP": f"198.51.100.{index + 1}",
                            "X-Forwarded-For": f"203.0.113.{index + 1}",
                        },
                        json={
                            "email": f"{EMAIL_PREFIX}{index}@example.com",
                            "password": "valid-password",
                        },
                    )
                )

        assert [response.status_code for response in responses] == [
            202,
            202,
            202,
            202,
            202,
            429,
        ]
        assert responses[0].json() == {"message": REGISTER_ACCEPTED_MESSAGE}
        assert responses[0].headers.get_list("set-cookie") == []
        assert "access_token" not in responses[0].text
        assert int(responses[-1].headers["retry-after"]) > 0

        keys = [
            key
            async for key in redis.scan_iter(
                match="retailops:rate-limit:staff-registration:*"
            )
        ]
        assert len(keys) == 1
        assert int(await redis.get(keys[0])) == 6

        email = f"{EMAIL_PREFIX}0@example.com"
        with Session(migrated_integration_engine) as session:
            user = session.scalar(select(User).where(User.email_normalized == email))
            assert user is not None
            assert user.role == "STAFF"
            assert user.status == "PENDING_APPROVAL"
            approval = session.scalar(
                select(StaffApprovalRequest).where(
                    StaffApprovalRequest.user_id == user.id
                )
            )
            assert approval is not None
            assert approval.status == "PENDING"
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AdminNotification)
                    .where(AdminNotification.approval_request_id == approval.id)
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AuthSession)
                    .where(AuthSession.user_id == user.id)
                )
                == 0
            )
    finally:
        keys = [
            key
            async for key in redis.scan_iter(
                match="retailops:rate-limit:staff-registration:*"
            )
        ]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()
        _cleanup_registrations(migrated_integration_engine)
