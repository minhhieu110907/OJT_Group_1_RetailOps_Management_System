"""Runtime shape of the frozen CF-02 inventory dependency."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.inventory.schemas import (
    LockedStock,
    StockLine,
    StockLockSet,
    StockResult,
)


class InventoryServicePort(Protocol):
    def lock_for_mutation(
        self, session: Session, *, product_ids: Sequence[int]
    ) -> StockLockSet: ...

    def decrease_for_checkout(
        self,
        session: Session,
        *,
        locks: StockLockSet,
        order_id: int,
        actor_id: int,
        lines: Sequence[StockLine],
    ) -> list[StockResult]: ...


__all__ = [
    "InventoryServicePort",
    "LockedStock",
    "StockLine",
    "StockLockSet",
    "StockResult",
]
