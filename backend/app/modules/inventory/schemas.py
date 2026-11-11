"""Value objects and DTOs for the Inventory Service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from app.modules.inventory.models import MovementKind, MovementType, ReferenceType


@dataclass(frozen=True)
class StockLine:
    """Line item for receipt/checkout/cancel stock changes (CF-02 contract)."""

    product_id: int
    quantity: int


@dataclass(frozen=True)
class LockedStock:
    """Snapshot of a Product and its Inventory balance under SELECT ... FOR UPDATE."""

    product_id: int
    sku: str
    name: str
    status: str
    sale_price_vnd: int
    quantity: int
    stock_version: int


@dataclass(frozen=True)
class StockLockSet:
    """Transaction-scoped set of locked Product+Inventory rows sorted by ID."""

    rows: Mapping[int, LockedStock]
    session_identity: int | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class StockResult:
    """Post-mutation inventory state for a product (CF-02 contract)."""

    product_id: int
    quantity: int
    stock_version: int


@dataclass(frozen=True)
class CountAdjustment:
    """Input for physical inventory count adjustment (CF-02 & SRS INV-02)."""

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
    reference_id: int
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
    "AdjustmentResult",
    "CountAdjustment",
    "LockedStock",
    "StockChangeItem",
    "StockLine",
    "StockLockSet",
    "StockMovementResult",
    "StockResult",
]
