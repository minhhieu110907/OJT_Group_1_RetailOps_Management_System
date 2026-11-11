"""Unit coverage for approval transitions and the transactional Outbox writer."""

from datetime import datetime

import pytest

from app.core.exceptions import AppException
from app.modules.auth.approval_repository import StaffApprovalRepository
from app.modules.auth.approval_service import StaffApprovalService
from app.modules.auth.models import StaffApprovalRequest, User
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.writer import OutboxWriter


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def user(user_id: int, role: str, status: str) -> User:
    now = datetime(2026, 11, 11, 8, 0)
    return User(
        id=user_id,
        email_normalized=f"u{user_id}@example.com",
        password_hash="hash",
        role=role,
        status=status,
        admin_slot=1 if role == "ADMIN" else None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )


def approval(status: str = "PENDING") -> StaffApprovalRequest:
    return StaffApprovalRequest(
        id=10,
        user_id=2,
        attempt_no=1,
        status=status,
        requested_at=datetime(2026, 11, 11, 8, 0),
        decided_by=None if status == "PENDING" else 1,
        decided_at=None if status == "PENDING" else datetime(2026, 11, 11, 9, 0),
        decision_reason=None,
    )


class FakeRepository(StaffApprovalRepository):
    def __init__(self, *, actor: User, request: StaffApprovalRequest, staff: User):
        self.actor = actor
        self.request = request
        self.staff = staff

    def find_actor(self, _session: object, _actor_id: int) -> User | None:
        return self.actor

    def lock_approval(
        self, _session: object, _approval_id: int
    ) -> StaffApprovalRequest | None:
        return self.request

    def lock_user(self, _session: object, _user_id: int) -> User | None:
        return self.staff


@pytest.mark.parametrize(
    ("decision", "reason", "expected_user", "event_type"),
    [
        ("APPROVED", None, "ACTIVE", "STAFF_APPROVED"),
        ("REJECTED", "Không đạt", "REJECTED", "STAFF_REJECTED"),
    ],
)
def test_decide_commits_state_and_event_once(
    decision: str, reason: str | None, expected_user: str, event_type: str
) -> None:
    session = FakeSession()
    request = approval()
    staff = user(2, "STAFF", "PENDING_APPROVAL")
    service = StaffApprovalService(
        repository=FakeRepository(
            actor=user(1, "ADMIN", "ACTIVE"), request=request, staff=staff
        )
    )

    result = service.decide(
        session,  # type: ignore[arg-type]
        actor_id=1,
        approval_id=10,
        decision=decision,
        reason=reason,
    )

    assert result.status == decision
    assert staff.status == expected_user
    assert session.commits == 1
    assert session.rollbacks == 0
    events = [row for row in session.added if isinstance(row, OutboxEvent)]
    assert len(events) == 1
    assert events[0].event_type == event_type
    assert "password" not in str(events[0].payload).lower()
    assert "token" not in str(events[0].payload).lower()


@pytest.mark.parametrize(
    ("actor_role", "actor_status", "approval_status", "user_status", "code"),
    [
        ("STAFF", "ACTIVE", "PENDING", "PENDING_APPROVAL", "FORBIDDEN"),
        ("ADMIN", "ACTIVE", "APPROVED", "ACTIVE", "INVALID_STATE"),
        ("ADMIN", "ACTIVE", "PENDING", "REJECTED", "INVALID_STATE"),
    ],
)
def test_decide_rejects_invalid_authority_or_state_and_rolls_back(
    actor_role: str,
    actor_status: str,
    approval_status: str,
    user_status: str,
    code: str,
) -> None:
    session = FakeSession()
    service = StaffApprovalService(
        repository=FakeRepository(
            actor=user(1, actor_role, actor_status),
            request=approval(approval_status),
            staff=user(2, "STAFF", user_status),
        )
    )

    with pytest.raises(AppException) as captured:
        service.decide(
            session,  # type: ignore[arg-type]
            actor_id=1,
            approval_id=10,
            decision="APPROVED",
            reason=None,
        )

    assert captured.value.code == code
    assert session.commits == 0
    assert session.rollbacks == 1
    assert not session.added


def test_outbox_writer_only_adds_without_commit_or_rollback() -> None:
    session = FakeSession()
    event_id = OutboxWriter().append(
        session,  # type: ignore[arg-type]
        subject_user_id=2,
        event_type="STAFF_REGISTERED",
        payload={"schema_version": 1},
        available_at_utc=datetime(2026, 11, 11, 8, 0),
    )
    assert len(event_id) == 16
    assert len(session.added) == 1
    event = session.added[0]
    assert isinstance(event, OutboxEvent)
    assert event.available_at >= event.created_at
    assert session.commits == session.rollbacks == 0


@pytest.mark.parametrize("reason", [None, "   ", "x" * 501])
def test_reject_reason_invariant_is_enforced_inside_service(
    reason: str | None,
) -> None:
    session = FakeSession()
    service = StaffApprovalService(
        repository=FakeRepository(
            actor=user(1, "ADMIN", "ACTIVE"),
            request=approval(),
            staff=user(2, "STAFF", "PENDING_APPROVAL"),
        )
    )
    with pytest.raises(AppException) as captured:
        service.decide(
            session,  # type: ignore[arg-type]
            actor_id=1,
            approval_id=10,
            decision="REJECTED",
            reason=reason,
        )
    assert captured.value.code == "VALIDATION_ERROR"
    assert session.rollbacks == 1
