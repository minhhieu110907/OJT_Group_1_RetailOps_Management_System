"""Hybrid AI orchestrator: Gemini, allowlist validation, and AIToolExecutor."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.modules.ai.gemini_provider import (
    APPROVED_TOOL_NAMES,
    GeminiProviderError,
    LLMProvider,
    ToolResponseItem,
)
from app.modules.ai.schemas import AIAskResponse, AIEvidence
from app.modules.ai.tool_executor import (
    BoundToolRequest,
    ToolId,
    ToolResult,
    serialize_tool_result,
)

_ALLOWED_TOOLS = frozenset(APPROVED_TOOL_NAMES)
_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

_TOOL_SOURCES: dict[ToolId, str] = {
    "get_sales_summary": "orders, order_items",
    "get_top_products": "orders, order_items, products",
    "get_slow_products": "products, inventory_stocks, order_items",
    "get_low_stock": "products, inventory_stocks",
}

_GREETING_EXACT = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "xin chao",
        "xin chào",
        "chao",
        "chào",
        "chao ban",
        "chào bạn",
        "chao ai",
        "chào ai",
    }
)

_HELP_EXACT = frozenset(
    {
        "help",
        "huong dan",
        "hướng dẫn",
        "ban lam duoc gi",
        "bạn làm được gì",
        "ban co the lam gi",
        "bạn có thể làm gì",
    }
)

_LOW_STOCK_PHRASES = frozenset(
    {
        "tồn kho thấp",
        "ton kho thap",
        "xem tồn kho thấp",
        "xem ton kho thap",
        "kiểm tra tồn kho thấp",
        "kiem tra ton kho thap",
        "sản phẩm tồn kho thấp",
        "san pham ton kho thap",
        "hàng sắp hết",
        "hang sap het",
        "sản phẩm sắp hết hàng",
        "san pham sap het hang",
    }
)

_TODAY_SALES_PHRASES = frozenset(
    {
        "doanh thu hôm nay",
        "doanh thu hom nay",
        "xem doanh thu hôm nay",
        "xem doanh thu hom nay",
        "báo cáo doanh thu hôm nay",
        "bao cao doanh thu hom nay",
    }
)

_DATE_RANGE_SALES_RE = re.compile(
    r"^(?:xem\s+|báo cáo\s+|bao cao\s+)?doanh thu\s+(?:từ|tu)\s+"
    r"(\d{4}-\d{2}-\d{2})\s+(?:đến|den|tới|toi)\s+(\d{4}-\d{2}-\d{2})$"
)

SessionFactory = Callable[[], AbstractContextManager[Session]]


def _normalize_text(message: str) -> str:
    cleaned = re.sub(r"[?!.,:;]+$", "", message.strip().lower())
    return re.sub(r"\s+", " ", cleaned)


def _match_direct_tool(
    normalized: str, *, now_vn: datetime | None = None
) -> tuple[ToolId, dict[str, Any]] | None:
    if normalized in _LOW_STOCK_PHRASES:
        return ("get_low_stock", {"limit": 10})
    if normalized in _TODAY_SALES_PHRASES:
        current = now_vn or datetime.now(_VN_TZ)
        today = current.date().isoformat()
        return ("get_sales_summary", {"start_date": today, "end_date": today})
    range_match = _DATE_RANGE_SALES_RE.match(normalized)
    if range_match:
        return (
            "get_sales_summary",
            {"start_date": range_match.group(1), "end_date": range_match.group(2)},
        )
    return None


def _is_insufficient_result(result: ToolResult) -> bool:
    data = result.data
    if result.tool_id == "get_sales_summary":
        return (
            int(data.get("completed_orders", 0)) == 0
            and int(data.get("cancelled_orders", 0)) == 0
        )
    items = data.get("items")
    total = int(data.get("total", 0))
    return total == 0 and (not isinstance(items, list) or len(items) == 0)


def _build_evidence(result: ToolResult) -> AIEvidence:
    data = result.data
    source = f"{result.tool_id} ({_TOOL_SOURCES[result.tool_id]})"
    if result.tool_id == "get_sales_summary":
        summary = (
            f"revenue_vnd={data['revenue_vnd']}, "
            f"completed_orders={data['completed_orders']}, "
            f"cancelled_orders={data['cancelled_orders']}, "
            f"aov_vnd={data['aov_vnd']}"
        )
    elif result.tool_id in {"get_top_products", "get_slow_products"}:
        items = data.get("items", [])
        top_names = ", ".join(
            f"{item['sku']} (sold={item['sold_units']}, rev={item['revenue_vnd']})"
            for item in items[:3]
        )
        summary = f"total={data['total']}, returned={len(items)}" + (
            f"; top=[{top_names}]" if top_names else ""
        )
    else:
        items = data.get("items", [])
        low_names = ", ".join(
            f"{item['sku']} (qty={item['quantity']}/{item['threshold']})"
            for item in items[:3]
        )
        summary = f"total={data['total']}, returned={len(items)}" + (
            f"; items=[{low_names}]" if low_names else ""
        )
    return AIEvidence(
        source=source,
        period=result.source_period,
        summary=summary,
    )


def _format_direct_answer(result: ToolResult) -> tuple[str, bool]:
    data = result.data
    insufficient = _is_insufficient_result(result)
    if result.tool_id == "get_sales_summary":
        if insufficient:
            period_label = result.source_period or "đã chọn"
            return (
                f"Chưa có dữ liệu đơn hàng trong kỳ {period_label} "
                "(0 đơn hoàn thành, 0 đơn hủy).",
                True,
            )
        return (
            f"Doanh thu kỳ {result.source_period}: {data['revenue_vnd']:,} VND "
            f"({data['completed_orders']} đơn hoàn thành, "
            f"{data['cancelled_orders']} đơn hủy, AOV {data['aov_vnd']:,} VND).",
            False,
        )
    if result.tool_id == "get_low_stock":
        items = data.get("items", [])
        if insufficient:
            return ("Hiện không có sản phẩm nào dưới ngưỡng tồn kho thấp.", True)
        preview = "; ".join(
            f"{item['name']} ({item['sku']}): "
            f"còn {item['quantity']}/{item['threshold']}"
            for item in items[:5]
        )
        return (
            f"Có {data['total']} sản phẩm tồn kho thấp "
            f"(hiển thị {len(items)}): {preview}.",
            False,
        )
    return ("Đã hoàn tất truy vấn dữ liệu.", insufficient)


class AIOrchestrator:
    """Coordinates hybrid routing, Gemini Function Calling, and AIToolExecutor."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        provider_factory: Callable[[], LLMProvider],
        gemini_timeout_seconds: float,
        clock_vn: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self._gemini_timeout_seconds = gemini_timeout_seconds
        self._clock_vn = clock_vn or (lambda: datetime.now(_VN_TZ))

    def _execute_tool_sync(
        self,
        bound: BoundToolRequest,
        *,
        tool_id: ToolId,
        arguments: dict[str, Any],
    ) -> tuple[ToolResult, dict[str, Any]]:
        with self._session_factory() as session:
            result = bound.executor.execute(
                session,
                tool_id=tool_id,
                arguments=arguments,
                context=bound.context,
            )
        serialized = serialize_tool_result(result)
        return result, json.loads(serialized.decode("utf-8"))

    async def handle_query(
        self,
        *,
        message: str,
        bound: BoundToolRequest,
    ) -> AIAskResponse:
        normalized = _normalize_text(message)

        # 1. Fixed non-data intents: zero Gemini tokens, zero DB work
        if normalized in _GREETING_EXACT:
            return AIAskResponse(
                answer=(
                    "Xin chào! Tôi có thể hỗ trợ tra cứu doanh thu, sản phẩm bán chạy, "
                    "sản phẩm bán chậm và tồn kho thấp của cửa hàng."
                ),
                evidence=[],
                insufficient_data=False,
            )
        if normalized in _HELP_EXACT:
            return AIAskResponse(
                answer=(
                    "Tôi hỗ trợ 4 nhóm tra cứu dữ liệu thực tế: tổng hợp doanh thu "
                    "theo ngày, sản phẩm bán chạy, bán chậm và tồn kho thấp."
                ),
                evidence=[],
                insufficient_data=False,
            )

        # 2. Unambiguous rule-based direct execution via AIToolExecutor
        direct = _match_direct_tool(normalized, now_vn=self._clock_vn())
        if direct is not None:
            tool_id, arguments = direct
            result, _payload = await run_in_threadpool(
                self._execute_tool_sync,
                bound,
                tool_id=tool_id,
                arguments=arguments,
            )
            answer, insufficient = _format_direct_answer(result)
            return AIAskResponse(
                answer=answer,
                evidence=[_build_evidence(result)],
                insufficient_data=insufficient,
            )

        # 3. Complex natural-language execution via Gemini Function Calling
        provider = self._provider_factory()
        collected_results: list[ToolResult] = []
        turn = await provider.generate_turn(
            message, timeout_seconds=self._remaining_provider_timeout(bound)
        )

        max_rounds = bound.budget.max_calls
        rounds = 0
        while turn.function_calls:
            rounds += 1
            if rounds > max_rounds:
                break
            tool_responses: list[ToolResponseItem] = []
            for call in turn.function_calls:
                if call.name not in _ALLOWED_TOOLS:
                    raise DomainValidationError(
                        "Công cụ do AI đề xuất không nằm trong danh sách được phép."
                    )
                validated_tool: Literal[
                    "get_sales_summary",
                    "get_top_products",
                    "get_slow_products",
                    "get_low_stock",
                ] = call.name  # type: ignore[assignment]
                result, payload = await run_in_threadpool(
                    self._execute_tool_sync,
                    bound,
                    tool_id=validated_tool,
                    arguments=call.arguments,
                )
                collected_results.append(result)
                tool_responses.append(
                    ToolResponseItem(name=validated_tool, payload=payload)
                )

            bound.budget.check_deadline()
            turn = await provider.submit_tool_results(
                turn.conversation_state,
                tuple(tool_responses),
                timeout_seconds=self._remaining_provider_timeout(bound),
            )

        if turn.function_calls:
            raise GeminiProviderError(
                "AI yêu cầu vượt quá số lượt gọi công cụ tối đa trong một yêu cầu."
            )

        if not collected_results:
            return AIAskResponse(
                answer=(
                    "Chưa có dữ liệu thực tế từ hệ thống để trả lời câu hỏi này. "
                    "Vui lòng nêu rõ chỉ số cần tra cứu (doanh thu, bán chạy, bán chậm "
                    "hoặc tồn kho thấp)."
                ),
                evidence=[],
                insufficient_data=True,
            )

        answer_text = (turn.text or "").strip()
        if not answer_text:
            raise GeminiProviderError("Dịch vụ AI không trả về nội dung trả lời.")

        evidence = [_build_evidence(res) for res in collected_results]
        insufficient = all(_is_insufficient_result(res) for res in collected_results)
        return AIAskResponse(
            answer=answer_text,
            evidence=evidence,
            insufficient_data=insufficient,
        )

    def _remaining_provider_timeout(self, bound: BoundToolRequest) -> float:
        bound.budget.check_deadline()
        elapsed = time.monotonic() - bound.budget.started_at
        remaining = bound.budget.deadline_seconds - elapsed
        if remaining <= 0:
            bound.budget.check_deadline()
        return max(0.1, min(self._gemini_timeout_seconds, remaining))
