"""Shared idempotency executor preserving use-case transaction ownership."""

import hmac
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Generic, TypeVar, cast

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    DomainValidationError,
    IdempotencyKeyReusedError,
    RequestInProgressError,
)
from app.modules.idempotency.repository import IdempotencyRepository
from app.modules.idempotency.validation import (
    DEFAULT_MAX_RESPONSE_BYTES,
    key_digest,
    request_digest,
    serialize_response_body,
)

T = TypeVar("T")


class IdempotencyOperation(StrEnum):
    CHECKOUT = "CHECKOUT"
    CONFIRM_RECEIPT = "CONFIRM_RECEIPT"
    CANCEL_ORDER = "CANCEL_ORDER"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"


_RESOURCE_OPERATIONS = frozenset(
    {
        IdempotencyOperation.CONFIRM_RECEIPT,
        IdempotencyOperation.CANCEL_ORDER,
        IdempotencyOperation.INVENTORY_ADJUSTMENT,
    }
)


@dataclass(frozen=True)
class CommandOutcome(Generic[T]):  # noqa: UP046 - frozen CF-01 runtime contract
    status_code: int
    body: T


class IdempotencyExecutor:
    def __init__(
        self,
        *,
        secret: bytes | None = None,
        repository: IdempotencyRepository | None = None,
        clock: Callable[[], datetime] | None = None,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._secret = secret
        self._repository = repository or IdempotencyRepository()
        self._clock = clock or (lambda: datetime.now(UTC).replace(tzinfo=None))
        self._max_response_bytes = max_response_bytes

    def execute(
        self,
        session: Session,
        *,
        actor_id: int,
        operation: IdempotencyOperation,
        idempotency_key: str,
        request_identity: Mapping[str, object],
        command: Callable[[], CommandOutcome[T]],
    ) -> CommandOutcome[T]:
        if actor_id <= 0:
            raise DomainValidationError("Authenticated actor_id must be positive.")
        if not isinstance(operation, IdempotencyOperation):
            raise DomainValidationError("Unsupported idempotency operation.")
        if request_identity.get("operation") != operation.value:
            raise DomainValidationError(
                "Request identity operation does not match the executor operation."
            )
        if "body" not in request_identity:
            raise DomainValidationError("Request identity must include body.")
        expected_fields = {"operation", "body"}
        if operation in _RESOURCE_OPERATIONS:
            expected_fields.add("resource_id")
            resource_id = request_identity.get("resource_id")
            if (
                not isinstance(resource_id, int)
                or isinstance(resource_id, bool)
                or resource_id <= 0
            ):
                raise DomainValidationError(
                    "Request identity resource_id must be a positive integer."
                )
        if set(request_identity) != expected_fields:
            raise DomainValidationError(
                "Request identity fields do not match the operation contract."
            )

        secret = self._secret or get_settings().require_idempotency_secret()
        key_fingerprint = key_digest(idempotency_key, secret)
        request_fingerprint = request_digest(request_identity)
        now = self._clock()
        record, claimed = self._repository.claim_or_lock(
            session,
            actor_id=actor_id,
            operation=operation.value,
            key_digest=key_fingerprint,
            request_digest=request_fingerprint,
            created_at=now,
        )

        if not hmac.compare_digest(record.request_digest, request_fingerprint):
            raise IdempotencyKeyReusedError()
        if not claimed:
            if record.completed_at is None:
                raise RequestInProgressError()
            # Expiry controls cleanup eligibility, not replay in place. Until a
            # cleanup transaction deletes the row, the committed result wins.
            return CommandOutcome(
                status_code=cast(int, record.response_status),
                body=cast(T, record.response_body),
            )

        outcome = command()
        if not isinstance(outcome, CommandOutcome):
            raise DomainValidationError("Command must return CommandOutcome.")
        if not 200 <= outcome.status_code <= 499:
            raise DomainValidationError("Command response status must be 200..499.")
        body = serialize_response_body(outcome.body, max_bytes=self._max_response_bytes)
        completed_at = self._clock()
        record.response_status = outcome.status_code
        record.response_body = body
        record.completed_at = completed_at
        record.expires_at = completed_at + timedelta(hours=24)
        session.flush()
        return CommandOutcome(status_code=outcome.status_code, body=cast(T, body))
