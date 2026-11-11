"""Domain exceptions for the Inventory Service module."""

from typing import Any

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    InvalidStateError,
    ResourceNotFoundError,
)


class StockItemNotFoundError(ResourceNotFoundError):
    """Raised when one or more requested product/inventory records do not exist."""

    def __init__(
        self,
        product_ids: list[int] | None = None,
        message: str = "Không tìm thấy thông tin tồn kho của sản phẩm.",
    ) -> None:
        details = {"missing_product_ids": product_ids} if product_ids else None
        super().__init__(message=message, details=details)


class InsufficientStockError(ConflictError):
    """Raised when a stock deduction would result in a negative inventory balance."""

    def __init__(
        self,
        *,
        product_id: int,
        requested_quantity: int,
        available_quantity: int,
        message: str = "Số lượng tồn kho không đủ để thực hiện giao dịch.",
    ) -> None:
        super().__init__(
            code="INSUFFICIENT_STOCK",
            message=message,
            details={
                "product_id": product_id,
                "requested_quantity": requested_quantity,
                "available_quantity": available_quantity,
            },
        )


class StaleStockVersionError(ConflictError):
    """Raised when expected_stock_version does not match current stock_version."""

    def __init__(
        self,
        *,
        product_id: int,
        expected_stock_version: int,
        current_stock_version: int,
        message: str = "Phiên bản tồn kho đã thay đổi, vui lòng tải lại dữ liệu.",
    ) -> None:
        super().__init__(
            code="STALE_STOCK_VERSION",
            message=message,
            details={
                "product_id": product_id,
                "expected_stock_version": expected_stock_version,
                "current_stock_version": current_stock_version,
            },
        )


class StockConflictError(ConflictError):
    """Raised on concurrent stock version conflict, lock timeout, or deadlock."""

    def __init__(
        self,
        message: str = "Xung đột cập nhật tồn kho đồng thời, vui lòng thử lại.",
        details: Any = None,
        code: str = "STOCK_CONFLICT",
    ) -> None:
        super().__init__(code=code, message=message, details=details)


class DuplicateMovementError(ConflictError):
    """Raised when a stock movement for the same reference/product conflicts."""

    def __init__(
        self,
        message: str = "Biến động tồn kho cho chứng từ này đã được ghi nhận.",
        details: Any = None,
    ) -> None:
        super().__init__(
            code="DUPLICATE_STOCK_MOVEMENT",
            message=message,
            details=details,
        )


class InactiveProductStockError(InvalidStateError):
    """Raised when attempting receipt/checkout stock changes on an INACTIVE product."""

    def __init__(
        self,
        *,
        product_id: int,
        message: str = "Sản phẩm đang ngừng kinh doanh, không thể giao dịch tồn kho.",
    ) -> None:
        super().__init__(
            message=message,
            details={"product_id": product_id},
        )


class InventoryValidationError(DomainValidationError):
    """Raised when stock change input fails business validation rules."""


MYSQL_LOCK_CONFLICT_ERRNOS = frozenset({1205, 1213})


def is_mysql_lock_conflict_error(error: BaseException) -> bool:
    """Return True if a DBAPI/SQLAlchemy error is a MySQL lock timeout or deadlock."""
    orig = getattr(error, "orig", None)
    args = getattr(orig, "args", ())
    if args and isinstance(args[0], int) and args[0] in MYSQL_LOCK_CONFLICT_ERRNOS:
        return True
    msg = str(error).lower()
    return "deadlock found" in msg or "lock wait timeout exceeded" in msg


__all__ = [
    "DuplicateMovementError",
    "InactiveProductStockError",
    "InsufficientStockError",
    "InventoryValidationError",
    "StaleStockVersionError",
    "StockConflictError",
    "StockItemNotFoundError",
    "is_mysql_lock_conflict_error",
]
