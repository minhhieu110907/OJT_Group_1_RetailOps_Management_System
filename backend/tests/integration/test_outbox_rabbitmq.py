"""Real RabbitMQ acceptance checks for the frozen T04A90F topology."""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import datetime
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


def worker_environment(database_url: URL) -> dict[str, str]:
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
            "RETAILOPS_SMTP_HOST": "127.0.0.1",
            "RETAILOPS_SMTP_PORT": "1",
            "RETAILOPS_SMTP_FROM_ADDRESS": "no-reply@retailops.local",
            "RETAILOPS_SMTP_STARTTLS": "false",
        }
    )
    return environment


@contextmanager
def running_worker(database_url: URL) -> Iterator[subprocess.Popen[bytes]]:
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
            "--loglevel=WARNING",
            "--queues=retailops.email.v1",
        ],
        env=worker_environment(database_url),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"Celery worker exited with code {process.returncode}")
            queue = management_get("/api/queues/%2Fretailops/retailops.email.v1")
            if isinstance(queue, dict) and queue.get("consumers", 0) >= 1:
                yield process
                return
            time.sleep(0.25)
        pytest.fail("Celery worker did not start consuming within 30 seconds")
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
    app.send_task(
        "retailops.email.deliver_v1",
        kwargs={"envelope": envelope},
        task_id=task_id,
        exchange="retailops.email",
        routing_key="email.deliver.v1",
        serializer="json",
        delivery_mode=2,
        mandatory=True,
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


@contextmanager
def receive_message(
    connection_url: str, queue: Queue, timeout: float = 10.0
) -> Iterator[Message]:
    deadline = time.monotonic() + timeout
    with Connection(connection_url) as connection:
        bound_queue = queue(connection.default_channel)
        while time.monotonic() < deadline:
            message = bound_queue.get(no_ack=False)
            if message is not None:
                try:
                    yield message
                finally:
                    if not message.acknowledged:
                        with suppress(ChannelError, OperationalError):
                            message.reject(requeue=True)
                return
            time.sleep(0.1)
        pytest.fail(f"No message arrived in {queue.name} within {timeout} seconds")


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
    app.send_task(
        "retailops.email.deliver_v1",
        kwargs={"envelope": {"event_id": event_id, "schema_version": 1}},
        task_id=event_id,
        exchange="retailops.email",
        routing_key="email.deliver.v1",
        serializer="json",
        delivery_mode=2,
        retry=False,
    )

    with receive_message(worker_url, LIVE_QUEUE) as message:
        body = message.body.decode()
        assert message.headers["task"] == "retailops.email.deliver_v1"
        assert message.headers["id"] == event_id
        assert event_id in body
        for forbidden in ("password", "credential", "token", "email_body"):
            assert forbidden not in body.casefold()
        message.ack()

    # The worker identity must be able to republish a delayed Celery retry.
    with Connection(worker_url, transport_options={"confirm_publish": True}) as conn:
        Producer(conn).publish(
            {"retry_probe": event_id},
            exchange=LIVE_EXCHANGE,
            routing_key="email.deliver.v1",
            serializer="json",
            delivery_mode=2,
            declare=[LIVE_EXCHANGE, LIVE_QUEUE],
            retry=False,
        )
    with receive_message(worker_url, LIVE_QUEUE) as retry_probe:
        retry_probe.ack()

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
    with receive_message(bootstrap_url, PARKING_QUEUE) as parked_message:
        assert correlation_id in parked_message.body.decode()
        parked_message.ack()


def test_real_worker_transient_smtp_publishes_routed_retry(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    cleanup_worker_events(migrated_integration_engine)
    event_id = create_event(migrated_integration_engine, delivery_attempts=0)
    try:
        with running_worker(integration_database_url):
            publish_email_task(event_id)
            event = wait_for_event(
                migrated_integration_engine,
                event_id,
                lambda current: (
                    current.delivery_attempts == 1
                    and current.last_error_code == "SMTP_TRANSIENT"
                ),
            )
            assert event.outcome is None

        # Terminating the worker before the 30-second ETA returns its reserved
        # retry to RabbitMQ. Inspect that real Celery retry while the channel is open.
        with receive_message(
            required_environment("RETAILOPS_TEST_RABBITMQ_WORKER_URL"), LIVE_QUEUE
        ) as retry_message:
            assert retry_message.headers["task"] == "retailops.email.deliver_v1"
            assert retry_message.headers["retries"] == 1
            assert retry_message.headers["id"] == str(UUID(bytes=event_id))
            assert str(UUID(bytes=event_id)) in retry_message.body.decode()
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
        ) as parked_message:
            assert parked_message.headers["task"] == "retailops.email.deliver_v1"
            assert parked_message.headers["id"] == task_id
            assert "not-a-canonical-uuid" in parked_message.body.decode()
            parked_message.ack()
