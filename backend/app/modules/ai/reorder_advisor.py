"""Read-only reorder advisor for RetailOps AI Assistant [T04AB0B].

Synthesizes reorder recommendations strictly from allowlisted read-only tools
(`get_low_stock`, `get_top_products`, `get_slow_products`) executed through
`AIToolExecutor`. Never mutates business data, never fabricates quantities,
and always attaches verifiable evidence and insufficient-data flags.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import (
    DomainValidationError,
    ForbiddenError,
    RateLimitedError,
)
from app.modules.ai.schemas import AIEvidence
from app.modules.ai.tool_executor import ToolId, ToolResult

ReorderClassification = Literal[
    "PRIORITY_RESTOCK",
    "LOW_STOCK_NO_SALES_HISTORY",
    "SLOW_MOVING_HOLD",
    "NO_CANDIDATES",
]
ReorderConfidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
AdvisorStatus = Literal["OK", "PARTIAL_DATA", "INSUFFICIENT_DATA", "SOURCE_ERROR"]

DEFAULT_REORDER_ANALYSIS_DAYS = 7
DEFAULT_REORDER_LIMIT = 20

_TOOL_SOURCES: dict[ToolId, str] = {
    "get_sales_summary": "orders, order_items",
    "get_top_products": "orders, order_items, products",
    "get_slow_products": "products, inventory_stocks, order_items",
    "get_low_stock": "products, inventory_stocks",
}


class _StrictAdvisorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReorderRecommendationItem(_StrictAdvisorModel):
    """Single product reorder recommendation backed by tool evidence."""

    product_id: int = Field(ge=1)
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    current_quantity: int = Field(ge=0)
    low_stock_threshold: int = Field(ge=0)
    sold_units: int | None = Field(default=None, ge=0)
    analysis_days: int | None = Field(default=None, ge=1, le=90)
    sales_period: str | None = None
    average_daily_sales: float | None = Field(default=None, ge=0)
    suggested_quantity: int | None = Field(default=None, ge=1)
    classification: ReorderClassification
    confidence: ReorderConfidence
    reason: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1)


class ReorderSuggestionReport(_StrictAdvisorModel):
    """Evidence-only DTO returned by ReadOnlyReorderAdvisor.suggest."""

    status: AdvisorStatus
    recommendations: list[ReorderRecommendationItem]
    summary: str = Field(min_length=1)
    evidence: list[AIEvidence]
    insufficient_data: bool
    missing_data: list[str]
    assumptions: list[str]
    warnings: list[str]


def _extract_valid_items(
    result: ToolResult,
    *,
    required_fields: tuple[str, ...],
) -> tuple[list[dict[str, Any]], bool]:
    """Validate tool payload items without raising on malformed model/tool output."""
    data = result.data
    if not isinstance(data, Mapping):
        return [], True
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return [], True

    valid: list[dict[str, Any]] = []
    malformed = False
    for entry in raw_items:
        if not isinstance(entry, Mapping):
            malformed = True
            continue
        if any(entry.get(field) is None for field in required_fields):
            malformed = True
            continue
        try:
            product_id = int(entry["product_id"])
            sku = str(entry["sku"]).strip()
            name = str(entry["name"]).strip()
            if product_id < 1 or not sku or not name:
                malformed = True
                continue
        except (TypeError, ValueError):
            malformed = True
            continue
        valid.append(dict(entry))
    return valid, malformed


def _parse_int(value: Any, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= minimum else None


def _build_evidence_item(result: ToolResult, *, note: str | None = None) -> AIEvidence:
    data = result.data if isinstance(result.data, Mapping) else {}
    source = f"{result.tool_id} ({_TOOL_SOURCES[result.tool_id]})"
    items = data.get("items") if isinstance(data.get("items"), list) else []
    total = _parse_int(data.get("total"))
    total_label = str(total) if total is not None else "unknown"

    if result.tool_id == "get_low_stock":
        preview = ", ".join(
            f"{it.get('sku', '?')} "
            f"(qty={it.get('quantity', '?')}/{it.get('threshold', '?')})"
            for it in items[:3]
            if isinstance(it, Mapping)
        )
        summary = f"snapshot_total={total_label}, returned={len(items)}" + (
            f"; items=[{preview}]" if preview else ""
        )
        # Inventory snapshot must never carry a fabricated sales period.
        period = None
    else:
        preview = ", ".join(
            f"{it.get('sku', '?')} (sold={it.get('sold_units', '?')})"
            for it in items[:3]
            if isinstance(it, Mapping)
        )
        summary = f"total={total_label}, returned={len(items)}" + (
            f"; items=[{preview}]" if preview else ""
        )
        period = result.source_period

    if note:
        summary = f"{summary}; {note}"
    return AIEvidence(source=source, period=period, summary=summary)


class ReadOnlyReorderAdvisor:
    """Read-only reorder advisor using allowlisted inventory & analytics tools."""

    def suggest(
        self,
        *,
        low_stock_result: ToolResult | None = None,
        top_products_result: ToolResult | None = None,
        slow_products_result: ToolResult | None = None,
        analysis_days: int = DEFAULT_REORDER_ANALYSIS_DAYS,
        source_errors: Mapping[str, str] | None = None,
    ) -> ReorderSuggestionReport:
        """Build evidence-backed reorder recommendations without mutating state."""
        errors = dict(source_errors or {})
        evidence: list[AIEvidence] = []
        missing_data: list[str] = []
        warnings: list[str] = []
        assumptions: list[str] = []

        if low_stock_result is None:
            err_msg = errors.get("get_low_stock", "Không truy vấn được tồn kho thấp.")
            warnings.append(f"Lỗi nguồn tồn kho (get_low_stock): {err_msg}")
            missing_data.append("inventory_low_stock")
            return ReorderSuggestionReport(
                status="SOURCE_ERROR",
                recommendations=[],
                summary=(
                    "Không thể đưa ra gợi ý nhập hàng vì nguồn dữ liệu tồn kho thấp "
                    f"gặp lỗi ({err_msg}). Vui lòng thử lại sau."
                ),
                evidence=[],
                insufficient_data=True,
                missing_data=missing_data,
                assumptions=[],
                warnings=warnings,
            )

        low_items, low_malformed = _extract_valid_items(
            low_stock_result,
            required_fields=("product_id", "sku", "name", "quantity", "threshold"),
        )
        evidence.append(_build_evidence_item(low_stock_result))
        if low_malformed:
            warnings.append(
                "Dữ liệu tồn kho thấp có bản ghi không hợp lệ đã bị bỏ qua."
            )
            missing_data.append("malformed_low_stock_items")

        top_by_id: dict[int, dict[str, Any]] = {}
        top_period: str | None = None
        if top_products_result is not None:
            top_items, top_malformed = _extract_valid_items(
                top_products_result,
                required_fields=(
                    "product_id",
                    "sku",
                    "name",
                    "sold_units",
                    "revenue_vnd",
                ),
            )
            evidence.append(_build_evidence_item(top_products_result))
            top_period = top_products_result.source_period
            if top_malformed:
                warnings.append(
                    "Dữ liệu top sản phẩm có bản ghi không hợp lệ đã bị bỏ qua."
                )
                missing_data.append("malformed_top_products_items")
            for item in top_items:
                top_by_id[int(item["product_id"])] = item
        else:
            if "get_top_products" in errors:
                err_top = errors["get_top_products"]
                warnings.append(f"Lỗi nguồn lịch sử bán (get_top_products): {err_top}")
            missing_data.append("sales_velocity_top_products")

        slow_ids: set[int] = set()
        slow_by_id: dict[int, dict[str, Any]] = {}
        if slow_products_result is not None:
            slow_items, slow_malformed = _extract_valid_items(
                slow_products_result,
                required_fields=(
                    "product_id",
                    "sku",
                    "name",
                    "sold_units",
                    "revenue_vnd",
                ),
            )
            evidence.append(_build_evidence_item(slow_products_result))
            if slow_malformed:
                warnings.append("Dữ liệu sản phẩm bán chậm có bản ghi không hợp lệ.")
                missing_data.append("malformed_slow_products_items")
            for item in slow_items:
                pid = int(item["product_id"])
                slow_ids.add(pid)
                slow_by_id[pid] = item
        elif "get_slow_products" in errors:
            warnings.append(
                f"Lỗi nguồn bán chậm (get_slow_products): {errors['get_slow_products']}"
            )
            missing_data.append("slow_moving_products")

        if not low_items and not low_malformed:
            # Slow products without low stock should not be recommended for restock.
            if errors:
                return ReorderSuggestionReport(
                    status="PARTIAL_DATA",
                    recommendations=[],
                    summary=(
                        "Hiện không có sản phẩm nào dưới ngưỡng tồn kho thấp theo "
                        "snapshot hiện tại, tuy nhiên nguồn phân tích bán hàng gặp lỗi "
                        "nên chưa thể đối chiếu đầy đủ."
                    ),
                    evidence=evidence,
                    insufficient_data=True,
                    missing_data=missing_data,
                    assumptions=[],
                    warnings=warnings,
                )
            return ReorderSuggestionReport(
                status="OK",
                recommendations=[],
                summary=(
                    "Hiện không tìm thấy sản phẩm nào dưới hoặc bằng ngưỡng tồn kho "
                    "thấp để đề xuất nhập hàng."
                ),
                evidence=evidence,
                insufficient_data=False,
                missing_data=missing_data,
                assumptions=[],
                warnings=warnings,
            )

        if low_malformed and not low_items:
            return ReorderSuggestionReport(
                status="INSUFFICIENT_DATA",
                recommendations=[],
                summary=(
                    "Dữ liệu tồn kho thấp trả về không hợp lệ nên chưa thể lập đề xuất "
                    "nhập hàng."
                ),
                evidence=evidence,
                insufficient_data=True,
                missing_data=missing_data,
                assumptions=[],
                warnings=warnings,
            )

        recommendations: list[ReorderRecommendationItem] = []
        has_missing_sales = False

        for raw in low_items:
            pid = int(raw["product_id"])
            sku = str(raw["sku"]).strip()
            name = str(raw["name"]).strip()
            qty = _parse_int(raw.get("quantity"))
            threshold = _parse_int(raw.get("threshold"))
            if qty is None or threshold is None:
                warnings.append(
                    f"Bỏ qua {sku} do thiếu quantity hoặc threshold hợp lệ."
                )
                missing_data.append(f"product_{pid}_stock_fields")
                continue

            # Ignore items above threshold if any unexpected item slips in.
            if qty > threshold:
                continue

            top_match = top_by_id.get(pid)
            slow_match = slow_by_id.get(pid)

            if pid in slow_ids and top_match is None:
                sold_slow = (
                    _parse_int(slow_match.get("sold_units")) if slow_match else None
                )
                recommendations.append(
                    ReorderRecommendationItem(
                        product_id=pid,
                        sku=sku,
                        name=name,
                        current_quantity=qty,
                        low_stock_threshold=threshold,
                        sold_units=sold_slow,
                        analysis_days=30,
                        sales_period=(
                            slow_products_result.source_period
                            if slow_products_result is not None
                            else None
                        ),
                        average_daily_sales=(
                            round(sold_slow / 30, 2) if sold_slow is not None else None
                        ),
                        suggested_quantity=None,
                        classification="SLOW_MOVING_HOLD",
                        confidence="MEDIUM",
                        reason=(
                            f"Tồn kho hiện tại ({qty}/{threshold}) thấp nhưng sản phẩm "
                            "đang nằm trong nhóm bán chậm (<= 2 đơn vị trong 30 ngày), "
                            "chưa ưu tiên nhập thêm."
                        ),
                        sources=["get_low_stock", "get_slow_products"],
                    )
                )
                continue

            sold_units = _parse_int(top_match.get("sold_units")) if top_match else None
            if sold_units is not None and sold_units > 0 and analysis_days > 0:
                avg_daily = round(sold_units / analysis_days, 2)
                threshold_gap = max(0, threshold - qty)
                demand_gap = max(0, sold_units - qty)
                suggested_qty = max(1, threshold_gap, demand_gap)
                confidence: ReorderConfidence = (
                    "HIGH" if analysis_days >= 7 and sold_units >= 3 else "MEDIUM"
                )
                recommendations.append(
                    ReorderRecommendationItem(
                        product_id=pid,
                        sku=sku,
                        name=name,
                        current_quantity=qty,
                        low_stock_threshold=threshold,
                        sold_units=sold_units,
                        analysis_days=analysis_days,
                        sales_period=top_period,
                        average_daily_sales=avg_daily,
                        suggested_quantity=suggested_qty,
                        classification="PRIORITY_RESTOCK",
                        confidence=confidence,
                        reason=(
                            f"Tồn kho thấp ({qty}/{threshold}) và đã bán {sold_units} "
                            f"đơn vị trong {analysis_days} ngày (~{avg_daily}/ngày); "
                            f"đề xuất cân nhắc nhập tham khảo {suggested_qty} đơn vị."
                        ),
                        sources=["get_low_stock", "get_top_products"],
                    )
                )
            else:
                has_missing_sales = True
                recommendations.append(
                    ReorderRecommendationItem(
                        product_id=pid,
                        sku=sku,
                        name=name,
                        current_quantity=qty,
                        low_stock_threshold=threshold,
                        sold_units=None if top_products_result is None else 0,
                        analysis_days=analysis_days
                        if top_products_result is not None
                        else None,
                        sales_period=top_period,
                        average_daily_sales=None,
                        suggested_quantity=None,
                        classification="LOW_STOCK_NO_SALES_HISTORY",
                        confidence="LOW",
                        reason=(
                            f"Tồn kho thấp ({qty}/{threshold}) nhưng thiếu lịch sử bán "
                            "hoặc chưa ghi nhận lượt bán trong kỳ phân tích; cần ADMIN "
                            "kiểm tra nhu cầu thực tế trước khi quyết định số lượng."
                        ),
                        sources=(
                            ["get_low_stock", "get_top_products"]
                            if top_products_result is not None
                            else ["get_low_stock"]
                        ),
                    )
                )

        if any(r.classification == "PRIORITY_RESTOCK" for r in recommendations):
            assumptions.append(
                f"Số lượng gợi ý tính theo nhu cầu bán thực tế trong {analysis_days} "
                "ngày và ngưỡng tồn kho thấp hiện tại; chưa tính lead time nhà cung "
                "cấp hay safety stock."
            )
        if has_missing_sales:
            assumptions.append(
                "Các sản phẩm thiếu lịch sử bán trong kỳ không được tự suy đoán "
                "số lượng nhập."
            )

        insufficient_data = bool(
            errors
            or low_malformed
            or not recommendations
            or (all(r.suggested_quantity is None for r in recommendations))
        )
        status: AdvisorStatus
        if errors or low_malformed:
            status = "PARTIAL_DATA"
        elif not recommendations:
            status = "OK"
            insufficient_data = False
        elif all(r.suggested_quantity is None for r in recommendations):
            status = "INSUFFICIENT_DATA"
        else:
            status = "OK"

        summary = _format_report_summary(
            recommendations=recommendations,
            top_period=top_period,
            warnings=warnings,
            assumptions=assumptions,
        )
        return ReorderSuggestionReport(
            status=status,
            recommendations=recommendations,
            summary=summary,
            evidence=evidence,
            insufficient_data=insufficient_data,
            missing_data=missing_data,
            assumptions=assumptions,
            warnings=warnings,
        )


def _format_report_summary(
    *,
    recommendations: list[ReorderRecommendationItem],
    top_period: str | None,
    warnings: list[str],
    assumptions: list[str],
) -> str:
    if not recommendations:
        return (
            "Hiện không tìm thấy sản phẩm nào dưới hoặc bằng ngưỡng tồn kho thấp "
            "để đề xuất nhập hàng."
        )

    priority = [r for r in recommendations if r.classification == "PRIORITY_RESTOCK"]
    no_hist = [
        r for r in recommendations if r.classification == "LOW_STOCK_NO_SALES_HISTORY"
    ]
    slow_hold = [r for r in recommendations if r.classification == "SLOW_MOVING_HOLD"]

    parts: list[str] = []
    if priority:
        items_text = "; ".join(
            f"{r.name} ({r.sku}): tồn {r.current_quantity}/{r.low_stock_threshold}, "
            f"đã bán {r.sold_units} ({r.average_daily_sales}/ngày), "
            f"gợi ý nhập {r.suggested_quantity}"
            for r in priority[:5]
        )
        period_note = f" (kỳ bán {top_period})" if top_period else ""
        parts.append(f"Ưu tiên cân nhắc nhập hàng{period_note}: {items_text}.")

    if no_hist:
        items_text = "; ".join(
            f"{r.name} ({r.sku}): tồn {r.current_quantity}/{r.low_stock_threshold}"
            for r in no_hist[:5]
        )
        parts.append(
            "Tồn kho thấp nhưng thiếu dữ liệu bán để định lượng: " + items_text + "."
        )

    if slow_hold:
        items_text = "; ".join(
            f"{r.name} ({r.sku}): tồn {r.current_quantity}/{r.low_stock_threshold}"
            for r in slow_hold[:5]
        )
        parts.append(
            "Không ưu tiên nhập thêm (nhóm bán chậm 30 ngày): " + items_text + "."
        )

    if warnings:
        parts.append("Lưu ý nguồn dữ liệu: " + " ".join(warnings))
    if assumptions:
        parts.append("Giả định: " + " ".join(assumptions))
    parts.append(
        "AI chỉ tư vấn read-only; quản trị viên tự tạo và xác nhận phiếu nhập tại "
        "mục Purchasing."
    )
    return " ".join(parts)


def run_reorder_advisor_via_executor(
    *,
    execute_tool: Callable[[ToolId, dict[str, Any]], ToolResult],
    analysis_days: int = DEFAULT_REORDER_ANALYSIS_DAYS,
    limit: int = DEFAULT_REORDER_LIMIT,
) -> ReorderSuggestionReport:
    """Execute allowlisted tools via callback and return a ReorderSuggestionReport."""
    low_result: ToolResult | None = None
    top_result: ToolResult | None = None
    slow_result: ToolResult | None = None
    source_errors: dict[str, str] = {}

    for tool_id, args in (
        ("get_low_stock", {"limit": limit}),
        ("get_top_products", {"days": analysis_days, "limit": limit}),
        ("get_slow_products", {"limit": limit}),
    ):
        try:
            res = execute_tool(tool_id, args)  # type: ignore[arg-type]
            if tool_id == "get_low_stock":
                low_result = res
            elif tool_id == "get_top_products":
                top_result = res
            else:
                slow_result = res
        except (ForbiddenError, DomainValidationError, RateLimitedError):
            raise
        except Exception as exc:  # noqa: BLE001 - surface source outage cleanly
            # Never swallow AI budget/deadline errors (e.g. AIToolLimit/Timeout).
            if exc.__class__.__name__ in {
                "AIToolBudgetExceededError",
                "AIRequestTimeoutError",
            }:
                raise
            source_errors[tool_id] = str(exc) or exc.__class__.__name__

    return ReadOnlyReorderAdvisor().suggest(
        low_stock_result=low_result,
        top_products_result=top_result,
        slow_products_result=slow_result,
        analysis_days=analysis_days,
        source_errors=source_errors,
    )
