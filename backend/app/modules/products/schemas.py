"""Pydantic request and response schemas for the Product API."""

from datetime import datetime
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictInt,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.modules.products.models import CatalogStatus

MAX_PRODUCT_SEARCH_LENGTH = 100
_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


def validate_image_url(value: str | None) -> str | None:
    """Accept only absolute HTTPS references; the backend never fetches them."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 500:
        raise ValueError("image_url must contain 1 to 500 characters")
    try:
        parsed = _HTTP_URL_ADAPTER.validate_python(normalized)
    except ValueError as error:
        raise ValueError("image_url must be an absolute HTTPS URL") from error
    if parsed.scheme != "https":
        raise ValueError("image_url must use the HTTPS scheme")
    return normalized


class ProductSortOrder(StrEnum):
    """Whitelisted sort keys for the product catalog query API."""

    QUANTITY_ASC = "quantity_asc"
    RESTOCK_FIRST = "restock_first"
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"
    SKU_ASC = "sku_asc"
    SKU_DESC = "sku_desc"
    CREATED_DESC = "created_desc"


def normalize_search_query(value: str | None) -> str | None:
    """Validate and trim an optional product search keyword."""
    if value is None:
        return None
    if len(value) > MAX_PRODUCT_SEARCH_LENGTH:
        raise ValueError(
            f"Search query must not exceed {MAX_PRODUCT_SEARCH_LENGTH} characters"
        )
    trimmed = value.strip()
    return trimmed if trimmed else None


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
    image_url: str | None = Field(
        default=None,
        max_length=500,
        json_schema_extra={"format": "uri", "pattern": "^https://"},
    )

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        return normalize_sku(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_product_name(value)

    _validate_image_url = field_validator("image_url")(validate_image_url)


class ProductUpdateRequest(StrictRequest):
    """Whitelisted payload for updating product master fields (excluding stock)."""

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category_id: StrictInt | None = Field(default=None, gt=0)
    sale_price_vnd: StrictInt | None = Field(default=None, gt=0)
    image_url: str | None = Field(
        default=None,
        max_length=500,
        json_schema_extra={"format": "uri", "pattern": "^https://"},
    )

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

    _validate_image_url = field_validator("image_url")(validate_image_url)


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
    image_url: str | None = Field(
        max_length=500,
        json_schema_extra={"format": "uri", "pattern": "^https://"},
    )
    status: CatalogStatus
    sale_price_vnd: int
    quantity: int
    stock_version: int
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def legacy_image_url_defaults_to_null(cls, value: object) -> object:
        if isinstance(value, dict) and "image_url" not in value:
            return {**value, "image_url": None}
        return value


class ProductListResponse(BaseModel):
    """Paginated list envelope for products."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProductRead]
    total: int
    page: int
    page_size: int


class ProductImportRowError(BaseModel):
    """Per-row validation or persistence error from CSV product import."""

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=2)
    sku: str | None = None
    reason: str = Field(min_length=1)


class ProductImportResponse(BaseModel):
    """Summary and detailed row error report for CSV product import (T3C9EFC)."""

    model_config = ConfigDict(extra="forbid")

    total_rows: int = Field(ge=0)
    imported_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    errors: list[ProductImportRowError]
