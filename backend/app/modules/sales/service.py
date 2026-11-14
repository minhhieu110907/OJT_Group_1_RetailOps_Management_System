"""Atomic checkout orchestration over CF-01 and the injected CF-02 port."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    ForbiddenError,
    InvalidStateError,
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

VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


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
            message=str(body.get("message", "Không thể hoàn tất checkout.")),
            details=body.get("details"),
        )

    def _normalize(self, items: Sequence[CheckoutLine]) -> list[CheckoutLine]:
        if not items:
            raise DomainValidationError("Danh sách sản phẩm không được rỗng.")
        prices: dict[int, int] = {}
        quantities: dict[int, int] = {}
        for item in items:
            previous_price = prices.get(item.product_id)
            if (
                previous_price is not None
                and previous_price != item.viewed_unit_price_vnd
            ):
                raise DomainValidationError(
                    "Các dòng trùng sản phẩm phải có cùng giá đã xem.",
                    details={"product_id": item.product_id},
                )
            prices[item.product_id] = item.viewed_unit_price_vnd
            quantity = quantities.get(item.product_id, 0) + item.quantity
            if quantity > MAX_SQL_INT:
                raise DomainValidationError("Tổng số lượng vượt giới hạn SQL INT.")
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
                "Sản phẩm không còn hoạt động.",
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
                "Giá bán đã thay đổi. Vui lòng xác nhận lại.",
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
                "INSUFFICIENT_STOCK", "Không đủ tồn kho.", {"items": insufficient}
            )

        snapshots: list[dict[str, object]] = []
        total = 0
        for item in items:
            locked = locks.rows[item.product_id]
            line_total = item.quantity * locked.sale_price_vnd
            if line_total > MAX_SQL_BIGINT or total > MAX_SQL_BIGINT - line_total:
                raise DomainValidationError("Tổng tiền vượt giới hạn SQL BIGINT.")
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
                "Không tìm thấy sản phẩm.", {"product_ids": missing}
            )

    @staticmethod
    def _refusal(
        code: str, message: str, details: object
    ) -> CommandOutcome[dict[str, object]]:
        return CommandOutcome(
            409, {"code": code, "message": message, "details": details}
        )


class OrderService:
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

    def cancel(
        self,
        session: Session,
        *,
        actor_id: int,
        actor_role: str,
        order_id: int,
        reason: str,
        idempotency_key: str,
    ) -> OrderRead:
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 500:
            raise DomainValidationError("Lý do hủy đơn không hợp lệ.")
        if actor_role not in {"ADMIN", "STAFF"}:
            raise ForbiddenError()
        identity = {
            "operation": "CANCEL_ORDER",
            "resource_id": order_id,
            "body": {"reason": normalized_reason},
        }
        try:
            outcome = self._idempotency.execute(
                session,
                actor_id=actor_id,
                operation=IdempotencyOperation.CANCEL_ORDER,
                idempotency_key=idempotency_key,
                request_identity=identity,
                command=lambda: self._cancel_command(
                    session,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    order_id=order_id,
                    reason=normalized_reason,
                ),
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        return OrderRead.model_validate(outcome.body)

    def _cancel_command(
        self,
        session: Session,
        *,
        actor_id: int,
        actor_role: str,
        order_id: int,
        reason: str,
    ) -> CommandOutcome[dict[str, object]]:
        order = self._repository.lock_by_id(session, order_id)
        if order is None:
            raise ResourceNotFoundError("Không tìm thấy đơn hàng.")
        if order.status != "COMPLETED":
            raise InvalidStateError("Đơn hàng không còn ở trạng thái COMPLETED.")

        now_aware = self._clock()
        if now_aware.tzinfo is None:
            now_aware = now_aware.replace(tzinfo=UTC)
        now_utc = now_aware.astimezone(UTC)
        sold_at_utc = order.sold_at.replace(tzinfo=UTC)
        if (
            now_utc.astimezone(VIETNAM_TIMEZONE).date()
            != sold_at_utc.astimezone(VIETNAM_TIMEZONE).date()
        ):
            raise ForbiddenError("Chỉ được hủy đơn trong cùng ngày kinh doanh.")
        if actor_role == "STAFF":
            if order.created_by != actor_id:
                raise ForbiddenError("Staff chỉ được hủy đơn do chính mình tạo.")
            if now_utc > sold_at_utc + timedelta(minutes=15):
                raise ForbiddenError("Đã quá thời hạn 15 phút để hủy đơn.")

        items = self._repository.list_items(session, order_id)
        product_ids = [item.product_id for item in items]
        locks = self._inventory.lock_for_mutation(
            session, product_ids=sorted(product_ids)
        )
        CheckoutService._require_complete_locks(locks, product_ids)

        cancelled_at = now_utc.replace(tzinfo=None)
        order.status = "CANCELLED"
        order.cancelled_by = actor_id
        order.cancelled_at = cancelled_at
        order.cancel_reason = reason
        session.flush()
        self._inventory.restore_for_cancel(
            session,
            locks=locks,
            order_id=order.id,
            actor_id=actor_id,
            lines=[StockLine(item.product_id, item.quantity) for item in items],
        )
        body = {
            "id": order.id,
            "status": "CANCELLED",
            "total_vnd": order.total_vnd,
            "created_by": order.created_by,
            "sold_at": sold_at_utc.isoformat().replace("+00:00", "Z"),
            "cancelled_by": actor_id,
            "cancelled_at": now_utc.isoformat().replace("+00:00", "Z"),
            "cancel_reason": reason,
            "items": [
                {
                    "product_id": item.product_id,
                    "sku_snapshot": item.sku_snapshot,
                    "product_name_snapshot": item.product_name_snapshot,
                    "quantity": item.quantity,
                    "unit_price_vnd": item.unit_price_vnd,
                    "line_total_vnd": item.line_total_vnd,
                }
                for item in items
            ],
        }
        serialized = OrderRead.model_validate(body).model_dump(mode="json")
        return CommandOutcome(200, serialized)
