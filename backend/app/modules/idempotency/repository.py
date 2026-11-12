"""Repository operations that never commit or roll back the owner transaction."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import delete, insert, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.idempotency.models import IdempotencyRecord


def _is_duplicate_key(error: IntegrityError) -> bool:
    original = error.orig
    return bool(getattr(original, "args", ())) and original.args[0] == 1062


class IdempotencyRepository:
    def claim_or_lock(
        self,
        session: Session,
        *,
        actor_id: int,
        operation: str,
        key_digest: bytes,
        request_digest: bytes,
        created_at: datetime,
    ) -> tuple[IdempotencyRecord, bool]:
        if session.new or session.dirty or session.deleted:
            raise RuntimeError(
                "Idempotency claim must precede pending business mutations"
            )
        with self._bounded_lock_wait(session):
            return self._claim_or_lock(
                session,
                actor_id=actor_id,
                operation=operation,
                key_digest=key_digest,
                request_digest=request_digest,
                created_at=created_at,
            )

    @contextmanager
    def _bounded_lock_wait(self, session: Session) -> Iterator[None]:
        if session.get_bind().dialect.name != "mysql":
            yield
            return
        original = int(
            session.scalar(text("SELECT @@SESSION.innodb_lock_wait_timeout"))
        )
        bounded = min(original, 2)
        if bounded != original:
            session.execute(text(f"SET SESSION innodb_lock_wait_timeout = {bounded}"))
        try:
            yield
        finally:
            if bounded != original:
                session.execute(
                    text(f"SET SESSION innodb_lock_wait_timeout = {original}")
                )

    def _claim_or_lock(
        self,
        session: Session,
        *,
        actor_id: int,
        operation: str,
        key_digest: bytes,
        request_digest: bytes,
        created_at: datetime,
    ) -> tuple[IdempotencyRecord, bool]:
        values = {
            "user_id": actor_id,
            "operation": operation,
            "key_digest": key_digest,
            "request_digest": request_digest,
            "created_at": created_at,
        }
        try:
            with session.begin_nested():
                claim = insert(IdempotencyRecord).values(**values)
                session.execute(claim)
            record = session.get(IdempotencyRecord, (actor_id, operation, key_digest))
            assert record is not None
            return record, True
        except IntegrityError as error:
            if not _is_duplicate_key(error):
                raise

        statement = (
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == actor_id,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.key_digest == key_digest,
            )
            .with_for_update()
        )
        record = session.scalar(statement)
        if record is None:
            raise RuntimeError("Concurrent idempotency claim could not be observed")
        return record, False

    def delete_expired(
        self, session: Session, *, before: datetime, limit: int = 500
    ) -> int:
        """Lock and delete a bounded batch; active replay rows are skipped."""
        records = list(
            session.execute(
                select(IdempotencyRecord)
                .where(IdempotencyRecord.expires_at < before)
                .order_by(IdempotencyRecord.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        if not records:
            return 0
        keys = [(row.user_id, row.operation, row.key_digest) for row in records]
        result = session.execute(
            delete(IdempotencyRecord).where(
                tuple_(
                    IdempotencyRecord.user_id,
                    IdempotencyRecord.operation,
                    IdempotencyRecord.key_digest,
                ).in_(keys),
                IdempotencyRecord.expires_at < before,
            )
        )
        return result.rowcount or 0
