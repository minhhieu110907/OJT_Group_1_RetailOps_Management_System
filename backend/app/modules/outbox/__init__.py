"""Durable transactional outbox for business events."""

from app.modules.outbox.contracts import EmailOutcome, PublishBatchResult
from app.modules.outbox.handler import EmailEventHandler
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.publisher import OutboxPublisher
from app.modules.outbox.writer import OutboxWriter

__all__ = [
    "EmailEventHandler",
    "EmailOutcome",
    "OutboxEvent",
    "OutboxPublisher",
    "OutboxWriter",
    "PublishBatchResult",
]
