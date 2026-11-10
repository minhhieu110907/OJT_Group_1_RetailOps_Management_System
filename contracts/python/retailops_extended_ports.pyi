"""RetailOps CF-2.0 typed cross-module ports — design proposal, not existing implementation.
One SQLAlchemy Session per use case; nested provider ports never commit/rollback.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Generic, Literal, Mapping, Sequence, TypeVar
from sqlalchemy.orm import Session

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
EventType = Literal["STAFF_REGISTERED", "STAFF_APPROVED", "STAFF_REJECTED", "PASSWORD_RESET", "STAFF_REAPPLY_PROOF"]
ToolId = Literal["get_sales_summary", "get_top_products", "get_slow_products", "get_low_stock"]
T = TypeVar("T")

@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    total: int
    page: int
    page_size: int

@dataclass(frozen=True)
class Period:
    start_utc: datetime
    end_utc_exclusive: datetime

@dataclass(frozen=True)
class ApprovalRead:
    id: int
    user_id: int
    attempt_no: int
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    requested_at: datetime
    decided_by: int | None
    decided_at: datetime | None
    decision_reason: str | None

@dataclass(frozen=True)
class InventoryRead:
    product_id: int
    sku: str
    name: str
    category_id: int
    status: Literal["ACTIVE", "INACTIVE"]
    quantity: int
    stock_version: int
    first_stocked_at: datetime | None

@dataclass(frozen=True)
class InventoryQuery:
    page: int = 1
    page_size: int = 20
    category_id: int | None = None
    status: Literal["ACTIVE", "INACTIVE"] | None = None
    in_stock: bool | None = None

@dataclass(frozen=True)
class StockMovementRead:
    id: int
    product_id: int
    sku: str
    kind: Literal["PURCHASE_CONFIRM", "SALE", "ORDER_CANCEL", "ADJUSTMENT"]
    quantity_before: int
    quantity_after: int
    stock_version_after: int
    reference_id: int | None
    occurred_at: datetime

@dataclass(frozen=True)
class MovementQuery:
    page: int = 1
    page_size: int = 20
    product_id: int | None = None
    kind: str | None = None

@dataclass(frozen=True)
class LowStockItem:
    product_id: int
    sku: str
    name: str
    quantity: int
    threshold: int

@dataclass(frozen=True)
class SalesSummary:
    period_start: datetime
    period_end_exclusive: datetime
    revenue_vnd: int
    completed_orders: int
    cancelled_orders: int
    aov_vnd: int

@dataclass(frozen=True)
class ProductAnalyticsItem:
    product_id: int
    sku: str
    name: str
    sold_units: int
    revenue_vnd: int
    quantity: int | None = None
    first_stocked_at: datetime | None = None

@dataclass(frozen=True)
class DashboardRead:
    sales: SalesSummary
    low_stock_count: int
    top_products: tuple[ProductAnalyticsItem, ...]

@dataclass(frozen=True)
class ToolContext:
    actor_id: int
    actor_role: str  # derived from authenticated principal, never model arguments
    request_id: str

@dataclass(frozen=True)
class ToolResult:
    tool_id: ToolId
    data: Mapping[str, JsonValue]
    source_period: str | None

@dataclass(frozen=True)
class PublishBatchResult:
    scanned: int
    published: int
    failed: int

@dataclass(frozen=True)
class EmailOutcome:
    event_id: bytes
    status: Literal["SENT", "FAILED", "SKIPPED", "RETRY"]

class OutboxWriter:
    def append(self, session: Session, *, subject_user_id: int, event_type: EventType,
               payload: Mapping[str, JsonValue], available_at_utc: datetime,
               secret_ciphertext: bytes | None = None,
               secret_expires_at_utc: datetime | None = None) -> bytes: ...

class OutboxPublisher:
    def publish_due(self, session_factory: Callable[[], Session], *, batch_size: int) -> PublishBatchResult: ...

class EmailEventHandler:
    def handle(self, *, event_id: bytes) -> EmailOutcome: ...

class StaffApprovalService:
    def list(self, session: Session, *, status: Literal["PENDING", "APPROVED", "REJECTED"] | None,
             page: int, page_size: int) -> Page[ApprovalRead]: ...
    def decide(self, session: Session, *, actor_id: int, approval_id: int,
               decision: Literal["APPROVED", "REJECTED"], reason: str | None) -> ApprovalRead: ...

class InventoryReadService:
    def list(self, session: Session, *, filters: InventoryQuery) -> Page[InventoryRead]: ...
    def get(self, session: Session, *, product_id: int) -> InventoryRead: ...
    def low_stock(self, session: Session, *, page: int, page_size: int) -> Page[LowStockItem]: ...

class StockMovementReadService:
    def list(self, session: Session, *, filters: MovementQuery, actor_role: str) -> Page[StockMovementRead]: ...

class SalesAnalyticsService:
    def summary(self, session: Session, *, period: Period) -> SalesSummary: ...

class ProductAnalyticsService:
    def top(self, session: Session, *, period: Period, page: int, page_size: int) -> Page[ProductAnalyticsItem]: ...
    def slow(self, session: Session, *, as_of_utc: datetime, page: int, page_size: int) -> Page[ProductAnalyticsItem]: ...
    def low_stock(self, session: Session, *, page: int, page_size: int) -> Page[LowStockItem]: ...

class DashboardService:
    def read(self, session: Session, *, period: Period) -> DashboardRead: ...

class AIToolExecutor:
    def execute(self, session: Session, *, tool_id: ToolId,
                arguments: Mapping[str, JsonValue], context: ToolContext) -> ToolResult: ...
