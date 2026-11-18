"""Runtime DTOs matching the frozen BE-OUTBOX Python ABI."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class PublishBatchResult:
    scanned: int
    published: int
    failed: int


@dataclass(frozen=True)
class EmailOutcome:
    event_id: bytes
    status: Literal["SENT", "FAILED", "SKIPPED", "RETRY"]


@dataclass(frozen=True)
class StuckEventCandidate:
    event_id: bytes
    event_type: str
    published_at: datetime
    publish_attempts: int
    delivery_attempts: int
    last_error_code: str | None


@dataclass(frozen=True)
class ReplayResult:
    event_id: bytes
    status: Literal[
        "DRY_RUN_ELIGIBLE",
        "REPLAY_QUEUED",
        "REPLAY_NOT_VERIFIABLE",
        "REPLAY_REJECTED",
    ]
    reason_code: str
    delivery_attempts: int | None = None
