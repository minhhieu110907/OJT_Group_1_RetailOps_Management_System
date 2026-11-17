"""Unit tests for the T04A90F publisher and email handler."""

from datetime import datetime
from inspect import signature
from types import SimpleNamespace
from uuid import UUID

import pytest
from amqp.exceptions import MessageNacked
from celery.exceptions import Reject, Retry
from kombu.exceptions import ChannelError, OperationalError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.modules.outbox.broker import CeleryEventPublisher
from app.modules.outbox.contracts import EmailOutcome, PublishBatchResult
from app.modules.outbox.errors import (
    BrokerPublishError,
    DatabaseUnavailableError,
    PermanentEmailError,
    TransientEmailError,
)
from app.modules.outbox.handler import EmailEventHandler
from app.modules.outbox.protocol import parse_envelope
from app.modules.outbox.publisher import OutboxPublisher
from app.modules.outbox.retry import retry_or_requeue

EVENT_ID = UUID("3a7a6e1b-8d55-4132-bb4c-1fd0e7e2c001").bytes
NOW = datetime(2026, 11, 18, 8, 0)


class FakeSession:
    def __init__(self, commit_error: Exception | None = None) -> None:
        self.commits = 0
        self.commit_error = commit_error

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error


def session_factory() -> FakeSession:
    return FakeSession()


class PublisherRepository:
    def __init__(self) -> None:
        self.mark_result = True
        self.readback: datetime | None = None
        self.errors: list[str] = []

    def due_event_ids(self, _session: object, **_kwargs: object) -> tuple[bytes, ...]:
        return (EVENT_ID,)

    def skip_expired_disabled_secrets(self, _session: object, **_kwargs: object) -> int:
        return 0

    def increment_publish_attempt(self, _session: object, _event_id: bytes) -> bool:
        return True

    def mark_published(self, _session: object, **_kwargs: object) -> bool:
        return self.mark_result

    def published_at(self, _session: object, _event_id: bytes) -> datetime | None:
        return self.readback

    def record_publish_error(self, _session: object, **kwargs: object) -> None:
        self.errors.append(str(kwargs["error_code"]))


class FakeBroker:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[bytes] = []

    def publish(self, event_id: bytes) -> None:
        if self.fail:
            raise BrokerPublishError("broker unavailable")
        self.published.append(event_id)


class ProgrammingErrorBroker:
    def publish(self, _event_id: bytes) -> None:
        raise ValueError("programming defect")


class FakeCeleryApp:
    def __init__(self) -> None:
        self.options: dict[str, object] | None = None

    def send_task(self, _name: str, **options: object) -> None:
        self.options = options


@pytest.mark.parametrize("batch_size", [0, 26])
def test_publisher_rejects_batch_outside_contract(batch_size: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 25"):
        OutboxPublisher(FakeBroker()).publish_due(
            session_factory,  # type: ignore[arg-type]
            batch_size=batch_size,
        )


def test_publisher_marks_only_after_broker_success() -> None:
    repository = PublisherRepository()
    broker = FakeBroker()
    result = OutboxPublisher(
        broker,
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    ).publish_due(session_factory, batch_size=1)  # type: ignore[arg-type]

    assert result == PublishBatchResult(scanned=1, published=1, failed=0)
    assert broker.published == [EVENT_ID]


def test_broker_failure_keeps_event_unpublished() -> None:
    repository = PublisherRepository()
    result = OutboxPublisher(
        FakeBroker(fail=True),
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    ).publish_due(session_factory, batch_size=1)  # type: ignore[arg-type]

    assert result == PublishBatchResult(scanned=1, published=0, failed=1)
    assert repository.errors == ["BROKER_PUBLISH_FAILED"]


def test_publisher_does_not_swallow_programming_error() -> None:
    with pytest.raises(ValueError, match="programming defect"):
        OutboxPublisher(
            ProgrammingErrorBroker(),
            repository=PublisherRepository(),  # type: ignore[arg-type]
            clock=lambda: NOW,
        ).publish_due(session_factory, batch_size=1)  # type: ignore[arg-type]


def test_confirmed_publish_commit_unknown_uses_fresh_readback() -> None:
    repository = PublisherRepository()
    repository.readback = NOW
    sessions = iter(
        [
            FakeSession(),
            FakeSession(),
            FakeSession(SQLAlchemyError("commit acknowledgement lost")),
            FakeSession(),
        ]
    )

    result = OutboxPublisher(
        FakeBroker(),
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    ).publish_due(lambda: next(sessions), batch_size=1)  # type: ignore[arg-type]

    assert result == PublishBatchResult(scanned=1, published=1, failed=0)


def test_confirmed_publish_conditional_update_miss_is_visible_without_pii(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = PublisherRepository()
    repository.mark_result = False
    result = OutboxPublisher(
        FakeBroker(),
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    ).publish_due(session_factory, batch_size=1)  # type: ignore[arg-type]
    assert result == PublishBatchResult(scanned=1, published=0, failed=1)
    record = next(
        item
        for item in caplog.records
        if getattr(item, "error_code", None) == "DB_PUBLISH_CONFIRM_NOT_APPLIED"
    )
    assert record.event_id == str(UUID(bytes=EVENT_ID))  # type: ignore[attr-defined]
    assert "email" not in record.getMessage().casefold()


def test_celery_envelope_contains_only_event_id_and_version() -> None:
    envelope = CeleryEventPublisher.envelope(EVENT_ID)
    assert envelope == {
        "event_id": "3a7a6e1b-8d55-4132-bb4c-1fd0e7e2c001",
        "schema_version": 1,
    }
    assert "email" not in envelope
    assert "token" not in envelope


def test_celery_publish_requires_routable_persistent_confirm() -> None:
    app = FakeCeleryApp()
    settings = Settings(
        db_host="mysql",
        db_name="retailops_test",
        db_user="test",
        db_password="test-password",
    )
    CeleryEventPublisher(app, settings).publish(EVENT_ID)  # type: ignore[arg-type]
    assert app.options is not None
    assert app.options["delivery_mode"] == 2
    assert app.options["mandatory"] is True
    assert app.options["declare"] == ()
    assert app.options["retry"] is False
    assert app.options["queue"] == "retailops.email.v1"
    assert app.options["exchange"] == "retailops.email"
    assert app.options["routing_key"] == "email.deliver.v1"
    assert app.options["serializer"] == "json"
    assert app.options["ignore_result"] is True
    assert app.options["task_id"] == str(UUID(bytes=EVENT_ID))
    assert app.options["kwargs"] == {
        "envelope": {
            "event_id": str(UUID(bytes=EVENT_ID)),
            "schema_version": 1,
        }
    }


def test_celery_app_disables_worker_topology_declarations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("RETAILOPS_DB_HOST", "mysql")
    monkeypatch.setenv("RETAILOPS_DB_NAME", "retailops_test")
    monkeypatch.setenv("RETAILOPS_DB_USER", "test")
    monkeypatch.setenv("RETAILOPS_DB_PASSWORD", "test-password")
    monkeypatch.setenv(
        "RETAILOPS_RABBITMQ_URL",
        "amqp://worker:pass@rabbitmq:5672/%2Fretailops",
    )
    get_settings.cache_clear()
    try:
        from app.worker.celery_app import create_celery_app

        app = create_celery_app()
        assert app.conf.worker_enable_remote_control is False
        assert app.conf.task_create_missing_queues is False
        assert app.conf.task_default_queue == "retailops.email.v1"
        assert app.conf.task_default_exchange == "retailops.email"
        assert app.conf.task_default_routing_key == "email.deliver.v1"
        assert "retailops.email.v1" in app.amqp.queues
        assert "celery" not in app.amqp.queues
        assert app.amqp.default_queue.name == "retailops.email.v1"
        assert len(app.conf.task_queues) == 1
        queue = app.conf.task_queues[0]
        assert queue.name == "retailops.email.v1"
        assert queue.no_declare is True
        assert queue.exchange.name == "retailops.email"
        assert queue.exchange.no_declare is True
    finally:
        get_settings.cache_clear()


def test_celery_retry_uses_configured_default_queue_without_celery_keyerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager

    from kombu import Connection, Producer

    from app.core.config import get_settings

    monkeypatch.setenv("RETAILOPS_DB_HOST", "mysql")
    monkeypatch.setenv("RETAILOPS_DB_NAME", "retailops_test")
    monkeypatch.setenv("RETAILOPS_DB_USER", "test")
    monkeypatch.setenv("RETAILOPS_DB_PASSWORD", "test-password")
    monkeypatch.setenv(
        "RETAILOPS_RABBITMQ_URL",
        "amqp://worker:pass@rabbitmq:5672/%2Fretailops",
    )
    get_settings.cache_clear()
    try:
        from app.worker.celery_app import create_celery_app

        app = create_celery_app()
        published: list[dict[str, object]] = []

        @app.task(
            bind=True,
            name="retailops.email.deliver_v1",
            acks_late=True,
            reject_on_worker_lost=True,
            max_retries=3,
        )
        def probe_task(self: object, *, envelope: object) -> None:
            return None

        canonical_id = str(UUID(bytes=EVENT_ID))
        with Connection("memory://") as memory_conn:
            real_producer = Producer(memory_conn)

            def spy_publish(_body: object, **kwargs: object) -> None:
                published.append(kwargs)

            monkeypatch.setattr(real_producer, "publish", spy_publish)

            @contextmanager
            def memory_producer_or_acquire(
                _producer: object = None,
            ) -> Iterator[Producer]:
                yield real_producer

            monkeypatch.setattr(app, "producer_or_acquire", memory_producer_or_acquire)

            probe_task.push_request(
                id=canonical_id,
                retries=0,
                called_directly=False,
                kwargs={"envelope": {"event_id": canonical_id, "schema_version": 1}},
                delivery_info={
                    "exchange": "retailops.email",
                    "routing_key": "email.deliver.v1",
                },
            )
            try:
                with pytest.raises(Retry):
                    retry_or_requeue(
                        probe_task,
                        RuntimeError("SMTP_TRANSIENT"),
                        delays=(30, 120, 300),
                    )
            finally:
                probe_task.pop_request()

        assert len(published) == 1
        call = published[0]
        assert call["exchange"] == "retailops.email"
        assert call["routing_key"] == "email.deliver.v1"
        headers = call["headers"]
        assert isinstance(headers, dict)
        assert headers["task"] == "retailops.email.deliver_v1"
        assert headers["id"] == canonical_id
        assert headers["retries"] == 1
        assert headers.get("eta") is not None
        declared = call.get("declare") or ()
        assert all(getattr(entity, "no_declare", False) for entity in declared)
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "event_id",
    [
        "3A7A6E1B-8D55-4132-BB4C-1FD0E7E2C001",
        "3a7a6e1b8d554132bb4c1fd0e7e2c001",
        "not-a-uuid",
    ],
)
def test_envelope_rejects_noncanonical_event_id(event_id: str) -> None:
    with pytest.raises(ValueError):
        parse_envelope({"event_id": event_id, "schema_version": 1})


def test_envelope_round_trip() -> None:
    assert parse_envelope(CeleryEventPublisher.envelope(EVENT_ID)) == EVENT_ID


def test_runtime_abi_matches_frozen_contract() -> None:
    publish_parameters = signature(OutboxPublisher.publish_due).parameters
    handler_parameters = signature(EmailEventHandler.handle).parameters
    assert tuple(publish_parameters) == ("self", "session_factory", "batch_size")
    assert publish_parameters["batch_size"].kind.name == "KEYWORD_ONLY"
    assert tuple(handler_parameters) == ("self", "event_id")
    assert handler_parameters["event_id"].kind.name == "KEYWORD_ONLY"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outbox_exchange", "other.exchange"),
        ("outbox_queue", "other.queue"),
        ("outbox_routing_key", "other.route"),
        ("outbox_task_name", "other.task"),
    ],
)
def test_broker_contract_names_cannot_drift(field: str, value: str) -> None:
    values = {
        "db_host": "mysql",
        "db_name": "retailops_test",
        "db_user": "test",
        "db_password": "test-password",
        field: value,
    }
    with pytest.raises(ValidationError, match="frozen by the BE-OUTBOX contract"):
        Settings(**values)


def base_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "db_host": "mysql",
        "db_name": "retailops_test",
        "db_user": "test",
        "db_password": "test-password",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_api_does_not_require_smtp() -> None:
    settings = base_settings(
        environment="production",
        cookie_secure=True,
        jwt_secret="j" * 32,
        csrf_secret="c" * 32,
    )
    assert settings.smtp_host is None


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"smtp_host": "mailpit", "smtp_starttls": True},
        {"smtp_host": "smtp.example.com", "smtp_starttls": False},
        {
            "smtp_host": "smtp.example.com",
            "smtp_starttls": True,
            "smtp_from_address": "no-reply@retailops.local",
        },
    ],
)
def test_production_worker_rejects_unsafe_smtp(overrides: dict[str, object]) -> None:
    settings = base_settings(
        environment="production",
        cookie_secure=True,
        jwt_secret="j" * 32,
        csrf_secret="c" * 32,
        **overrides,
    )
    with pytest.raises(RuntimeError):
        settings.validate_email_worker_configuration()


def test_production_worker_accepts_tls_provider_configuration() -> None:
    settings = base_settings(
        environment="production",
        cookie_secure=True,
        jwt_secret="j" * 32,
        csrf_secret="c" * 32,
        smtp_host="smtp.provider.example",
        smtp_starttls=True,
        smtp_from_address="no-reply@example.com",
    )
    settings.validate_email_worker_configuration()


def test_rabbitmq_url_encodes_credentials_and_vhost() -> None:
    settings = base_settings(
        rabbitmq_host="rabbitmq",
        rabbitmq_username="worker+mail",
        rabbitmq_password="p@ss:/word",
        rabbitmq_vhost="/retailops email",
    )
    assert settings.require_rabbitmq_url() == (
        "amqp://worker%2Bmail:p%40ss%3A%2Fword@rabbitmq:5672/%2Fretailops%20email"
    )


class RetryPublishFailureTask:
    request = SimpleNamespace(retries=0)

    def __init__(self, error: Exception) -> None:
        self.error = error

    def retry(self, **_kwargs: object) -> None:
        raise self.error


class RetryTask:
    def __init__(self, retries: int) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.options: dict[str, object] | None = None

    def retry(self, **options: object) -> None:
        self.options = options
        raise Retry()


@pytest.mark.parametrize(
    "publish_error",
    [
        OperationalError("broker unavailable"),
        ChannelError("route unavailable"),
        MessageNacked(),
    ],
)
def test_retry_publish_failure_requeues_without_blocking(
    publish_error: Exception,
) -> None:
    with pytest.raises(Reject) as raised:
        retry_or_requeue(
            RetryPublishFailureTask(publish_error),  # type: ignore[arg-type]
            RuntimeError("smtp transient"),
            delays=(30, 120, 300),
        )
    assert raised.value.requeue is True


def test_confirmed_retry_uses_frozen_delay_and_budget() -> None:
    task = RetryTask(retries=1)
    with pytest.raises(Retry):
        retry_or_requeue(  # type: ignore[arg-type]
            task,
            RuntimeError("smtp transient"),
            delays=(30, 120, 300),
        )
    assert task.options is not None
    assert isinstance(task.options["exc"], RuntimeError)
    assert task.options["countdown"] == 120
    assert task.options["max_retries"] == 3


def test_exhausted_infrastructure_retry_is_parked_not_requeued() -> None:
    task = RetryTask(retries=3)
    with pytest.raises(Reject) as raised:
        retry_or_requeue(  # type: ignore[arg-type]
            task,
            RuntimeError("database unavailable"),
            delays=(30, 120, 300),
        )
    assert raised.value.requeue is False
    assert task.options is None


class HandlerRepository:
    def __init__(self, *, outcome: str | None = None, attempts: int = 1) -> None:
        self.event = SimpleNamespace(
            id=EVENT_ID,
            event_type="STAFF_APPROVED",
            outcome=outcome,
        )
        self.user = SimpleNamespace(email_normalized="staff@example.com")
        self.attempts = attempts
        self.finished: list[tuple[str, str | None]] = []
        self.transient: list[str] = []

    def load_event_and_user(self, _session: object, _event_id: bytes):
        return self.event, self.user

    def begin_delivery_attempt(
        self, _session: object, _event_id: bytes, **_kwargs: object
    ) -> int | None:
        return self.attempts

    def delivery_state(
        self, _session: object, _event_id: bytes
    ) -> tuple[int, str | None, str | None]:
        error_code = self.transient[-1] if self.transient else None
        return self.attempts, self.event.outcome, error_code

    def finish_delivery(self, _session: object, **kwargs: object) -> bool:
        self.finished.append((str(kwargs["outcome"]), kwargs.get("error_code")))
        self.event.outcome = kwargs["outcome"]
        return True

    def record_transient_delivery_error(
        self, _session: object, **kwargs: object
    ) -> bool:
        self.transient.append(str(kwargs["error_code"]))
        return True


class FakeTransport:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def send(self, **_kwargs: object) -> None:
        self.calls += 1
        if self.error:
            raise self.error


def handler(
    repository: HandlerRepository, transport: FakeTransport
) -> EmailEventHandler:
    return EmailEventHandler(
        session_factory,  # type: ignore[arg-type]
        transport,
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )


def test_handler_terminal_short_circuit_does_not_send() -> None:
    repository = HandlerRepository(outcome="SENT")
    transport = FakeTransport()
    result = handler(repository, transport).handle(event_id=EVENT_ID)
    assert result == EmailOutcome(EVENT_ID, "SKIPPED")
    assert transport.calls == 0


def test_handler_transient_failure_remains_nonterminal() -> None:
    repository = HandlerRepository(attempts=1)
    result = handler(
        repository, FakeTransport(TransientEmailError("temporary"))
    ).handle(event_id=EVENT_ID)
    assert result == EmailOutcome(EVENT_ID, "RETRY")
    assert repository.finished == []
    assert repository.transient == ["SMTP_TRANSIENT"]


def test_fourth_transient_attempt_becomes_failed() -> None:
    repository = HandlerRepository(attempts=4)
    result = handler(
        repository, FakeTransport(TransientEmailError("temporary"))
    ).handle(event_id=EVENT_ID)
    assert result == EmailOutcome(EVENT_ID, "FAILED")
    assert repository.finished == [("FAILED", "SMTP_RETRIES_EXHAUSTED")]


def test_exhausted_database_budget_does_not_send_fifth_email() -> None:
    repository = HandlerRepository(attempts=0)
    transport = FakeTransport()
    result = handler(repository, transport).handle(event_id=EVENT_ID)
    assert result == EmailOutcome(EVENT_ID, "FAILED")
    assert transport.calls == 0


class NonDurableTerminalRepository(HandlerRepository):
    def finish_delivery(self, _session: object, **_kwargs: object) -> bool:
        return True


def test_terminal_commit_failure_is_not_reported_as_success() -> None:
    repository = NonDurableTerminalRepository()
    transport = FakeTransport()
    sessions = iter(
        [
            FakeSession(),
            FakeSession(),
            FakeSession(SQLAlchemyError("commit failed")),
            FakeSession(),
        ]
    )
    instance = EmailEventHandler(
        lambda: next(sessions),  # type: ignore[arg-type]
        transport,
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    with pytest.raises(
        DatabaseUnavailableError, match="Terminal Outbox state was not persisted"
    ):
        instance.handle(event_id=EVENT_ID)
    assert transport.calls == 1


def test_permanent_failure_is_terminal() -> None:
    repository = HandlerRepository()
    result = handler(
        repository, FakeTransport(PermanentEmailError("bad recipient"))
    ).handle(event_id=EVENT_ID)
    assert result == EmailOutcome(EVENT_ID, "FAILED")
    assert repository.finished == [("FAILED", "SMTP_PERMANENT")]
