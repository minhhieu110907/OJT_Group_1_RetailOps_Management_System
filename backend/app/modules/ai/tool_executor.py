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


@dataclass(frozen=True)
class ReorderSnapshot:
    """Bounded, read-only inventory & analytics snapshot for Reorder Advisor."""

    low_stock_result: ToolResult | None
    product_sales_by_id: Mapping[int, int] | None
    sales_period: str | None
    slow_products_result: ToolResult | None
    analysis_days: int
    low_stock_truncated: bool
    low_stock_total_available: int | None
    slow_products_truncated: bool
    source_errors: Mapping[str, str]


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

    def collect_reorder_snapshot(
        self,
        session: Session,
        *,
        context: ToolContext,
        analysis_days: int = 7,
        page_size: int = 50,
        max_pages: int = 5,
    ) -> ReorderSnapshot:
        """Collect bounded, paginated read-only data for Reorder Advisor [T04AB0B].

        Enforces the same ADMIN authentication, context verification, budget, and
        deadline checks as `execute`, without exposing arbitrary SQL or write tools.
        """
        started = time.monotonic()
        status = "error"
        verified = False
        error_code: str | None = None
        source_errors: dict[str, str] = {}
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
                days = self._bounded_int(analysis_days, "days", 1, 90)
                eff_page_size = self._bounded_int(page_size, "page_size", 1, 100)
                eff_max_pages = self._bounded_int(max_pages, "max_pages", 1, 20)
                self._budget.reserve()

                # 1. Bounded pagination over InventoryQueryService.get_low_stock
                low_items: list[dict[str, Any]] = []
                seen_low_ids: set[int] = set()
                low_total: int | None = None
                low_stock_result: ToolResult | None = None
                low_stock_truncated = False
                try:
                    for page_num in range(1, eff_max_pages + 1):
                        self._budget.check_deadline()
                        page = self._inventory.get_low_stock(
                            session=session,
                            page=page_num,
                            page_size=eff_page_size,
                            threshold=DEFAULT_LOW_STOCK_THRESHOLD,
                        )
                        low_total = int(page.total)
                        if not page.items:
                            break
                        added_this_page = 0
                        for item in page.items:
                            mapped = self._safe_low(item)
                            pid = int(mapped["product_id"])
                            if pid not in seen_low_ids:
                                seen_low_ids.add(pid)
                                low_items.append(mapped)
                                added_this_page += 1
                        if (
                            added_this_page == 0
                            or len(low_items) >= low_total
                            or len(page.items) < eff_page_size
                        ):
                            break
                    if low_total is None:
                        low_total = len(low_items)
                    low_stock_truncated = low_total > len(low_items)
                    low_stock_result = ToolResult(
                        tool_id="get_low_stock",
                        data={"items": low_items, "total": low_total},
                        source_period=None,
                    )
                except (ForbiddenError, DomainValidationError, RateLimitedError):
                    raise
                except DependencyUnavailableError as exc:
                    # Re-raise if deadline expired; otherwise record safe error
                    self._budget.check_deadline()
                    logger.warning(
                        "ai_reorder_source_error",
                        extra={
                            "request_id": context.request_id,
                            "tool_id": "get_low_stock",
                            "error_type": exc.__class__.__name__,
                            "error_code": exc.code,
                        },
                    )
                    source_errors["get_low_stock"] = "SOURCE_UNAVAILABLE"
                except Exception as exc:  # noqa: BLE001
                    self._budget.check_deadline()
                    logger.warning(
                        "ai_reorder_source_error",
                        extra={
                            "request_id": context.request_id,
                            "tool_id": "get_low_stock",
                            "error_type": exc.__class__.__name__,
                            "error_code": getattr(exc, "code", None),
                        },
                    )
                    source_errors["get_low_stock"] = "SOURCE_UNAVAILABLE"

                # 2. Exact per-product sales in period for all low-stock candidates
                period = resolve_days_period(days, now_fn=self._clock)
                sales_period = (
                    f"{period.start_utc.isoformat()}/"
                    f"{period.end_utc_exclusive.isoformat()}"
                )
                product_sales_by_id: dict[int, int] | None = None
                if low_items:
                    self._budget.check_deadline()
                    try:
                        product_sales_by_id = self._products.sold_units_for_products(
                            session,
                            product_ids=[int(it["product_id"]) for it in low_items],
                            period=period,
                        )
                    except (ForbiddenError, DomainValidationError, RateLimitedError):
                        raise
                    except DependencyUnavailableError as exc:
                        self._budget.check_deadline()
                        logger.warning(
                            "ai_reorder_source_error",
                            extra={
                                "request_id": context.request_id,
                                "tool_id": "product_sales",
                                "error_type": exc.__class__.__name__,
                                "error_code": exc.code,
                            },
                        )
                        source_errors["product_sales"] = "SOURCE_UNAVAILABLE"
                    except Exception as exc:  # noqa: BLE001
                        self._budget.check_deadline()
                        logger.warning(
                            "ai_reorder_source_error",
                            extra={
                                "request_id": context.request_id,
                                "tool_id": "product_sales",
                                "error_type": exc.__class__.__name__,
                                "error_code": getattr(exc, "code", None),
                            },
                        )
                        source_errors["product_sales"] = "SOURCE_UNAVAILABLE"
                elif low_stock_result is not None:
                    product_sales_by_id = {}

                # 3. Bounded pagination over ProductAnalyticsService.slow
                slow_items: list[dict[str, Any]] = []
                seen_slow_ids: set[int] = set()
                slow_total: int | None = None
                slow_products_result: ToolResult | None = None
                slow_products_truncated = False
                as_of = self._clock()
                slow_period = (
                    f"as_of={self._utc(as_of)}; trailing_30_days; "
                    "stocked_more_than_7_days"
                )
                try:
                    for page_num in range(1, eff_max_pages + 1):
                        self._budget.check_deadline()
                        page = self._products.slow(
                            session,
                            as_of_utc=as_of,
                            page=page_num,
                            page_size=eff_page_size,
                        )
                        slow_total = int(page.total)
                        if not page.items:
                            break
                        added_this_page = 0
                        for item in page.items:
                            mapped = self._item(item)
                            pid = int(mapped["product_id"])
                            if pid not in seen_slow_ids:
                                seen_slow_ids.add(pid)
                                slow_items.append(mapped)
                                added_this_page += 1
                        if (
                            added_this_page == 0
                            or len(slow_items) >= slow_total
                            or len(page.items) < eff_page_size
                        ):
                            break
                    if slow_total is None:
                        slow_total = len(slow_items)
                    slow_products_truncated = slow_total > len(slow_items)
                    slow_products_result = ToolResult(
                        tool_id="get_slow_products",
                        data={"items": slow_items, "total": slow_total},
                        source_period=slow_period,
                    )
                except (ForbiddenError, DomainValidationError, RateLimitedError):
                    raise
                except DependencyUnavailableError as exc:
                    self._budget.check_deadline()
                    logger.warning(
                        "ai_reorder_source_error",
                        extra={
                            "request_id": context.request_id,
                            "tool_id": "get_slow_products",
                            "error_type": exc.__class__.__name__,
                            "error_code": exc.code,
                        },
                    )
                    source_errors["get_slow_products"] = "SOURCE_UNAVAILABLE"
                except Exception as exc:  # noqa: BLE001
                    self._budget.check_deadline()
                    logger.warning(
                        "ai_reorder_source_error",
                        extra={
                            "request_id": context.request_id,
                            "tool_id": "get_slow_products",
                            "error_type": exc.__class__.__name__,
                            "error_code": getattr(exc, "code", None),
                        },
                    )
                    source_errors["get_slow_products"] = "SOURCE_UNAVAILABLE"

                self._budget.check_deadline()
                status = "success"
                return ReorderSnapshot(
                    low_stock_result=low_stock_result,
                    product_sales_by_id=product_sales_by_id,
                    sales_period=sales_period,
                    slow_products_result=slow_products_result,
                    analysis_days=days,
                    low_stock_truncated=low_stock_truncated,
                    low_stock_total_available=low_total,
                    slow_products_truncated=slow_products_truncated,
                    source_errors=source_errors,
                )
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
                    "tool_id": "reorder_advisor_snapshot",
                    "status": status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "output_bytes": 0,
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
