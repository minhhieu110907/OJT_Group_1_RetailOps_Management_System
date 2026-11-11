"""Transactional outbox module."""

from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.writer import OutboxWriter

__all__ = ["OutboxEvent", "OutboxWriter"]
