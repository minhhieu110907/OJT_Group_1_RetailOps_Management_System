"""Pydantic schemas with explicit safe field allowlists."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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


class StaffApprovalRead(OrmReadModel):
    """Safe staff approval representation."""

    id: int
    user_id: int
    attempt_no: int
    status: ApprovalStatus
    requested_at: datetime
    decided_by: int | None
    decided_at: datetime | None
    decision_reason: str | None


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
