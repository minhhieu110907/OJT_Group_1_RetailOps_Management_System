"""Pydantic request and response schemas for Categories."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.modules.categories.models import CategoryStatus


def _ensure_utc_iso(dt: datetime) -> str:
    """Format naive or aware UTC datetimes to ISO-8601 with trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class CategoryCreate(BaseModel):
    """Request payload for creating a new category."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tên danh mục không được để trống.")
        return trimmed


class CategoryUpdate(BaseModel):
    """Request payload for updating a category name."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tên danh mục không được để trống.")
        return trimmed


class CategoryStatusUpdate(BaseModel):
    """Request payload for changing category status."""

    model_config = ConfigDict(extra="forbid")

    status: CategoryStatus


class CategoryRead(BaseModel):
    """Public representation of a category."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
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
