"""Long-running singleton polling entry point for the Outbox publisher."""

import logging
import time
from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.modules.outbox.broker import CeleryEventPublisher
from app.modules.outbox.publisher import OutboxPublisher
from app.modules.outbox.reconciler import OutboxStuckDetector
from app.worker.celery_app import celery_app

LOGGER = logging.getLogger(__name__)
MAX_DB_BACKOFF_SECONDS = 60.0


def compute_db_backoff_seconds(poll_seconds: float, consecutive_failures: int) -> float:
    """Return bounded exponential backoff (capped at 60s) for transient DB errors."""
    if consecutive_failures <= 0:
        return poll_seconds
    exponent = min(consecutive_failures - 1, 4)
    return min(poll_seconds * (2**exponent), MAX_DB_BACKOFF_SECONDS)


def run_poll_cycle(
    publisher: OutboxPublisher,
    detector: OutboxStuckDetector,
    session_factory: Callable[[], Session],
    settings: Settings,
    *,
    consecutive_db_failures: int,
    should_detect_stuck: bool,
) -> tuple[int, float]:
    """Execute one resilient poll (+ optional read-only stuck scan) iteration."""
    try:
        result = publisher.publish_due(
            session_factory,
            batch_size=settings.outbox_batch_size,
        )
    except SQLAlchemyError:
        failures = consecutive_db_failures + 1
        delay = compute_db_backoff_seconds(settings.outbox_poll_seconds, failures)
        LOGGER.warning(
            "Outbox publisher database poll failed",
            extra={
                "error_code": "OUTBOX_DATABASE_UNAVAILABLE",
                "consecutive_failures": failures,
                "backoff_seconds": delay,
            },
        )
        return failures, delay

    if result.failed:
        LOGGER.warning(
            "Outbox publish batch had failures",
            extra={
                "scanned": result.scanned,
                "published": result.published,
                "failed": result.failed,
            },
        )

    if should_detect_stuck:
        try:
            detector.detect(
                session_factory,
                batch_size=settings.outbox_batch_size,
                stuck_after_seconds=settings.outbox_stuck_after_seconds,
            )
        except SQLAlchemyError:
            LOGGER.warning(
                "Outbox stuck-event detection skipped due to database error",
                extra={"error_code": "OUTBOX_DATABASE_UNAVAILABLE"},
            )

    return 0, settings.outbox_poll_seconds


def main() -> None:
    settings = get_settings()
    publisher = OutboxPublisher(CeleryEventPublisher(celery_app, settings))
    detector = OutboxStuckDetector()
    session_factory = get_session_factory()
    consecutive_db_failures = 0
    last_detect_at = 0.0

    while True:
        now_mono = time.monotonic()
        should_detect = (
            now_mono - last_detect_at
        ) >= settings.outbox_reconcile_interval_seconds
        consecutive_db_failures, sleep_seconds = run_poll_cycle(
            publisher,
            detector,
            session_factory,
            settings,
            consecutive_db_failures=consecutive_db_failures,
            should_detect_stuck=should_detect,
        )
        if should_detect and consecutive_db_failures == 0:
            last_detect_at = now_mono
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
