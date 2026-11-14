"""MySQL 8 integration tests for AdminNotification schema and HTTP PATCH."""

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from redis.exceptions import RedisError
from sqlalchemy import delete, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.main import create_app
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
)
from app.modules.auth.security import PasswordHasher
from app.modules.auth.service import AuthService, utc_now_naive
from app.modules.notifications.models import AdminNotification
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

EMAIL_PREFIX = "t3c9b8a_notif_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


@pytest.fixture(autouse=True)
def clean_notification_test_rows(
    migrated_integration_engine: Engine,
) -> None:
    """Remove test rows created under EMAIL_PREFIX after every MySQL test."""
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        user_ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if not user_ids:
            return
        session_ids = list(
            session.scalars(
                select(AuthSession.id).where(AuthSession.user_id.in_(user_ids))
            )
        )
        if session_ids:
            session.execute(
                delete(RefreshToken).where(RefreshToken.session_id.in_(session_ids))
            )
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
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
                    (AdminNotification.approval_request_id.in_(approval_ids))
                    | (AdminNotification.admin_user_id.in_(user_ids))
                )
            )
        else:
            session.execute(
                delete(AdminNotification).where(
                    AdminNotification.admin_user_id.in_(user_ids)
                )
            )
        session.execute(
            delete(StaffApprovalRequest).where(
                StaffApprovalRequest.user_id.in_(user_ids)
            )
        )
        session.execute(delete(User).where(User.id.in_(user_ids)))


def _seed_admin_and_approval(
    session: Session,
    suffix: str,
) -> tuple[User, User, StaffApprovalRequest]:
    now = datetime(2026, 11, 7, 8, 0, 0)
    # Reuse existing ADMIN if present to avoid colliding with uq_users_admin_slot=1
    existing_admin = session.scalar(select(User).where(User.admin_slot == 1))
    if existing_admin is None:
        admin = User(
            email_normalized=f"{EMAIL_PREFIX}admin_{suffix}@example.com",
            password_hash=PasswordHasher(work_factor=4).hash("admin-password"),
            role="ADMIN",
            status="ACTIVE",
            admin_slot=1,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
    else:
        admin = existing_admin

    staff = User(
        email_normalized=f"{EMAIL_PREFIX}staff_{suffix}@example.com",
        password_hash=PasswordHasher(work_factor=4).hash("staff-password"),
        role="STAFF",
        status="PENDING_APPROVAL",
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(staff)
    session.flush()

    approval = StaffApprovalRequest(
        user_id=staff.id,
        attempt_no=1,
        status="PENDING",
        requested_at=now,
        decided_by=None,
        decided_at=None,
        decision_reason=None,
    )
    session.add(approval)
    session.flush()
    return admin, staff, approval


def test_admin_notifications_schema_constraints_and_index_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    inspector = inspect(migrated_integration_engine)
    columns = [col["name"] for col in inspector.get_columns("admin_notifications")]
    assert columns == [
        "id",
        "admin_user_id",
        "approval_request_id",
        "created_at",
        "read_at",
    ]

    indexes = {
        idx["name"]: idx["column_names"]
        for idx in inspector.get_indexes("admin_notifications")
    }
    assert indexes.get(
        "ix_admin_notifications_admin_user_id_read_at_created_at_id"
    ) == [
        "admin_user_id",
        "read_at",
        "created_at",
        "id",
    ]

    now = datetime(2026, 11, 7, 8, 30, 0)
    with Session(migrated_integration_engine) as session:
        admin, _staff, approval = _seed_admin_and_approval(session, "schema")
        notif = AdminNotification(
            admin_user_id=admin.id,
            approval_request_id=approval.id,
            created_at=now,
        )
        session.add(notif)
        session.commit()
        assert notif.read_at is None

        # Duplicate approval_request_id must violate UNIQUE
        session.add(
            AdminNotification(
                admin_user_id=admin.id,
                approval_request_id=approval.id,
                created_at=now + timedelta(minutes=1),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Invalid FK must raise IntegrityError
        session.add(
            AdminNotification(
                admin_user_id=admin.id,
                approval_request_id=9_999_999_999,
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_create_for_approval_shares_caller_transaction_without_committing(
    migrated_integration_engine: Engine,
) -> None:
    repo = NotificationRepository()
    t0 = datetime(2026, 11, 7, 9, 0, 0)
    t1 = t0 + timedelta(minutes=5)
    t2 = t0 + timedelta(minutes=10)
    t3 = t0 + timedelta(minutes=15)
    t4 = t0 + timedelta(minutes=20)
    calls = [t0, t1, t2, t3, t4]
    service = NotificationService(repository=repo, clock=lambda: calls.pop(0))

    with Session(migrated_integration_engine) as auth_session:
        admin, _staff, approval = _seed_admin_and_approval(auth_session, "tx_share")
        admin_id = admin.id
        approval_id = approval.id

        first = service.create_for_approval(
            auth_session,
            admin_user_id=admin_id,
            approval_request_id=approval_id,
        )
        second = service.create_for_approval(
            auth_session,
            admin_user_id=admin_id,
            approval_request_id=approval_id,
        )
        assert first.id == second.id
        assert second.created_at == t0

        # Independent connection MUST NOT see uncommitted row before caller commits
        with Session(migrated_integration_engine) as outside_session:
            visible_before_commit = outside_session.scalar(
                select(AdminNotification).where(
                    AdminNotification.approval_request_id == approval_id
                )
            )
            assert visible_before_commit is None

        # Caller (AuthService role) commits
        auth_session.commit()

    with Session(migrated_integration_engine) as after_commit_session:
        visible_after_commit = after_commit_session.scalar(
            select(AdminNotification).where(
                AdminNotification.approval_request_id == approval_id
            )
        )
        assert visible_after_commit is not None
        assert visible_after_commit.created_at == t0

        # Mark read commits t2; repeated create_for_approval preserves timestamps
        marked = service.mark_read(
            after_commit_session,
            admin_user_id=admin_id,
            notification_id=visible_after_commit.id,
        )
        assert marked.read_at == t2

        third = service.create_for_approval(
            after_commit_session,
            admin_user_id=admin_id,
            approval_request_id=approval_id,
        )
        assert third.created_at == t0
        assert third.read_at == t2
        after_commit_session.commit()

        # Invalid FK in create_for_approval must raise IntegrityError untouched
        with pytest.raises(IntegrityError):
            service.create_for_approval(
                after_commit_session,
                admin_user_id=admin_id,
                approval_request_id=9_999_999_999,
            )
        after_commit_session.rollback()
        assert calls == []


def test_forced_failure_after_create_for_approval_rolls_back_all_entities(
    migrated_integration_engine: Engine,
) -> None:
    repo = NotificationRepository()
    service = NotificationService(repository=repo)

    with Session(migrated_integration_engine) as auth_session:
        admin, staff, approval = _seed_admin_and_approval(auth_session, "rollback")
        staff_id = staff.id
        approval_id = approval.id

        service.create_for_approval(
            auth_session,
            admin_user_id=admin.id,
            approval_request_id=approval_id,
        )
        # Simulate failure in caller transaction -> rollback
        auth_session.rollback()

    with Session(migrated_integration_engine) as verify_session:
        assert verify_session.get(User, staff_id) is None
        assert verify_session.get(StaffApprovalRequest, approval_id) is None
        assert (
            verify_session.scalar(
                select(AdminNotification).where(
                    AdminNotification.approval_request_id == approval_id
                )
            )
            is None
        )


def test_concurrent_create_mark_read_and_mark_all_read(
    migrated_integration_engine: Engine,
) -> None:
    with Session(migrated_integration_engine) as setup_session:
        admin, _staff1, approval1 = _seed_admin_and_approval(setup_session, "conc1")
        _admin2, _staff2, approval2 = _seed_admin_and_approval(setup_session, "conc2")
        admin_id = admin.id
        approval1_id = approval1.id
        approval2_id = approval2.id
        setup_session.commit()

    # 1. Two concurrent transactions calling create_for_approval for approval1_id
    def worker_create() -> int:
        svc = NotificationService(repository=NotificationRepository())
        with Session(migrated_integration_engine) as worker_session:
            notif = svc.create_for_approval(
                worker_session,
                admin_user_id=admin_id,
                approval_request_id=approval1_id,
            )
            worker_session.commit()
            return notif.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        created_ids = list(pool.map(lambda _i: worker_create(), range(2)))
    assert created_ids[0] == created_ids[1]

    # Create second unread notification for mark_all_read concurrency test
    with Session(migrated_integration_engine) as seed2_session:
        svc = NotificationService(repository=NotificationRepository())
        notif2 = svc.create_for_approval(
            seed2_session,
            admin_user_id=admin_id,
            approval_request_id=approval2_id,
        )
        notif1_id = created_ids[0]
        notif2_id = notif2.id
        seed2_session.commit()

    # 2. Two concurrent mark_read on notif1_id -> read_at keeps first timestamp
    t_early = datetime(2026, 11, 7, 10, 0, 0)
    t_late = datetime(2026, 11, 7, 10, 5, 0)

    def worker_mark_read(ts: datetime) -> datetime | None:
        svc = NotificationService(repository=NotificationRepository(), clock=lambda: ts)
        with Session(migrated_integration_engine) as worker_session:
            res = svc.mark_read(
                worker_session,
                admin_user_id=admin_id,
                notification_id=notif1_id,
            )
            return res.read_at

    with ThreadPoolExecutor(max_workers=2) as pool:
        mark_results = list(pool.map(worker_mark_read, (t_early, t_late)))
    assert mark_results[0] == mark_results[1]

    # Reset notif1 and notif2 to unread for concurrent mark_all_read
    with Session(migrated_integration_engine) as reset_session:
        for nid in (notif1_id, notif2_id):
            row = reset_session.get(AdminNotification, nid)
            if row is not None:
                row.read_at = None
        reset_session.commit()

    # 3. Two concurrent mark_all_read -> sum of updated_count == initial unread (2)
    def worker_mark_all() -> int:
        svc = NotificationService(repository=NotificationRepository())
        with Session(migrated_integration_engine) as worker_session:
            res = svc.mark_all_read(worker_session, admin_user_id=admin_id)
            return res.updated_count

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _i: worker_mark_all(), range(2)))
    assert sum(counts) == 2


@pytest.mark.anyio
async def test_http_patch_endpoints_persist_in_mysql_and_enforce_permissions(
    migrated_integration_engine: Engine,
) -> None:
    settings = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins="http://127.0.0.1:5173",
    )
    auth_service = AuthService(
        settings,
        password_hasher=PasswordHasher(work_factor=4),
    )

    def override_get_db_session() -> Generator[Session]:
        """Mirror app.db.session.get_db_session (no auto-commit on exit)."""
        with Session(
            migrated_integration_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    now = datetime(2026, 11, 7, 11, 0, 0)
    session_now = utc_now_naive()
    session_expires_at = session_now + timedelta(seconds=settings.session_ttl_seconds)
    admin_session_id = uuid4()

    with Session(migrated_integration_engine) as setup_session:
        # If no Admin exists yet, seed a sentinel Admin under EMAIL_PREFIX so
        # _seed_admin_and_approval always takes the shared-Admin reuse branch.
        if setup_session.scalar(select(User).where(User.admin_slot == 1)) is None:
            setup_session.add(
                User(
                    email_normalized=f"{EMAIL_PREFIX}shared_admin_sentinel@example.com",
                    password_hash="$2b$04$sentinel.shared.admin.hash.do.not.mutate",
                    role="ADMIN",
                    status="ACTIVE",
                    admin_slot=1,
                    last_reapplied_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            setup_session.flush()

        admin, _s1, approval1 = _seed_admin_and_approval(setup_session, "http1")
        _admin, _s2, approval2 = _seed_admin_and_approval(setup_session, "http2")
        _admin, _s3, approval3 = _seed_admin_and_approval(setup_session, "http3")

        admin_id = admin.id
        original_admin_email = admin.email_normalized
        original_admin_password_hash = admin.password_hash

        # Create an isolated AuthSession for Admin without mutating Admin credentials
        setup_session.add(
            AuthSession(
                id=admin_session_id.bytes,
                user_id=admin_id,
                created_at=session_now,
                expires_at=session_expires_at,
                revoked_at=None,
            )
        )

        active_staff = User(
            email_normalized=f"{EMAIL_PREFIX}active_staff_http@example.com",
            password_hash=PasswordHasher(work_factor=4).hash("staff-pass"),
            role="STAFF",
            status="ACTIVE",
            admin_slot=None,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        setup_session.add(active_staff)
        setup_session.flush()

        notif_svc = NotificationService(repository=NotificationRepository())
        n1 = notif_svc.create_for_approval(
            setup_session,
            admin_user_id=admin_id,
            approval_request_id=approval1.id,
        )
        n2 = notif_svc.create_for_approval(
            setup_session,
            admin_user_id=admin_id,
            approval_request_id=approval2.id,
        )
        other_notif = notif_svc.create_for_approval(
            setup_session,
            admin_user_id=active_staff.id,
            approval_request_id=approval3.id,
        )
        n1_id = n1.id
        n2_id = n2.id
        other_notif_id = other_notif.id
        staff_email = active_staff.email_normalized
        setup_session.commit()

        admin_token, _ = auth_service.jwt.issue(
            user_id=admin_id,
            session_id=admin_session_id,
            session_expires_at=session_expires_at,
            now=session_now.replace(tzinfo=UTC),
        )
        staff_token = auth_service.login(
            setup_session, staff_email, "staff-pass"
        ).response.access_token

    app = create_app(settings)

    class UnavailableRedis:
        async def eval(self, *_args, **_kwargs):
            raise RedisError("test Redis outage")

    app.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        UnavailableRedis(), "retailops:test"
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_auth_service] = lambda: auth_service

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # 1. Staff receives 403 and does NOT mutate database
            staff_patch = await client.patch(
                f"/api/v1/admin/notifications/{n1_id}/read",
                headers=staff_headers,
                json={},
            )
            staff_all = await client.patch(
                "/api/v1/admin/notifications/read-all",
                headers=staff_headers,
                json={},
            )
            assert staff_patch.status_code == 403
            assert staff_all.status_code == 403

            with Session(migrated_integration_engine) as verify_session:
                assert verify_session.get(AdminNotification, n1_id).read_at is None
                assert verify_session.get(AdminNotification, n2_id).read_at is None

            # 2. Resource not owned by Admin returns 404 and does NOT mutate database
            not_owned = await client.patch(
                f"/api/v1/admin/notifications/{other_notif_id}/read",
                headers=admin_headers,
                json={},
            )
            assert not_owned.status_code == 404
            assert not_owned.json()["code"] == "RESOURCE_NOT_FOUND"

            with Session(migrated_integration_engine) as verify_session:
                assert (
                    verify_session.get(AdminNotification, other_notif_id).read_at
                    is None
                )

            # 3. Admin PATCH /{id}/read returns 200 and persists read_at in MySQL
            patch1 = await client.patch(
                f"/api/v1/admin/notifications/{n1_id}/read",
                headers=admin_headers,
                json={},
            )
            assert patch1.status_code == 200
            assert patch1.json()["read_at"] is not None

            with Session(migrated_integration_engine) as verify_session:
                persisted_n1 = verify_session.get(AdminNotification, n1_id)
                assert persisted_n1 is not None
                assert persisted_n1.read_at is not None
                first_persisted_read_at = persisted_n1.read_at

            # 4. Repeated PATCH /{id}/read does not alter persisted read_at
            patch2 = await client.patch(
                f"/api/v1/admin/notifications/{n1_id}/read",
                headers=admin_headers,
                json={},
            )
            assert patch2.status_code == 200
            assert patch2.json()["read_at"] == patch1.json()["read_at"]

            with Session(migrated_integration_engine) as verify_session:
                persisted_n1_again = verify_session.get(AdminNotification, n1_id)
                assert persisted_n1_again is not None
                assert persisted_n1_again.read_at == first_persisted_read_at

            # 5. Admin PATCH /read-all returns updated_count=1 and persists read_at
            read_all1 = await client.patch(
                "/api/v1/admin/notifications/read-all",
                headers=admin_headers,
                json={},
            )
            assert read_all1.status_code == 200
            assert read_all1.json() == {"updated_count": 1}

            with Session(migrated_integration_engine) as verify_session:
                persisted_n2 = verify_session.get(AdminNotification, n2_id)
                assert persisted_n2 is not None
                assert persisted_n2.read_at is not None
                # Other user's notification remains unread
                assert (
                    verify_session.get(AdminNotification, other_notif_id).read_at
                    is None
                )

            read_all2 = await client.patch(
                "/api/v1/admin/notifications/read-all",
                headers=admin_headers,
                json={},
            )
            assert read_all2.status_code == 200
            assert read_all2.json() == {"updated_count": 0}

            # 6. Shared Admin credentials remain completely untouched in MySQL
            with Session(migrated_integration_engine) as verify_session:
                persisted_admin = verify_session.get(User, admin_id)
                assert persisted_admin is not None
                assert persisted_admin.email_normalized == original_admin_email
                assert persisted_admin.password_hash == original_admin_password_hash
    finally:
        with (
            Session(migrated_integration_engine) as cleanup_session,
            cleanup_session.begin(),
        ):
            cleanup_session.execute(
                delete(AuthSession).where(AuthSession.id == admin_session_id.bytes)
            )
