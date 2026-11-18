"""Real RabbitMQ acceptance checks for the frozen T04A90F topology."""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import IO
from uuid import UUID, uuid4

import pytest
from amqp.exceptions import MessageNacked
from celery import Celery
from kombu import Connection, Exchange, Producer, Queue
from kombu.exceptions import ChannelError, OperationalError
from kombu.message import Message
from sqlalchemy import delete, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.outbox.models import OutboxEvent

pytestmark = pytest.mark.rabbitmq_integration

LIVE_EXCHANGE = Exchange("retailops.email", type="direct", durable=True)
LIVE_QUEUE = Queue(
    "retailops.email.v1",
    exchange=LIVE_EXCHANGE,
    routing_key="email.deliver.v1",
    durable=True,
    queue_arguments={"x-queue-type": "quorum"},
)
PARKING_EXCHANGE = Exchange("retailops.email.parking", type="direct", durable=True)
PARKING_QUEUE = Queue(
    "retailops.email.parked.v1",
    exchange=PARKING_EXCHANGE,
    routing_key="email.parked.v1",
    durable=True,
    queue_arguments={"x-queue-type": "quorum"},
)
EMAIL_PREFIX = "t04a90f_worker_"
NOW = datetime(2026, 11, 18, 8, 0)


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} is required for RabbitMQ integration tests")
    return value


def management_get(path: str) -> object:
    username = required_environment("RABBITMQ_BOOTSTRAP_USER")
    password = required_environment("RABBITMQ_BOOTSTRAP_PASSWORD")
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = urllib.request.Request(
        f"{required_environment('RETAILOPS_TEST_RABBITMQ_MANAGEMENT_URL')}{path}",
        headers={"Authorization": f"Basic {token}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


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


def cleanup_worker_events(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        user_ids = select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
        session.execute(
            delete(OutboxEvent).where(OutboxEvent.subject_user_id.in_(user_ids))
        )
        session.execute(
            delete(User).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
        )


def worker_environment(
    database_url: URL,
    *,
    smtp_host: str = "127.0.0.1",
    smtp_port: int = 1,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "RETAILOPS_ENVIRONMENT": "development",
            "RETAILOPS_DB_HOST": database_url.host or "",
            "RETAILOPS_DB_PORT": str(database_url.port or 3306),
            "RETAILOPS_DB_NAME": database_url.database or "",
            "RETAILOPS_DB_USER": database_url.username or "",
            "RETAILOPS_DB_PASSWORD": database_url.password or "",
            "RETAILOPS_RABBITMQ_URL": required_environment(
                "RETAILOPS_TEST_RABBITMQ_WORKER_URL"
            ),
            "RETAILOPS_SMTP_HOST": smtp_host,
            "RETAILOPS_SMTP_PORT": str(smtp_port),
            "RETAILOPS_SMTP_FROM_ADDRESS": "no-reply@retailops.local",
            "RETAILOPS_SMTP_STARTTLS": "false",
        }
    )
    if extra_env:
        environment.update(extra_env)
    return environment


def sanitized_worker_output(
    output: bytes, environment: dict[str, str], *, limit: int = 4_000
) -> str:
    text = output.decode("utf-8", errors="replace")
    for name, value in environment.items():
        if value and ("PASSWORD" in name or name.endswith("_URL")):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(
        r"\b(?:amqps?|mysql(?:\+pymysql)?|redis)://[^\s@]+@",
        "[URL_REDACTED]@",
        text,
    )
    text = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[EMAIL_REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    return text[-limit:]


@dataclass(frozen=True)
class WorkerHandle:
    process: subprocess.Popen[bytes]
    read_log: Callable[[], str]


def read_worker_log(worker_log: IO[bytes]) -> bytes:
    # pread never moves the file offset shared with the running child process.
    return os.pread(worker_log.fileno(), os.fstat(worker_log.fileno()).st_size, 0)


@contextmanager
def running_worker(
    database_url: URL,
    *,
    loglevel: str = "WARNING",
    smtp_host: str = "127.0.0.1",
    smtp_port: int = 1,
    extra_env: dict[str, str] | None = None,
) -> Iterator[WorkerHandle]:
    environment = worker_environment(
        database_url, smtp_host=smtp_host, smtp_port=smtp_port, extra_env=extra_env
    )
    with tempfile.TemporaryFile() as worker_log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.worker.celery_app:celery_app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--prefetch-multiplier=1",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                f"--loglevel={loglevel}",
                "--queues=retailops.email.v1",
            ],
            env=environment,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    worker_log.seek(0)
                    diagnostics = sanitized_worker_output(
                        worker_log.read(), environment
                    )
                    pytest.fail(
                        f"Celery worker exited with code {process.returncode}:\n"
                        f"{diagnostics}"
                    )
                queue = management_get("/api/queues/%2Fretailops/retailops.email.v1")
                if isinstance(queue, dict) and queue.get("consumers", 0) >= 1:
                    yield WorkerHandle(
                        process,
                        lambda: sanitized_worker_output(
                            read_worker_log(worker_log), environment
                        ),
                    )
                    return
                time.sleep(0.25)
            worker_log.seek(0)
            diagnostics = sanitized_worker_output(worker_log.read(), environment)
            pytest.fail(
                "Celery worker did not start consuming within 30 seconds:\n"
                f"{diagnostics}"
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def publish_email_task(event_id: bytes) -> None:
    canonical_id = str(UUID(bytes=event_id))
    publish_envelope({"event_id": canonical_id, "schema_version": 1}, canonical_id)


def publish_envelope(envelope: object, task_id: str) -> None:
    app = Celery(
        "t04a90f-worker-test",
        broker=required_environment("RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL"),
    )
    app.conf.broker_transport_options = {"confirm_publish": True}
    app.conf.task_queues = (LIVE_QUEUE,)
    app.send_task(
        "retailops.email.deliver_v1",
        kwargs={"envelope": envelope},
        task_id=task_id,
        queue=LIVE_QUEUE.name,
        exchange="retailops.email",
        routing_key="email.deliver.v1",
        serializer="json",
        delivery_mode=2,
        mandatory=True,
        declare=(),
        retry=False,
    )


def wait_for_event(
    engine: Engine,
    event_id: bytes,
    predicate: Callable[[OutboxEvent], bool],
    timeout: float = 15.0,
) -> OutboxEvent:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with Session(engine) as session:
            event = session.get(OutboxEvent, event_id)
            if event is not None and predicate(event):
                session.expunge(event)
                return event
        time.sleep(0.1)
    pytest.fail("Outbox event did not reach the expected state")


def queue_state(queue_name: str) -> dict[str, int]:
    queue = management_get(f"/api/queues/%2Fretailops/{queue_name}")
    assert isinstance(queue, dict)
    return {
        key: int(queue.get(key) or 0)
        for key in (
            "messages",
            "messages_ready",
            "messages_unacknowledged",
            "consumers",
        )
    }


def wait_until(
    condition: Callable[[], bool],
    *,
    timeout: float,
    failure: Callable[[], str],
    interval: float = 0.25,
) -> None:
    """Poll an observable condition; fail with sanitized diagnostics, never skip."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    if condition():
        return
    pytest.fail(failure())


def parse_eta(value: object) -> datetime:
    assert isinstance(value, str), f"Celery eta header missing: {value!r}"
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def broker_diagnostics(queue_name: str, exchange_name: str) -> str:
    """Counters that tell a dropped/unroutable retry from one that is merely held."""
    queue = management_get(f"/api/queues/%2Fretailops/{queue_name}")
    exchange = management_get(f"/api/exchanges/%2Fretailops/{exchange_name}")
    assert isinstance(queue, dict)
    assert isinstance(exchange, dict)
    return json.dumps(
        {
            "queue": queue_state(queue_name),
            "queue_message_stats": queue.get("message_stats"),
            "exchange_message_stats": exchange.get("message_stats"),
        },
        sort_keys=True,
    )


def worker_reported_retry(log: str, task_id: str, delay_seconds: int) -> bool:
    """Match Celery's retry log line by task id, not by its exact layout."""
    return any(
        task_id in line and "retry" in line.casefold() and f"{delay_seconds}s" in line
        for line in log.splitlines()
    )


@contextmanager
def receive_message(
    connection_url: str,
    queue: Queue,
    timeout: float = 10.0,
    predicate: Callable[[Message], bool] | None = None,
) -> Iterator[Message]:
    deadline = time.monotonic() + timeout
    with Connection(connection_url) as connection:
        bound_queue = queue(connection.default_channel)
        held: list[Message] = []
        try:
            while time.monotonic() < deadline:
                message = bound_queue.get(no_ack=False)
                if message is not None:
                    if predicate is None or predicate(message):
                        for other in held:
                            with suppress(ChannelError, OperationalError):
                                other.reject(requeue=True)
                        held.clear()
                        try:
                            yield message
                        finally:
                            if not message.acknowledged:
                                with suppress(ChannelError, OperationalError):
                                    message.reject(requeue=True)
                        return
                    held.append(message)
                    continue
                time.sleep(0.1)
            pytest.fail(f"No message arrived in {queue.name} within {timeout} seconds")
        finally:
            for other in held:
                with suppress(ChannelError, OperationalError):
                    other.reject(requeue=True)


def message_body_text(message: Message) -> str:
    body = message.body
    if isinstance(body, bytes):
        return body.decode("utf-8")
    if isinstance(body, str):
        return body
    pytest.fail(f"Unexpected broker message body type: {type(body).__name__}")


def test_effective_quorum_dead_letter_policy() -> None:
    queue = management_get("/api/queues/%2Fretailops/retailops.email.v1")
    assert isinstance(queue, dict)
    assert queue["type"] == "quorum"
    assert queue["effective_policy_definition"] == {
        "dead-letter-exchange": "retailops.email.parking",
        "dead-letter-routing-key": "email.parked.v1",
        "dead-letter-strategy": "at-least-once",
        "overflow": "reject-publish",
        "delivery-limit": 5,
        "max-length-bytes": 67_108_864,
    }
    policy = management_get(
        "/api/policies/%2Fretailops/retailops-email-live-reliability"
    )
    assert isinstance(policy, dict)
    assert policy["apply-to"] == "quorum_queues"
    assert policy["pattern"] == r"^retailops\.email\.v1$"
    assert policy["priority"] == 100

    live_bindings = management_get(
        "/api/bindings/%2Fretailops/e/retailops.email/q/retailops.email.v1"
    )
    parking_bindings = management_get(
        "/api/bindings/%2Fretailops/e/retailops.email.parking/q/"
        "retailops.email.parked.v1"
    )
    assert isinstance(live_bindings, list)
    assert isinstance(parking_bindings, list)
    assert any(item["routing_key"] == "email.deliver.v1" for item in live_bindings)
    assert any(item["routing_key"] == "email.parked.v1" for item in parking_bindings)


def test_mandatory_publish_rejects_unroutable_message() -> None:
    publisher_url = required_environment("RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL")
    with (
        pytest.raises((ChannelError, MessageNacked, OperationalError)),
        Connection(publisher_url, transport_options={"confirm_publish": True}) as conn,
    ):
        Producer(conn).publish(
            {"event_id": str(uuid4()), "schema_version": 1},
            exchange=LIVE_EXCHANGE,
            routing_key="email.missing.v1",
            serializer="json",
            delivery_mode=2,
            mandatory=True,
            retry=False,
        )


def test_real_celery_protocol_retry_acl_and_secret_free_body() -> None:
    publisher_url = required_environment("RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL")
    worker_url = required_environment("RETAILOPS_TEST_RABBITMQ_WORKER_URL")
    event_id = str(uuid4())
    app = Celery("t04a90f-test", broker=publisher_url)
    app.conf.broker_transport_options = {"confirm_publish": True}
    app.conf.task_queues = (LIVE_QUEUE,)
    app.send_task(
        "retailops.email.deliver_v1",
        kwargs={"envelope": {"event_id": event_id, "schema_version": 1}},
        task_id=event_id,
        queue=LIVE_QUEUE.name,
        exchange="retailops.email",
        routing_key="email.deliver.v1",
        serializer="json",
        delivery_mode=2,
        mandatory=True,
        declare=(),
        retry=False,
    )

    with receive_message(worker_url, LIVE_QUEUE) as message:
        body = message_body_text(message)
        assert message.headers["task"] == "retailops.email.deliver_v1"
        assert message.headers["id"] == event_id
        assert event_id in body
        for forbidden in ("password", "credential", "token", "email_body"):
            assert forbidden not in body.casefold()
        message.ack()

    # Verify exact least-privilege ACL definitions stored in RabbitMQ.
    publisher_user = required_environment("RABBITMQ_PUBLISHER_USER")
    worker_user = required_environment("RABBITMQ_WORKER_USER")
    publisher_perm = management_get(f"/api/permissions/%2Fretailops/{publisher_user}")
    worker_perm = management_get(f"/api/permissions/%2Fretailops/{worker_user}")
    assert isinstance(publisher_perm, dict)
    assert isinstance(worker_perm, dict)
    assert publisher_perm["configure"] == "^$"
    assert publisher_perm["write"] == r"^retailops\.email$"
    assert publisher_perm["read"] == "^$"
    assert worker_perm["configure"] == "^$"
    assert worker_perm["write"] == r"^retailops\.email$"
    assert worker_perm["read"] == r"^retailops\.email\.v1$"

    # The worker identity must be able to republish a delayed Celery retry
    # without declaring or binding topology.
    with Connection(worker_url, transport_options={"confirm_publish": True}) as conn:
        Producer(conn).publish(
            {"retry_probe": event_id},
            exchange=LIVE_EXCHANGE,
            routing_key="email.deliver.v1",
            serializer="json",
            delivery_mode=2,
            retry=False,
        )
    with receive_message(worker_url, LIVE_QUEUE) as retry_probe:
        retry_probe.ack()

    # The worker cannot declare exchanges/queues or bind queues.
    with (
        pytest.raises((ChannelError, OperationalError)),
        Connection(worker_url) as conn,
    ):
        conn.default_channel.exchange_declare(
            exchange="retailops.email", type="direct", durable=True
        )
    with (
        pytest.raises((ChannelError, OperationalError)),
        Connection(worker_url) as conn,
    ):
        conn.default_channel.queue_bind(
            queue="retailops.email.v1",
            exchange="retailops.email",
            routing_key="email.deliver.v1",
        )

    # The worker cannot read from parking.
    with (
        pytest.raises((ChannelError, OperationalError)),
        Connection(worker_url) as conn,
    ):
        PARKING_QUEUE(conn.default_channel).get(no_ack=False)

    # The worker cannot bypass the broker and write directly to parking.
    with (
        pytest.raises((ChannelError, OperationalError)),
        Connection(worker_url, transport_options={"confirm_publish": True}) as conn,
    ):
        Producer(conn).publish(
            {"unauthorized": event_id},
            exchange=PARKING_EXCHANGE,
            routing_key="email.parked.v1",
            serializer="json",
            delivery_mode=2,
            retry=False,
        )


def test_reject_without_requeue_dead_letters_to_parking() -> None:
    publisher_url = required_environment("RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL")
    worker_url = required_environment("RETAILOPS_TEST_RABBITMQ_WORKER_URL")
    bootstrap_url = required_environment("RETAILOPS_TEST_RABBITMQ_BOOTSTRAP_URL")
    correlation_id = str(uuid4())
    with Connection(publisher_url, transport_options={"confirm_publish": True}) as conn:
        Producer(conn).publish(
            {"event_id": correlation_id, "schema_version": 1},
            exchange=LIVE_EXCHANGE,
            routing_key="email.deliver.v1",
            serializer="json",
            delivery_mode=2,
            retry=False,
        )
    with receive_message(worker_url, LIVE_QUEUE) as live_message:
        live_message.reject(requeue=False)
    with receive_message(
        bootstrap_url,
        PARKING_QUEUE,
        predicate=lambda msg: correlation_id in message_body_text(msg),
    ) as parked_message:
        assert correlation_id in message_body_text(parked_message)
        parked_message.ack()


def test_real_worker_transient_smtp_publishes_routed_retry(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    cleanup_worker_events(migrated_integration_engine)
    event_id = create_event(migrated_integration_engine, delivery_attempts=0)
    canonical_id = str(UUID(bytes=event_id))
    live = "retailops.email.v1"

    def broker() -> str:
        return broker_diagnostics(live, "retailops.email")

    worker_log = ""
    try:
        with running_worker(integration_database_url, loglevel="INFO") as worker:
            published_at = datetime.now(UTC)
            publish_email_task(event_id)

            # Evidence 1 (database): the first delivery attempt was recorded durably.
            event = wait_for_event(
                migrated_integration_engine,
                event_id,
                lambda current: (
                    current.delivery_attempts == 1
                    and current.last_error_code == "SMTP_TRANSIENT"
                ),
            )
            assert event.outcome is None

            # Evidence 2 (worker): Celery logs the retry only after task.retry() has
            # called apply_async. This is NOT proof of broker acceptance; the broker
            # evidence below and the fetched message are what establish that.
            wait_until(
                lambda: worker_reported_retry(worker.read_log(), canonical_id, 30),
                timeout=20,
                failure=lambda: (
                    "Worker never reported the 30s retry for the event:\n"
                    f"{worker.read_log()}"
                ),
            )

            # Evidence 3 (broker): after the original was acked, one message
            # (the ETA retry) is outstanding. Total = ready + unacked, so it does not
            # matter whether the worker currently holds it in its ETA timer.
            wait_until(
                lambda: queue_state(live)["messages"] >= 1,
                timeout=20,
                failure=lambda: (
                    "Broker holds no retry message after the worker reported it: "
                    f"{broker()}\n{worker.read_log()}"
                ),
            )
            worker_log = worker.read_log()

        # The worker is stopped; unacked ETA messages return to ready on channel close.
        # Observe that transition explicitly instead of assuming it is instantaneous.
        wait_until(
            lambda: queue_state(live)["messages_ready"] >= 1,
            timeout=30,
            failure=lambda: (
                "Retry message was not returned to ready after worker shutdown: "
                f"{broker()}\n{worker_log}"
            ),
        )

        with receive_message(
            required_environment("RETAILOPS_TEST_RABBITMQ_WORKER_URL"),
            LIVE_QUEUE,
            timeout=20,
            predicate=lambda msg: msg.headers.get("id") == canonical_id,
        ) as retry_message:
            headers = retry_message.headers
            assert headers["task"] == "retailops.email.deliver_v1"
            assert headers["id"] == canonical_id
            assert headers["retries"] == 1
            # First retry delay is exactly the contract value 30s, measured from
            # when the worker processed the task (shortly after publish).
            eta = parse_eta(headers.get("eta"))
            assert (
                published_at + timedelta(seconds=29)
                <= eta
                <= published_at + timedelta(seconds=30 + 25)
            )
            # Frozen envelope without secrets (protocol-2 body: args, kwargs, embed).
            body = json.loads(message_body_text(retry_message))
            assert body[1] == {
                "envelope": {"event_id": canonical_id, "schema_version": 1}
            }
            retry_message.ack()
    finally:
        cleanup_worker_events(migrated_integration_engine)


def test_real_worker_fourth_transient_attempt_is_terminal(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    cleanup_worker_events(migrated_integration_engine)
    event_id = create_event(migrated_integration_engine, delivery_attempts=3)
    try:
        with running_worker(integration_database_url):
            publish_email_task(event_id)
            event = wait_for_event(
                migrated_integration_engine,
                event_id,
                lambda current: current.outcome == "FAILED",
            )
            assert event.delivery_attempts == 4
            assert event.last_error_code == "SMTP_RETRIES_EXHAUSTED"

        queue = management_get("/api/queues/%2Fretailops/retailops.email.v1")
        assert isinstance(queue, dict)
        assert queue["messages"] == 0
    finally:
        cleanup_worker_events(migrated_integration_engine)


def test_real_worker_invalid_envelope_is_parked(
    integration_database_url: URL,
) -> None:
    task_id = str(uuid4())
    with running_worker(integration_database_url):
        publish_envelope(
            {"event_id": "not-a-canonical-uuid", "schema_version": 1}, task_id
        )
        with receive_message(
            required_environment("RETAILOPS_TEST_RABBITMQ_BOOTSTRAP_URL"),
            PARKING_QUEUE,
            predicate=lambda msg: msg.headers.get("id") == task_id,
        ) as parked_message:
            assert parked_message.headers["task"] == "retailops.email.deliver_v1"
            assert parked_message.headers["id"] == task_id
            assert "not-a-canonical-uuid" in message_body_text(parked_message)
            parked_message.ack()


def mailpit_message_count_for_recipient(recipient: str) -> int:
    http_port = int(required_environment("MAILPIT_HTTP_HOST_PORT"))
    with urllib.request.urlopen(
        f"http://127.0.0.1:{http_port}/api/v1/messages", timeout=10
    ) as response:
        data = json.loads(response.read())
    messages = data.get("messages", [])
    return sum(
        1
        for msg in messages
        if any(
            isinstance(to, dict) and to.get("Address") == recipient
            for to in msg.get("To", [])
        )
    )


def test_t04aa00_duplicate_delivery_is_idempotent(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    cleanup_worker_events(migrated_integration_engine)
    event_id = create_event(migrated_integration_engine, delivery_attempts=0)
    with Session(migrated_integration_engine) as session:
        user_id = session.scalar(
            select(OutboxEvent.subject_user_id).where(OutboxEvent.id == event_id)
        )
        recipient = session.scalar(
            select(User.email_normalized).where(User.id == user_id)
        )
        assert recipient is not None
    smtp_port = int(required_environment("MAILPIT_SMTP_HOST_PORT"))
    try:
        with running_worker(
            integration_database_url, smtp_host="127.0.0.1", smtp_port=smtp_port
        ):
            publish_email_task(event_id)
            publish_email_task(event_id)
            event = wait_for_event(
                migrated_integration_engine,
                event_id,
                lambda current: current.outcome == "SENT",
            )
            assert event.delivery_attempts == 1
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                queue = management_get("/api/queues/%2Fretailops/retailops.email.v1")
                if isinstance(queue, dict) and queue.get("messages") == 0:
                    break
                time.sleep(0.2)
            with Session(migrated_integration_engine) as session:
                refreshed = session.get(OutboxEvent, event_id)
                assert refreshed is not None
                assert refreshed.delivery_attempts == 1
                assert refreshed.outcome == "SENT"
            assert mailpit_message_count_for_recipient(recipient) == 1
    finally:
        from kombu import pools

        pools.reset()
        cleanup_worker_events(migrated_integration_engine)


def create_t04aa00_event(
    engine: Engine,
    *,
    created_at: datetime,
    available_at: datetime,
    published_at: datetime | None,
    delivery_attempts: int,
    publish_attempts: int = 0,
) -> bytes:
    event_id = uuid4().bytes
    with Session(engine) as session:
        user = User(
            email_normalized=f"{EMAIL_PREFIX}{uuid4().hex}@example.com",
            password_hash="test-hash",
            role="STAFF",
            status="ACTIVE",
            admin_slot=None,
            last_reapplied_at=None,
            created_at=created_at,
            updated_at=created_at,
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
                created_at=created_at,
                available_at=available_at,
                published_at=published_at,
                publish_attempts=publish_attempts,
                delivery_attempts=delivery_attempts,
                outcome=None,
                finished_at=None,
                last_error_code=None,
            )
        )
        session.commit()
    return event_id


def test_t04aa00_broker_outage_and_controlled_replay_recovery(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    from pydantic import SecretStr
    from sqlalchemy.orm import sessionmaker

    from app.core.config import Settings
    from app.modules.outbox.broker import CeleryEventPublisher
    from app.modules.outbox.publisher import OutboxPublisher
    from app.modules.outbox.reconciler import (
        AmqpQuiesceVerifier,
        OutboxOperatorRecovery,
        OutboxStuckDetector,
    )

    cleanup_worker_events(migrated_integration_engine)
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    past_time = now_utc - timedelta(minutes=20)
    event_id = create_t04aa00_event(
        migrated_integration_engine,
        created_at=past_time,
        available_at=past_time,
        published_at=None,
        delivery_attempts=1,
        publish_attempts=0,
    )
    session_factory = sessionmaker(
        bind=migrated_integration_engine, autoflush=False, expire_on_commit=False
    )
    publisher_url = required_environment("RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL")
    smtp_port = int(required_environment("MAILPIT_SMTP_HOST_PORT"))

    def build_isolated_settings(amqp_url: str) -> Settings:
        return Settings(
            db_host=integration_database_url.host or "127.0.0.1",
            db_name=integration_database_url.database or "retailops_test",
            db_user=integration_database_url.username or "unused",
            db_password=SecretStr(integration_database_url.password or "unused"),
            rabbitmq_url=SecretStr(amqp_url),
        )

    def build_isolated_celery(amqp_url: str) -> Celery:
        app = Celery("t04aa00-publisher-test", broker=amqp_url)
        app.conf.broker_transport_options = {"confirm_publish": True}
        app.conf.task_queues = (LIVE_QUEUE,)
        return app

    try:
        # 1. Real unreachable AMQP endpoint keeps Outbox intent unpublished
        unreachable_url = "amqp://unused:unused@127.0.0.1:1/%2Fretailops"
        unreachable_publisher = OutboxPublisher(
            CeleryEventPublisher(
                build_isolated_celery(unreachable_url),
                build_isolated_settings(unreachable_url),
            )
        )
        offline_result = unreachable_publisher.publish_due(
            session_factory, batch_size=10
        )
        assert offline_result.failed == 1
        with Session(migrated_integration_engine) as session:
            ev = session.get(OutboxEvent, event_id)
            assert ev is not None
            assert ev.published_at is None
            assert ev.last_error_code == "BROKER_PUBLISH_FAILED"

        # 2. Simulate stuck/parked state after publish in the past
        with Session(migrated_integration_engine) as session:
            ev = session.get(OutboxEvent, event_id)
            assert ev is not None
            ev.published_at = past_time
            ev.last_error_code = "SMTP_TRANSIENT"
            session.commit()

        detector = OutboxStuckDetector()
        candidates = detector.detect(
            session_factory, batch_size=10, stuck_after_seconds=900
        )
        assert [c.event_id for c in candidates] == [event_id]

        bootstrap_url = required_environment("RETAILOPS_TEST_RABBITMQ_BOOTSTRAP_URL")
        verifier = AmqpQuiesceVerifier(
            amqp_url=bootstrap_url,
            queue_name="retailops.email.v1",
            management_url=required_environment(
                "RETAILOPS_TEST_RABBITMQ_MANAGEMENT_URL"
            ),
            admin_user=required_environment("RABBITMQ_BOOTSTRAP_USER"),
            admin_password=required_environment("RABBITMQ_BOOTSTRAP_PASSWORD"),
            vhost="/retailops",
            quiesced_users=(
                required_environment("RABBITMQ_PUBLISHER_USER"),
                required_environment("RABBITMQ_WORKER_USER"),
            ),
        )
        recovery = OutboxOperatorRecovery(verifier)

        # 3. Fail-closed while worker consumer is active
        with running_worker(
            integration_database_url, smtp_host="127.0.0.1", smtp_port=smtp_port
        ):
            blocked = recovery.replay(
                session_factory,
                event_id=event_id,
                reason="t04aa00-active-worker-check",
                execute=True,
            )
            assert blocked.status == "REPLAY_NOT_VERIFIABLE"

        # 4. After worker and test publisher pool stop, replay succeeds
        from kombu import pools

        pools.reset()
        quiesce_deadline = time.monotonic() + 10
        while time.monotonic() < quiesce_deadline:
            ok, _ = verifier.verify_quiesced()
            if ok:
                break
            time.sleep(0.25)

        replayed = recovery.replay(
            session_factory,
            event_id=event_id,
            reason="t04aa00-quiesced-replay",
            execute=True,
        )
        assert replayed.status == "REPLAY_QUEUED"
        assert replayed.delivery_attempts == 1

        # 5. Resume publisher + worker and verify terminal SENT
        publisher = OutboxPublisher(
            CeleryEventPublisher(
                build_isolated_celery(publisher_url),
                build_isolated_settings(publisher_url),
            )
        )
        pub_result = publisher.publish_due(session_factory, batch_size=10)
        assert pub_result.published >= 1

        with running_worker(
            integration_database_url, smtp_host="127.0.0.1", smtp_port=smtp_port
        ):
            delivered = wait_for_event(
                migrated_integration_engine,
                event_id,
                lambda current: current.outcome == "SENT",
            )
            assert delivered.delivery_attempts == 2
    finally:
        from kombu import pools

        pools.reset()
        cleanup_worker_events(migrated_integration_engine)


def _cleanup_password_reset_run(
    engine: Engine,
    *,
    user_id: int | None,
    session_ids: tuple[bytes, ...] = (),
    token_ids: tuple[int, ...] = (),
    event_ids: tuple[bytes, ...] = (),
) -> None:
    """Delete only exact records owned by a run; fail closed on foreign refs."""
    if user_id is None:
        return
    from app.modules.auth.models import AuthSession, PasswordResetToken

    tracked_sessions = set(session_ids)
    tracked_tokens = set(token_ids)
    tracked_events = set(event_ids)

    with Session(engine) as session, session.begin():
        found_tokens = set(
            session.scalars(
                select(PasswordResetToken.id).where(
                    PasswordResetToken.user_id == user_id
                )
            )
        )
        found_sessions = set(
            session.scalars(
                select(AuthSession.id).where(AuthSession.user_id == user_id)
            )
        )
        found_events = set(
            session.scalars(
                select(OutboxEvent.id).where(OutboxEvent.subject_user_id == user_id)
            )
        )

        foreign_tokens = found_tokens - tracked_tokens
        foreign_sessions = found_sessions - tracked_sessions
        foreign_events = found_events - tracked_events
        if foreign_tokens or foreign_sessions or foreign_events:
            raise AssertionError(
                "Refusing run cleanup due to unexpected external references "
                f"(tokens={len(foreign_tokens)}, sessions={len(foreign_sessions)}, "
                f"events={len(foreign_events)})"
            )

        if tracked_tokens:
            session.execute(
                delete(PasswordResetToken).where(
                    PasswordResetToken.id.in_(tracked_tokens)
                )
            )
        if tracked_sessions:
            session.execute(
                delete(AuthSession).where(AuthSession.id.in_(tracked_sessions))
            )
        if tracked_events:
            session.execute(
                delete(OutboxEvent).where(OutboxEvent.id.in_(tracked_events))
            )
        session.execute(delete(User).where(User.id == user_id))


def test_password_reset_e2e_api_outbox_rabbitmq_worker_mailpit_and_reset(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from sqlalchemy.orm import sessionmaker

    from app.core.config import Settings, get_settings
    from app.db.session import get_db_session
    from app.infrastructure.dependencies import (
        enforce_forgot_password_rate_limit,
        enforce_reset_password_rate_limit,
    )
    from app.main import create_app
    from app.modules.auth.models import AuthSession, PasswordResetToken
    from app.modules.auth.security import PasswordHasher
    from app.modules.outbox.broker import CeleryEventPublisher
    from app.modules.outbox.publisher import OutboxPublisher

    def build_isolated_settings(amqp_url: str) -> Settings:
        return Settings(
            _env_file=None,
            db_host=integration_database_url.host or "127.0.0.1",
            db_name=integration_database_url.database or "retailops_test",
            db_user=integration_database_url.username or "unused",
            db_password=SecretStr(integration_database_url.password or "unused"),
            rabbitmq_url=SecretStr(amqp_url),
        )

    def build_isolated_celery(amqp_url: str) -> Celery:
        isolated = Celery("t04aa1c-e2e-publisher-test", broker=amqp_url)
        isolated.conf.broker_transport_options = {"confirm_publish": True}
        isolated.conf.task_queues = (LIVE_QUEUE,)
        return isolated

    smtp_port = int(required_environment("MAILPIT_SMTP_HOST_PORT"))
    mailpit_http_port = int(required_environment("MAILPIT_HTTP_HOST_PORT"))
    publisher_url = required_environment("RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL")
    secret_key = "e2e-outbox-secret-key-" + ("k" * 16)
    staff_email = f"{EMAIL_PREFIX}reset-e2e-{uuid4().hex}@example.com"
    old_password = "OldPassword!123"
    new_password = "NewPassword!456"
    hasher = PasswordHasher(work_factor=4)
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    existing_session_id = uuid4().bytes

    staff_id: int | None = None
    tracked_session_ids: list[bytes] = []
    tracked_token_ids: list[int] = []
    tracked_event_ids: list[bytes] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            staff = User(
                email_normalized=staff_email,
                password_hash=hasher.hash(old_password),
                role="STAFF",
                status="ACTIVE",
                admin_slot=None,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(staff)
            session.flush()
            staff_id = staff.id
            session.add(
                AuthSession(
                    id=existing_session_id,
                    user_id=staff_id,
                    created_at=now,
                    expires_at=now + timedelta(hours=8),
                    revoked_at=None,
                )
            )
            tracked_session_ids.append(existing_session_id)

        session_factory = sessionmaker(
            bind=migrated_integration_engine, expire_on_commit=False
        )
        api_settings = Settings(
            _env_file=None,
            environment="development",
            db_host=integration_database_url.host or "127.0.0.1",
            db_port=integration_database_url.port or 3306,
            db_name=integration_database_url.database or "retailops_test",
            db_user=integration_database_url.username or "retailops_test_runner",
            db_password=SecretStr(integration_database_url.password or ""),
            jwt_secret=SecretStr("j" * 32),
            csrf_secret=SecretStr("c" * 32),
            outbox_secret_key=SecretStr(secret_key),
            password_reset_base_url="https://app.retailops.example/reset-password",
            password_reset_email_adapter="outbox",
        )
        app = create_app(api_settings)

        def _override_db():
            with session_factory() as session:
                yield session

        app.dependency_overrides[get_settings] = lambda: api_settings
        app.dependency_overrides[get_db_session] = _override_db
        app.dependency_overrides[enforce_forgot_password_rate_limit] = lambda: None
        app.dependency_overrides[enforce_reset_password_rate_limit] = lambda: None

        with TestClient(app) as client:
            forgot_resp = client.post(
                "/api/v1/auth/forgot-password", json={"email": staff_email}
            )
            assert forgot_resp.status_code == 202

        with Session(migrated_integration_engine) as session:
            tok = session.scalar(
                select(PasswordResetToken).where(PasswordResetToken.user_id == staff_id)
            )
            ev = session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.subject_user_id == staff_id,
                    OutboxEvent.event_type == "PASSWORD_RESET",
                )
            )
            assert tok is not None
            assert ev is not None
            tracked_token_ids.append(tok.id)
            tracked_event_ids.append(ev.id)
            assert ev.secret_ciphertext is not None
            event_id = ev.id

        publisher = OutboxPublisher(
            CeleryEventPublisher(
                build_isolated_celery(publisher_url),
                build_isolated_settings(publisher_url),
            )
        )
        pub_result = publisher.publish_due(session_factory, batch_size=10)
        assert pub_result.published >= 1

        worker_log = ""
        with running_worker(
            integration_database_url,
            loglevel="INFO",
            smtp_host="127.0.0.1",
            smtp_port=smtp_port,
            extra_env={"RETAILOPS_OUTBOX_SECRET_KEY": secret_key},
        ) as worker:
            delivered = wait_for_event(
                migrated_integration_engine,
                event_id,
                lambda current: current.outcome == "SENT",
            )
            assert delivered.secret_ciphertext is None
            worker_log = worker.read_log()

        with urllib.request.urlopen(
            f"http://127.0.0.1:{mailpit_http_port}/api/v1/messages", timeout=10
        ) as resp:
            messages_data = json.loads(resp.read())
        matched = [
            m
            for m in messages_data.get("messages", [])
            if any(
                isinstance(to, dict) and to.get("Address") == staff_email
                for to in m.get("To", [])
            )
        ]
        assert len(matched) == 1
        msg_id = matched[0]["ID"]
        with urllib.request.urlopen(
            f"http://127.0.0.1:{mailpit_http_port}/api/v1/message/{msg_id}", timeout=10
        ) as resp:
            full_msg = json.loads(resp.read())
        email_text = full_msg.get("Text", "") or full_msg.get("HTML", "")
        token_match = re.search(
            r"https://app\.retailops\.example/reset-password\?token=([A-Za-z0-9_-]+)",
            email_text,
        )
        assert token_match is not None, (
            "Password reset link not found in captured email"
        )
        raw_token = token_match.group(1)
        assert raw_token not in worker_log

        with TestClient(app) as client:
            reset_resp = client.post(
                "/api/v1/auth/reset-password",
                json={"token": raw_token, "new_password": new_password},
            )
            assert reset_resp.status_code == 200

            replay_resp = client.post(
                "/api/v1/auth/reset-password",
                json={"token": raw_token, "new_password": "AnotherPassword!789"},
            )
            assert replay_resp.status_code == 401

        with Session(migrated_integration_engine) as session:
            refreshed_user = session.get(User, staff_id)
            refreshed_session = session.get(AuthSession, existing_session_id)
            assert refreshed_user is not None
            assert hasher.verify(new_password, refreshed_user.password_hash)
            assert refreshed_session is not None
            assert refreshed_session.revoked_at is not None
    finally:
        from kombu import pools

        pools.reset()
        _cleanup_password_reset_run(
            migrated_integration_engine,
            user_id=staff_id,
            session_ids=tuple(tracked_session_ids),
            token_ids=tuple(tracked_token_ids),
            event_ids=tuple(tracked_event_ids),
        )


def test_password_reset_run_scoped_cleanup_isolation_and_fail_closed(
    migrated_integration_engine: Engine,
) -> None:
    from app.modules.auth.models import AuthSession, PasswordResetToken
    from app.modules.auth.security import PasswordHasher

    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    pw_hash = PasswordHasher(work_factor=4).hash("CleanupPass!123")
    email_a = f"{EMAIL_PREFIX}run-a-{uuid4().hex}@example.com"
    email_b = f"{EMAIL_PREFIX}run-b-{uuid4().hex}@example.com"
    sess_a = uuid4().bytes
    sess_b = uuid4().bytes
    ev_a = uuid4().bytes
    ev_b = uuid4().bytes
    user_a_id: int | None = None
    user_b_id: int | None = None
    tok_a_id: int | None = None
    tok_b_id: int | None = None

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            user_a = User(
                email_normalized=email_a,
                password_hash=pw_hash,
                role="STAFF",
                status="ACTIVE",
                admin_slot=None,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
            user_b = User(
                email_normalized=email_b,
                password_hash=pw_hash,
                role="STAFF",
                status="ACTIVE",
                admin_slot=None,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add_all([user_a, user_b])
            session.flush()
            user_a_id, user_b_id = user_a.id, user_b.id

            tok_a = PasswordResetToken(
                user_id=user_a_id,
                token_hash=uuid4().hex + uuid4().hex,
                expires_at=now + timedelta(minutes=15),
                used_at=None,
                created_at=now,
            )
            tok_b = PasswordResetToken(
                user_id=user_b_id,
                token_hash=uuid4().hex + uuid4().hex,
                expires_at=now + timedelta(minutes=15),
                used_at=None,
                created_at=now,
            )
            session.add_all(
                [
                    tok_a,
                    tok_b,
                    AuthSession(
                        id=sess_a,
                        user_id=user_a_id,
                        created_at=now,
                        expires_at=now + timedelta(hours=8),
                        revoked_at=None,
                    ),
                    AuthSession(
                        id=sess_b,
                        user_id=user_b_id,
                        created_at=now,
                        expires_at=now + timedelta(hours=8),
                        revoked_at=None,
                    ),
                    OutboxEvent(
                        id=ev_a,
                        subject_user_id=user_a_id,
                        event_type="PASSWORD_RESET",
                        payload={"schema_version": 1},
                        secret_expires_at=now + timedelta(minutes=15),
                        secret_ciphertext=b"cipher-a",
                        created_at=now,
                        available_at=now,
                        published_at=None,
                        publish_attempts=0,
                        delivery_attempts=0,
                        outcome=None,
                        finished_at=None,
                        last_error_code=None,
                    ),
                    OutboxEvent(
                        id=ev_b,
                        subject_user_id=user_b_id,
                        event_type="PASSWORD_RESET",
                        payload={"schema_version": 1},
                        secret_expires_at=now + timedelta(minutes=15),
                        secret_ciphertext=b"cipher-b",
                        created_at=now,
                        available_at=now,
                        published_at=None,
                        publish_attempts=0,
                        delivery_attempts=0,
                        outcome=None,
                        finished_at=None,
                        last_error_code=None,
                    ),
                ]
            )
            session.flush()
            tok_a_id, tok_b_id = tok_a.id, tok_b.id

        # 1. Partial/uncreated setup (user_id=None) -> safe no-op
        _cleanup_password_reset_run(migrated_integration_engine, user_id=None)

        # 2. Fail-closed on unexpected external ref -> raises & rolls back cleanly
        with pytest.raises(AssertionError, match="unexpected external references"):
            _cleanup_password_reset_run(
                migrated_integration_engine,
                user_id=user_a_id,
                session_ids=(sess_a,),
                token_ids=(),  # omit tok_a_id to simulate unexpected external token
                event_ids=(ev_a,),
            )
        with Session(migrated_integration_engine) as session:
            assert session.get(User, user_a_id) is not None
            assert session.get(AuthSession, sess_a) is not None
            assert session.get(OutboxEvent, ev_a) is not None
            assert session.get(PasswordResetToken, tok_a_id) is not None

        # 3. Clean up Run A -> deletes Run A only, preserves Run B completely
        _cleanup_password_reset_run(
            migrated_integration_engine,
            user_id=user_a_id,
            session_ids=(sess_a,),
            token_ids=(tok_a_id,),
            event_ids=(ev_a,),
        )
        user_a_id = None
        with Session(migrated_integration_engine) as session:
            assert session.get(User, user_b_id) is not None
            assert session.get(AuthSession, sess_b) is not None
            assert session.get(OutboxEvent, ev_b) is not None
            assert session.get(PasswordResetToken, tok_b_id) is not None
    finally:
        if user_a_id is not None and tok_a_id is not None:
            _cleanup_password_reset_run(
                migrated_integration_engine,
                user_id=user_a_id,
                session_ids=(sess_a,),
                token_ids=(tok_a_id,),
                event_ids=(ev_a,),
            )
        if user_b_id is not None and tok_b_id is not None:
            _cleanup_password_reset_run(
                migrated_integration_engine,
                user_id=user_b_id,
                session_ids=(sess_b,),
                token_ids=(tok_b_id,),
                event_ids=(ev_b,),
            )
