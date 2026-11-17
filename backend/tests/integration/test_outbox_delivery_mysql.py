"""Real MySQL delivery-budget and commit-ambiguity tests for T04A90F."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.auth.models import User
from app.modules.outbox.handler import EmailEventHandler
from app.modules.outbox.models import OutboxEvent

pytestmark = pytest.mark.integration
EMAIL_PREFIX = "t04a90f_delivery_"
NOW = datetime(2026, 11, 18, 8, 0)


class RecordingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def send(self, **_kwargs: object) -> None:
        self.calls += 1


def create_event(engine: Engine, *, delivery_attempts: int) -> bytes:
    event_id = uuid4().bytes
    with Session(engine) as session:
        user = User(
            email_normalized=f"{EMAIL_PREFIX}{uuid4().hex}@example.com",
            password_hash="test-hash",
            role="STAFF",
            status="ACTIVE",
            admin_slot=None,
            last_reapplied_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(user)
        session.flush()
        session.add(
            OutboxEvent(
                id=event_id,
                subject_user_id=user.id,
                event_type="STAFF_APPROVED",
                payload={
                    "schema_version": 1,
                    "approval_request_id": 1,
                    "actor_id": 1,
                },
                secret_expires_at=None,
                secret_ciphertext=None,
                created_at=NOW,
                available_at=NOW,
                published_at=NOW,
                publish_attempts=1,
                delivery_attempts=delivery_attempts,
                outcome=None,
                finished_at=None,
                last_error_code=None,
            )
        )
        session.commit()
    return event_id


@pytest.fixture(autouse=True)
def cleanup(migrated_integration_engine: Engine):
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        user_ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if user_ids:
            session.execute(
                delete(OutboxEvent).where(OutboxEvent.subject_user_id.in_(user_ids))
            )
            session.execute(delete(User).where(User.id.in_(user_ids)))


def test_database_budget_prevents_fifth_smtp_send(
    migrated_integration_engine: Engine,
) -> None:
    event_id = create_event(migrated_integration_engine, delivery_attempts=4)
    transport = RecordingTransport()
    factory = sessionmaker(
        bind=migrated_integration_engine, autoflush=False, expire_on_commit=False
    )

    outcome = EmailEventHandler(factory, transport).handle(event_id=event_id)

    assert outcome.status == "FAILED"
    assert transport.calls == 0
    with Session(migrated_integration_engine) as session:
        event = session.get(OutboxEvent, event_id)
        assert event is not None
        assert event.delivery_attempts == 4
        assert event.outcome == "FAILED"
        assert event.last_error_code == "DELIVERY_ATTEMPT_BUDGET_EXHAUSTED"


class CommitThenRaiseSession(Session):
    def commit(self) -> None:
        super().commit()
        raise SQLAlchemyError("simulated lost commit acknowledgement")


def test_terminal_commit_ack_loss_is_verified_before_sent_outcome(
    migrated_integration_engine: Engine,
) -> None:
    event_id = create_event(migrated_integration_engine, delivery_attempts=0)
    transport = RecordingTransport()
    regular_factory = sessionmaker(
        bind=migrated_integration_engine, autoflush=False, expire_on_commit=False
    )
    ambiguous_factory = sessionmaker(
        bind=migrated_integration_engine,
        class_=CommitThenRaiseSession,
        autoflush=False,
        expire_on_commit=False,
    )
    calls = 0

    def factory() -> Session:
        nonlocal calls
        calls += 1
        return ambiguous_factory() if calls == 3 else regular_factory()

    outcome = EmailEventHandler(
        factory,  # type: ignore[arg-type]
        transport,
    ).handle(event_id=event_id)

    assert outcome.status == "SENT"
    assert transport.calls == 1
    with Session(migrated_integration_engine) as session:
        event = session.get(OutboxEvent, event_id)
        assert event is not None
        assert event.delivery_attempts == 1
        assert event.outcome == "SENT"
