from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.exceptions import ForbiddenError, InvalidStateError, ResourceNotFoundError
from app.modules.idempotency.service import CommandOutcome
from app.modules.sales.inventory_port import LockedStock, StockLockSet
from app.modules.sales.service import OrderService


class FakeSession:
    def __init__(self, *, fail_commit: bool = False, fail_flush: bool = False) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.fail_commit = fail_commit
        self.fail_flush = fail_flush

    def flush(self) -> None:
        self.flushes += 1
        if self.fail_flush:
            raise RuntimeError("flush failure")

    def commit(self) -> None:
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("commit failure")

    def rollback(self) -> None:
        self.rollbacks += 1


class MemoryIdempotency:
    def __init__(self) -> None:
        self.records: dict[tuple[int, str], tuple[object, CommandOutcome[object]]] = {}
        self.identities: list[object] = []

    def execute(self, session: object, **kwargs: object) -> CommandOutcome[object]:
        del session
        key = (kwargs["actor_id"], kwargs["idempotency_key"])
        identity = kwargs["request_identity"]
        self.identities.append(identity)
        if key in self.records:
            previous_identity, outcome = self.records[key]
            if previous_identity != identity:
                from app.core.exceptions import IdempotencyKeyReusedError

                raise IdempotencyKeyReusedError()
            return outcome
        outcome = kwargs["command"]()
        self.records[key] = (identity, outcome)
        return outcome


class FakeRepository:
    def __init__(self, order: SimpleNamespace | None) -> None:
        self.order = order
        self.lock_calls = 0

    def lock_by_id(self, session: object, order_id: int):
        del session, order_id
        self.lock_calls += 1
        return self.order

    def list_items(self, session: object, order_id: int):
        del session, order_id
        return [
            SimpleNamespace(
                product_id=3,
                sku_snapshot="SKU-3",
                product_name_snapshot="Product 3",
                quantity=2,
                unit_price_vnd=10_000,
                line_total_vnd=20_000,
            )
        ]


class FakeInventory:
    def __init__(self, *, fail_restore: bool = False) -> None:
        self.fail_restore = fail_restore
        self.restore_calls = 0

    def lock_for_mutation(self, session: object, *, product_ids: list[int]):
        del session
        return StockLockSet(
            {
                product_id: LockedStock(
                    product_id,
                    f"SKU-{product_id}",
                    f"Product {product_id}",
                    "ACTIVE",
                    10_000,
                    5,
                    1,
                )
                for product_id in product_ids
            }
        )

    def restore_for_cancel(self, session: object, **kwargs: object):
        del session, kwargs
        self.restore_calls += 1
        if self.fail_restore:
            raise RuntimeError("restore failure")
        return []


NOW = datetime(2026, 11, 14, 3, 15, tzinfo=UTC)  # 10:15 Vietnam


def order(
    *, sold_at: datetime | None = None, owner: int = 7, status: str = "COMPLETED"
):
    return SimpleNamespace(
        id=91,
        status=status,
        total_vnd=20_000,
        created_by=owner,
        sold_at=(sold_at or NOW.replace(tzinfo=None)),
        cancelled_by=None,
        cancelled_at=None,
        cancel_reason=None,
    )


def cancel_service(order_row, inventory=None, idempotency=None, clock=lambda: NOW):
    return OrderService(
        inventory or FakeInventory(),
        repository=FakeRepository(order_row),  # type: ignore[arg-type]
        idempotency=idempotency or MemoryIdempotency(),  # type: ignore[arg-type]
        clock=clock,
    )


@pytest.mark.parametrize(
    "elapsed", [timedelta(minutes=14, seconds=59), timedelta(minutes=15)]
)
def test_staff_can_cancel_at_or_before_exact_15_minute_boundary(elapsed) -> None:
    row = order(sold_at=(NOW - elapsed).replace(tzinfo=None))
    result = cancel_service(row).cancel(
        FakeSession(),  # type: ignore[arg-type]
        actor_id=7,
        actor_role="STAFF",
        order_id=91,
        reason="  Customer mistake  ",
        idempotency_key="cancel-order-key-0001",
    )
    assert result.status == "CANCELLED"
    assert result.cancel_reason == "Customer mistake"


def test_staff_after_15_minutes_or_not_owner_is_forbidden() -> None:
    for row in (
        order(
            sold_at=(NOW - timedelta(minutes=15, microseconds=1)).replace(tzinfo=None)
        ),
        order(owner=8),
    ):
        with pytest.raises(ForbiddenError):
            cancel_service(row).cancel(
                FakeSession(),  # type: ignore[arg-type]
                actor_id=7,
                actor_role="STAFF",
                order_id=91,
                reason="Reason",
                idempotency_key="cancel-order-key-0002",
            )


def test_admin_after_15_minutes_same_day_is_allowed_but_next_day_is_forbidden() -> None:
    same_day = order(sold_at=datetime(2026, 11, 13, 17, 1))  # 00:01 Vietnam
    result = cancel_service(
        same_day, clock=lambda: datetime(2026, 11, 14, 16, 59, tzinfo=UTC)
    ).cancel(
        FakeSession(),  # type: ignore[arg-type]
        actor_id=1,
        actor_role="ADMIN",
        order_id=91,
        reason="Admin cancellation",
        idempotency_key="cancel-order-key-0003",
    )
    assert result.status == "CANCELLED"

    next_day = order(sold_at=datetime(2026, 11, 14, 16, 59))  # 23:59 Vietnam
    with pytest.raises(ForbiddenError):
        cancel_service(
            next_day, clock=lambda: datetime(2026, 11, 14, 17, 0, tzinfo=UTC)
        ).cancel(
            FakeSession(),  # type: ignore[arg-type]
            actor_id=1,
            actor_role="ADMIN",
            order_id=91,
            reason="Too late",
            idempotency_key="cancel-order-key-0004",
        )


def test_replay_uses_exact_identity_and_does_not_restore_twice() -> None:
    row = order()
    inventory = FakeInventory()
    idempotency = MemoryIdempotency()
    service = cancel_service(row, inventory, idempotency)
    session = FakeSession()
    first = service.cancel(
        session,  # type: ignore[arg-type]
        actor_id=7,
        actor_role="STAFF",
        order_id=91,
        reason="  Duplicate sale  ",
        idempotency_key="cancel-order-key-0005",
    )
    second = service.cancel(
        session,  # type: ignore[arg-type]
        actor_id=7,
        actor_role="STAFF",
        order_id=91,
        reason="Duplicate sale",
        idempotency_key="cancel-order-key-0005",
    )
    assert second == first
    assert inventory.restore_calls == 1
    assert idempotency.identities[0] == {
        "operation": "CANCEL_ORDER",
        "resource_id": 91,
        "body": {"reason": "Duplicate sale"},
    }


def test_cancelled_order_and_restore_failure_roll_back() -> None:
    with pytest.raises(InvalidStateError):
        cancel_service(order(status="CANCELLED")).cancel(
            FakeSession(),  # type: ignore[arg-type]
            actor_id=7,
            actor_role="STAFF",
            order_id=91,
            reason="Reason",
            idempotency_key="cancel-order-key-0006",
        )

    session = FakeSession()
    with pytest.raises(RuntimeError, match="restore failure"):
        cancel_service(order(), FakeInventory(fail_restore=True)).cancel(
            session,  # type: ignore[arg-type]
            actor_id=7,
            actor_role="STAFF",
            order_id=91,
            reason="Reason",
            idempotency_key="cancel-order-key-0007",
        )
    assert session.commits == 0
    assert session.rollbacks == 1


def test_not_found_flush_and_commit_failures_are_safe() -> None:
    with pytest.raises(ResourceNotFoundError):
        cancel_service(None).cancel(
            FakeSession(),  # type: ignore[arg-type]
            actor_id=7,
            actor_role="STAFF",
            order_id=404,
            reason="Reason",
            idempotency_key="cancel-order-key-0008",
        )

    for session, message in (
        (FakeSession(fail_flush=True), "flush failure"),
        (FakeSession(fail_commit=True), "commit failure"),
    ):
        with pytest.raises(RuntimeError, match=message):
            cancel_service(order()).cancel(
                session,  # type: ignore[arg-type]
                actor_id=7,
                actor_role="STAFF",
                order_id=91,
                reason="Reason",
                idempotency_key=f"cancel-{message.replace(' ', '-')}-0001",
            )
        assert session.rollbacks == 1
