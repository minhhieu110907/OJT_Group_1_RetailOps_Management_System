"""Real MySQL transaction and row-lock tests for Staff approval decisions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.modules.auth.approval_service import StaffApprovalService
from app.modules.auth.models import StaffApprovalRequest, User
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
    user_id, approval_id = create_pending(
        migrated_integration_engine, decision.lower()
    )
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
