"""MySQL/InnoDB evidence for the shared TD-04C idempotency framework."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event, Lock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.exceptions import IdempotencyKeyReusedError
from app.modules.auth.models import User
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.idempotency.repository import IdempotencyRepository
from app.modules.idempotency.service import (
    CommandOutcome,
    IdempotencyExecutor,
    IdempotencyOperation,
)
from app.modules.outbox.models import OutboxEvent

pytestmark = pytest.mark.integration
SECRET = b"integration-idempotency-secret!!" * 2
EMAIL_PREFIX = "idem_test_"


def cleanup(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.user_id.in_(ids))
            )
            session.execute(
                delete(OutboxEvent).where(OutboxEvent.subject_user_id.in_(ids))
            )
            session.execute(delete(User).where(User.id.in_(ids)))


@pytest.fixture(autouse=True)
def clean_test_rows(migrated_integration_engine: Engine):
    cleanup(migrated_integration_engine)
    yield
    cleanup(migrated_integration_engine)


def create_actor(engine: Engine, suffix: str) -> int:
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session, session.begin():
        actor = User(
            email_normalized=f"{EMAIL_PREFIX}{suffix}_{uuid4().hex}@example.com",
            password_hash="not-used-by-idempotency-tests",
            role="STAFF",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        session.add(actor)
        session.flush()
        return actor.id


def append_effect(session: Session, actor_id: int, marker: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        OutboxEvent(
            id=uuid4().bytes,
            subject_user_id=actor_id,
            event_type="STAFF_APPROVED",
            payload={"marker": marker},
            created_at=now,
            available_at=now,
        )
    )
    session.flush()


def effect_count(engine: Engine, actor_id: int) -> int:
    with Session(engine) as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.subject_user_id == actor_id)
            )
            or 0
        )


def execute_and_commit(
    engine: Engine,
    *,
    actor_id: int,
    operation: IdempotencyOperation = IdempotencyOperation.CHECKOUT,
    key: str = "0123456789abcdef",
    identity: dict[str, object] | None = None,
    marker: str = "first",
) -> CommandOutcome[dict[str, object]]:
    identity = identity or {"operation": operation.value, "body": {"quantity": 1}}
    with Session(engine) as session:
        outcome = IdempotencyExecutor(secret=SECRET).execute(
            session,
            actor_id=actor_id,
            operation=operation,
            idempotency_key=key,
            request_identity=identity,
            command=lambda: (
                append_effect(session, actor_id, marker)
                or CommandOutcome(201, {"marker": marker})
            ),
        )
        session.commit()
        return outcome


def test_replay_collision_and_response_loss(
    migrated_integration_engine: Engine,
) -> None:
    actor_id = create_actor(migrated_integration_engine, "replay")
    first = execute_and_commit(migrated_integration_engine, actor_id=actor_id)
    replay = execute_and_commit(
        migrated_integration_engine, actor_id=actor_id, marker="must-not-run"
    )
    assert first == replay == CommandOutcome(201, {"marker": "first"})
    with pytest.raises(IdempotencyKeyReusedError):
        execute_and_commit(
            migrated_integration_engine,
            actor_id=actor_id,
            identity={"operation": "CHECKOUT", "body": {"quantity": 2}},
        )
    assert effect_count(migrated_integration_engine, actor_id) == 1


def test_actor_and_operation_are_independent_namespaces(
    migrated_integration_engine: Engine,
) -> None:
    actor_a = create_actor(migrated_integration_engine, "namespace_a")
    actor_b = create_actor(migrated_integration_engine, "namespace_b")
    execute_and_commit(migrated_integration_engine, actor_id=actor_a)
    execute_and_commit(migrated_integration_engine, actor_id=actor_b)
    execute_and_commit(
        migrated_integration_engine,
        actor_id=actor_a,
        operation=IdempotencyOperation.CANCEL_ORDER,
        identity={"operation": "CANCEL_ORDER", "resource_id": 1, "body": {}},
    )
    assert effect_count(migrated_integration_engine, actor_a) == 2
    assert effect_count(migrated_integration_engine, actor_b) == 1


def test_concurrent_duplicate_proves_lock_wait_and_one_command(
    migrated_integration_engine: Engine,
) -> None:
    actor_id = create_actor(migrated_integration_engine, "concurrency")
    first_inside = Event()
    release_first = Event()
    second_started = Event()
    calls = 0
    calls_lock = Lock()

    def run(first: bool) -> CommandOutcome[dict[str, object]]:
        nonlocal calls
        with Session(migrated_integration_engine) as session:

            def command() -> CommandOutcome[dict[str, object]]:
                nonlocal calls
                with calls_lock:
                    calls += 1
                append_effect(session, actor_id, "winner")
                if first:
                    first_inside.set()
                    assert release_first.wait(timeout=5)
                return CommandOutcome(201, {"marker": "winner"})

            if not first:
                second_started.set()
            result = IdempotencyExecutor(secret=SECRET).execute(
                session,
                actor_id=actor_id,
                operation=IdempotencyOperation.CHECKOUT,
                idempotency_key="concurrent-key-01",
                request_identity={"operation": "CHECKOUT", "body": {"quantity": 1}},
                command=command,
            )
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(run, True)
        assert first_inside.wait(timeout=5)
        second_future = pool.submit(run, False)
        assert second_started.wait(timeout=5)
        assert not second_future.done(), "duplicate did not wait on InnoDB unique key"
        release_first.set()
        assert first_future.result(timeout=10) == second_future.result(timeout=10)
    assert calls == 1
    assert effect_count(migrated_integration_engine, actor_id) == 1


def test_business_write_and_claim_roll_back_together(
    migrated_integration_engine: Engine,
) -> None:
    actor_id = create_actor(migrated_integration_engine, "rollback")
    with (
        pytest.raises(RuntimeError, match="forced failure"),
        Session(migrated_integration_engine) as session,
    ):

        def failing_command() -> CommandOutcome[dict[str, object]]:
            append_effect(session, actor_id, "rolled-back")
            raise RuntimeError("forced failure")

        IdempotencyExecutor(secret=SECRET).execute(
            session,
            actor_id=actor_id,
            operation=IdempotencyOperation.CHECKOUT,
            idempotency_key="rollback-key-001",
            request_identity={"operation": "CHECKOUT", "body": {}},
            command=failing_command,
        )
    assert effect_count(migrated_integration_engine, actor_id) == 0
    execute_and_commit(
        migrated_integration_engine,
        actor_id=actor_id,
        key="rollback-key-001",
        identity={"operation": "CHECKOUT", "body": {}},
    )
    assert effect_count(migrated_integration_engine, actor_id) == 1


def test_autobegin_expiry_and_bounded_cleanup(
    migrated_integration_engine: Engine,
) -> None:
    actor_id = create_actor(migrated_integration_engine, "autobegin")
    with Session(migrated_integration_engine) as session:
        assert session.get(User, actor_id) is not None
        assert session.in_transaction()
        IdempotencyExecutor(secret=SECRET).execute(
            session,
            actor_id=actor_id,
            operation=IdempotencyOperation.CHECKOUT,
            idempotency_key="autobegun-key-01",
            request_identity={"operation": "CHECKOUT", "body": {}},
            command=lambda: (
                append_effect(session, actor_id, "autobegun") or CommandOutcome(200, {})
            ),
        )
        session.commit()


def test_duplicate_lock_timeout_rolls_back_then_retry_replays(
    migrated_integration_engine: Engine,
) -> None:
    actor_id = create_actor(migrated_integration_engine, "lock_timeout")
    first_inside = Event()
    release_first = Event()

    def winner() -> None:
        with Session(migrated_integration_engine) as session:

            def command() -> CommandOutcome[dict[str, object]]:
                append_effect(session, actor_id, "lock-timeout-winner")
                first_inside.set()
                assert release_first.wait(timeout=5)
                return CommandOutcome(201, {"winner": True})

            IdempotencyExecutor(secret=SECRET).execute(
                session,
                actor_id=actor_id,
                operation=IdempotencyOperation.CHECKOUT,
                idempotency_key="lock-timeout-key",
                request_identity={"operation": "CHECKOUT", "body": {}},
                command=command,
            )
            session.commit()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(winner)
        assert first_inside.wait(timeout=5)
        with Session(migrated_integration_engine) as session:
            with pytest.raises(OperationalError) as caught:
                IdempotencyExecutor(secret=SECRET).execute(
                    session,
                    actor_id=actor_id,
                    operation=IdempotencyOperation.CHECKOUT,
                    idempotency_key="lock-timeout-key",
                    request_identity={"operation": "CHECKOUT", "body": {}},
                    command=lambda: pytest.fail("timed-out duplicate ran command"),
                )
            assert caught.value.orig.args[0] == 1205
            session.rollback()
        release_first.set()
        future.result(timeout=10)

    replay = execute_and_commit(
        migrated_integration_engine,
        actor_id=actor_id,
        key="lock-timeout-key",
        identity={"operation": "CHECKOUT", "body": {}},
        marker="must-not-run",
    )
    assert replay == CommandOutcome(201, {"winner": True})
    assert effect_count(migrated_integration_engine, actor_id) == 1


def test_real_deadlock_rolls_back_losing_claim_and_business_effect(
    migrated_integration_engine: Engine,
) -> None:
    actor_id = create_actor(migrated_integration_engine, "deadlock_a")
    with Session(migrated_integration_engine) as seed_session, seed_session.begin():
        first_row_id = uuid4().bytes
        second_row_id = uuid4().bytes
        now = datetime.now(UTC).replace(tzinfo=None)
        for row_id in (first_row_id, second_row_id):
            seed_session.add(
                OutboxEvent(
                    id=row_id,
                    subject_user_id=actor_id,
                    event_type="STAFF_APPROVED",
                    payload={"seed": True},
                    created_at=now,
                    available_at=now,
                )
            )
    first_locks = [Event(), Event()]

    def run(index: int, first_id: bytes, second_id: bytes) -> str:
        with Session(migrated_integration_engine) as session:

            def command() -> CommandOutcome[dict[str, object]]:
                session.scalar(
                    select(OutboxEvent)
                    .where(OutboxEvent.id == first_id)
                    .with_for_update()
                )
                first_locks[index].set()
                assert first_locks[1 - index].wait(timeout=5)
                session.scalar(
                    select(OutboxEvent)
                    .where(OutboxEvent.id == second_id)
                    .with_for_update()
                )
                append_effect(session, actor_id, f"deadlock-winner-{index}")
                return CommandOutcome(200, {"index": index})

            try:
                IdempotencyExecutor(secret=SECRET).execute(
                    session,
                    actor_id=actor_id,
                    operation=IdempotencyOperation.CHECKOUT,
                    idempotency_key=f"deadlock-key-000{index}",
                    request_identity={
                        "operation": "CHECKOUT",
                        "body": {"index": index},
                    },
                    command=command,
                )
                session.commit()
                return "SUCCESS"
            except OperationalError as error:
                session.rollback()
                return f"MYSQL_{error.orig.args[0]}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda args: run(*args),
                [
                    (0, first_row_id, second_row_id),
                    (1, second_row_id, first_row_id),
                ],
            )
        )
    assert sorted(outcomes) == ["MYSQL_1213", "SUCCESS"]
    assert effect_count(migrated_integration_engine, actor_id) == 3
    with Session(migrated_integration_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.user_id == actor_id)
            )
            == 1
        )
    with Session(migrated_integration_engine) as session:
        record = session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.user_id == actor_id)
        )
        assert record is not None and record.completed_at is not None
        assert record.expires_at == record.completed_at + timedelta(hours=24)
        assert (
            IdempotencyRepository().delete_expired(
                session, before=record.expires_at + timedelta(microseconds=1), limit=1
            )
            == 1
        )
        session.commit()
