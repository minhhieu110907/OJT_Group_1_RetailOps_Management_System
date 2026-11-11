"""Pydantic v2 request and response schemas for Purchase Receipts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class StrictRequest(BaseModel):
    """Base schema rejecting unapproved request fields."""

    model_config = ConfigDict(extra="forbid")


class ReceiptLineInput(StrictRequest):
    """Line item input for creating or updating a draft purchase receipt."""

    product_id: StrictInt = Field(gt=0, description="Product ID")
    quantity: StrictInt = Field(gt=0, description="Quantity must be greater than 0")
    unit_cost_vnd: StrictInt = Field(
        ge=0, description="Unit cost in VND must be non-negative"
    )


class ReceiptCreateRequest(StrictRequest):
    """Request body for creating a new DRAFT purchase receipt."""

    supplier_id: StrictInt = Field(gt=0, description="Supplier ID")
    items: list[ReceiptLineInput] = Field(
        min_length=1, description="List of receipt line items (minimum 1 item)"
    )


class ReceiptUpdateRequest(StrictRequest):
    """Request body for updating a DRAFT purchase receipt with optimistic locking."""

    expected_draft_version: StrictInt = Field(
        ge=1, description="Expected draft version for optimistic concurrency control"
    )
    supplier_id: StrictInt | None = Field(
        default=None, gt=0, description="Optional new supplier ID"
    )
    items: list[ReceiptLineInput] | None = Field(
        default=None,
        min_length=1,
        description="Optional replacement list of receipt line items",
    )


class ReceiptItemRead(BaseModel):
    """Line item response schema."""

    model_config = ConfigDict(from_attributes=True)

    product_id: int
    sku_snapshot: str
    product_name_snapshot: str
    quantity: int
    unit_cost_vnd: int
    line_total_vnd: int


class ReceiptRead(BaseModel):
    """Purchase receipt header and line items response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    supplier_name_snapshot: str | None
    status: str
    draft_version: int
    total_vnd: int
    created_by: int
    closed_by: int | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    items: list[ReceiptItemRead]
