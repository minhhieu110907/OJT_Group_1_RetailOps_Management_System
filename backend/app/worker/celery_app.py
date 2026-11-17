"""Celery application restricted to the RetailOps email queue."""

from celery import Celery, signals
from kombu import Exchange, Queue

from app.core.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    exchange = Exchange(
        settings.outbox_exchange, type="direct", durable=True, no_declare=True
    )
    queue = Queue(
        settings.outbox_queue,
        exchange=exchange,
        routing_key=settings.outbox_routing_key,
        durable=True,
        queue_arguments={"x-queue-type": "quorum"},
        no_declare=True,
    )
    app = Celery("retailops-email", broker=settings.require_rabbitmq_url())
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_backend=None,
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_concurrency=1,
        worker_enable_remote_control=False,
        task_create_missing_queues=False,
        task_publish_retry=False,
        broker_transport_options={"confirm_publish": True},
        task_default_queue=settings.outbox_queue,
        task_default_exchange=settings.outbox_exchange,
        task_default_exchange_type="direct",
        task_default_routing_key=settings.outbox_routing_key,
        task_queues=(queue,),
        task_routes={
            settings.outbox_task_name: {
                "queue": settings.outbox_queue,
                "exchange": settings.outbox_exchange,
                "routing_key": settings.outbox_routing_key,
            }
        },
        imports=("app.worker.tasks",),
    )
    return app


celery_app = create_celery_app()


@signals.worker_init.connect
def validate_worker_startup(**_kwargs: object) -> None:
    """Reject unsafe SMTP configuration before the worker starts consuming."""
    get_settings().validate_email_worker_configuration()
