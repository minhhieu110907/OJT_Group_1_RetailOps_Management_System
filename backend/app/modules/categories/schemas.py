"""Pydantic request and response schemas for Categories."""

from datetime import UTC, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.modules.categories.models import CategoryStatus

MAX_DESCRIPTION_LENGTH = 2000


def _ensure_utc_iso(dt: datetime) -> str:
    """Format naive or aware UTC datetimes to ISO-8601 with trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class CategoryCreate(BaseModel):
    """Request payload for creating a new category."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tên danh mục không được để trống.")
        return trimmed


class CategoryUpdate(BaseModel):
    """Partial update supporting an explicit null description to clear it."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tên danh mục không được để trống.")
        return trimmed

    @model_validator(mode="after")
    def reject_explicit_null_name(self) -> "CategoryUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Category name cannot be null.")
        return self


class CategoryStatusUpdate(BaseModel):
    """Request payload for changing category status."""

    model_config = ConfigDict(extra="forbid")

    status: CategoryStatus


class CategoryRead(BaseModel):
    """Public representation of a category."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return _ensure_utc_iso(value)

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return _ensure_utc_iso(value)


class CategoryListResponse(BaseModel):
    """Paginated list of categories."""

    model_config = ConfigDict(extra="forbid")

    items: list[CategoryRead]
    total: int
    page: int
    page_size: int
