"""Read-only reorder advisor for RetailOps AI Assistant [T04AB0B].

Synthesizes reorder recommendations strictly from allowlisted read-only tools
(`get_low_stock`, `get_top_products`, `get_slow_products`) executed through
`AIToolExecutor`. Never mutates business data, never fabricates quantities,
and always attaches verifiable evidence and insufficient-data flags.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import (
    DomainValidationError,
    ForbiddenError,
    RateLimitedError,
)
from app.modules.ai.schemas import AIEvidence
from app.modules.ai.tool_executor import ToolId, ToolResult

logger = logging.getLogger(__name__)
_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def format_period_vn(period_str: str | None) -> str | None:
    """Convert raw UTC ISO period/as_of strings into clean DD/MM/YYYY labels."""
    if not period_str:
        return None
    if period_str == "current_stock":
        return "Hiện tại"
    if "/" in period_str:
        parts = period_str.split("/", 1)
        try:
            start_dt = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(parts[1].replace("Z", "+00:00"))
            start_d = start_dt.astimezone(_VN_TZ).date()
            end_d = (end_dt.astimezone(_VN_TZ) - timedelta(microseconds=1)).date()
            if start_d == end_d:
                return start_d.strftime("%d/%m/%Y")
            return f"{start_d.strftime('%d/%m/%Y')} - {end_d.strftime('%d/%m/%Y')}"
        except ValueError:
            return period_str
    if ".." in period_str:
        parts = period_str.split("..", 1)
        try:
            start_d = date.fromisoformat(parts[0].strip())
            end_d = date.fromisoformat(parts[1].strip())
            if start_d == end_d:
                return start_d.strftime("%d/%m/%Y")
            return f"{start_d.strftime('%d/%m/%Y')} - {end_d.strftime('%d/%m/%Y')}"
        except ValueError:
            return period_str
    if period_str.startswith("as_of="):
        raw_ts = period_str[len("as_of=") :].split(";", 1)[0].strip()
        try:
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            date_str = dt.astimezone(_VN_TZ).strftime("%d/%m/%Y")
            return f"30 ngày gần nhất (đến {date_str})"
        except ValueError:
            return period_str
    return period_str


ReorderClassification = Literal[
    "PRIORITY_RESTOCK",
    "LOW_STOCK_NO_SALES_HISTORY",
    "UNVERIFIED_SLOW_MOVING",
    "SLOW_MOVING_HOLD",
    "NO_CANDIDATES",
]
SlowSourceState = Literal["COMPLETE", "TRUNCATED", "UNAVAILABLE"]
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

_SAFE_SOURCE_ERROR_MESSAGES: dict[str, str] = {
    "get_low_stock": "Nguồn dữ liệu tồn kho tạm thời không khả dụng.",
    "get_top_products": "Nguồn dữ liệu sản phẩm bán chạy tạm thời không khả dụng.",
    "product_sales": "Nguồn dữ liệu lịch sử bán hàng tạm thời không khả dụng.",
    "get_slow_products": "Nguồn dữ liệu sản phẩm bán chậm tạm thời không khả dụng.",
}


def _safe_source_error_message(source_key: str) -> str:
    return _SAFE_SOURCE_ERROR_MESSAGES.get(
        source_key, "Nguồn dữ liệu phân tích tạm thời không khả dụng."
    )


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
        period = format_period_vn(result.source_period)

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
        product_sales_by_id: Mapping[int, int] | None = None,
        sales_period: str | None = None,
        analysis_days: int = DEFAULT_REORDER_ANALYSIS_DAYS,
        low_stock_truncated: bool = False,
        low_stock_total_available: int | None = None,
        slow_products_truncated: bool = False,
        source_errors: Mapping[str, str] | None = None,
    ) -> ReorderSuggestionReport:
        """Build evidence-backed reorder recommendations without mutating state."""
        errors = dict(source_errors or {})
        evidence: list[AIEvidence] = []
        missing_data: list[str] = []
        warnings: list[str] = []
        assumptions: list[str] = []

        if low_stock_result is None:
            safe_msg = _safe_source_error_message("get_low_stock")
            warnings.append(safe_msg)
            missing_data.append("inventory_low_stock")
            return ReorderSuggestionReport(
                status="SOURCE_ERROR",
                recommendations=[],
                summary=(
                    "Không thể đưa ra gợi ý nhập hàng vì "
                    f"{safe_msg[0].lower()}{safe_msg[1:]} Vui lòng thử lại sau."
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
        low_total = _parse_int(
            low_stock_result.data.get("total")
            if isinstance(low_stock_result.data, Mapping)
            else None
        )
        effective_low_total = (
            low_stock_total_available
            if low_stock_total_available is not None
            else low_total
        )
        is_low_stock_truncated = low_stock_truncated or (
            effective_low_total is not None and effective_low_total > len(low_items)
        )
        low_note = (
            f"truncated={len(low_items)}/{effective_low_total}"
            if is_low_stock_truncated and effective_low_total is not None
            else None
        )
        evidence.append(_build_evidence_item(low_stock_result, note=low_note))
        if low_malformed:
            warnings.append(
                "Dữ liệu tồn kho thấp có bản ghi không hợp lệ đã bị bỏ qua."
            )
            missing_data.append("malformed_low_stock_items")
        if is_low_stock_truncated:
            total_label = (
                str(effective_low_total)
                if effective_low_total is not None
                else "nhiều hơn giới hạn"
            )
            warnings.append(
                f"Chỉ phân tích được {len(low_items)}/{total_label} sản phẩm tồn thấp "
                "do giới hạn xử lý an toàn; danh sách đề xuất chưa đầy đủ."
            )
            missing_data.append("low_stock_truncated")

        formatted_sales_period = format_period_vn(sales_period)
        exact_sales_by_id: dict[int, int] | None = None
        if product_sales_by_id is not None:
            exact_sales_by_id = {}
            for raw_pid, raw_sold in product_sales_by_id.items():
                pid_parsed = _parse_int(raw_pid, minimum=1)
                sold_parsed = _parse_int(raw_sold, minimum=0)
                if pid_parsed is not None and sold_parsed is not None:
                    exact_sales_by_id[pid_parsed] = sold_parsed
            with_sales_count = sum(1 for v in exact_sales_by_id.values() if v > 0)
            evidence.append(
                AIEvidence(
                    source="product_sales (orders, order_items, products)",
                    period=formatted_sales_period,
                    summary=(
                        f"queried={len(exact_sales_by_id)}, "
                        f"with_sales={with_sales_count}, days={analysis_days}"
                    ),
                )
            )
        elif "product_sales" in errors:
            warnings.append(_safe_source_error_message("product_sales"))
            missing_data.append("product_sales_velocity")

        top_by_id: dict[int, dict[str, Any]] = {}
        top_period: str | None = formatted_sales_period
        top_truncated = False
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
            top_total = _parse_int(
                top_products_result.data.get("total")
                if isinstance(top_products_result.data, Mapping)
                else None
            )
            top_truncated = top_total is not None and top_total > len(top_items)
            top_note = (
                f"truncated={len(top_items)}/{top_total}" if top_truncated else None
            )
            evidence.append(_build_evidence_item(top_products_result, note=top_note))
            if top_period is None:
                top_period = format_period_vn(top_products_result.source_period)
            if top_malformed:
                warnings.append(
                    "Dữ liệu top sản phẩm có bản ghi không hợp lệ đã bị bỏ qua."
                )
                missing_data.append("malformed_top_products_items")
            for item in top_items:
                top_by_id[int(item["product_id"])] = item
        elif exact_sales_by_id is None:
            if "get_top_products" in errors:
                warnings.append(_safe_source_error_message("get_top_products"))
            if "sales_velocity_top_products" not in missing_data and (
                "product_sales_velocity" not in missing_data
            ):
                missing_data.append("sales_velocity_top_products")

        slow_ids: set[int] = set()
        slow_by_id: dict[int, dict[str, Any]] = {}
        slow_malformed = False
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
            slow_total = _parse_int(
                slow_products_result.data.get("total")
                if isinstance(slow_products_result.data, Mapping)
                else None
            )
            is_slow_truncated = slow_products_truncated or (
                slow_total is not None and slow_total > len(slow_items)
            )
            slow_note = (
                f"truncated={len(slow_items)}/{slow_total}"
                if is_slow_truncated and slow_total is not None
                else None
            )
            evidence.append(_build_evidence_item(slow_products_result, note=slow_note))
            if slow_malformed:
                warnings.append("Dữ liệu sản phẩm bán chậm có bản ghi không hợp lệ.")
                missing_data.append("malformed_slow_products_items")
            if is_slow_truncated:
                warnings.append(
                    "Danh sách sản phẩm bán chậm vượt giới hạn xử lý an toàn nên "
                    "chưa đối chiếu đầy đủ."
                )
                missing_data.append("slow_products_truncated")
            for item in slow_items:
                pid = int(item["product_id"])
                slow_ids.add(pid)
                slow_by_id[pid] = item
        else:
            is_slow_truncated = slow_products_truncated
            if "get_slow_products" in errors:
                warnings.append(_safe_source_error_message("get_slow_products"))
                missing_data.append("slow_moving_products")

        slow_source_state: SlowSourceState
        if (
            slow_products_result is not None
            and not is_slow_truncated
            and not slow_malformed
            and "get_slow_products" not in errors
        ):
            slow_source_state = "COMPLETE"
        elif slow_products_result is not None and is_slow_truncated:
            slow_source_state = "TRUNCATED"
        else:
            slow_source_state = "UNAVAILABLE"

        if not low_items and not low_malformed:
            # Slow products without low stock should not be recommended for restock.
            if errors or is_low_stock_truncated or is_slow_truncated:
                return ReorderSuggestionReport(
                    status="PARTIAL_DATA",
                    recommendations=[],
                    summary=(
                        "Hiện không có sản phẩm nào dưới ngưỡng tồn kho thấp theo "
                        "snapshot hiện tại, tuy nhiên nguồn dữ liệu chưa đầy đủ hoặc "
                        "gặp lỗi nên chưa thể đối chiếu toàn bộ."
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
        has_zero_sales_items = False
        has_missing_sales_items = False
        has_unverified_slow_items = False

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

            slow_match = slow_by_id.get(pid)
            sales_source: str | None = None
            sold_units: int | None = None
            sales_data_known = False

            if exact_sales_by_id is not None and pid in exact_sales_by_id:
                sold_units = exact_sales_by_id[pid]
                sales_source = "product_sales"
                sales_data_known = True
            elif pid in top_by_id:
                sold_units = _parse_int(top_by_id[pid].get("sold_units"))
                sales_source = "get_top_products"
                sales_data_known = sold_units is not None
            elif (
                exact_sales_by_id is None
                and top_products_result is not None
                and not top_truncated
                and "product_sales" not in errors
                and "get_top_products" not in errors
            ):
                # Non-truncated top_products covers every product with sales in period.
                sold_units = 0
                sales_source = "get_top_products"
                sales_data_known = True

            if pid in slow_ids and (sold_units is None or sold_units <= 2):
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
                            format_period_vn(slow_products_result.source_period)
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

            if (
                sales_data_known
                and sold_units is not None
                and sold_units > 0
                and analysis_days > 0
            ):
                avg_daily = round(sold_units / analysis_days, 2)
                can_rule_out_slow = slow_source_state == "COMPLETE" or (
                    sold_units > 2 and analysis_days <= 30
                )
                if not can_rule_out_slow:
                    has_unverified_slow_items = True
                    slow_state_note = (
                        "danh sách bán chậm bị giới hạn"
                        if slow_source_state == "TRUNCATED"
                        else "nguồn sản phẩm bán chậm không khả dụng"
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
                            suggested_quantity=None,
                            classification="UNVERIFIED_SLOW_MOVING",
                            confidence="INSUFFICIENT",
                            reason=(
                                f"Tồn kho thấp ({qty}/{threshold}) và đã bán "
                                f"{sold_units} đơn vị trong {analysis_days} ngày, "
                                f"nhưng {slow_state_note} nên chưa đủ bằng chứng loại "
                                "trừ nhóm bán chậm (<= 2 đơn vị/30 ngày); chưa đề xuất "
                                "số lượng nhập."
                            ),
                            sources=["get_low_stock", sales_source or "product_sales"],
                        )
                    )
                    continue

                threshold_gap = max(0, threshold - qty)
                demand_gap = max(0, sold_units - qty)
                suggested_qty = max(1, threshold_gap, demand_gap)
                confidence: ReorderConfidence = (
                    "MEDIUM"
                    if slow_source_state != "COMPLETE"
                    else (
                        "HIGH" if analysis_days >= 7 and sold_units >= 3 else "MEDIUM"
                    )
                )
                slow_caveat = (
                    " (Lưu ý: nguồn sản phẩm bán chậm chưa đầy đủ; sản phẩm được "
                    f"loại trừ nhờ bán {sold_units} > 2 đơn vị trong {analysis_days} "
                    "ngày.)"
                    if slow_source_state != "COMPLETE"
                    else ""
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
                            f"{slow_caveat}"
                        ),
                        sources=["get_low_stock", sales_source or "product_sales"],
                    )
                )
            elif sales_data_known and sold_units == 0:
                has_zero_sales_items = True
                recommendations.append(
                    ReorderRecommendationItem(
                        product_id=pid,
                        sku=sku,
                        name=name,
                        current_quantity=qty,
                        low_stock_threshold=threshold,
                        sold_units=0,
                        analysis_days=analysis_days,
                        sales_period=top_period,
                        average_daily_sales=0.0,
                        suggested_quantity=None,
                        classification="LOW_STOCK_NO_SALES_HISTORY",
                        confidence="LOW",
                        reason=(
                            f"Tồn kho thấp ({qty}/{threshold}) và ghi nhận 0 lượt bán "
                            f"trong {analysis_days} ngày qua; cần ADMIN kiểm tra nhu "
                            "cầu thực tế trước khi quyết định số lượng nhập."
                        ),
                        sources=["get_low_stock", sales_source or "product_sales"],
                    )
                )
            else:
                has_missing_sales_items = True
                missing_reason = (
                    "không nằm trong danh sách Top Products bị giới hạn"
                    if top_truncated
                    else "thiếu dữ liệu bán từ nguồn Analytics"
                )
                recommendations.append(
                    ReorderRecommendationItem(
                        product_id=pid,
                        sku=sku,
                        name=name,
                        current_quantity=qty,
                        low_stock_threshold=threshold,
                        sold_units=None,
                        analysis_days=None,
                        sales_period=top_period,
                        average_daily_sales=None,
                        suggested_quantity=None,
                        classification="LOW_STOCK_NO_SALES_HISTORY",
                        confidence="INSUFFICIENT",
                        reason=(
                            f"Tồn kho thấp ({qty}/{threshold}) nhưng chưa xác định "
                            f"được tốc độ bán ({missing_reason}); không giả định bằng "
                            "0 và không tự suy đoán số lượng nhập."
                        ),
                        sources=["get_low_stock"],
                    )
                )

        if top_truncated and has_missing_sales_items:
            warnings.append(
                "Một số sản phẩm tồn thấp nằm ngoài giới hạn Top Products nên chưa "
                "xác định được tốc độ bán thực tế."
            )
            missing_data.append("top_products_truncated")

        if any(r.classification == "PRIORITY_RESTOCK" for r in recommendations):
            assumptions.append(
                f"Số lượng gợi ý tính theo công thức "
                f"max(1, threshold - current_stock, sold_units_{analysis_days}d - "
                "current_stock); chưa tính lead time nhà cung cấp hay safety stock."
            )
        if has_zero_sales_items or has_missing_sales_items:
            assumptions.append(
                "Các sản phẩm không có lượt bán hoặc thiếu dữ liệu bán trong kỳ không "
                "được tự suy đoán số lượng nhập."
            )

        has_partial_condition = bool(
            errors
            or low_malformed
            or is_low_stock_truncated
            or is_slow_truncated
            or has_missing_sales_items
            or has_unverified_slow_items
        )
        insufficient_data = bool(
            has_partial_condition
            or not recommendations
            or all(r.suggested_quantity is None for r in recommendations)
        )
        status: AdvisorStatus
        if has_partial_condition:
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


def _format_group_header(label: str, total: int, shown: int) -> str:
    if total > shown:
        hidden = total - shown
        return (
            f"{label} (hiển thị {shown}/{total} sản phẩm, còn {hidden} sản phẩm khác "
            "chưa liệt kê)"
        )
    return f"{label} ({total} sản phẩm)"


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
    unverified_slow = [
        r for r in recommendations if r.classification == "UNVERIFIED_SLOW_MOVING"
    ]
    no_hist = [
        r for r in recommendations if r.classification == "LOW_STOCK_NO_SALES_HISTORY"
    ]
    slow_hold = [r for r in recommendations if r.classification == "SLOW_MOVING_HOLD"]

    parts: list[str] = []
    if priority:
        shown = priority[:5]
        lines = "\n".join(
            f"- **{r.name}** (`{r.sku}`): tồn {r.current_quantity}/"
            f"{r.low_stock_threshold}, đã bán {r.sold_units} "
            f"({r.average_daily_sales}/ngày), gợi ý nhập **{r.suggested_quantity}**"
            for r in shown
        )
        period_note = f" (kỳ bán {top_period})" if top_period else ""
        header = _format_group_header(
            f"Ưu tiên cân nhắc nhập hàng{period_note}", len(priority), len(shown)
        )
        parts.append(f"**{header}:**\n{lines}")

    if unverified_slow:
        shown = unverified_slow[:5]
        lines = "\n".join(
            f"- **{r.name}** (`{r.sku}`): tồn {r.current_quantity}/"
            f"{r.low_stock_threshold}, đã bán {r.sold_units}"
            for r in shown
        )
        header = _format_group_header(
            "Thiếu bằng chứng loại trừ nhóm bán chậm (chưa đề xuất số lượng)",
            len(unverified_slow),
            len(shown),
        )
        parts.append(f"**{header}:**\n{lines}")

    if no_hist:
        shown = no_hist[:5]
        lines = "\n".join(
            f"- **{r.name}** (`{r.sku}`): tồn {r.current_quantity}/"
            f"{r.low_stock_threshold}"
            for r in shown
        )
        header = _format_group_header(
            "Tồn kho thấp nhưng thiếu dữ liệu bán để định lượng",
            len(no_hist),
            len(shown),
        )
        parts.append(f"**{header}:**\n{lines}")

    if slow_hold:
        shown = slow_hold[:5]
        lines = "\n".join(
            f"- **{r.name}** (`{r.sku}`): tồn {r.current_quantity}/"
            f"{r.low_stock_threshold}"
            for r in shown
        )
        header = _format_group_header(
            "Không ưu tiên nhập thêm (nhóm bán chậm 30 ngày)",
            len(slow_hold),
            len(shown),
        )
        parts.append(f"**{header}:**\n{lines}")

    if warnings:
        warn_lines = "\n".join(f"- {w}" for w in warnings)
        parts.append(f"**Lưu ý nguồn dữ liệu:**\n{warn_lines}")
    if assumptions:
        assump_lines = "\n".join(f"- {a}" for a in assumptions)
        parts.append(f"**Giả định:**\n{assump_lines}")
    parts.append(
        "AI chỉ tư vấn read-only; quản trị viên tự tạo và xác nhận phiếu nhập tại "
        "mục Purchasing."
    )
    return "\n\n".join(parts)


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
            logger.warning(
                "ai_reorder_source_error",
                extra={
                    "tool_id": tool_id,
                    "error_type": exc.__class__.__name__,
                    "error_code": getattr(exc, "code", None),
                },
            )
            source_errors[tool_id] = "SOURCE_UNAVAILABLE"

    return ReadOnlyReorderAdvisor().suggest(
        low_stock_result=low_result,
        top_products_result=top_result,
        slow_products_result=slow_result,
        analysis_days=analysis_days,
        source_errors=source_errors,
    )
