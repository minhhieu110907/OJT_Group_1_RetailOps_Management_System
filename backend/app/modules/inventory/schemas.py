"""Pydantic schemas for inventory queries, low-stock warnings, and stock movements."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

DEFAULT_LOW_STOCK_THRESHOLD: int = 5

StockMovementKind = Literal[
    "PURCHASE_CONFIRM",
    "SALE",
    "ORDER_CANCEL",
    "ADJUSTMENT",
]


def _ensure_utc_iso(dt: datetime) -> str:
    """Format naive or aware UTC datetimes to ISO-8601 with trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class InventoryRead(BaseModel):
    """Public inventory view for active ADMIN and STAFF."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    product_id: int = Field(..., ge=1, description="Mã định danh sản phẩm")
    sku: str = Field(..., description="Mã SKU của sản phẩm")
    name: str = Field(..., description="Tên sản phẩm")
    category_id: int = Field(..., ge=1, description="Mã định danh danh mục")
    status: Literal["ACTIVE", "INACTIVE"] = Field(
        ..., description="Trạng thái sản phẩm"
    )
    quantity: int = Field(..., ge=0, description="Số lượng tồn kho hiện tại")
    stock_version: int = Field(..., ge=0, description="Phiên bản tồn kho lạc quan")
    first_stocked_at: datetime | None = Field(
        default=None,
        description="Thời điểm lần đầu tiên sản phẩm có tồn kho dương",
    )

    @field_serializer("first_stocked_at")
    def serialize_first_stocked_at(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _ensure_utc_iso(value)


class InventoryPage(BaseModel):
    """Paginated inventory list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[InventoryRead] = Field(..., description="Danh sách bản ghi tồn kho")
    total: int = Field(..., ge=0, description="Tổng số bản ghi thỏa mãn điều kiện")
    page: int = Field(..., ge=1, description="Trang hiện tại")
    page_size: int = Field(..., ge=1, le=100, description="Số lượng bản ghi mỗi trang")


class LowStockItem(BaseModel):
    """Low-stock warning product item with threshold."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    product_id: int = Field(..., ge=1, description="Mã định danh sản phẩm")
    sku: str = Field(..., description="Mã SKU của sản phẩm")
    name: str = Field(..., description="Tên sản phẩm")
    quantity: int = Field(..., ge=0, description="Số lượng tồn kho hiện tại")
    threshold: int = Field(
        default=DEFAULT_LOW_STOCK_THRESHOLD,
        ge=0,
        description="Ngưỡng cảnh báo tồn kho thấp P0",
    )


class LowStockPage(BaseModel):
    """Paginated low-stock warning list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[LowStockItem] = Field(
        ..., description="Danh sách sản phẩm có tồn kho thấp"
    )
    total: int = Field(..., ge=0, description="Tổng số sản phẩm thỏa mãn điều kiện")
    page: int = Field(..., ge=1, description="Trang hiện tại")
    page_size: int = Field(..., ge=1, le=100, description="Số lượng bản ghi mỗi trang")


class StockMovementRead(BaseModel):
    """Safe stock movement view for STAFF without internal reasons or audit actors."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int = Field(..., ge=1, description="Mã định danh bản ghi biến động")
    product_id: int = Field(..., ge=1, description="Mã định danh sản phẩm")
    sku: str = Field(..., description="Mã SKU sản phẩm")
    kind: StockMovementKind = Field(..., description="Loại biến động kho")
    quantity_before: int = Field(
        ..., ge=0, description="Số lượng tồn kho trước biến động"
    )
    quantity_after: int = Field(..., ge=0, description="Số lượng tồn kho sau biến động")
    stock_version_after: int = Field(
        ..., ge=0, description="Phiên bản tồn kho sau biến động"
    )
    reference_id: int = Field(..., ge=1, description="Mã tham chiếu chứng từ nguồn")
    occurred_at: datetime = Field(..., description="Thời điểm biến động (UTC ISO-8601)")

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: datetime) -> str:
        return _ensure_utc_iso(value)


class StockMovementAdminRead(BaseModel):
    """Audited stock movement view for ADMIN including actor and adjustment reason."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int = Field(..., ge=1, description="Mã định danh bản ghi biến động")
    product_id: int = Field(..., ge=1, description="Mã định danh sản phẩm")
    sku: str = Field(..., description="Mã SKU sản phẩm")
    kind: StockMovementKind = Field(..., description="Loại biến động kho")
    quantity_before: int = Field(
        ..., ge=0, description="Số lượng tồn kho trước biến động"
    )
    quantity_after: int = Field(..., ge=0, description="Số lượng tồn kho sau biến động")
    stock_version_after: int = Field(
        ..., ge=0, description="Phiên bản tồn kho sau biến động"
    )
    reference_id: int = Field(..., ge=1, description="Mã tham chiếu chứng từ nguồn")
    occurred_at: datetime = Field(..., description="Thời điểm biến động (UTC ISO-8601)")
    actor_id: int = Field(..., ge=1, description="Mã người dùng thực hiện")
    adjustment_reason: str | None = Field(
        default=None,
        description="Lý do điều chỉnh kiểm kê (chỉ có khi kind=ADJUSTMENT)",
    )

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: datetime) -> str:
        return _ensure_utc_iso(value)


class StockMovementPage(BaseModel):
    """Paginated stock movement response for STAFF."""

    model_config = ConfigDict(extra="forbid")

    items: list[StockMovementRead] = Field(
        ..., description="Danh sách bản ghi biến động kho"
    )
    total: int = Field(..., ge=0, description="Tổng số bản ghi thỏa mãn điều kiện")
    page: int = Field(..., ge=1, description="Trang hiện tại")
    page_size: int = Field(..., ge=1, le=100, description="Số lượng bản ghi mỗi trang")


class StockMovementAdminPage(BaseModel):
    """Paginated stock movement response for ADMIN with audited details."""

    model_config = ConfigDict(extra="forbid")

    items: list[StockMovementAdminRead] = Field(
        ..., description="Danh sách bản ghi biến động kho có kiểm toán"
    )
    total: int = Field(..., ge=0, description="Tổng số bản ghi thỏa mãn điều kiện")
    page: int = Field(..., ge=1, description="Trang hiện tại")
    page_size: int = Field(..., ge=1, le=100, description="Số lượng bản ghi mỗi trang")
