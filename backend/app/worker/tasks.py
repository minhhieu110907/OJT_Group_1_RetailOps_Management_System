"""Celery task adapter for email Outbox events."""

from uuid import UUID

from celery import Task
from celery.exceptions import Reject

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.outbox.errors import DatabaseUnavailableError, UnknownEventError
from app.modules.outbox.handler import EmailEventHandler
from app.modules.outbox.protocol import parse_envelope
from app.modules.outbox.retry import retry_or_requeue
from app.modules.outbox.smtp import SmtpEmailTransport
from app.worker.celery_app import celery_app


def build_handler() -> EmailEventHandler:
    settings = get_settings()
    secret_key = (
        settings.outbox_secret_key.get_secret_value()
        if settings.outbox_secret_key is not None
        else None
    )
    return EmailEventHandler(
        get_session_factory(),
        SmtpEmailTransport(settings),
        secret_key=secret_key,
    )


def _retry_or_park(task: Task, error: Exception) -> None:
    settings = get_settings()
    retry_or_requeue(
        task,
        error,
        delays=settings.email_retry_delays_seconds,
    )


@celery_app.task(
    bind=True,
    name="retailops.email.deliver_v1",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def deliver_email(self: Task, *, envelope: object) -> dict[str, object]:
    try:
        event_id = parse_envelope(envelope)
    except ValueError as error:
        raise Reject("INVALID_ENVELOPE", requeue=False) from error

    try:
        outcome = build_handler().handle(event_id=event_id)
    except UnknownEventError as error:
        raise Reject(error.code, requeue=False) from error
    except DatabaseUnavailableError as error:
        _retry_or_park(self, error)
        raise AssertionError("Celery retry must raise") from error
    except Exception as error:
        raise Reject("UNEXPECTED_WORKER_FAILURE", requeue=False) from error

    if outcome.status == "RETRY":
        _retry_or_park(self, RuntimeError("EMAIL_DELIVERY_RETRY"))
    return {"event_id": str(UUID(bytes=event_id)), "status": outcome.status}
