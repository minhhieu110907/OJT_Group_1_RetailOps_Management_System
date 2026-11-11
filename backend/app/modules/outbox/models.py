"""Transactional outbox persistence model shared by business modules."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.mysql import BINARY, DATETIME, JSON, VARBINARY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    """A durable event written in the owning business transaction."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_published_available_id",
            "published_at",
            "available_at",
            "id",
        ),
        Index("ix_outbox_events_outcome_finished_id", "outcome", "finished_at", "id"),
        CheckConstraint(
            "event_type IN ('STAFF_REGISTERED','STAFF_APPROVED',"
            "'STAFF_REJECTED','PASSWORD_RESET','STAFF_REAPPLY_PROOF')",
            name="ck_outbox_events_event_type",
        ),
        CheckConstraint(
            "(outcome IS NULL AND finished_at IS NULL) OR "
            "(outcome IN ('SENT','FAILED','SKIPPED') AND finished_at IS NOT NULL)",
            name="ck_outbox_events_outcome_state",
        ),
        CheckConstraint(
            "publish_attempts >= 0 AND delivery_attempts >= 0",
            name="ck_outbox_events_attempts_nonnegative",
        ),
        CheckConstraint(
            "secret_ciphertext IS NULL OR secret_expires_at IS NOT NULL",
            name="ck_outbox_events_secret_expiry",
        ),
        CheckConstraint(
            "available_at >= created_at", name="ck_outbox_events_availability"
        ),
    )

    id: Mapped[bytes] = mapped_column(BINARY(16), primary_key=True)
    subject_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    secret_expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    secret_ciphertext: Mapped[bytes | None] = mapped_column(VARBINARY(2048))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    publish_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    outcome: Mapped[str | None] = mapped_column(String(9))
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
