"""Read-only stuck-event detection and controlled operator replay for Outbox."""

import base64
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote, urlsplit
from uuid import UUID

from amqp.exceptions import AMQPError
from kombu import Connection
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.modules.outbox.contracts import ReplayResult, StuckEventCandidate
from app.modules.outbox.repository import OutboxRepository

LOGGER = logging.getLogger(__name__)
MAX_RECONCILE_BATCH_SIZE = 25
MIN_STUCK_AFTER_SECONDS = 60


class BrokerQuiesceVerifier(Protocol):
    """Verifies that no publisher/worker is connected and the live queue is empty."""

    def verify_quiesced(self) -> tuple[bool, str]: ...


class AmqpQuiesceVerifier:
    """Synchronous AMQP + Management API quiesce verifier for operator replay."""

    def __init__(
        self,
        *,
        amqp_url: str,
        queue_name: str,
        management_url: str,
        admin_user: str,
        admin_password: str,
        vhost: str = "/retailops",
        quiesced_users: tuple[str, ...] = (),
        timeout: float = 5.0,
    ) -> None:
        self.amqp_url = amqp_url
        self.queue_name = queue_name
        self.management_url = management_url.rstrip("/")
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.vhost = vhost
        self.quiesced_users = tuple(u for u in quiesced_users if u)
        self.timeout = timeout

    def _management_get(self, path: str) -> Any:
        token = base64.b64encode(
            f"{self.admin_user}:{self.admin_password}".encode()
        ).decode()
        request = urllib.request.Request(
            f"{self.management_url}{path}",
            headers={"Authorization": f"Basic {token}"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
            return json.loads(body) if body else None

    @staticmethod
    def _is_allowed_management_url(url: str) -> bool:
        parsed = urlsplit(url)
        if parsed.scheme == "https" and bool(parsed.hostname):
            return True
        return parsed.scheme == "http" and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }

    @staticmethod
    def _parse_nonneg_int(payload: dict[str, Any], key: str) -> int | None:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    def verify_quiesced(self) -> tuple[bool, str]:
        if (
            not self.management_url
            or not self.admin_user
            or not self.admin_password
            or not self.quiesced_users
        ):
            LOGGER.warning(
                "Outbox replay blocked: incomplete operator broker verification config",
                extra={"reason_code": "REPLAY_NOT_VERIFIABLE"},
            )
            return False, "REPLAY_NOT_VERIFIABLE"

        if not self._is_allowed_management_url(self.management_url):
            LOGGER.warning(
                "Outbox replay blocked: insecure Management API transport",
                extra={"reason_code": "REPLAY_NOT_VERIFIABLE"},
            )
            return False, "REPLAY_NOT_VERIFIABLE"

        try:
            with Connection(self.amqp_url, connect_timeout=self.timeout) as conn:
                conn.connect()
                with conn.channel() as channel:
                    declare_ok = channel.queue_declare(
                        queue=self.queue_name, passive=True
                    )
                    amqp_messages = int(declare_ok.message_count)
                    amqp_consumers = int(declare_ok.consumer_count)

            vhost_q = quote(self.vhost, safe="")
            queue_q = quote(self.queue_name, safe="")
            queue_info = self._management_get(f"/api/queues/{vhost_q}/{queue_q}")
            connections = self._management_get("/api/connections")
        except (
            AMQPError,
            KombuError,
            OSError,
            urllib.error.URLError,
            ValueError,
        ) as exc:
            LOGGER.warning(
                "Outbox replay broker verification failed",
                extra={
                    "reason_code": "REPLAY_NOT_VERIFIABLE",
                    "error_type": type(exc).__name__,
                },
            )
            return False, "REPLAY_NOT_VERIFIABLE"

        if not isinstance(queue_info, dict) or not isinstance(connections, list):
            return False, "REPLAY_NOT_VERIFIABLE"

        mgmt_consumers = self._parse_nonneg_int(queue_info, "consumers")
        mgmt_messages = self._parse_nonneg_int(queue_info, "messages")
        mgmt_ready = self._parse_nonneg_int(queue_info, "messages_ready")
        mgmt_unacked = self._parse_nonneg_int(queue_info, "messages_unacknowledged")

        if (
            mgmt_consumers is None
            or mgmt_messages is None
            or mgmt_ready is None
            or mgmt_unacked is None
        ):
            LOGGER.warning(
                "Outbox replay blocked: malformed Management API queue payload",
                extra={"reason_code": "REPLAY_NOT_VERIFIABLE"},
            )
            return False, "REPLAY_NOT_VERIFIABLE"

        active_runtime_connections = [
            conn
            for conn in connections
            if isinstance(conn, dict)
            and conn.get("vhost") == self.vhost
            and conn.get("user") in self.quiesced_users
        ]

        if (
            amqp_consumers != 0
            or amqp_messages != 0
            or mgmt_consumers != 0
            or mgmt_messages != 0
            or mgmt_ready != 0
            or mgmt_unacked != 0
            or active_runtime_connections
        ):
            LOGGER.warning(
                "Outbox replay rejected because runtime is not quiesced",
                extra={
                    "amqp_consumers": amqp_consumers,
                    "amqp_messages": amqp_messages,
                    "mgmt_consumers": mgmt_consumers,
                    "mgmt_ready": mgmt_ready,
                    "mgmt_unacked": mgmt_unacked,
                    "active_runtime_connections": len(active_runtime_connections),
                },
            )
            return False, "REPLAY_NOT_VERIFIABLE"
        return True, "VERIFIED_QUIESCED"


class OutboxStuckDetector:
    """Read-only detector for published Outbox events without a terminal outcome."""

    def __init__(
        self,
        repository: OutboxRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository or OutboxRepository()
        self.clock = clock or (lambda: datetime.now(UTC).replace(tzinfo=None))

    def detect(
        self,
        session_factory: Callable[[], Session],
        *,
        batch_size: int,
        stuck_after_seconds: int,
    ) -> tuple[StuckEventCandidate, ...]:
        if not 1 <= batch_size <= MAX_RECONCILE_BATCH_SIZE:
            raise ValueError("Outbox reconcile batch_size must be between 1 and 25")
        if stuck_after_seconds < MIN_STUCK_AFTER_SECONDS:
            raise ValueError("stuck_after_seconds must be at least 60")

        stuck_before = self.clock() - timedelta(seconds=stuck_after_seconds)
        with session_factory() as session:
            candidates = self.repository.find_stuck_events(
                session, stuck_before=stuck_before, batch_size=batch_size
            )

        if candidates:
            candidate_ids = [str(UUID(bytes=item.event_id)) for item in candidates]
            LOGGER.warning(
                "Detected stuck Outbox events awaiting operator investigation",
                extra={
                    "stuck_count": len(candidates),
                    "event_ids": candidate_ids,
                },
            )
        return candidates


class OutboxOperatorRecovery:
    """Controlled, single-event operator replay with fail-closed broker verification."""

    def __init__(
        self,
        verifier: BrokerQuiesceVerifier,
        repository: OutboxRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.verifier = verifier
        self.repository = repository or OutboxRepository()
        self.clock = clock or (lambda: datetime.now(UTC).replace(tzinfo=None))

    def replay(
        self,
        session_factory: Callable[[], Session],
        *,
        event_id: bytes,
        reason: str,
        execute: bool = False,
    ) -> ReplayResult:
        if not isinstance(event_id, bytes) or len(event_id) != 16:
            raise ValueError("Outbox event ID must contain exactly 16 bytes")
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 128:
            raise ValueError("Operator replay reason must be 1 to 128 characters")

        canonical_id = str(UUID(bytes=event_id))
        verified, verify_code = self.verifier.verify_quiesced()
        if not verified:
            LOGGER.warning(
                "Outbox operator replay blocked",
                extra={
                    "action": "REPLAY_BLOCKED",
                    "event_id": canonical_id,
                    "reason_code": verify_code,
                },
            )
            return ReplayResult(
                event_id=event_id,
                status="REPLAY_NOT_VERIFIABLE",
                reason_code=verify_code,
            )

        if not execute:
            with session_factory() as session:
                code, attempts = self.repository.check_replay_eligibility(
                    session, event_id=event_id
                )
            if code != "ELIGIBLE":
                return ReplayResult(
                    event_id=event_id,
                    status="REPLAY_REJECTED",
                    reason_code=code,
                    delivery_attempts=attempts,
                )
            return ReplayResult(
                event_id=event_id,
                status="DRY_RUN_ELIGIBLE",
                reason_code="ELIGIBLE",
                delivery_attempts=attempts,
            )

        now = self.clock()
        with session_factory() as session:
            code, attempts = self.repository.requeue_for_operator_replay(
                session, event_id=event_id, now=now
            )
            if code != "REPLAY_QUEUED":
                session.rollback()
                LOGGER.warning(
                    "Outbox operator replay rejected by DB guard",
                    extra={
                        "action": "REPLAY_REJECTED",
                        "event_id": canonical_id,
                        "reason_code": code,
                        "delivery_attempts": attempts,
                    },
                )
                return ReplayResult(
                    event_id=event_id,
                    status="REPLAY_REJECTED",
                    reason_code=code,
                    delivery_attempts=attempts,
                )
            session.commit()

        LOGGER.warning(
            "Outbox operator replay queued event for re-publishing",
            extra={
                "action": "REPLAY_QUEUED",
                "event_id": canonical_id,
                "delivery_attempts": attempts,
                "operator_reason": normalized_reason,
            },
        )
        return ReplayResult(
            event_id=event_id,
            status="REPLAY_QUEUED",
            reason_code="REPLAY_QUEUED",
            delivery_attempts=attempts,
        )
