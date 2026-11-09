"""Pydantic request and response schemas for the Product API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.modules.products.models import CatalogStatus


def normalize_sku(value: str) -> str:
    """Validate and trim a canonical ASCII SKU."""
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("SKU must not be empty")
    if len(trimmed) > 64:
        raise ValueError("SKU must not exceed 64 characters")
    try:
        trimmed.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("SKU must contain ASCII characters only") from error
    if any(ch.isspace() or not ch.isprintable() for ch in trimmed):
        raise ValueError("SKU must not contain whitespace or control characters")
    return trimmed


def normalize_product_name(value: str) -> str:
    """Validate and trim a product display name."""
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Product name must not be empty")
    if len(trimmed) > 160:
        raise ValueError("Product name must not exceed 160 characters")
    return trimmed


class StrictRequest(BaseModel):
    """Base schema rejecting unapproved request fields."""

    model_config = ConfigDict(extra="forbid")


class ProductCreateRequest(StrictRequest):
    """Payload for creating a new product and its initial zero-stock inventory."""

    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    category_id: StrictInt = Field(gt=0)
    sale_price_vnd: StrictInt = Field(gt=0)

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        return normalize_sku(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_product_name(value)


class ProductUpdateRequest(StrictRequest):
    """Whitelisted payload for updating product master fields (excluding stock)."""

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category_id: StrictInt | None = Field(default=None, gt=0)
    sale_price_vnd: StrictInt | None = Field(default=None, gt=0)

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_sku(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_product_name(value)


class ProductStatusUpdateRequest(StrictRequest):
    """Payload for activating or deactivating a product."""

    status: CatalogStatus


class ProductRead(BaseModel):
    """Safe product representation joined with current inventory balance."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    category_id: int
    sku: str
    name: str
    status: CatalogStatus
    sale_price_vnd: int
    quantity: int
    stock_version: int
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    """Paginated list envelope for products."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProductRead]
    total: int
    page: int
    page_size: int

