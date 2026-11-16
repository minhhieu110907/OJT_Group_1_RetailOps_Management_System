"""Pydantic schemas for analytics endpoints."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.modules.inventory.schemas import DEFAULT_LOW_STOCK_THRESHOLD, LowStockPage


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


class ProductAnalyticsItemRead(BaseModel):
    """Product metric item matching openapi ProductAnalyticsItem."""

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)
    sku: str
    name: str
    sold_units: int = Field(ge=0)
    revenue_vnd: int = Field(ge=0)
    quantity: int | None = Field(default=None, ge=0)
    first_stocked_at: datetime | None = None

    @field_serializer("first_stocked_at")
    def serialize_first_stocked_at(self, value: datetime | None) -> str | None:
        """Format UTC datetime into ISO-8601 with trailing Z if present."""
        if value is None:
            return None
        if value.tzinfo is None:
            utc_dt = value.replace(tzinfo=UTC)
        else:
            utc_dt = value.astimezone(UTC)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class ProductAnalyticsPageRead(BaseModel):
    """Paginated product analytics list matching openapi ProductAnalyticsPage."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProductAnalyticsItemRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class LowStockAnalyticsPageRead(LowStockPage):
    """Paginated low-stock analytics response aligned with Inventory threshold."""

    model_config = ConfigDict(extra="forbid")

    threshold: int = Field(
        default=DEFAULT_LOW_STOCK_THRESHOLD,
        ge=0,
        description="Ngưỡng tồn kho thấp đang áp dụng (P0 = 5)",
    )


class DashboardRead(BaseModel):
    """Executive dashboard summary matching openapi DashboardRead."""

    model_config = ConfigDict(extra="forbid")

    sales: SalesSummaryRead
    low_stock_count: int = Field(ge=0)
    top_products: list[ProductAnalyticsItemRead]
