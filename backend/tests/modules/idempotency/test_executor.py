from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import DomainValidationError, IdempotencyKeyReusedError
from app.modules.idempotency.service import (
    CommandOutcome,
    IdempotencyExecutor,
    IdempotencyOperation,
)
from app.modules.idempotency.validation import request_digest


class FakeSession:
    def __init__(self) -> None:
        self.flushes = 0
        self.commits = 0

    def flush(self) -> None:
        self.flushes += 1

    def commit(self) -> None:
        self.commits += 1


class FakeRepository:
    def __init__(self, record: SimpleNamespace, claimed: bool) -> None:
        self.record = record
        self.claimed = claimed

    def claim_or_lock(self, *_args: object, **_kwargs: object):
        return self.record, self.claimed


def record_for(identity: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        request_digest=request_digest(identity),
        response_status=None,
        response_body=None,
        completed_at=None,
        expires_at=None,
    )


def test_executor_flushes_outcome_but_never_commits() -> None:
    identity = {"operation": "CHECKOUT", "body": {"items": [1]}}
    session = FakeSession()
    executor = IdempotencyExecutor(
        secret=b"s" * 32,
        repository=FakeRepository(record_for(identity), True),  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 11, 11, 1, 2, 3),
    )
    calls = 0

    def command() -> CommandOutcome[dict[str, int]]:
        nonlocal calls
        calls += 1
        return CommandOutcome(201, {"id": 7})

    result = executor.execute(
        session,  # type: ignore[arg-type]
        actor_id=4,
        operation=IdempotencyOperation.CHECKOUT,
        idempotency_key="0123456789abcdef",
        request_identity=identity,
        command=command,
    )
    assert result == CommandOutcome(201, {"id": 7})
    assert calls == 1
    assert session.flushes == 1
    assert session.commits == 0


def test_completed_record_replays_without_command() -> None:
    identity = {"operation": "CANCEL_ORDER", "resource_id": 9, "body": {}}
    record = record_for(identity)
    record.completed_at = datetime(2026, 11, 11)
    record.response_status = 200
    record.response_body = {"id": 9, "status": "CANCELLED"}
    executor = IdempotencyExecutor(
        secret=b"s" * 32,
        repository=FakeRepository(record, False),  # type: ignore[arg-type]
    )
    result = executor.execute(
        FakeSession(),  # type: ignore[arg-type]
        actor_id=4,
        operation=IdempotencyOperation.CANCEL_ORDER,
        idempotency_key="0123456789abcdef",
        request_identity=identity,
        command=lambda: pytest.fail("replay executed command"),
    )
    assert result.status_code == 200
    assert result.body == {"id": 9, "status": "CANCELLED"}


def test_reused_key_with_different_payload_is_conflict() -> None:
    original = {"operation": "CHECKOUT", "body": {"quantity": 1}}
    executor = IdempotencyExecutor(
        secret=b"s" * 32,
        repository=FakeRepository(record_for(original), False),  # type: ignore[arg-type]
    )
    with pytest.raises(IdempotencyKeyReusedError):
        executor.execute(
            FakeSession(),  # type: ignore[arg-type]
            actor_id=4,
            operation=IdempotencyOperation.CHECKOUT,
            idempotency_key="0123456789abcdef",
            request_identity={"operation": "CHECKOUT", "body": {"quantity": 2}},
            command=lambda: CommandOutcome(201, {}),
        )


@pytest.mark.parametrize("status", [199, 500])
def test_invalid_status_does_not_complete_claim(status: int) -> None:
    identity = {"operation": "CHECKOUT", "body": {}}
    with pytest.raises(DomainValidationError, match="200..499"):
        IdempotencyExecutor(
            secret=b"s" * 32,
            repository=FakeRepository(record_for(identity), True),  # type: ignore[arg-type]
        ).execute(
            FakeSession(),  # type: ignore[arg-type]
            actor_id=1,
            operation=IdempotencyOperation.CHECKOUT,
            idempotency_key="0123456789abcdef",
            request_identity=identity,
            command=lambda: CommandOutcome(status, {}),
        )


@pytest.mark.parametrize(
    "identity",
    [{"operation": "CANCEL_ORDER", "body": {}}, {"operation": "CHECKOUT"}],
)
def test_request_identity_must_match_operation_and_include_body(
    identity: dict[str, object],
) -> None:
    with pytest.raises(DomainValidationError, match="operation|body"):
        IdempotencyExecutor(secret=b"s" * 32).execute(
            FakeSession(),  # type: ignore[arg-type]
            actor_id=1,
            operation=IdempotencyOperation.CHECKOUT,
            idempotency_key="0123456789abcdef",
            request_identity=identity,
            command=lambda: CommandOutcome(200, {}),
        )
