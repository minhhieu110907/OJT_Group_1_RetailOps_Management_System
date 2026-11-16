"""Atomic checkout orchestration over CF-01 and the injected CF-02 port."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

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
from app.modules.sales.models import Order
from app.modules.sales.repository import OrderRepository
from app.modules.sales.schemas import (
    MAX_SQL_BIGINT,
    MAX_SQL_INT,
    CheckoutLine,
    OrderLineRead,
    OrderPage,
    OrderRead,
)

VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
try:
    VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:
    VN_TZ = VIETNAM_TIMEZONE


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


@dataclass(frozen=True)
class OrderQuery:
    """Query parameters for order history search and filtering."""

    page: int = 1
    page_size: int = 20
    status: str | None = None
    search: str | None = None
    from_date: date | None = None
    to_date: date | None = None


class OrderReadService:
    """Read-only order service enforcing active user access and business rules."""

    def __init__(self, repository: OrderRepository | None = None) -> None:
        self._repository = repository or OrderRepository()

    @staticmethod
    def _to_order_read(order: Order) -> OrderRead:
        sold_at = (
            order.sold_at.replace(tzinfo=UTC)
            if order.sold_at.tzinfo is None
            else order.sold_at.astimezone(UTC)
        )
        cancelled_at = (
            order.cancelled_at.replace(tzinfo=UTC)
            if order.cancelled_at and order.cancelled_at.tzinfo is None
            else (order.cancelled_at.astimezone(UTC) if order.cancelled_at else None)
        )
        items = tuple(
            OrderLineRead(
                product_id=item.product_id,
                sku_snapshot=item.sku_snapshot,
                product_name_snapshot=item.product_name_snapshot,
                quantity=item.quantity,
                unit_price_vnd=item.unit_price_vnd,
                line_total_vnd=item.line_total_vnd,
            )
            for item in order.items
        )
        return OrderRead(
            id=order.id,
            status=order.status,
            total_vnd=order.total_vnd,
            created_by=order.created_by,
            sold_at=sold_at,
            cancelled_by=order.cancelled_by,
            cancelled_at=cancelled_at,
            cancel_reason=order.cancel_reason,
            items=items,
        )

    def list(
        self,
        session: Session,
        *,
        actor_id: int,
        actor_role: str,
        filters: OrderQuery,
    ) -> OrderPage:
        """List orders with Vietnam business date range, status, and search filters."""
        if actor_role not in {"ADMIN", "STAFF"}:
            raise ForbiddenError()

        if (
            filters.from_date is not None
            and filters.to_date is not None
            and filters.from_date > filters.to_date
        ):
            raise DomainValidationError("from_date must not be greater than to_date")

        sold_from_utc: datetime | None = None
        if filters.from_date is not None:
            sold_from_utc = (
                datetime.combine(filters.from_date, time.min, tzinfo=VN_TZ)
                .astimezone(UTC)
                .replace(tzinfo=None)
            )

        sold_to_utc_exclusive: datetime | None = None
        if filters.to_date is not None:
            if filters.to_date >= date.max:
                raise DomainValidationError("Giá trị to_date vượt giới hạn cho phép.")
            try:
                sold_to_utc_exclusive = (
                    datetime.combine(
                        filters.to_date + timedelta(days=1), time.min, tzinfo=VN_TZ
                    )
                    .astimezone(UTC)
                    .replace(tzinfo=None)
                )
            except OverflowError as err:
                raise DomainValidationError(
                    "Khoảng ngày lọc vượt giới hạn cho phép."
                ) from err

        order_id_exact: int | None = None
        sku_search: str | None = None
        if filters.search is not None:
            cleaned = filters.search.strip()
            if cleaned:
                sku_search = cleaned
                if cleaned.isdigit():
                    val = int(cleaned)
                    if val <= MAX_SQL_BIGINT:
                        order_id_exact = val

        page = max(1, filters.page)
        page_size = max(1, min(100, filters.page_size))
        offset = (page - 1) * page_size

        orders, total = self._repository.list_orders(
            session,
            status=filters.status,
            sold_from_utc=sold_from_utc,
            sold_to_utc_exclusive=sold_to_utc_exclusive,
            order_id_exact=order_id_exact,
            sku_search=sku_search,
            offset=offset,
            limit=page_size,
        )

        return OrderPage(
            items=[self._to_order_read(order) for order in orders],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get(
        self,
        session: Session,
        *,
        actor_id: int,
        actor_role: str,
        order_id: int,
    ) -> OrderRead:
        """Fetch a single order by ID."""
        if actor_role not in {"ADMIN", "STAFF"}:
            raise ForbiddenError()

        order = self._repository.get_by_id(session, order_id)
        if order is None:
            raise ResourceNotFoundError("Không tìm thấy đơn hàng.")

        return self._to_order_read(order)
