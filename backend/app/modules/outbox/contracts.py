"""Runtime DTOs matching the frozen BE-OUTBOX Python ABI."""

from dataclasses import dataclass
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
