"""Pydantic schemas for analytics endpoints."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class SalesSummaryRead(BaseModel):
    """Aggregated sales KPI summary matching contracts/openapi.yaml SalesSummary."""

    model_config = ConfigDict(extra="forbid")

    period_start: datetime
    period_end_exclusive: datetime
    revenue_vnd: int = Field(ge=0)
    completed_orders: int = Field(ge=0)
    cancelled_orders: int = Field(ge=0)
    aov_vnd: int = Field(ge=0)

    @field_serializer("period_start", "period_end_exclusive")
    def serialize_utc_datetime(self, value: datetime) -> str:
        """Format UTC datetime into ISO-8601 with trailing Z."""
        if value.tzinfo is None:
            utc_dt = value.replace(tzinfo=UTC)
        else:
            utc_dt = value.astimezone(UTC)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

