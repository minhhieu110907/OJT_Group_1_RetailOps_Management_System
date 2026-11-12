"""Atomic checkout orchestration over CF-01 and the injected CF-02 port."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    ResourceNotFoundError,
)
from app.modules.idempotency.service import (
    CommandOutcome,
    IdempotencyExecutor,
    IdempotencyOperation,
)
from app.modules.sales.inventory_port import (
    InventoryServicePort,
    StockLine,
    StockLockSet,
)
from app.modules.sales.repository import OrderRepository
from app.modules.sales.schemas import (
    MAX_SQL_BIGINT,
    MAX_SQL_INT,
    CheckoutLine,
    OrderRead,
)


class CheckoutService:
    def __init__(
        self,
        inventory: InventoryServicePort,
        *,
        idempotency: IdempotencyExecutor | None = None,
        repository: OrderRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._inventory = inventory
        self._idempotency = idempotency or IdempotencyExecutor()
        self._repository = repository or OrderRepository()
        self._clock = clock or (lambda: datetime.now(UTC))

    def checkout(
        self,
        session: Session,
        *,
        actor_id: int,
        idempotency_key: str,
        items: Sequence[CheckoutLine],
    ) -> OrderRead:
        normalized = self._normalize(items)
        identity_body = {"items": [item.model_dump(mode="json") for item in normalized]}
        try:
            outcome = self._idempotency.execute(
                session,
                actor_id=actor_id,
                operation=IdempotencyOperation.CHECKOUT,
                idempotency_key=idempotency_key,
                request_identity={"operation": "CHECKOUT", "body": identity_body},
                command=lambda: self._checkout_command(session, actor_id, normalized),
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        if outcome.status_code == 201:
            return OrderRead.model_validate(outcome.body)
        body = outcome.body
        if not isinstance(body, dict):
            raise RuntimeError("Checkout refusal outcome is not an object")
        raise ConflictError(
            code=str(body.get("code", "ORDER_CONFLICT")),
            message=str(body.get("message", "KhÃ´ng thá»ƒ hoÃ n táº¥t checkout.")),
            details=body.get("details"),
        )

    def _normalize(self, items: Sequence[CheckoutLine]) -> list[CheckoutLine]:
        if not items:
            raise DomainValidationError(
                "Danh sÃ¡ch sáº£n pháº©m khÃ´ng Ä‘Æ°á»£c rá»—ng."
            )
        prices: dict[int, int] = {}
        quantities: dict[int, int] = {}
        for item in items:
            previous_price = prices.get(item.product_id)
            if (
                previous_price is not None
                and previous_price != item.viewed_unit_price_vnd
            ):
                raise DomainValidationError(
                    "CÃ¡c dÃ²ng trÃ¹ng sáº£n pháº©m pháº£i cÃ³ cÃ¹ng giÃ¡ Ä‘Ã£ xem.",
                    details={"product_id": item.product_id},
                )
            prices[item.product_id] = item.viewed_unit_price_vnd
            quantity = quantities.get(item.product_id, 0) + item.quantity
            if quantity > MAX_SQL_INT:
                raise DomainValidationError(
                    "Tá»•ng sá»‘ lÆ°á»£ng vÆ°á»£t giá»›i háº¡n SQL INT."
                )
            quantities[item.product_id] = quantity
        return [
            CheckoutLine(
                product_id=product_id,
                quantity=quantities[product_id],
                viewed_unit_price_vnd=prices[product_id],
            )
            for product_id in sorted(quantities)
        ]

    def _checkout_command(
        self, session: Session, actor_id: int, items: Sequence[CheckoutLine]
    ) -> CommandOutcome[dict[str, object]]:
        product_ids = [item.product_id for item in items]
        locks = self._inventory.lock_for_mutation(session, product_ids=product_ids)
        self._require_complete_locks(locks, product_ids)

        inactive = [pid for pid in product_ids if locks.rows[pid].status != "ACTIVE"]
        if inactive:
            return self._refusal(
                "PRODUCT_INACTIVE",
                "Sáº£n pháº©m khÃ´ng cÃ²n hoáº¡t Ä‘á»™ng.",
                {"product_ids": inactive},
            )

        changed = [
            {
                "product_id": item.product_id,
                "viewed_unit_price_vnd": item.viewed_unit_price_vnd,
                "current_unit_price_vnd": locks.rows[item.product_id].sale_price_vnd,
            }
            for item in items
            if item.viewed_unit_price_vnd != locks.rows[item.product_id].sale_price_vnd
        ]
        if changed:
            return self._refusal(
                "PRICE_CHANGED",
                "GiÃ¡ bÃ¡n Ä‘Ã£ thay Ä‘á»•i. Vui lÃ²ng xÃ¡c nháº­n láº¡i.",
                {"changed_items": changed},
            )

        insufficient = [
            {
                "product_id": item.product_id,
                "available_quantity": locks.rows[item.product_id].quantity,
            }
            for item in items
            if locks.rows[item.product_id].quantity < item.quantity
        ]
        if insufficient:
            return self._refusal(
                "INSUFFICIENT_STOCK", "KhÃ´ng Ä‘á»§ tá»“n kho.", {"items": insufficient}
            )

        snapshots: list[dict[str, object]] = []
        total = 0
        for item in items:
            locked = locks.rows[item.product_id]
            line_total = item.quantity * locked.sale_price_vnd
            if line_total > MAX_SQL_BIGINT or total > MAX_SQL_BIGINT - line_total:
                raise DomainValidationError(
                    "Tá»•ng tiá»n vÆ°á»£t giá»›i háº¡n SQL BIGINT."
                )
            total += line_total
            snapshots.append(
                {
                    "product_id": item.product_id,
                    "sku_snapshot": locked.sku,
                    "product_name_snapshot": locked.name,
                    "quantity": item.quantity,
                    "unit_price_vnd": locked.sale_price_vnd,
                    "line_total_vnd": line_total,
                }
            )

        sold_at_aware = self._clock()
        if sold_at_aware.tzinfo is None:
            sold_at_aware = sold_at_aware.replace(tzinfo=UTC)
        sold_at = sold_at_aware.astimezone(UTC).replace(tzinfo=None)
        order = self._repository.create_completed(
            session,
            actor_id=actor_id,
            sold_at=sold_at,
            total_vnd=total,
            items=snapshots,
        )
        self._inventory.decrease_for_checkout(
            session,
            locks=locks,
            order_id=order.id,
            actor_id=actor_id,
            lines=[StockLine(item.product_id, item.quantity) for item in items],
        )
        body = {
            "id": order.id,
            "status": "COMPLETED",
            "total_vnd": total,
            "created_by": actor_id,
            "sold_at": sold_at_aware.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "cancelled_by": None,
            "cancelled_at": None,
            "cancel_reason": None,
            "items": snapshots,
        }
        serialized = OrderRead.model_validate(body).model_dump(mode="json")
        return CommandOutcome(201, serialized)

    @staticmethod
    def _require_complete_locks(
        locks: StockLockSet, product_ids: Sequence[int]
    ) -> None:
        missing = [
            product_id for product_id in product_ids if product_id not in locks.rows
        ]
        if missing:
            raise ResourceNotFoundError(
                "KhÃ´ng tÃ¬m tháº¥y sáº£n pháº©m.", {"product_ids": missing}
            )

    @staticmethod
    def _refusal(
        code: str, message: str, details: object
    ) -> CommandOutcome[dict[str, object]]:
        return CommandOutcome(
            409, {"code": code, "message": message, "details": details}
        )
