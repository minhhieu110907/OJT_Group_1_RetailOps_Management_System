"""Secure, bounded dispatch for the RetailOps read-only AI tools."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.exceptions import (
    DependencyUnavailableError,
    DomainValidationError,
    ForbiddenError,
)
from app.modules.analytics.service import (
    ProductAnalyticsService,
    SalesAnalyticsService,
    resolve_days_period,
    resolve_sales_period,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.inventory.schemas import DEFAULT_LOW_STOCK_THRESHOLD
from app.modules.inventory.service import InventoryQueryService

logger = logging.getLogger(__name__)
ToolId = Literal[
    "get_sales_summary", "get_top_products", "get_slow_products", "get_low_stock"
]
_TOOLS = frozenset(
    ("get_sales_summary", "get_top_products", "get_slow_products", "get_low_stock")
)
_MAX_CALLS = 3
_MAX_OUTPUT_BYTES = 32 * 1024
_DEADLINE_SECONDS = 15.0


@dataclass(frozen=True)
class ToolContext:
    actor_id: int
    actor_role: str
    request_id: str


@dataclass(frozen=True)
class ToolResult:
    tool_id: ToolId
    data: Mapping[str, Any]
    source_period: str | None


@dataclass
class ToolBudget:
    """Request-owned mutable budget; pass the same instance for every call."""

    started_at: float = 0.0
    calls: int = 0
    output_bytes: int = 0

    def __post_init__(self) -> None:
        if self.started_at == 0.0:
            self.started_at = time.monotonic()

    def reserve(self) -> None:
        if (
            self.calls >= _MAX_CALLS
            or time.monotonic() - self.started_at >= _DEADLINE_SECONDS
        ):
            raise DomainValidationError("AI tool request budget exceeded.")
        self.calls += 1

    def add_output(self, payload: bytes) -> None:
        if self.output_bytes + len(payload) > _MAX_OUTPUT_BYTES:
            raise DomainValidationError("AI tool output budget exceeded.")
        self.output_bytes += len(payload)

    def check_deadline(self) -> None:
        if time.monotonic() - self.started_at >= _DEADLINE_SECONDS:
            raise DomainValidationError("AI tool request deadline exceeded.")


class AIToolExecutor:
    """Typed allowlist dispatcher; the model never receives the database session."""

    def __init__(
        self,
        sales_service: SalesAnalyticsService | None = None,
        product_service: ProductAnalyticsService | None = None,
        inventory_service: InventoryQueryService | None = None,
        budget: ToolBudget | None = None,
        clock: callable | None = None,
        context_verifier: Callable[[ToolContext], bool] | None = None,
    ) -> None:
        self._sales = sales_service or SalesAnalyticsService()
        self._products = product_service or ProductAnalyticsService()
        self._inventory = inventory_service or InventoryQueryService()
        self._budget = budget or ToolBudget()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._context_verifier = context_verifier

    def execute(
        self,
        session: Session,
        *,
        tool_id: ToolId,
        arguments: Mapping[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        started = time.monotonic()
        status = "error"
        output_bytes = 0
        try:
            if self._context_verifier is None or not self._context_verifier(context):
                raise ForbiddenError()
            self._authenticate_admin(session, context)
            if tool_id not in _TOOLS:
                raise DomainValidationError("Unknown AI tool.")
            if not isinstance(arguments, Mapping):
                raise DomainValidationError("Tool arguments must be an object.")
            self._budget.reserve()
            self._budget.check_deadline()
            result = self._dispatch(session, tool_id, arguments)
            self._budget.check_deadline()
            payload = json.dumps(
                {
                    "tool_id": result.tool_id,
                    "data": result.data,
                    "source_period": result.source_period,
                },
                default=self._json_default,
                separators=(",", ":"),
            ).encode()
            self._budget.add_output(payload)
            output_bytes = len(payload)
            status = "success"
            return result
        except (DomainValidationError, ForbiddenError, DependencyUnavailableError):
            raise
        except Exception as error:
            raise DependencyUnavailableError() from error
        finally:
            logger.info(
                "ai_tool_execution",
                extra={
                    "request_id": context.request_id,
                    "actor_id": context.actor_id,
                    "tool_id": tool_id,
                    "status": status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "output_bytes": output_bytes,
                },
            )

    @staticmethod
    def _authenticate_admin(session: Session, context: ToolContext) -> None:
        user = session.get(User, context.actor_id)
        if (
            user is None
            or user.status != UserStatus.ACTIVE
            or user.role != UserRole.ADMIN
        ):
            raise ForbiddenError()

    def _dispatch(
        self, session: Session, tool_id: ToolId, args: Mapping[str, Any]
    ) -> ToolResult:
        if tool_id == "get_sales_summary":
            self._check_keys(args, {"start_date", "end_date"})
            start = self._date(args.get("start_date"), "start_date")
            end = self._date(args.get("end_date"), "end_date")
            today = self._clock().date()
            if start is not None and end is not None and (end - start).days > 89:
                raise DomainValidationError("Date range must not exceed 90 days.")
            if end and end > today or start and start > today:
                raise DomainValidationError("Future dates are not allowed.")
            period = resolve_sales_period(
                from_date=start, to_date=end, now_fn=self._clock
            )
            value = self._sales.summary(session, period=period)
            data = {
                k: getattr(value, k)
                for k in (
                    "period_start",
                    "period_end_exclusive",
                    "revenue_vnd",
                    "completed_orders",
                    "cancelled_orders",
                    "aov_vnd",
                )
            }
            return ToolResult(
                tool_id,
                data,
                f"{period.start_utc.isoformat()}/{period.end_utc_exclusive.isoformat()}",
            )
        if tool_id == "get_top_products":
            self._check_keys(args, {"days", "limit"})
            days, limit = (
                self._bounded_int(args.get("days", 7), "days", 1, 90),
                self._bounded_int(args.get("limit", 5), "limit", 1, 20),
            )
            page = self._products.top(
                session,
                period=resolve_days_period(days, now_fn=self._clock),
                page=1,
                page_size=limit,
            )
            return ToolResult(
                tool_id,
                {"items": [self._item(i) for i in page.items], "total": page.total},
                f"last_{days}_days",
            )
        if tool_id == "get_slow_products":
            self._check_keys(args, {"limit"})
            limit = self._bounded_int(args.get("limit", 10), "limit", 1, 20)
            page = self._products.slow(
                session, as_of_utc=self._clock(), page=1, page_size=limit
            )
            return ToolResult(
                tool_id,
                {"items": [self._item(i) for i in page.items], "total": page.total},
                "trailing_30_days; stocked_more_than_7_days",
            )
        self._check_keys(args, {"limit"})
        limit = self._bounded_int(args.get("limit", 10), "limit", 1, 20)
        page = self._inventory.get_low_stock(
            session=session,
            page=1,
            page_size=limit,
            threshold=DEFAULT_LOW_STOCK_THRESHOLD,
        )
        return ToolResult(
            tool_id,
            {"items": [self._safe_low(i) for i in page.items], "total": page.total},
            "current_stock",
        )

    @staticmethod
    def _check_keys(args: Mapping[str, Any], allowed: set[str]) -> None:
        if any(key not in allowed for key in args):
            raise DomainValidationError("Unexpected tool argument.")

    @staticmethod
    def _bounded_int(value: Any, name: str, low: int, high: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not low <= value <= high
        ):
            raise DomainValidationError(f"Invalid {name}.")
        return value

    @staticmethod
    def _date(value: Any, name: str) -> date | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise DomainValidationError(f"Invalid {name}.")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise DomainValidationError(f"Invalid {name}.") from error

    @staticmethod
    def _item(item: Any) -> dict[str, Any]:
        return {
            k: getattr(item, k)
            for k in (
                "product_id",
                "sku",
                "name",
                "sold_units",
                "revenue_vnd",
                "quantity",
                "first_stocked_at",
            )
            if getattr(item, k, None) is not None
        }

    @staticmethod
    def _safe_low(item: Any) -> dict[str, Any]:
        return {
            k: getattr(item, k)
            for k in ("product_id", "sku", "name", "quantity", "threshold")
        }

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        raise TypeError
