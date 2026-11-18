"""Controlled operator CLI for Outbox stuck-event inspection and single-event replay."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from urllib.parse import quote
from uuid import UUID

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.modules.outbox.reconciler import (
    AmqpQuiesceVerifier,
    OutboxOperatorRecovery,
    OutboxStuckDetector,
)


def parse_canonical_uuid(raw_id: str) -> bytes:
    """Parse a canonical lowercase UUID string into 16 bytes."""
    parsed = UUID(raw_id)
    if str(parsed) != raw_id:
        raise ValueError("Outbox event ID must use canonical lowercase UUID format")
    return parsed.bytes


def build_operator_verifier(settings: Settings) -> AmqpQuiesceVerifier:
    """Build operator quiesce verifier using bootstrap/management credentials only."""
    explicit_url = os.environ.get("RETAILOPS_OPERATOR_RABBITMQ_URL")
    username = os.environ.get("RABBITMQ_BOOTSTRAP_USER")
    password = os.environ.get("RABBITMQ_BOOTSTRAP_PASSWORD")
    management_url = os.environ.get("RETAILOPS_RABBITMQ_MANAGEMENT_URL")
    publisher_user = os.environ.get("RABBITMQ_PUBLISHER_USER")
    worker_user = os.environ.get("RABBITMQ_WORKER_USER")
    host = settings.rabbitmq_host or os.environ.get("RETAILOPS_RABBITMQ_HOST")
    if (
        not username
        or not password
        or not management_url
        or not publisher_user
        or not worker_user
        or (not explicit_url and not host)
    ):
        raise RuntimeError(
            "Operator RabbitMQ verification requires RABBITMQ_BOOTSTRAP_USER, "
            "RABBITMQ_BOOTSTRAP_PASSWORD, RETAILOPS_RABBITMQ_MANAGEMENT_URL, "
            "RABBITMQ_PUBLISHER_USER, RABBITMQ_WORKER_USER, and RabbitMQ host/URL"
        )
    vhost = quote(settings.rabbitmq_vhost, safe="")
    amqp_url = explicit_url or (
        f"amqp://{quote(username, safe='')}:{quote(password, safe='')}"
        f"@{host}:{settings.rabbitmq_port}/{vhost}"
    )
    return AmqpQuiesceVerifier(
        amqp_url=amqp_url,
        queue_name=settings.outbox_queue,
        management_url=management_url,
        admin_user=username,
        admin_password=password,
        vhost=settings.rabbitmq_vhost,
        quiesced_users=(publisher_user, worker_user),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.worker.reconcile_outbox",
        description=(
            "Inspect stuck Outbox events or perform a controlled single-event "
            "replay after quiescing publisher and worker."
        ),
    )
    parser.add_argument(
        "--detect-only",
        action="store_true",
        help="List stuck Outbox candidates without modifying any state.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum stuck candidates to inspect in --detect-only mode (1-25).",
    )
    parser.add_argument(
        "--event-id",
        type=str,
        help="Canonical lowercase UUID of a single Outbox event to check or replay.",
    )
    parser.add_argument(
        "--reason",
        type=str,
        default="",
        help="Required audit reason (1-128 chars) when using --execute.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform the replay mutation. Omit for default read-only dry-run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.detect_only:
        if args.execute or args.event_id:
            parser.error(
                "--detect-only cannot be combined with --execute or --event-id"
            )
        settings = get_settings()
        session_factory = get_session_factory()
        detector = OutboxStuckDetector()
        candidates = detector.detect(
            session_factory,
            batch_size=args.limit,
            stuck_after_seconds=settings.outbox_stuck_after_seconds,
        )
        print(
            json.dumps(
                {
                    "mode": "DETECT_ONLY",
                    "stuck_count": len(candidates),
                    "candidates": [
                        {
                            "event_id": str(UUID(bytes=item.event_id)),
                            "event_type": item.event_type,
                            "publish_attempts": item.publish_attempts,
                            "delivery_attempts": item.delivery_attempts,
                            "last_error_code": item.last_error_code,
                        }
                        for item in candidates
                    ],
                }
            )
        )
        return 0

    if not args.event_id:
        parser.error("--event-id is required unless --detect-only is specified")

    try:
        event_id = parse_canonical_uuid(args.event_id)
    except ValueError as error:
        parser.error(str(error))

    reason = args.reason.strip()
    if args.execute and (not reason or len(reason) > 128):
        parser.error("--reason (1-128 chars) is required with --execute")
    effective_reason = reason or "dry-run-inspection"

    settings = get_settings()
    session_factory = get_session_factory()

    try:
        verifier = build_operator_verifier(settings)
    except RuntimeError as error:
        print(
            json.dumps(
                {
                    "event_id": args.event_id,
                    "status": "REPLAY_NOT_VERIFIABLE",
                    "reason_code": "OPERATOR_BROKER_CREDENTIALS_MISSING",
                    "detail": str(error),
                }
            ),
            file=sys.stderr,
        )
        return 2

    recovery = OutboxOperatorRecovery(verifier)
    result = recovery.replay(
        session_factory,
        event_id=event_id,
        reason=effective_reason,
        execute=bool(args.execute),
    )
    print(
        json.dumps(
            {
                "event_id": str(UUID(bytes=result.event_id)),
                "status": result.status,
                "reason_code": result.reason_code,
                "delivery_attempts": result.delivery_attempts,
            }
        )
    )
    if result.status in {"DRY_RUN_ELIGIBLE", "REPLAY_QUEUED"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
