"""Pydantic query DTOs and domain dataclasses for the Inventory module."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.modules.inventory.models import MovementKind, MovementType, ReferenceType

# inventory.quantity / stock_movements.quantity_* are signed MySQL INT columns.
MAX_STOCK_QUANTITY = 2_147_483_647
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


class AdjustRequest(BaseModel):
    """Payload for physical inventory count adjustment (CF-02)."""

    model_config = ConfigDict(extra="forbid")

    counted_quantity: int = Field(
        ...,
        ge=0,
        le=MAX_STOCK_QUANTITY,
        description="Số lượng kiểm kê thực tế",
    )
    expected_stock_version: int = Field(
        ...,
        ge=0,
        description="Phiên bản tồn kho kỳ vọng (optimistic concurrency guard)",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Lý do điều chỉnh",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Lý do kiểm kê không được để trống.")
        return trimmed


class AdjustResponse(BaseModel):
    """Result of an inventory count adjustment."""

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(..., ge=1, description="Mã định danh sản phẩm")
    quantity: int = Field(..., ge=0, description="Số lượng tồn kho sau điều chỉnh")
    stock_version: int = Field(
        ...,
        ge=0,
        description="Phiên bản tồn kho sau điều chỉnh",
    )
    audit_id: int = Field(..., ge=1, description="Mã bản ghi kiểm kê audit")
    movement_created: bool = Field(
        ...,
        description="True nếu tạo biến động tồn kho, False nếu số lượng không đổi",
    )


@dataclass(frozen=True)
class StockLine:
    """Line item for receipt confirmation, checkout, or order cancellation (CF-02)."""

    product_id: int
    quantity: int


@dataclass(frozen=True)
class LockedStock:
    """Snapshot of a locked Product + Inventory row pair under SELECT ... FOR UPDATE."""

    product_id: int
    sku: str
    name: str
    status: str
    sale_price_vnd: int
    quantity: int
    stock_version: int


@dataclass(frozen=True)
class StockLockSet:
    """Collection of locked stock snapshots bound to one active Session/Transaction."""

    rows: Mapping[int, LockedStock]
    session_identity: int | None = None
    transaction_identity: int | None = None
    _state: dict[str, bool] = field(
        default_factory=lambda: {"consumed": False},
        repr=False,
        compare=False,
    )

    @property
    def is_consumed(self) -> bool:
        """Return True if this lockset has already been consumed by a mutation."""
        return bool(self._state.get("consumed", False))

    def mark_consumed(self) -> None:
        """Mark this lockset as consumed so it cannot be reused across mutations."""
        self._state["consumed"] = True


@dataclass(frozen=True)
class StockResult:
    """Updated stock balance and version returned after a mutation (CF-02)."""

    product_id: int
    quantity: int
    stock_version: int


@dataclass(frozen=True)
class CountAdjustment:
    """Input payload for Admin physical count adjustment (CF-02)."""

    product_id: int
    counted_quantity: int
    expected_stock_version: int
    reason: str


@dataclass(frozen=True)
class AdjustmentResult:
    """Outcome of an Admin inventory count adjustment (CF-02 contract)."""

    stock: StockResult
    audit_id: int
    movement_created: bool
    movement: StockMovementResult | None = None


@dataclass(frozen=True)
class StockChangeItem:
    """Unified input item for InventoryService.apply_stock_change().

    - For INCREASE / DECREASE / RETURN: provide ``product_id`` and positive
      ``quantity``. Optional ``expected_stock_version`` can be supplied for extra
      optimistic checking.
    - For ADJUST: provide ``product_id``, ``counted_quantity`` (>= 0), and
      ``expected_stock_version`` (>= 0).
    """

    product_id: int
    quantity: int | None = None
    counted_quantity: int | None = None
    expected_stock_version: int | None = None


@dataclass(frozen=True)
class StockMovementResult:
    """Detailed result returned by unified stock change operations."""

    movement_id: int | None
    product_id: int
    sku_snapshot: str
    kind: MovementKind
    movement_type: MovementType
    reference_type: ReferenceType
    reference_id: int | None
    actor_id: int
    quantity_before: int
    quantity_after: int
    delta: int
    stock_version_before: int
    stock_version_after: int
    occurred_at: datetime
    movement_created: bool = True
    audit_id: int | None = None


__all__ = [
    "AdjustRequest",
    "AdjustResponse",
    "AdjustmentResult",
    "CountAdjustment",
    "DEFAULT_LOW_STOCK_THRESHOLD",
    "InventoryPage",
    "InventoryRead",
    "LockedStock",
    "LowStockItem",
    "LowStockPage",
    "MAX_STOCK_QUANTITY",
    "StockChangeItem",
    "StockLine",
    "StockLockSet",
    "StockMovementAdminPage",
    "StockMovementAdminRead",
    "StockMovementKind",
    "StockMovementPage",
    "StockMovementRead",
    "StockMovementResult",
    "StockResult",
]
