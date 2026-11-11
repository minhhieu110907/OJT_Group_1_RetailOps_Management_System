"""Inventory module public exports."""

from app.modules.inventory.exceptions import (
    DuplicateMovementError,
    InactiveProductStockError,
    InsufficientStockError,
    InventoryValidationError,
    StaleStockVersionError,
    StockConflictError,
    StockItemNotFoundError,
)
from app.modules.inventory.models import (
    Inventory,
    InventoryAdjustment,
    MovementKind,
    MovementType,
    Product,
    ProductStatus,
    ReferenceType,
    StockMovement,
)
from app.modules.inventory.repository import InventoryMovementRepository
from app.modules.inventory.schemas import (
    AdjustmentResult,
    CountAdjustment,
    LockedStock,
    StockChangeItem,
    StockLine,
    StockLockSet,
    StockMovementResult,
    StockResult,
)
from app.modules.inventory.service import (
    InventoryService,
    merge_and_sort_stock_lines,
    normalize_lock_order,
)

__all__ = [
    "AdjustmentResult",
    "CountAdjustment",
    "DuplicateMovementError",
    "InactiveProductStockError",
    "InsufficientStockError",
    "Inventory",
    "InventoryAdjustment",
    "InventoryMovementRepository",
    "InventoryService",
    "InventoryValidationError",
    "LockedStock",
    "MovementKind",
    "MovementType",
    "Product",
    "ProductStatus",
    "ReferenceType",
    "StaleStockVersionError",
    "StockChangeItem",
    "StockConflictError",
    "StockItemNotFoundError",
    "StockLine",
    "StockLockSet",
    "StockMovement",
    "StockMovementResult",
    "StockResult",
    "merge_and_sort_stock_lines",
    "normalize_lock_order",
]
