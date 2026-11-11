"""Pydantic schemas for inventory queries."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class InventoryPage(BaseModel):
    """Paginated inventory list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[InventoryRead] = Field(..., description="Danh sách bản ghi tồn kho")
    total: int = Field(..., ge=0, description="Tổng số bản ghi thỏa mãn điều kiện")
    page: int = Field(..., ge=1, description="Trang hiện tại")
    page_size: int = Field(..., ge=1, le=100, description="Số lượng bản ghi mỗi trang")
