"""Secure, bounded dispatch for the RetailOps read-only AI tools."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from threading import RLock
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError
from sqlalchemy.orm import Session

from app.core.config import (
    AI_MAX_TOOL_CALLS,
    AI_MAX_TOOL_OUTPUT_BYTES,
    AI_REQUEST_DEADLINE_SECONDS,
    Settings,
)
from app.core.exceptions import (
    AppException,
    DependencyUnavailableError,
    DomainValidationError,
    ForbiddenError,
    RateLimitedError,
)
from app.modules.analytics.service import (
    ProductAnalyticsService,
    SalesAnalyticsService,
    resolve_days_period,
    resolve_sales_period,
)
from app.modules.auth.dependencies import CurrentPrincipal
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
_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_CANONICAL_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


class _StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _SalesData(_StrictDTO):
    period_start: StrictStr
    period_end_exclusive: StrictStr
    revenue_vnd: StrictInt = Field(ge=0)
    completed_orders: StrictInt = Field(ge=0)
    cancelled_orders: StrictInt = Field(ge=0)
    aov_vnd: StrictInt = Field(ge=0)


class _ProductItem(_StrictDTO):
    product_id: StrictInt = Field(ge=1)
    sku: StrictStr
    name: StrictStr
    sold_units: StrictInt = Field(ge=0)
    revenue_vnd: StrictInt = Field(ge=0)
    quantity: StrictInt | None = Field(default=None, ge=0)
    first_stocked_at: StrictStr | None = None


class _LowStockItem(_StrictDTO):
    product_id: StrictInt = Field(ge=1)
    sku: StrictStr
    name: StrictStr
    quantity: StrictInt = Field(ge=0)
    threshold: StrictInt = Field(ge=0)


class _ProductPage(_StrictDTO):
    items: list[_ProductItem] = Field(max_length=20)
    total: StrictInt = Field(ge=0)


class _LowStockPage(_StrictDTO):
    items: list[_LowStockItem] = Field(max_length=20)
    total: StrictInt = Field(ge=0)


@dataclass(frozen=True)
class ToolContext:
    actor_id: int
    actor_role: str
    request_id: str


@dataclass(frozen=True)
class BoundToolRequest:
    """One authenticated request's opaque context, executor, and shared budget."""

    context: ToolContext
    executor: AIToolExecutor
    budget: ToolBudget


def bind_authenticated_request(
    principal: CurrentPrincipal,
    *,
    request_id: str,
    sales_service: SalesAnalyticsService | None = None,
    product_service: ProductAnalyticsService | None = None,
    inventory_service: InventoryQueryService | None = None,
    clock: Callable[[], datetime] | None = None,
    settings: Settings | None = None,
) -> BoundToolRequest:
    """Call only after the live auth dependency; never pass a body/model principal.

    Create once at orchestration start, then reuse context and executor for all calls.
    The context object identity is a per-request capability, not a comparable tuple.
    """
    if not isinstance(principal, CurrentPrincipal):
        raise ForbiddenError()
    user = principal.user
    context = ToolContext(user.id, str(user.role), request_id)
    budget = ToolBudget(
        max_calls=settings.ai_max_tool_calls if settings else AI_MAX_TOOL_CALLS,
        max_output_bytes=(
            settings.ai_max_tool_output_bytes if settings else AI_MAX_TOOL_OUTPUT_BYTES
        ),
        deadline_seconds=(
            settings.ai_request_deadline_seconds
            if settings
            else AI_REQUEST_DEADLINE_SECONDS
        ),
    )
    executor = AIToolExecutor(
        sales_service=sales_service,
        product_service=product_service,
        inventory_service=inventory_service,
        budget=budget,
        clock=clock,
        context_verifier=lambda supplied: (
            supplied is context
            and principal.user.id == context.actor_id
            and str(principal.user.role) == context.actor_role
        ),
    )
    return BoundToolRequest(context, executor, budget)


@dataclass(frozen=True)
class ToolResult:
    tool_id: ToolId
    data: Mapping[str, Any]
    source_period: str | None


def serialize_tool_result(result: ToolResult) -> bytes:
    """Use these exact UTF-8 bytes when handing a result to the LLM provider."""
    return json.dumps(
        {
            "tool_id": result.tool_id,
            "data": result.data,
            "source_period": result.source_period,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass
class ToolBudget:
    """Request-owned mutable budget; pass the same instance for every call."""

    started_at: float = 0.0
    calls: int = 0
    output_bytes: int = 0
    max_calls: int = AI_MAX_TOOL_CALLS
    max_output_bytes: int = AI_MAX_TOOL_OUTPUT_BYTES
    deadline_seconds: float = AI_REQUEST_DEADLINE_SECONDS
    lock: RLock = field(default_factory=RLock, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.started_at == 0.0:
            self.started_at = time.monotonic()

    def reserve(self) -> None:
        if (
            self.calls >= self.max_calls
            or time.monotonic() - self.started_at >= self.deadline_seconds
        ):
            if self.calls >= self.max_calls:
                raise RateLimitedError(60)
            raise DependencyUnavailableError()
        self.calls += 1

    def add_output(self, payload: bytes) -> None:
        if self.output_bytes + len(payload) > self.max_output_bytes:
            raise RateLimitedError(60)
        self.output_bytes += len(payload)

    def check_deadline(self) -> None:
        if time.monotonic() - self.started_at >= self.deadline_seconds:
            raise DependencyUnavailableError()


class AIToolExecutor:
    """Typed allowlist dispatcher; the model never receives the database session."""

    def __init__(
        self,
        sales_service: SalesAnalyticsService | None = None,
        product_service: ProductAnalyticsService | None = None,
        inventory_service: InventoryQueryService | None = None,
        budget: ToolBudget | None = None,
        clock: Callable[[], datetime] | None = None,
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
        verified = False
        error_code = None
        try:
            with self._budget.lock:
                if self._context_verifier is None or not self._context_verifier(
                    context
                ):
                    raise ForbiddenError()
                verified = True
                self._budget.check_deadline()
                self._authenticate_admin(session, context)
                self._budget.check_deadline()
                self._budget.reserve()  # invalid model calls consume quota too
                if not isinstance(tool_id, str) or tool_id not in _TOOLS:
                    raise DomainValidationError("Unknown AI tool.")
                if not isinstance(arguments, Mapping):
                    raise DomainValidationError("Tool arguments must be an object.")
                result = self._dispatch(session, tool_id, arguments)
                self._budget.check_deadline()
                payload = serialize_tool_result(result)
                self._budget.check_deadline()
                self._budget.add_output(payload)
                output_bytes = len(payload)
                status = "success"
                return result
        except AppException as error:
            error_code = error.code
            raise
        except Exception as error:
            error_code = "DEPENDENCY_UNAVAILABLE"
            raise DependencyUnavailableError() from error
        finally:
            logger.info(
                "ai_tool_execution",
                extra={
                    "request_id": context.request_id if verified else "invalid",
                    "actor_id": context.actor_id if verified else None,
                    "tool_id": tool_id
                    if isinstance(tool_id, str) and tool_id in _TOOLS
                    else "unknown",
                    "status": status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "output_bytes": output_bytes,
                    "error_code": error_code,
                },
            )

    @staticmethod
    def _authenticate_admin(session: Session, context: ToolContext) -> None:
        user = session.get(User, context.actor_id, populate_existing=True)
        if (
            user is None
            or user.status != UserStatus.ACTIVE
            or user.role != UserRole.ADMIN
            or context.actor_role != UserRole.ADMIN
        ):
            raise ForbiddenError()

    def _dispatch(
        self, session: Session, tool_id: ToolId, args: Mapping[str, Any]
    ) -> ToolResult:
        if tool_id == "get_sales_summary":
            self._check_keys(args, {"start_date", "end_date"})
            start = (
                self._date(args["start_date"], "start_date")
                if "start_date" in args
                else None
            )
            end = (
                self._date(args["end_date"], "end_date") if "end_date" in args else None
            )
            today = self._clock().astimezone(_VN_TZ).date()
            end = end or today
            start = start or end
            inclusive_days = (end - start).days + 1
            if not 1 <= inclusive_days <= 90 or end > today:
                raise DomainValidationError("Invalid sales date range.")
            period = resolve_sales_period(
                from_date=start, to_date=end, now_fn=self._clock
            )
            value = self._sales.summary(session, period=period)
            data = {
                k: self._utc(getattr(value, k))
                if k.startswith("period_")
                else getattr(value, k)
                for k in (
                    "period_start",
                    "period_end_exclusive",
                    "revenue_vnd",
                    "completed_orders",
                    "cancelled_orders",
                    "aov_vnd",
                )
            }
            return self._validated_result(
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
            period = resolve_days_period(days, now_fn=self._clock)
            page = self._products.top(
                session,
                period=period,
                page=1,
                page_size=limit,
            )
            self._check_page(page, limit)
            return self._validated_result(
                tool_id,
                {"items": [self._item(i) for i in page.items], "total": page.total},
                f"{period.start_utc.isoformat()}/{period.end_utc_exclusive.isoformat()}",
            )
        if tool_id == "get_slow_products":
            self._check_keys(args, {"limit"})
            limit = self._bounded_int(args.get("limit", 10), "limit", 1, 20)
            as_of = self._clock()
            page = self._products.slow(
                session, as_of_utc=as_of, page=1, page_size=limit
            )
            self._check_page(page, limit)
            return self._validated_result(
                tool_id,
                {"items": [self._item(i) for i in page.items], "total": page.total},
                f"as_of={self._utc(as_of)}; trailing_30_days; stocked_more_than_7_days",
            )
        self._check_keys(args, {"limit"})
        limit = self._bounded_int(args.get("limit", 10), "limit", 1, 20)
        page = self._inventory.get_low_stock(
            session=session,
            page=1,
            page_size=limit,
            threshold=DEFAULT_LOW_STOCK_THRESHOLD,
        )
        self._check_page(page, limit)
        return self._validated_result(
            tool_id,
            {"items": [self._safe_low(i) for i in page.items], "total": page.total},
            "current_stock",
        )

    @staticmethod
    def _check_keys(args: Mapping[str, Any], allowed: set[str]) -> None:
        if any(key not in allowed for key in args):
            raise DomainValidationError("Unexpected tool argument.")

    @staticmethod
    def _check_page(page: Any, limit: int) -> None:
        if (
            len(page.items) > limit
            or type(page.total) is not int
            or page.total < len(page.items)
        ):
            raise DependencyUnavailableError()

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
    def _date(value: Any, name: str) -> date:
        if not isinstance(value, str) or not _CANONICAL_DATE.fullmatch(value):
            raise DomainValidationError(f"Invalid {name}.")
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
            return parsed
        except ValueError as error:
            raise DomainValidationError(f"Invalid {name}.") from error

    @staticmethod
    def _item(item: Any) -> dict[str, Any]:
        data = {
            k: getattr(item, k)
            for k in (
                "product_id",
                "sku",
                "name",
                "sold_units",
                "revenue_vnd",
            )
        }
        for key in ("quantity", "first_stocked_at"):
            if hasattr(item, key):
                data[key] = getattr(item, key)
        if "first_stocked_at" in data and data["first_stocked_at"] is not None:
            data["first_stocked_at"] = AIToolExecutor._utc(data["first_stocked_at"])
        return data

    @staticmethod
    def _safe_low(item: Any) -> dict[str, Any]:
        return {
            k: getattr(item, k)
            for k in ("product_id", "sku", "name", "quantity", "threshold")
        }

    @staticmethod
    def _utc(value: datetime) -> str:
        if not isinstance(value, datetime):
            raise ValueError("Invalid datetime from business service")
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)  # MySQL stores UTC without tzinfo
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _validated_result(
        tool_id: ToolId, data: dict[str, Any], source_period: str
    ) -> ToolResult:
        try:
            model = {
                "get_sales_summary": _SalesData,
                "get_top_products": _ProductPage,
                "get_slow_products": _ProductPage,
                "get_low_stock": _LowStockPage,
            }[tool_id]
            validated = model.model_validate(data)
            return ToolResult(
                tool_id, validated.model_dump(exclude_unset=True), source_period
            )
        except ValidationError as error:
            raise DependencyUnavailableError() from error
