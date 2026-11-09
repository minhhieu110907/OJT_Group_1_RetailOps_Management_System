"""Pydantic request and response schemas for Suppliers."""

from datetime import UTC, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.modules.suppliers.models import SupplierStatus


def _ensure_utc_iso(dt: datetime) -> str:
    """Format naive or aware UTC datetimes to ISO-8601 with trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class SupplierCreate(BaseModel):
    """Request payload for creating a new supplier."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=160)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tên nhà cung cấp không được để trống.")
        return trimmed

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None:
            trimmed = value.strip()
            return trimmed if trimmed else None
        return None


class SupplierUpdate(BaseModel):
    """Request payload for updating supplier info
    (supports setting None to clear contacts)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("Tên nhà cung cấp không được để trống.")
            return trimmed
        return None

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None:
            trimmed = value.strip()
            return trimmed if trimmed else None
        return None

    @model_validator(mode="after")
    def reject_explicit_null_name(self) -> "SupplierUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Tên nhà cung cấp không được là null.")
        return self


class SupplierStatusUpdate(BaseModel):
    """Request payload for changing supplier status."""

    model_config = ConfigDict(extra="forbid")

    status: SupplierStatus


class SupplierRead(BaseModel):
    """Public representation of a supplier."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    contact_email: str | None
    contact_phone: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return _ensure_utc_iso(value)

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return _ensure_utc_iso(value)


class SupplierListResponse(BaseModel):
    """Paginated list of suppliers."""

    model_config = ConfigDict(extra="forbid")

    items: list[SupplierRead]
    total: int
    page: int
    page_size: int
