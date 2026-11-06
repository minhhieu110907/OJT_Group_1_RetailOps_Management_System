"""SQLAlchemy models for the authentication foundation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BINARY, DATETIME, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(StrEnum):
    """Supported RetailOps roles."""

    ADMIN = "ADMIN"
    STAFF = "STAFF"


class UserStatus(StrEnum):
    """Supported account states."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"


class ApprovalStatus(StrEnum):
    """Supported staff approval states."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class User(Base):
    """RetailOps user identity."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        UniqueConstraint("admin_slot", name="uq_users_admin_slot"),
        CheckConstraint(
            "(role = 'ADMIN' AND admin_slot IS NOT NULL AND admin_slot = 1 "
            "AND status = 'ACTIVE') OR "
            "(role = 'STAFF' AND admin_slot IS NULL AND status IN "
            "('PENDING_APPROVAL', 'ACTIVE', 'REJECTED'))",
            name="ck_users_role_status_admin_slot",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email_normalized: Mapped[str] = mapped_column(
        String(254, collation="ascii_bin"), nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    admin_slot: Mapped[int | None] = mapped_column(TINYINT, nullable=True)
    last_reapplied_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    approval_requests: Mapped[list[StaffApprovalRequest]] = relationship(
        back_populates="user",
        foreign_keys="StaffApprovalRequest.user_id",
    )
    decided_approval_requests: Mapped[list[StaffApprovalRequest]] = relationship(
        back_populates="decided_by_user",
        foreign_keys="StaffApprovalRequest.decided_by",
    )
    auth_sessions: Mapped[list[AuthSession]] = relationship(back_populates="user")


class StaffApprovalRequest(Base):
    """One immutable review attempt for a staff account."""

    __tablename__ = "staff_approval_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "attempt_no", name="uq_staff_approval_user_attempt"
        ),
        Index(
            "ix_staff_approval_status_requested_id",
            "status",
            "requested_at",
            "id",
        ),
        CheckConstraint("attempt_no > 0", name="ck_staff_approval_attempt_positive"),
        CheckConstraint(
            "(status = 'PENDING' AND decided_by IS NULL AND decided_at IS NULL) "
            "OR (status IN ('APPROVED', 'REJECTED') "
            "AND decided_by IS NOT NULL AND decided_at IS NOT NULL "
            "AND decided_at >= requested_at)",
            name="ck_staff_approval_decision_state",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    decision_reason: Mapped[str | None] = mapped_column(String(500))

    user: Mapped[User] = relationship(
        back_populates="approval_requests", foreign_keys=[user_id]
    )
    decided_by_user: Mapped[User | None] = relationship(
        back_populates="decided_approval_requests", foreign_keys=[decided_by]
    )


class AuthSession(Base):
    """Server-side session checked by every protected request."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
        CheckConstraint(
            "expires_at > created_at "
            "AND expires_at <= DATE_ADD(created_at, INTERVAL 8 HOUR)",
            name="ck_auth_sessions_expiry",
        ),
    )

    id: Mapped[bytes] = mapped_column(BINARY(16), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))

    user: Mapped[User] = relationship(back_populates="auth_sessions")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="session")


class RefreshToken(Base):
    """Digest-only refresh token generation history."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "generation", name="uq_refresh_tokens_session_generation"
        ),
        CheckConstraint(
            "generation >= 0 AND (consumed_at IS NULL OR consumed_at >= issued_at)",
            name="ck_refresh_tokens_generation_consumption",
        ),
    )

    token_digest: Mapped[bytes] = mapped_column(BINARY(32), primary_key=True)
    session_id: Mapped[bytes] = mapped_column(
        ForeignKey("auth_sessions.id"), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))

    session: Mapped[AuthSession] = relationship(back_populates="refresh_tokens")
