"""Long-running singleton polling entry point for the Outbox publisher."""

import logging
import time

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.modules.outbox.broker import CeleryEventPublisher
from app.modules.outbox.publisher import OutboxPublisher
from app.worker.celery_app import celery_app

LOGGER = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    publisher = OutboxPublisher(CeleryEventPublisher(celery_app, settings))
    session_factory = get_session_factory()
    while True:
        result = publisher.publish_due(
            session_factory,
            batch_size=settings.outbox_batch_size,
        )
        if result.failed:
            LOGGER.warning(
                "Outbox publish batch had failures",
                extra={
                    "scanned": result.scanned,
                    "published": result.published,
                    "failed": result.failed,
                },
            )
        time.sleep(settings.outbox_poll_seconds)


if __name__ == "__main__":
    main()
