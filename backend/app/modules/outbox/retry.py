"""Bounded Celery retry behavior for recoverable email deliveries."""

from amqp.exceptions import MessageNacked
from celery import Task
from celery.exceptions import Reject
from kombu.exceptions import ChannelError, OperationalError


def retry_or_requeue(
    task: Task,
    error: Exception,
    *,
    delays: tuple[int, int, int],
) -> None:
    retry_number = task.request.retries
    if retry_number >= len(delays):
        raise Reject("RETRY_BUDGET_EXHAUSTED_UNPERSISTED", requeue=False)
    retry_delay = delays[retry_number]
    try:
        raise task.retry(exc=error, countdown=retry_delay, max_retries=3)
    except (ChannelError, MessageNacked, OperationalError) as publish_error:
        # If the channel is alive, Celery asks RabbitMQ to requeue the original;
        # the quorum delivery-limit bounds redelivery and then dead-letters it.
        # If the connection is already gone, Reject cannot be assumed to arrive:
        # the original remains unacknowledged and RabbitMQ redelivers it when the
        # connection closes. Never hold the single worker slot as a scheduler.
        raise Reject("RETRY_PUBLISH_FAILED", requeue=True) from publish_error
