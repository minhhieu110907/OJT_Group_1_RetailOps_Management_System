from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import ConflictError, DomainValidationError
from app.modules.idempotency.service import CommandOutcome
from app.modules.sales.inventory_port import LockedStock, StockLockSet
from app.modules.sales.schemas import CheckoutLine
from app.modules.sales.service import CheckoutService


class FakeSession:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit

    def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("commit failure")

    def rollback(self) -> None:
        self.rollbacks += 1


class MemoryIdempotency:
    def __init__(self) -> None:
        self.records: dict[
            tuple[int, object, str], tuple[object, CommandOutcome[object]]
        ] = {}
        self.command_calls = 0

    def execute(self, session: object, **kwargs: object) -> CommandOutcome[object]:
        del session
        key = (kwargs["actor_id"], kwargs["operation"], kwargs["idempotency_key"])
        identity = kwargs["request_identity"]
        existing = self.records.get(key)
        if existing is not None:
            if existing[0] != identity:
                raise ConflictError(code="IDEMPOTENCY_KEY_REUSED")
            return existing[1]
        self.command_calls += 1
        outcome = kwargs["command"]()
        self.records[key] = (identity, outcome)
        return outcome


class FakeInventory:
    def __init__(self, rows: dict[int, LockedStock], *, fail_decrease: bool = False):
        self.rows = rows
        self.fail_decrease = fail_decrease
        self.lock_calls = 0
        self.decrease_calls = 0
        self.lines = None

    def lock_for_mutation(self, session: object, *, product_ids: list[int]):
        del session
        self.lock_calls += 1
        return StockLockSet(
            {pid: self.rows[pid] for pid in product_ids if pid in self.rows}
        )

    def decrease_for_checkout(self, session: object, **kwargs: object):
        del session
        self.decrease_calls += 1
        self.lines = kwargs["lines"]
        if self.fail_decrease:
            raise RuntimeError("inventory failure")
        return []


class FakeOrderRepository:
    def __init__(self) -> None:
        self.calls = 0
        self.arguments: dict[str, object] = {}

    def create_completed(self, session: object, **kwargs: object):
        del session
        self.calls += 1
        self.arguments = kwargs
        return SimpleNamespace(id=91)


def stock(
    product_id: int = 1,
    *,
    price: int = 12_000,
    quantity: int = 10,
    status: str = "ACTIVE",
) -> LockedStock:
    return LockedStock(
        product_id=product_id,
        sku=f"SKU-{product_id}",
        name=f"Product {product_id}",
        status=status,
        sale_price_vnd=price,
        quantity=quantity,
        stock_version=3,
    )


def line(product_id: int = 1, quantity: int = 2, price: int = 12_000) -> CheckoutLine:
    return CheckoutLine(
        product_id=product_id,
        quantity=quantity,
        viewed_unit_price_vnd=price,
    )


def service(
    inventory: FakeInventory, idempotency: MemoryIdempotency, repo: FakeOrderRepository
):
    return CheckoutService(
        inventory,
        idempotency=idempotency,  # type: ignore[arg-type]
        repository=repo,  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 11, 12, 9, 30, tzinfo=UTC),
    )


def test_checkout_merges_duplicates_and_snapshots_locked_values() -> None:
    session = FakeSession()
    inventory = FakeInventory({1: stock()})
    idempotency = MemoryIdempotency()
    repo = FakeOrderRepository()

    result = service(inventory, idempotency, repo).checkout(
        session,  # type: ignore[arg-type]
        actor_id=7,
        idempotency_key="checkout-key-0001",
        items=[line(quantity=2), line(quantity=3)],
    )

    assert result.id == 91
    assert result.total_vnd == 60_000
    assert result.items[0].quantity == 5
    assert result.items[0].sku_snapshot == "SKU-1"
    assert repo.arguments["total_vnd"] == 60_000
    assert session.commits == 1
    assert session.rollbacks == 0
    assert inventory.decrease_calls == 1


def test_duplicate_product_with_different_viewed_price_is_rejected_before_claim() -> (
    None
):
    session = FakeSession()
    idempotency = MemoryIdempotency()
    checkout = service(FakeInventory({1: stock()}), idempotency, FakeOrderRepository())

    with pytest.raises(DomainValidationError):
        checkout.checkout(
            session,  # type: ignore[arg-type]
            actor_id=7,
            idempotency_key="checkout-key-0002",
            items=[line(price=12_000), line(price=13_000)],
        )

    assert idempotency.command_calls == 0
    assert session.commits == 0


@pytest.mark.parametrize(
    ("row", "code"),
    [
        (stock(status="INACTIVE"), "PRODUCT_INACTIVE"),
        (stock(price=13_000), "PRICE_CHANGED"),
        (stock(quantity=1), "INSUFFICIENT_STOCK"),
    ],
)
def test_refusal_is_committed_without_business_effect(
    row: LockedStock, code: str
) -> None:
    session = FakeSession()
    inventory = FakeInventory({1: row})
    repo = FakeOrderRepository()

    with pytest.raises(ConflictError) as exc_info:
        service(inventory, MemoryIdempotency(), repo).checkout(
            session,  # type: ignore[arg-type]
            actor_id=7,
            idempotency_key="checkout-key-0003",
            items=[line()],
        )

    assert exc_info.value.code == code
    assert repo.calls == 0
    assert inventory.decrease_calls == 0
    assert session.commits == 1
    assert session.rollbacks == 0


def test_same_key_same_payload_replays_without_second_business_command() -> None:
    session = FakeSession()
    inventory = FakeInventory({1: stock()})
    idempotency = MemoryIdempotency()
    repo = FakeOrderRepository()
    checkout = service(inventory, idempotency, repo)

    first = checkout.checkout(
        session,  # type: ignore[arg-type]
        actor_id=7,
        idempotency_key="checkout-key-0004",
        items=[line()],
    )
    second = checkout.checkout(
        session,  # type: ignore[arg-type]
        actor_id=7,
        idempotency_key="checkout-key-0004",
        items=[line()],
    )

    assert second == first
    assert idempotency.command_calls == 1
    assert repo.calls == 1
    assert inventory.lock_calls == 1
    assert inventory.decrease_calls == 1
    assert session.commits == 2


def test_same_key_different_payload_rolls_back_and_does_not_run_again() -> None:
    session = FakeSession()
    inventory = FakeInventory({1: stock()})
    idempotency = MemoryIdempotency()
    repo = FakeOrderRepository()
    checkout = service(inventory, idempotency, repo)
    checkout.checkout(
        session,  # type: ignore[arg-type]
        actor_id=7,
        idempotency_key="checkout-key-0005",
        items=[line(quantity=1)],
    )

    with pytest.raises(ConflictError) as exc_info:
        checkout.checkout(
            session,  # type: ignore[arg-type]
            actor_id=7,
            idempotency_key="checkout-key-0005",
            items=[line(quantity=2)],
        )

    assert exc_info.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert idempotency.command_calls == 1
    assert repo.calls == 1
    assert session.rollbacks == 1


def test_inventory_failure_after_order_insert_rolls_back_outer_transaction() -> None:
    session = FakeSession()
    inventory = FakeInventory({1: stock()}, fail_decrease=True)
    repo = FakeOrderRepository()

    with pytest.raises(RuntimeError, match="inventory failure"):
        service(inventory, MemoryIdempotency(), repo).checkout(
            session,  # type: ignore[arg-type]
            actor_id=7,
            idempotency_key="checkout-key-0006",
            items=[line()],
        )

    assert repo.calls == 1
    assert inventory.decrease_calls == 1
    assert session.commits == 0
    assert session.rollbacks == 1


def test_commit_failure_triggers_rollback_and_is_not_reported_as_success() -> None:
    session = FakeSession(fail_commit=True)
    inventory = FakeInventory({1: stock()})

    with pytest.raises(RuntimeError, match="commit failure"):
        service(inventory, MemoryIdempotency(), FakeOrderRepository()).checkout(
            session,  # type: ignore[arg-type]
            actor_id=7,
            idempotency_key="checkout-key-0007",
            items=[line()],
        )

    assert session.commits == 1
    assert session.rollbacks == 1
