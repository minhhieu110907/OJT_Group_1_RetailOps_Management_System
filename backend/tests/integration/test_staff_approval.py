"""Real MySQL transaction and row-lock tests for Staff approval decisions."""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from threading import Event

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.infrastructure.dependencies import (
    enforce_login_rate_limit,
    enforce_registration_rate_limit,
)
from app.main import create_app
from app.modules.auth.approval_repository import StaffApprovalRepository
from app.modules.auth.approval_service import StaffApprovalService
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
)
from app.modules.auth.security import PasswordHasher
from app.modules.auth.service import AuthService
from app.modules.notifications.models import AdminNotification
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.writer import OutboxWriter

pytestmark = pytest.mark.integration
EMAIL_PREFIX = "t04a61f_approval_"


def ensure_admin(engine: Engine) -> int:
    with Session(engine) as session:
        admin = session.scalar(select(User).where(User.admin_slot == 1))
        if admin is not None:
            return admin.id
        now = datetime(2026, 11, 11, 7, 0)
        admin = User(
            email_normalized=f"{EMAIL_PREFIX}admin@example.com",
            password_hash="test-hash",
            role="ADMIN",
            status="ACTIVE",
            admin_slot=1,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
        session.commit()
        return admin.id


def create_pending(engine: Engine, suffix: str) -> tuple[int, int]:
    now = datetime(2026, 11, 10, 8, 0)
    with Session(engine) as session:
        staff = User(
            email_normalized=f"{EMAIL_PREFIX}{suffix}@example.com",
            password_hash="test-hash",
            role="STAFF",
            status="PENDING_APPROVAL",
            admin_slot=None,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(staff)
        session.flush()
        request = StaffApprovalRequest(
            user_id=staff.id,
            attempt_no=1,
            status="PENDING",
            requested_at=now,
            decided_by=None,
            decided_at=None,
            decision_reason=None,
        )
        session.add(request)
        session.commit()
        return staff.id, request.id


def cleanup(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if not ids:
            return
        session_ids = list(
            session.scalars(select(AuthSession.id).where(AuthSession.user_id.in_(ids)))
        )
        approval_ids = list(
            session.scalars(
                select(StaffApprovalRequest.id).where(
                    StaffApprovalRequest.user_id.in_(ids)
                )
            )
        )
        if session_ids:
            session.execute(
                delete(RefreshToken).where(RefreshToken.session_id.in_(session_ids))
            )
        if approval_ids:
            session.execute(
                delete(AdminNotification).where(
                    AdminNotification.approval_request_id.in_(approval_ids)
                )
            )
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_(ids)))
        session.execute(delete(OutboxEvent).where(OutboxEvent.subject_user_id.in_(ids)))
        session.execute(
            delete(StaffApprovalRequest).where(StaffApprovalRequest.user_id.in_(ids))
        )
        session.execute(delete(User).where(User.id.in_(ids)))


@pytest.fixture(autouse=True)
def clean_rows(migrated_integration_engine: Engine) -> None:
    cleanup(migrated_integration_engine)
    yield
    cleanup(migrated_integration_engine)


@pytest.mark.parametrize(
    ("decision", "reason", "user_status", "event_type"),
    [
        ("APPROVED", None, "ACTIVE", "STAFF_APPROVED"),
        ("REJECTED", "Không đạt", "REJECTED", "STAFF_REJECTED"),
    ],
)
def test_decision_atomically_updates_user_approval_and_outbox(
    migrated_integration_engine: Engine,
    decision: str,
    reason: str | None,
    user_status: str,
    event_type: str,
) -> None:
    admin_id = ensure_admin(migrated_integration_engine)
    user_id, approval_id = create_pending(migrated_integration_engine, decision.lower())
    with Session(migrated_integration_engine) as session:
        result = StaffApprovalService().decide(
            session,
            actor_id=admin_id,
            approval_id=approval_id,
            decision=decision,
            reason=reason,
        )
        assert result.status == decision
        assert session.get(User, user_id).status == user_status
        assert session.get(StaffApprovalRequest, approval_id).status == decision
        events = list(
            session.scalars(
                select(OutboxEvent).where(OutboxEvent.subject_user_id == user_id)
            )
        )
        assert [event.event_type for event in events] == [event_type]


@pytest.mark.parametrize(
    "decisions",
    [("APPROVED", "APPROVED"), ("REJECTED", "REJECTED"), ("APPROVED", "REJECTED")],
)
def test_concurrent_decisions_have_one_winner_and_one_invalid_state(
    migrated_integration_engine: Engine, decisions: tuple[str, str]
) -> None:
    admin_id = ensure_admin(migrated_integration_engine)
    user_id, approval_id = create_pending(
        migrated_integration_engine, "race_" + "_".join(decisions).lower()
    )

    def decide(decision: str) -> str:
        with Session(migrated_integration_engine) as session:
            try:
                StaffApprovalService().decide(
                    session,
                    actor_id=admin_id,
                    approval_id=approval_id,
                    decision=decision,
                    reason="Không đạt" if decision == "REJECTED" else None,
                )
                return "SUCCESS"
            except AppException as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(decide, decisions))

    assert sorted(outcomes) == ["INVALID_STATE", "SUCCESS"]
    with Session(migrated_integration_engine) as session:
        event_count = session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.subject_user_id == user_id)
        )
        assert event_count == 1


class LockObservingRepository(StaffApprovalRepository):
    def __init__(
        self,
        *,
        lock_attempted: Event | None = None,
        lock_acquired: Event | None = None,
        release_lock: Event | None = None,
    ) -> None:
        self.lock_attempted = lock_attempted
        self.lock_acquired = lock_acquired
        self.release_lock = release_lock

    def lock_approval(
        self, session: Session, approval_id: int
    ) -> StaffApprovalRequest | None:
        if self.lock_attempted is not None:
            self.lock_attempted.set()
        approval = super().lock_approval(session, approval_id)
        if self.lock_acquired is not None:
            self.lock_acquired.set()
        if self.release_lock is not None and not self.release_lock.wait(timeout=5):
            raise TimeoutError("timed out waiting to release approval row lock")
        return approval


def test_second_mysql_transaction_waits_for_row_lock_then_observes_invalid_state(
    migrated_integration_engine: Engine,
) -> None:
    admin_id = ensure_admin(migrated_integration_engine)
    user_id, approval_id = create_pending(
        migrated_integration_engine, "observed_row_lock"
    )
    first_acquired = Event()
    release_first = Event()
    second_attempted = Event()
    second_acquired = Event()

    def decide(service: StaffApprovalService, decision: str) -> str:
        with Session(migrated_integration_engine) as session:
            try:
                service.decide(
                    session,
                    actor_id=admin_id,
                    approval_id=approval_id,
                    decision=decision,
                    reason="Không đạt" if decision == "REJECTED" else None,
                )
            except AppException as error:
                return error.code
            return "SUCCESS"

    first_service = StaffApprovalService(
        repository=LockObservingRepository(
            lock_acquired=first_acquired, release_lock=release_first
        )
    )
    second_service = StaffApprovalService(
        repository=LockObservingRepository(
            lock_attempted=second_attempted, lock_acquired=second_acquired
        )
    )

    first_future: Future[str] | None = None
    second_future: Future[str] | None = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            first_future = executor.submit(decide, first_service, "APPROVED")
            assert first_acquired.wait(timeout=5), (
                "first transaction did not acquire lock"
            )
            second_future = executor.submit(decide, second_service, "REJECTED")
            assert second_attempted.wait(timeout=5), (
                "second transaction did not attempt lock"
            )
            assert not second_acquired.wait(timeout=0.25)
            assert not second_future.done(), (
                "second transaction did not wait for row lock"
            )
        finally:
            release_first.set()

        assert first_future is not None
        assert second_future is not None
        assert first_future.result(timeout=10) == "SUCCESS"
        assert second_future.result(timeout=10) == "INVALID_STATE"
        assert second_acquired.is_set()

    with Session(migrated_integration_engine) as session:
        assert session.get(User, user_id).status == "ACTIVE"
        assert session.get(StaffApprovalRequest, approval_id).status == "APPROVED"
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.subject_user_id == user_id)
            )
            == 1
        )


class FailingOutboxWriter(OutboxWriter):
    def append(self, *_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("forced approval outbox failure")


def test_outbox_failure_rolls_back_entire_approval_decision(
    migrated_integration_engine: Engine,
) -> None:
    admin_id = ensure_admin(migrated_integration_engine)
    user_id, approval_id = create_pending(
        migrated_integration_engine, "outbox_rollback"
    )
    with (
        Session(migrated_integration_engine) as session,
        pytest.raises(RuntimeError, match="forced approval outbox"),
    ):
        StaffApprovalService(outbox_writer=FailingOutboxWriter()).decide(
            session,
            actor_id=admin_id,
            approval_id=approval_id,
            decision="APPROVED",
            reason=None,
        )

    with Session(migrated_integration_engine) as session:
        assert session.get(User, user_id).status == "PENDING_APPROVAL"
        assert session.get(StaffApprovalRequest, approval_id).status == "PENDING"
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.subject_user_id == user_id)
            )
            == 0
        )


@pytest.mark.anyio
async def test_real_http_registration_approval_and_login_flow(
    migrated_integration_engine: Engine,
) -> None:
    settings = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
    )
    password_hasher = PasswordHasher(work_factor=4)
    auth_service = AuthService(settings, password_hasher=password_hasher)
    email = f"{EMAIL_PREFIX}real_http@example.com"
    staff_password = "valid-staff-password"
    admin_password = "valid-admin-password"
    seeded_admin_id = ensure_admin(migrated_integration_engine)

    with Session(migrated_integration_engine) as session, session.begin():
        admin = session.get(User, seeded_admin_id)
        assert admin is not None
        admin_id = admin.id
        admin_email = admin.email_normalized
        original_admin_hash = admin.password_hash
        existing_admin_session_ids = set(
            session.scalars(
                select(AuthSession.id).where(AuthSession.user_id == admin_id)
            )
        )
        admin.password_hash = password_hasher.hash(admin_password)

    def db_session_override():
        with Session(migrated_integration_engine) as session:
            yield session

    async def allow_registration() -> None:
        return None

    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = db_session_override
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[enforce_registration_rate_limit] = allow_registration
    app.dependency_overrides[enforce_login_rate_limit] = allow_registration

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            registered = await client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": staff_password},
            )
            pending_login = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": staff_password},
            )
            admin_login = await client.post(
                "/api/v1/auth/login",
                json={"email": admin_email, "password": admin_password},
            )
            assert admin_login.status_code == 200
            admin_token = admin_login.json()["access_token"]

            with Session(migrated_integration_engine) as session:
                staff = session.scalar(
                    select(User).where(User.email_normalized == email)
                )
                assert staff is not None
                staff_id = staff.id
                approval = session.scalar(
                    select(StaffApprovalRequest).where(
                        StaffApprovalRequest.user_id == staff_id
                    )
                )
                assert approval is not None
                approval_id = approval.id

            listed = await client.get(
                "/api/v1/staff-approvals?status=PENDING&page=1&page_size=20",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert listed.status_code == 200
            matching_items = [
                item for item in listed.json()["items"] if item["id"] == approval_id
            ]
            assert len(matching_items) == 1
            assert matching_items[0]["email"] == email
            assert matching_items[0]["user_id"] == staff_id
            assert "password_hash" not in str(listed.json())

            approved = await client.post(
                f"/api/v1/staff-approvals/{approval_id}/approve",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            active_login = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": staff_password},
            )
            assert active_login.status_code == 200
            staff_token = active_login.json()["access_token"]
            forbidden = await client.post(
                f"/api/v1/staff-approvals/{approval_id}/approve",
                headers={"Authorization": f"Bearer {staff_token}"},
            )

        assert registered.status_code == 202
        assert pending_login.status_code == 401
        assert approved.status_code == 200
        assert forbidden.status_code == 403

        with Session(migrated_integration_engine) as session:
            assert session.get(User, staff_id).status == "ACTIVE"
            assert session.get(StaffApprovalRequest, approval_id).status == "APPROVED"
            events = list(
                session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.subject_user_id == staff_id)
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                )
            )
            assert [event.event_type for event in events] == [
                "STAFF_REGISTERED",
                "STAFF_APPROVED",
            ]
    finally:
        with Session(migrated_integration_engine) as session, session.begin():
            admin = session.get(User, admin_id)
            assert admin is not None
            admin.password_hash = original_admin_hash
            new_admin_session_ids = (
                set(
                    session.scalars(
                        select(AuthSession.id).where(AuthSession.user_id == admin_id)
                    )
                )
                - existing_admin_session_ids
            )
            if new_admin_session_ids:
                session.execute(
                    delete(RefreshToken).where(
                        RefreshToken.session_id.in_(new_admin_session_ids)
                    )
                )
                session.execute(
                    delete(AuthSession).where(AuthSession.id.in_(new_admin_session_ids))
                )
        cleanup(migrated_integration_engine)
