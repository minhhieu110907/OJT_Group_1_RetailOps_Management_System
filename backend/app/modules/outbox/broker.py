"""Celery/Kombu publisher for the frozen email-task protocol."""

from typing import Protocol
from uuid import UUID

from amqp.exceptions import MessageNacked
from celery import Celery
from kombu.exceptions import ChannelError, OperationalError

from app.core.config import Settings
from app.modules.outbox.errors import BrokerPublishError
from app.modules.outbox.protocol import build_envelope


class EventPublisher(Protocol):
    def publish(self, event_id: bytes) -> None: ...


class CeleryEventPublisher:
    def __init__(self, app: Celery, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    @staticmethod
    def envelope(event_id: bytes) -> object:
        return build_envelope(event_id)

    def publish(self, event_id: bytes) -> None:
        canonical_id = str(UUID(bytes=event_id))
        try:
            self.app.send_task(
                self.settings.outbox_task_name,
                kwargs={"envelope": self.envelope(event_id)},
                task_id=canonical_id,
                queue=self.settings.outbox_queue,
                exchange=self.settings.outbox_exchange,
                routing_key=self.settings.outbox_routing_key,
                serializer="json",
                delivery_mode=2,
                mandatory=True,
                retry=False,
                ignore_result=True,
            )
        except (ChannelError, MessageNacked, OperationalError, OSError) as error:
            raise BrokerPublishError("RabbitMQ publish was not confirmed") from error
