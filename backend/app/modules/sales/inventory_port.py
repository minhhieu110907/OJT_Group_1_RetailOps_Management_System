"""Runtime shape of the frozen CF-02 inventory dependency."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session


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
