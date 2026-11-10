"""Các bản khai báo Python interface giữa module, KHÔNG phải implementation chạy thật.
Khi triển khai module trong backend/app/modules/..., cần tuân theo các chữ ký này.
"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Callable, Generic, Mapping, Sequence, TypeVar, Literal
from sqlalchemy.orm import Session

T = TypeVar("T")

@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    total: int
    page: int
    page_size: int

class IdempotencyOperation(StrEnum):
    CHECKOUT = "CHECKOUT"
    CONFIRM_RECEIPT = "CONFIRM_RECEIPT"
    CANCEL_ORDER = "CANCEL_ORDER"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"

@dataclass(frozen=True)
class CommandOutcome(Generic[T]):
    status_code: int
    body: T

class IdempotencyExecutor:
    def execute(self, session: Session, *, actor_id: int, operation: IdempotencyOperation,
                idempotency_key: str, request_identity: Mapping[str, object],
                command: Callable[[], CommandOutcome[T]]) -> CommandOutcome[T]: ...

@dataclass(frozen=True)
class StockLine:
    product_id: int
    quantity: int

@dataclass(frozen=True)
class LockedStock:
    product_id: int
    sku: str
    name: str
    status: str
    sale_price_vnd: int
    quantity: int
    stock_version: int

@dataclass(frozen=True)
class StockLockSet:
    rows: Mapping[int, LockedStock]

@dataclass(frozen=True)
class StockResult:
    product_id: int
    quantity: int
    stock_version: int

@dataclass(frozen=True)
class CountAdjustment:
    product_id: int
    counted_quantity: int
    expected_stock_version: int
    reason: str

@dataclass(frozen=True)
class AdjustmentResult:
    stock: StockResult
    audit_id: int
    movement_created: bool

class InventoryService:
    def lock_for_mutation(self, session: Session, *, product_ids: Sequence[int]) -> StockLockSet: ...
    def increase_for_receipt(self, session: Session, *, locks: StockLockSet, receipt_id: int,
                             actor_id: int, lines: Sequence[StockLine]) -> list[StockResult]: ...
    def decrease_for_checkout(self, session: Session, *, locks: StockLockSet, order_id: int,
                              actor_id: int, lines: Sequence[StockLine]) -> list[StockResult]: ...
    def restore_for_cancel(self, session: Session, *, locks: StockLockSet, order_id: int,
                           actor_id: int, lines: Sequence[StockLine]) -> list[StockResult]: ...
    def adjust_to_count(self, session: Session, *, locks: StockLockSet, actor_id: int,
                        adjustment: CountAdjustment) -> AdjustmentResult: ...

@dataclass(frozen=True)
class ReceiptLineInput:
    product_id: int
    quantity: int
    unit_cost_vnd: int

@dataclass(frozen=True)
class ReceiptLineRead:
    product_id: int
    sku_snapshot: str
    product_name_snapshot: str
    quantity: int
    unit_cost_vnd: int
    line_total_vnd: int

@dataclass(frozen=True)
class ReceiptRead:
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
    items: tuple[ReceiptLineRead, ...]

class ReceiptDraftService:
    def create_draft(self, session: Session, *, actor_id: int, supplier_id: int,
                     items: Sequence[ReceiptLineInput]) -> ReceiptRead: ...
    def update_draft(self, session: Session, *, actor_id: int, receipt_id: int,
                     expected_draft_version: int, supplier_id: int | None,
                     items: Sequence[ReceiptLineInput] | None) -> ReceiptRead: ...
    def cancel_draft(self, session: Session, *, actor_id: int, receipt_id: int,
                     expected_draft_version: int) -> ReceiptRead: ...

class ReceiptConfirmService:
    def confirm(self, session: Session, *, actor_id: int, receipt_id: int,
                expected_draft_version: int, idempotency_key: str) -> ReceiptRead: ...

@dataclass(frozen=True)
class CheckoutLine:
    product_id: int
    quantity: int
    viewed_unit_price_vnd: int

@dataclass(frozen=True)
class OrderLineRead:
    product_id: int
    sku_snapshot: str
    product_name_snapshot: str
    quantity: int
    unit_price_vnd: int
    line_total_vnd: int

@dataclass(frozen=True)
class OrderRead:
    id: int
    status: str
    total_vnd: int
    created_by: int
    sold_at: datetime
    cancelled_by: int | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    items: tuple[OrderLineRead,...]

class CheckoutService:
    def checkout(self, session: Session, *, actor_id: int,
                 idempotency_key: str, items: Sequence[CheckoutLine]) -> OrderRead: ...

class OrderService:
    def cancel(self, session: Session, *, actor_id: int, actor_role: str,
               order_id: int, reason: str, idempotency_key: str) -> OrderRead: ...


# PUR-05 và SALE-03: danh sách đọc không tự commit; filter ngày thuộc ngày kinh doanh Việt Nam.
# Page kết quả, xử lý phân trang/role và date->UTC nằm trong service/router, không từ FE.
@dataclass(frozen=True)
class ReceiptQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None
    supplier_id: int | None = None
    from_date: date | None = None
    to_date: date | None = None

class ReceiptReadService:
    def list(self, session: Session, *, actor_id: int, actor_role: str, filters: ReceiptQuery) -> Page[ReceiptRead]: ...
    def get(self, session: Session, *, actor_id: int, actor_role: str, receipt_id: int) -> ReceiptRead: ...

@dataclass(frozen=True)
class OrderQuery:
    page: int = 1
    page_size: int = 20
    status: str | None = None
    search: str | None = None
    from_date: date | None = None
    to_date: date | None = None

class OrderReadService:
    def list(self, session: Session, *, actor_id: int, actor_role: str, filters: OrderQuery) -> Page[OrderRead]: ...
    def get(self, session: Session, *, actor_id: int, actor_role: str, order_id: int) -> OrderRead: ...


class InventoryAdjustmentService:
    def adjust(self, session: Session, *, actor_id: int, actor_role: Literal["ADMIN"],
               idempotency_key: str, adjustment: CountAdjustment) -> AdjustmentResult: ...
