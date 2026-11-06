"""SQLAlchemy ORM model for in-app Admin notifications."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminNotification(Base):
    """In-app notification alerted to an Admin for a Staff approval request."""

    __tablename__ = "admin_notifications"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    admin_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_admin_notifications_admin_user_id_users",
        ),
        nullable=False,
    )
    approval_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "staff_approval_requests.id",
            name="fk_admin_notifications_approval_request_id",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_admin_notifications"),
        UniqueConstraint(
            "approval_request_id",
            name="uq_admin_notifications_approval_request_id",
        ),
        Index(
            "ix_admin_notifications_admin_user_id_read_at_created_at_id",
            "admin_user_id",
            "read_at",
            "created_at",
            "id",
        ),
    )

