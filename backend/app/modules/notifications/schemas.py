"""Pydantic schemas for Admin in-app notifications."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class EmptyPatchRequest(BaseModel):
    """Strict empty JSON body for state-transition PATCH endpoints."""

    model_config = ConfigDict(extra="forbid")


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    approval_request_id: int
    created_at: datetime
    read_at: datetime | None

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return _ensure_utc(value).isoformat().replace("+00:00", "Z")

    @field_serializer("read_at")
    def serialize_read_at(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _ensure_utc(value).isoformat().replace("+00:00", "Z")


class NotificationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationRead]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int


class MarkAllReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_count: int
