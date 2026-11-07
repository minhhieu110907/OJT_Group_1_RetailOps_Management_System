"""MySQL 8 integration tests for AdminNotification schema and transactions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import StaffApprovalRequest, User
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
            password_hash="test-only-hash",
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
        password_hash="test-only-hash",
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
    calls = [t0, t0 + timedelta(minutes=10)]
    service = NotificationService(repository=repo, clock=lambda: calls.pop(0))

    with Session(migrated_integration_engine) as auth_session:
        admin, _staff, approval = _seed_admin_and_approval(auth_session, "tx_share")
        approval_id = approval.id

        first = service.create_for_approval(
            auth_session,
            admin_user_id=admin.id,
            approval_request_id=approval_id,
        )
        second = service.create_for_approval(
            auth_session,
            admin_user_id=admin.id,
            approval_request_id=approval_id,
        )
        assert first.id == second.id
        assert second.created_at == t0

        # Independent connection MUST NOT see uncommitted row
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
            worker_session.commit()
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
            worker_session.commit()
            return res.updated_count

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _i: worker_mark_all(), range(2)))
    assert sum(counts) == 2
