"""Pydantic schemas with explicit safe field allowlists."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
)

from app.modules.auth.models import ApprovalStatus, UserRole, UserStatus


class OrmReadModel(BaseModel):
    """Base configuration for safe ORM-backed response schemas."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UserRead(OrmReadModel):
    """Safe user representation without password material."""

    id: int
    email_normalized: str
    role: UserRole
    status: UserStatus
    last_reapplied_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalRead(OrmReadModel):
    """Safe staff approval representation."""

    id: int
    user_id: int
    attempt_no: int
    status: ApprovalStatus
    requested_at: datetime
    decided_by: int | None
    decided_at: datetime | None
    decision_reason: str | None

    @field_serializer("requested_at", "decided_at")
    def serialize_utc(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")


class ApprovalListItemRead(ApprovalRead):
    """Admin-only list item including the Staff account email."""

    email: EmailStr


StaffApprovalRead = ApprovalRead


class ApprovalPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ApprovalListItemRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class AuthSessionRead(OrmReadModel):
    """Session metadata without refresh-token material."""

    id: UUID
    user_id: int
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class RefreshTokenMetadata(OrmReadModel):
    """Non-secret refresh generation metadata."""

    session_id: UUID
    generation: int
    issued_at: datetime
    consumed_at: datetime | None


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RejectRequest(StrictRequest):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must contain non-whitespace characters")
        return normalized


class LoginRequest(StrictRequest):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class AuthenticatedUser(BaseModel):
    id: int
    email_normalized: str
    role: UserRole
    status: UserStatus


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


class CsrfResponse(BaseModel):
    csrf_token: str


class RegisterRequest(StrictRequest):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RegisterResponse(BaseModel):
    message: str
