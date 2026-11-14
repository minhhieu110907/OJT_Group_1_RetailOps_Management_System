"""Strict checkout input and order response DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt

MAX_SQL_INT = 2_147_483_647
MAX_SQL_BIGINT = 9_223_372_036_854_775_807
MAX_CHECKOUT_LINES = 100


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckoutLine(StrictRequest):
    product_id: StrictInt = Field(gt=0, le=MAX_SQL_BIGINT)
    quantity: StrictInt = Field(gt=0, le=MAX_SQL_INT)
    viewed_unit_price_vnd: StrictInt = Field(gt=0, le=MAX_SQL_BIGINT)


class CheckoutRequest(StrictRequest):
    items: list[CheckoutLine] = Field(min_length=1, max_length=MAX_CHECKOUT_LINES)


class OrderLineRead(BaseModel):
    product_id: int
    sku_snapshot: str
    product_name_snapshot: str
    quantity: int
    unit_price_vnd: int
    line_total_vnd: int


class OrderRead(BaseModel):
    id: int
    status: str
    total_vnd: int
    created_by: int
    sold_at: datetime
    cancelled_by: int | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    items: tuple[OrderLineRead, ...]
