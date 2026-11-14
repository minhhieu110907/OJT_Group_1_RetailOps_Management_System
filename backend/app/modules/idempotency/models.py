"""Persistence model for TD-04C Option A idempotency records."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.mysql import BINARY, DATETIME, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        Index("ix_idempotency_records_expires_at", "expires_at"),
        CheckConstraint(
            "operation IN ('CHECKOUT','CONFIRM_RECEIPT','CANCEL_ORDER',"
            "'INVENTORY_ADJUSTMENT')",
            name="ck_idempotency_records_operation",
        ),
        CheckConstraint(
            "(response_status IS NULL AND response_body IS NULL "
            "AND completed_at IS NULL AND expires_at IS NULL) OR "
            "(response_status BETWEEN 200 AND 499 AND response_body IS NOT NULL "
            "AND completed_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at = DATE_ADD(completed_at, INTERVAL 24 HOUR))",
            name="ck_idempotency_records_completion",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(20), primary_key=True)
    key_digest: Mapped[bytes] = mapped_column(BINARY(32), primary_key=True)
    request_digest: Mapped[bytes] = mapped_column(BINARY(32), nullable=False)
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[object | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
