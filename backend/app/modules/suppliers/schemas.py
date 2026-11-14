"""Pydantic request and response schemas for Suppliers."""

from datetime import UTC, datetime

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
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

DEFAULT_PHONE_REGION = "VN"
MAX_PHONE_INPUT_LENGTH = 64
_ALLOWED_PHONE_CHARACTERS = frozenset("0123456789+ -().")


def _ensure_utc_iso(dt: datetime) -> str:
    """Format naive or aware UTC datetimes to ISO-8601 with trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def normalize_contact_phone(value: str | None) -> str | None:
    """Validate a phone number with libphonenumber and return E.164."""
    if value is None:
        return None

    phone = value.strip()
    if not phone:
        return None
    if len(phone) > MAX_PHONE_INPUT_LENGTH:
        raise ValueError("Số điện thoại không được vượt quá 64 ký tự.")
    if not phone.isascii():
        raise ValueError("Số điện thoại chỉ được chứa ký tự ASCII.")
    if any(character not in _ALLOWED_PHONE_CHARACTERS for character in phone):
        raise ValueError("Số điện thoại chứa ký tự không được hỗ trợ.")
    if phone.count("+") > 1 or ("+" in phone and not phone.startswith("+")):
        raise ValueError("Dấu + chỉ được xuất hiện một lần ở đầu số điện thoại.")

    parse_region = None if phone.startswith("+") else DEFAULT_PHONE_REGION
    try:
        parsed = phonenumbers.parse(phone, parse_region)
    except NumberParseException as exc:
        raise ValueError("Số điện thoại không hợp lệ.") from exc

    if parsed.extension:
        raise ValueError("Số máy lẻ không được hỗ trợ.")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Số điện thoại không hợp lệ.")

    normalized = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    if not normalized.startswith("+") or len(normalized[1:]) > 15:
        raise ValueError("Số điện thoại vượt quá giới hạn E.164.")
    return normalized


class SupplierCreate(BaseModel):
    """Request payload for creating a new supplier."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=160)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=MAX_PHONE_INPUT_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tên nhà cung cấp không được để trống.")
        return trimmed

    @field_validator("contact_phone", mode="before")
    @classmethod
    def trim_phone(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def normalize_phone(self) -> "SupplierCreate":
        self.contact_phone = normalize_contact_phone(self.contact_phone)
        return self


class SupplierUpdate(BaseModel):
    """Request payload for updating supplier info
    (supports setting None to clear contacts)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=MAX_PHONE_INPUT_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("Tên nhà cung cấp không được để trống.")
            return trimmed
        return None

    @field_validator("contact_phone", mode="before")
    @classmethod
    def trim_phone(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_patch(self) -> "SupplierUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Tên nhà cung cấp không được là null.")
        if "contact_phone" in self.model_fields_set:
            self.contact_phone = normalize_contact_phone(self.contact_phone)
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
