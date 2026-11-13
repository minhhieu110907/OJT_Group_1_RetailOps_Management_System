"""End-to-end Nginx/Uvicorn/Redis/MySQL registration verification."""

from __future__ import annotations

import asyncio
import os
import time
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
from app.modules.outbox.models import OutboxEvent

pytestmark = [pytest.mark.integration, pytest.mark.proxy_integration]
EMAIL_PREFIX = "t3c9a33_proxy_registration_"
RATE_LIMIT = 5
WINDOW_SECONDS = 60
FIRST_OBSERVATION_GUARD_SECONDS = 1.0


async def _avoid_first_observation_expiry_race(redis: Redis) -> None:
    seconds, microseconds = await redis.time()
    server_time = seconds + microseconds / 1_000_000
    remaining = WINDOW_SECONDS - (server_time % WINDOW_SECONDS)
    if remaining <= FIRST_OBSERVATION_GUARD_SECONDS:
        await asyncio.sleep(remaining + 0.05)


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
            delete(OutboxEvent).where(OutboxEvent.subject_user_id.in_(user_ids))
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
        # A key created in the final fraction of a window could expire between
        # the first HTTP response and its Redis observation. Avoid only that
        # bounded race; later bucket peaks are retained in observed_counts.
        await _avoid_first_observation_expiry_race(redis)
        observed_counts: dict[bytes, int] = {}
        started_at = time.monotonic()
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as client:
            responses = []
            for index in range(11):
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

                # Keep the highest counter observed for every fixed-window bucket.
                # The previous bucket may expire while this deliberately rollover-safe
                # sequence is still running, so a final Redis scan alone is
                # insufficient.
                keys = [
                    key
                    async for key in redis.scan_iter(
                        match="retailops:rate-limit:staff-registration:*"
                    )
                ]
                for key in keys:
                    value = await redis.get(key)
                    if value is not None:
                        observed_counts[key] = max(
                            observed_counts.get(key, 0), int(value)
                        )

        assert time.monotonic() - started_at < WINDOW_SECONDS

        status_codes = [response.status_code for response in responses]
        assert set(status_codes) <= {202, 429}
        assert status_codes.count(202) == sum(
            min(count, RATE_LIMIT) for count in observed_counts.values()
        )
        assert status_codes.count(429) == sum(
            max(count - RATE_LIMIT, 0) for count in observed_counts.values()
        )
        assert status_codes.count(429) >= 1
        assert responses[0].json() == {"message": REGISTER_ACCEPTED_MESSAGE}
        assert responses[0].headers.get_list("set-cookie") == []
        assert "access_token" not in responses[0].text
        assert all(
            int(response.headers["retry-after"]) > 0
            for response in responses
            if response.status_code == 429
        )

        assert 1 <= len(observed_counts) <= 2
        key_prefixes = {key.rsplit(b":", 1)[0] for key in observed_counts}
        assert len(key_prefixes) == 1
        windows = sorted(int(key.rsplit(b":", 1)[1]) for key in observed_counts)
        if len(windows) == 2:
            assert windows[1] == windows[0] + 1
        assert sum(observed_counts.values()) == 11

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
