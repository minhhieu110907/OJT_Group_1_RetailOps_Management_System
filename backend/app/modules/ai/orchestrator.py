"""Hybrid AI orchestrator: Gemini, allowlist validation, and AIToolExecutor."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
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
from app.modules.ai.reorder_advisor import (
    ReadOnlyReorderAdvisor,
    ReorderSuggestionReport,
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

_RELATIVE_DAYS_RE = re.compile(
    r"\b(\d+)\s*(?:ngày|ngay|days?)\s*"
    r"(?:gần nhất|gan nhat|qua|trở lại đây|tro lai day|vừa qua|vua qua)?\b"
)
_RELATIVE_WEEKS_RE = re.compile(
    r"\b(\d+)\s*(?:tuần|tuan|weeks?)\s*(?:gần nhất|gan nhat|qua|vừa qua|vua qua)?\b"
)
_RELATIVE_MONTHS_RE = re.compile(
    r"\b(\d+)\s*(?:tháng|thang|months?)\s*"
    r"(?:gần nhất|gan nhat|qua|trở lại đây|tro lai day|vừa qua|vua qua)?\b"
)
_TOP_LIMIT_RE = re.compile(r"\btop\s*(\d+)\b")
_LEADING_PRODUCT_LIMIT_RE = re.compile(
    r"\b(\d+)\s*(?:sản phẩm|san pham|mặt hàng|mat hang|sp)\b"
)
_TOP_N_PRODUCT_RE = re.compile(
    r"\btop\s*(?:\d+\s*)?(?:sản phẩm|san pham|mặt hàng|mat hang|sp)\b"
)

_SALES_KEYWORDS: tuple[str, ...] = (
    "doanh thu",
    "doanh số",
    "doanh so",
    "số đơn",
    "so don",
    "tổng đơn",
    "tong don",
    "đơn hoàn thành",
    "don hoan thanh",
    "đơn hoàn tất",
    "don hoan tat",
    "đơn hủy",
    "don huy",
    "giá trị đơn trung bình",
    "gia tri don trung binh",
    "aov",
)
_OVERVIEW_KEYWORDS: tuple[str, ...] = (
    "tình hình bán hàng",
    "tinh hinh ban hang",
    "tình hình kinh doanh",
    "tinh hinh kinh doanh",
    "báo cáo bán hàng",
    "bao cao ban hang",
    "tổng quan cửa hàng",
    "tong quan cua hang",
    "tổng quan bán hàng",
    "tong quan ban hang",
)
_SALES_UNSUPPORTED_HINTS: tuple[str, ...] = (
    "cao nhất",
    "cao nhat",
    "thấp nhất",
    "thap nhat",
    "lớn nhất",
    "lon nhat",
    "nhiều nhất",
    "nhieu nhat",
    "ít nhất",
    "it nhat",
    "so sánh",
    "so sanh",
    "theo ngày",
    "theo ngay",
    "từng ngày",
    "tung ngay",
    "biểu đồ",
    "bieu do",
    "xu hướng",
    "xu huong",
    "tăng trưởng",
    "tang truong",
    "đơn nào",
    "don nao",
    "chi tiết đơn",
    "chi tiet don",
)
_TOP_PRODUCT_KEYWORDS: tuple[str, ...] = (
    "bán chạy",
    "ban chay",
    "chạy nhất",
    "chay nhat",
    "bán nhiều nhất",
    "ban nhieu nhat",
    "bán được nhiều nhất",
    "ban duoc nhieu nhat",
    "bán tốt nhất",
    "ban tot nhat",
    "bán mạnh",
    "ban manh",
    "tiêu thụ nhiều nhất",
    "tieu thu nhieu nhat",
    "tiêu thụ mạnh nhất",
    "tieu thu manh nhat",
    "mua nhiều nhất",
    "mua nhieu nhat",
    "đặt nhiều nhất",
    "dat nhieu nhat",
    "đắt khách nhất",
    "dat khach nhat",
    "hot nhất",
    "hot nhat",
    "best seller",
    "bestseller",
    "top bán chạy",
    "top ban chay",
)
_PRODUCT_REVENUE_SUPERLATIVE_KEYWORDS: tuple[str, ...] = (
    "doanh thu cao nhất",
    "doanh thu cao nhat",
    "doanh thu nhiều nhất",
    "doanh thu nhieu nhat",
    "doanh thu lớn nhất",
    "doanh thu lon nhat",
    "doanh số cao nhất",
    "doanh so cao nhat",
)
_SLOW_PRODUCT_KEYWORDS: tuple[str, ...] = (
    "bán chậm",
    "ban cham",
    "bán ế",
    "ban e",
    "ế ẩm",
    "e am",
    "ế nhất",
    "e nhat",
    "hàng ế",
    "hang e",
    "hàng chậm",
    "hang cham",
    "bán ít nhất",
    "ban it nhat",
    "ít bán nhất",
    "it ban nhat",
    "bán kém nhất",
    "ban kem nhat",
    "khó bán",
    "kho ban",
    "không bán được",
    "khong ban duoc",
    "chưa bán được",
    "chua ban duoc",
    "ít người mua nhất",
    "it nguoi mua nhat",
    "tồn kho lâu",
    "ton kho lau",
    "tồn lâu nhất",
    "ton lau nhat",
    "hàng tồn lâu",
    "hang ton lau",
    "tồn đọng",
    "ton dong",
    "chậm nhất",
    "cham nhat",
)
_LOW_STOCK_SUBSTRINGS: tuple[str, ...] = (
    "tồn kho thấp",
    "ton kho thap",
    "tồn thấp",
    "ton thap",
    "tồn kho ít nhất",
    "ton kho it nhat",
    "tồn ít nhất",
    "ton it nhat",
    "còn ít nhất",
    "con it nhat",
    "sắp hết hàng",
    "sap het hang",
    "hàng sắp hết",
    "hang sap het",
    "sắp hết",
    "sap het",
    "gần hết",
    "gan het",
    "hết hàng",
    "het hang",
    "cạn kho",
    "can kho",
    "thiếu hàng",
    "thieu hang",
    "hết tồn",
    "het ton",
    "dưới ngưỡng tồn",
    "duoi nguong ton",
    "tồn kho dưới ngưỡng",
    "ton kho duoi nguong",
    "cảnh báo tồn kho",
    "canh bao ton kho",
)
_PRODUCT_MENTION_KEYWORDS: tuple[str, ...] = (
    "sản phẩm",
    "san pham",
    "mặt hàng",
    "mat hang",
)
_EXPLICIT_DATE_HINT_RE = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:tháng|thang)\s+\d{1,2}\b"
)
_UNSUPPORTED_RELATIVE_PERIOD_RE = re.compile(r"\b(?:quý|quy|năm|nam|years?)\b")

_REORDER_ADVISOR_KEYWORDS: tuple[str, ...] = (
    "gợi ý nhập hàng",
    "goi y nhap hang",
    "đề xuất nhập hàng",
    "de xuat nhap hang",
    "tư vấn nhập hàng",
    "tu van nhap hang",
    "nên nhập hàng",
    "nen nhap hang",
    "nên nhập thêm",
    "nen nhap them",
    "nên nhập kho",
    "nen nhap kho",
    "nhập hàng gì",
    "nhap hang gi",
    "nhập thêm gì",
    "nhap them gi",
    "nhập kho gì",
    "nhap kho gi",
    "nhập gì",
    "nhap gi",
    "sản phẩm cần nhập",
    "san pham can nhap",
    "sản phẩm nào cần nhập",
    "san pham nao can nhap",
    "sản phẩm cần nhập thêm",
    "san pham can nhap them",
    "sản phẩm nên nhập",
    "san pham nen nhap",
    "cần nhập thêm",
    "can nhap them",
    "cần nhập hàng",
    "can nhap hang",
    "cần nhập kho",
    "can nhap kho",
    "cần nhập gì",
    "can nhap gi",
    "mặt hàng cần nhập",
    "mat hang can nhap",
    "hàng cần nhập",
    "hang can nhap",
    "cần nhập",
    "can nhap",
    "nhập thêm",
    "nhap them",
    "gợi ý nhập",
    "goi y nhap",
    "bổ sung hàng",
    "bo sung hang",
    "bổ sung kho",
    "bo sung kho",
    "cần bổ sung",
    "can bo sung",
    "đặt hàng thêm",
    "dat hang them",
    "cần đặt thêm",
    "can dat them",
    "nên đặt thêm",
    "nen dat them",
    "reorder advisor",
    "restock",
)


_REORDER_NEGATION_PHRASES: tuple[str, ...] = (
    "không cần",
    "khong can",
    "không muốn",
    "khong muon",
    "đừng ",
    "dung ",
    "không phải",
    "khong phai",
    "chưa cần",
    "chua can",
    "khỏi cần",
    "khoi can",
    "don't",
    "do not",
)

_REORDER_EXPLANATION_PHRASES: tuple[str, ...] = (
    "giải thích",
    "giai thich",
    "nguyên tắc",
    "nguyen tac",
    "công thức",
    "cong thuc",
    "là gì",
    "la gi",
    "cách tính",
    "cach tinh",
    "hoạt động như thế nào",
    "hoat dong nhu the nao",
    "explain",
    "how does",
)

_REORDER_DAYS_RE = re.compile(r"\b(\d+)\s*(?:ngày|ngay|days?)\b")
_REORDER_WEEKS_RE = re.compile(r"\b(\d+)\s*(?:tuần|tuan|weeks?)\b")
_REORDER_UNSUPPORTED_PERIOD_RE = re.compile(
    r"\b(?:\d+\s*)?(?:tháng|thang|months?|năm|nam|years?|quý|quy)\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
)


_EXPLICIT_REORDER_ADVISOR_PHRASES: tuple[str, ...] = (
    "gợi ý nhập hàng",
    "goi y nhap hang",
    "reorder advisor",
)


def _parse_reorder_advisor_intent(
    normalized: str,
) -> tuple[bool, int | None, str | None]:
    """Return (matched, analysis_days, error_message) for reorder advisor queries."""
    if not any(keyword in normalized for keyword in _REORDER_ADVISOR_KEYWORDS):
        return (False, None, None)
    if any(neg in normalized for neg in _REORDER_NEGATION_PHRASES):
        return (False, None, None)
    if any(exp in normalized for exp in _REORDER_EXPLANATION_PHRASES):
        return (False, None, None)
    if any(slow_kw in normalized for slow_kw in _SLOW_PRODUCT_KEYWORDS) and not any(
        explicit in normalized for explicit in _EXPLICIT_REORDER_ADVISOR_PHRASES
    ):
        return (False, None, None)

    days_match = _REORDER_DAYS_RE.search(normalized)
    if days_match is not None:
        days = int(days_match.group(1))
        if 1 <= days <= 90:
            return (True, days, None)
        return (
            True,
            None,
            f"Khoảng thời gian phân tích gợi ý nhập hàng chỉ hỗ trợ từ 1 đến 90 ngày "
            f"(bạn yêu cầu {days} ngày). Vui lòng chọn lại khoảng thời gian hợp lệ.",
        )

    weeks_match = _REORDER_WEEKS_RE.search(normalized)
    if weeks_match is not None:
        days = int(weeks_match.group(1)) * 7
        if 1 <= days <= 90:
            return (True, days, None)
        return (
            True,
            None,
            f"Khoảng thời gian phân tích gợi ý nhập hàng chỉ hỗ trợ từ 1 đến 90 ngày "
            f"(khoảng bạn yêu cầu tương đương {days} ngày). Vui lòng chọn lại số ngày "
            "hợp lệ.",
        )

    if _REORDER_UNSUPPORTED_PERIOD_RE.search(normalized) is not None:
        return (
            True,
            None,
            "Chức năng gợi ý nhập hàng hiện chỉ hỗ trợ phân tích theo số ngày từ 1 "
            "đến 90 ngày (ví dụ: 7 ngày, 30 ngày). Vui lòng nêu rõ số ngày hợp lệ.",
        )

    return (True, 7, None)


SessionFactory = Callable[[], AbstractContextManager[Session]]


def _normalize_text(message: str) -> str:
    cleaned = re.sub(r"[?!.,:;]+$", "", message.strip().lower())
    return re.sub(r"\s+", " ", cleaned)


def _has_out_of_range_period(normalized: str) -> bool:
    """Return True when a relative day/week/month count exceeds 1..90 days."""
    days_match = _RELATIVE_DAYS_RE.search(normalized)
    if days_match is not None and not (1 <= int(days_match.group(1)) <= 90):
        return True
    weeks_match = _RELATIVE_WEEKS_RE.search(normalized)
    if weeks_match is not None and not (1 <= int(weeks_match.group(1)) * 7 <= 90):
        return True
    months_match = _RELATIVE_MONTHS_RE.search(normalized)
    return months_match is not None and not (1 <= int(months_match.group(1)) * 30 <= 90)


def _resolve_relative_days(normalized: str, *, today_vn: Any) -> int | None:
    """Resolve supported relative period (1..90 days) from Vietnamese admin queries."""
    if _UNSUPPORTED_RELATIVE_PERIOD_RE.search(normalized):
        return None

    days_match = _RELATIVE_DAYS_RE.search(normalized)
    if days_match is not None:
        days = int(days_match.group(1))
        return days if 1 <= days <= 90 else None

    weeks_match = _RELATIVE_WEEKS_RE.search(normalized)
    if weeks_match is not None:
        days = int(weeks_match.group(1)) * 7
        return days if 1 <= days <= 90 else None

    months_match = _RELATIVE_MONTHS_RE.search(normalized)
    if months_match is not None:
        days = int(months_match.group(1)) * 30
        return days if 1 <= days <= 90 else None

    if "nửa tháng" in normalized or "nua thang" in normalized:
        return 15
    if "hôm nay" in normalized or "hom nay" in normalized:
        return 1
    if "tuần này" in normalized or "tuan nay" in normalized:
        return today_vn.weekday() + 1
    if any(
        phrase in normalized
        for phrase in (
            "tuần qua",
            "tuan qua",
            "tuần vừa qua",
            "tuan vua qua",
            "tuần gần nhất",
            "tuan gan nhat",
        )
    ):
        return 7
    if "tháng này" in normalized or "thang nay" in normalized:
        return today_vn.day
    if any(
        phrase in normalized
        for phrase in (
            "tháng qua",
            "thang qua",
            "tháng vừa qua",
            "thang vua qua",
            "tháng gần nhất",
            "thang gan nhat",
        )
    ):
        return 30
    return None


def _resolve_calendar_sales_range(
    normalized: str, *, today_vn: Any
) -> tuple[str, str] | None:
    """Resolve exact calendar ranges (yesterday, last week, last month) for sales."""
    if "hôm qua" in normalized or "hom qua" in normalized:
        yday = (today_vn - timedelta(days=1)).isoformat()
        return (yday, yday)
    if "tuần trước" in normalized or "tuan truoc" in normalized:
        this_mon = today_vn - timedelta(days=today_vn.weekday())
        prev_mon = this_mon - timedelta(days=7)
        prev_sun = this_mon - timedelta(days=1)
        return (prev_mon.isoformat(), prev_sun.isoformat())
    if "tháng trước" in normalized or "thang truoc" in normalized:
        first_this_month = today_vn.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        first_prev_month = last_prev_month.replace(day=1)
        return (first_prev_month.isoformat(), last_prev_month.isoformat())
    return None


def _has_past_calendar_period(normalized: str) -> bool:
    return any(
        phrase in normalized
        for phrase in ("tuần trước", "tuan truoc", "tháng trước", "thang truoc")
    )


def _extract_limit(normalized: str, *, default: int) -> int | None:
    match = _TOP_LIMIT_RE.search(normalized) or _LEADING_PRODUCT_LIMIT_RE.search(
        normalized
    )
    if match is None:
        return default
    limit = int(match.group(1))
    return limit if 1 <= limit <= 20 else None


def _match_direct_tools(
    normalized: str, *, now_vn: datetime | None = None
) -> list[tuple[ToolId, dict[str, Any]]] | None:
    """Match common Admin queries to deterministic read-only tool calls."""
    current = now_vn or datetime.now(_VN_TZ)
    today_vn = current.date()

    # 1. Exact legacy phrases & explicit YYYY-MM-DD range
    if normalized in _LOW_STOCK_PHRASES:
        return [("get_low_stock", {"limit": 10})]
    if normalized in _TODAY_SALES_PHRASES:
        today_iso = today_vn.isoformat()
        return [("get_sales_summary", {"start_date": today_iso, "end_date": today_iso})]
    range_match = _DATE_RANGE_SALES_RE.match(normalized)
    if range_match:
        return [
            (
                "get_sales_summary",
                {"start_date": range_match.group(1), "end_date": range_match.group(2)},
            )
        ]

    # Skip explicit calendar dates (e.g. "18/11", "tháng 10"), unsupported periods,
    # explanation/theory questions, or negated multi-clause prompts.
    if (
        _EXPLICIT_DATE_HINT_RE.search(normalized)
        or _UNSUPPORTED_RELATIVE_PERIOD_RE.search(normalized)
        or any(exp in normalized for exp in _REORDER_EXPLANATION_PHRASES)
        or any(neg in normalized for neg in _REORDER_NEGATION_PHRASES)
    ):
        return None

    has_sales = any(kw in normalized for kw in _SALES_KEYWORDS)
    has_overview = any(kw in normalized for kw in _OVERVIEW_KEYWORDS)
    has_slow = any(kw in normalized for kw in _SLOW_PRODUCT_KEYWORDS)
    has_low = any(kw in normalized for kw in _LOW_STOCK_SUBSTRINGS)
    has_product_word = any(kw in normalized for kw in _PRODUCT_MENTION_KEYWORDS)
    has_top_n_product = _TOP_N_PRODUCT_RE.search(normalized) is not None
    is_product_revenue_top = (has_product_word or has_top_n_product) and any(
        kw in normalized for kw in _PRODUCT_REVENUE_SUPERLATIVE_KEYWORDS
    )
    has_top_selling = (
        any(kw in normalized for kw in _TOP_PRODUCT_KEYWORDS) or is_product_revenue_top
    )
    has_top = has_top_selling or (has_top_n_product and not has_slow and not has_low)

    # 1b. Product ranked by highest revenue (e.g. "Top 3 SP doanh thu cao nhất 1 tháng")
    if (
        is_product_revenue_top
        and "doanh thu và" not in normalized
        and "doanh thu va" not in normalized
        and not has_slow
        and not has_low
    ):
        limit = _extract_limit(normalized, default=5)
        if (
            limit is None
            or _has_out_of_range_period(normalized)
            or _has_past_calendar_period(normalized)
        ):
            return None
        days = _resolve_relative_days(normalized, today_vn=today_vn) or 7
        return [("get_top_products", {"days": days, "limit": limit})]

    # 2. Combined Sales + Top Products (or store overview)
    if (
        (has_overview or (has_sales and (has_top or has_product_word)))
        and not has_slow
        and not has_low
    ):
        limit = _extract_limit(normalized, default=5)
        if limit is None or _has_out_of_range_period(normalized):
            return None
        cal_range = _resolve_calendar_sales_range(normalized, today_vn=today_vn)
        if cal_range is not None:
            if "hôm qua" in normalized or "hom qua" in normalized:
                return [
                    (
                        "get_sales_summary",
                        {"start_date": cal_range[0], "end_date": cal_range[1]},
                    ),
                    ("get_top_products", {"days": 2, "limit": limit}),
                ]
            if has_overview and not has_top and not has_product_word:
                return [
                    (
                        "get_sales_summary",
                        {"start_date": cal_range[0], "end_date": cal_range[1]},
                    )
                ]
            return None
        days = _resolve_relative_days(normalized, today_vn=today_vn)
        if days is None and has_overview:
            days = 7
        if days is not None:
            start_iso = (today_vn - timedelta(days=days - 1)).isoformat()
            end_iso = today_vn.isoformat()
            return [
                ("get_sales_summary", {"start_date": start_iso, "end_date": end_iso}),
                ("get_top_products", {"days": days, "limit": limit}),
            ]
        return None

    # 3. Sales summary with relative/calendar period (or default today VN per contract)
    if (
        has_sales
        and not has_top
        and not has_slow
        and not has_low
        and not has_product_word
    ):
        if any(kw in normalized for kw in _SALES_UNSUPPORTED_HINTS):
            return None
        if _has_out_of_range_period(normalized):
            return None
        cal_range = _resolve_calendar_sales_range(normalized, today_vn=today_vn)
        if cal_range is not None:
            return [
                (
                    "get_sales_summary",
                    {"start_date": cal_range[0], "end_date": cal_range[1]},
                )
            ]
        days = _resolve_relative_days(normalized, today_vn=today_vn)
        if days is not None:
            start_iso = (today_vn - timedelta(days=days - 1)).isoformat()
            end_iso = today_vn.isoformat()
            return [
                ("get_sales_summary", {"start_date": start_iso, "end_date": end_iso})
            ]
        today_iso = today_vn.isoformat()
        return [("get_sales_summary", {"start_date": today_iso, "end_date": today_iso})]

    # 4. Top products (e.g. "Top 5 sản phẩm bán chạy nhất trong 1 tháng")
    if has_top and not has_sales and not has_slow and not has_low:
        limit = _extract_limit(normalized, default=5)
        if (
            limit is None
            or _has_out_of_range_period(normalized)
            or _has_past_calendar_period(normalized)
        ):
            return None
        days = _resolve_relative_days(normalized, today_vn=today_vn) or 7
        return [("get_top_products", {"days": days, "limit": limit})]

    # 5. Slow-moving products (e.g. "Top 5 sản phẩm bán chậm nhất", "bán ế nhất")
    if has_slow and not has_sales and not has_top_selling and not has_low:
        limit = _extract_limit(normalized, default=10)
        if limit is None:
            return None
        return [("get_slow_products", {"limit": limit})]

    # 6. Low-stock products (e.g. "Top 5 sản phẩm tồn kho thấp nhất", "còn ít nhất")
    if has_low and not has_sales and not has_top_selling and not has_slow:
        limit = _extract_limit(normalized, default=10)
        if limit is None:
            return None
        return [("get_low_stock", {"limit": limit})]

    return None


def _match_direct_tool(
    normalized: str, *, now_vn: datetime | None = None
) -> tuple[ToolId, dict[str, Any]] | None:
    """Backward-compatible helper returning the first matched direct tool call."""
    matched = _match_direct_tools(normalized, now_vn=now_vn)
    if not matched or len(matched) != 1:
        return None
    return matched[0]


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
        period=_format_period_vn(result.source_period),
        summary=summary,
    )


def _format_period_vn(period_str: str | None) -> str | None:
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
    if period_str.startswith("as_of="):
        raw_ts = period_str[len("as_of=") :].split(";", 1)[0].strip()
        try:
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            date_str = dt.astimezone(_VN_TZ).strftime("%d/%m/%Y")
            return f"30 ngày gần nhất (đến {date_str})"
        except ValueError:
            return period_str
    return period_str


def _format_direct_answer(result: ToolResult) -> tuple[str, bool]:
    data = result.data
    insufficient = _is_insufficient_result(result)
    if result.tool_id == "get_sales_summary":
        period_label = _format_period_vn(result.source_period) or "đã chọn"
        if insufficient:
            return (
                f"Chưa có dữ liệu đơn hàng trong ngày/kỳ {period_label}:\n"
                "- Đơn hoàn thành: **0**\n"
                "- Đơn hủy: **0**",
                True,
            )
        return (
            f"Tổng hợp doanh thu ngày/kỳ **{period_label}**:\n"
            f"- Doanh thu: **{data['revenue_vnd']:,} VND**\n"
            f"- Đơn hoàn thành: **{data['completed_orders']}**\n"
            f"- Đơn hủy: **{data['cancelled_orders']}**\n"
            f"- Giá trị đơn trung bình (AOV): **{data['aov_vnd']:,} VND**",
            False,
        )
    if result.tool_id == "get_top_products":
        period_label = _format_period_vn(result.source_period) or "đã chọn"
        items = data.get("items", [])
        if insufficient:
            return (
                f"Chưa có dữ liệu sản phẩm bán chạy trong kỳ **{period_label}**.",
                True,
            )
        lines = "\n".join(
            f"- **{item['name']}** (`{item['sku']}`): "
            f"đã bán **{item['sold_units']}** sản phẩm, "
            f"doanh thu **{item['revenue_vnd']:,} VND**"
            for item in items
        )
        return (
            f"Top sản phẩm bán chạy kỳ **{period_label}** "
            f"(hiển thị {len(items)}/{data['total']}):\n{lines}",
            False,
        )
    if result.tool_id == "get_slow_products":
        period_label = _format_period_vn(result.source_period) or "30 ngày gần nhất"
        items = data.get("items", [])
        if insufficient:
            return (
                f"Hiện không có sản phẩm nào thuộc nhóm bán chậm ({period_label}).",
                True,
            )
        lines = "\n".join(
            f"- **{item['name']}** (`{item['sku']}`): "
            f"đã bán **{item['sold_units']}** sản phẩm"
            + (
                f", tồn kho **{item['quantity']}**"
                if item.get("quantity") is not None
                else ""
            )
            for item in items
        )
        return (
            f"Danh sách sản phẩm bán chậm ({period_label}, bán <= 2 SP/30 ngày "
            f"và đã nhập kho > 7 ngày, hiển thị {len(items)}/{data['total']}):\n"
            f"{lines}",
            False,
        )
    if result.tool_id == "get_low_stock":
        items = data.get("items", [])
        if insufficient:
            return ("Hiện không có sản phẩm nào dưới ngưỡng tồn kho thấp.", True)
        lines = "\n".join(
            f"- **{item['name']}** (`{item['sku']}`): còn {item['quantity']}"
            for item in items
        )
        return (
            f"Có {data['total']} sản phẩm tồn kho thấp "
            f"(hiển thị {len(items)}):\n{lines}",
            False,
        )
    return ("Đã hoàn tất truy vấn dữ liệu.", insufficient)


def _format_direct_answers(results: list[ToolResult]) -> tuple[str, bool]:
    if len(results) == 1:
        return _format_direct_answer(results[0])
    sections: list[str] = []
    insufficient_flags: list[bool] = []
    for res in results:
        text, is_insuff = _format_direct_answer(res)
        sections.append(text)
        insufficient_flags.append(is_insuff)
    return ("\n\n".join(sections), all(insufficient_flags))


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

    def _execute_reorder_advisor_sync(
        self, bound: BoundToolRequest, *, analysis_days: int = 7
    ) -> ReorderSuggestionReport:
        bound.budget.check_deadline()
        with self._session_factory() as session:
            snapshot = bound.executor.collect_reorder_snapshot(
                session,
                context=bound.context,
                analysis_days=analysis_days,
            )
        bound.budget.check_deadline()
        return ReadOnlyReorderAdvisor().suggest(
            low_stock_result=snapshot.low_stock_result,
            product_sales_by_id=snapshot.product_sales_by_id,
            sales_period=_format_period_vn(snapshot.sales_period),
            slow_products_result=snapshot.slow_products_result,
            analysis_days=snapshot.analysis_days,
            low_stock_truncated=snapshot.low_stock_truncated,
            low_stock_total_available=snapshot.low_stock_total_available,
            slow_products_truncated=snapshot.slow_products_truncated,
            source_errors=snapshot.source_errors,
        )

    async def handle_query(
        self,
        *,
        message: str,
        bound: BoundToolRequest,
    ) -> AIAskResponse:
        bound.budget.check_deadline()
        normalized = _normalize_text(message)

        # 1. Fixed non-data intents: zero Gemini tokens, zero DB work
        if normalized in _GREETING_EXACT:
            bound.budget.check_deadline()
            return AIAskResponse(
                answer=(
                    "Xin chào! Tôi có thể hỗ trợ tra cứu doanh thu, sản phẩm bán chạy, "
                    "sản phẩm bán chậm và tồn kho thấp của cửa hàng."
                ),
                evidence=[],
                insufficient_data=False,
            )
        if normalized in _HELP_EXACT:
            bound.budget.check_deadline()
            return AIAskResponse(
                answer=(
                    "Tôi hỗ trợ 4 nhóm tra cứu dữ liệu thực tế: tổng hợp doanh thu "
                    "theo ngày, sản phẩm bán chạy, bán chậm và tồn kho thấp."
                ),
                evidence=[],
                insufficient_data=False,
            )

        # 2a. Read-only Reorder Advisor [T04AB0B] via allowlisted AIToolExecutor
        # Evaluated before low-stock/slow fast-path so reorder prompts route here.
        is_reorder, analysis_days, period_error = _parse_reorder_advisor_intent(
            normalized
        )
        if is_reorder:
            bound.budget.check_deadline()
            if period_error is not None or analysis_days is None:
                return AIAskResponse(
                    answer=period_error
                    or "Khoảng thời gian phân tích gợi ý nhập hàng không hợp lệ.",
                    evidence=[],
                    insufficient_data=True,
                )
            report = await run_in_threadpool(
                self._execute_reorder_advisor_sync,
                bound,
                analysis_days=analysis_days,
            )
            bound.budget.check_deadline()
            return AIAskResponse(
                answer=report.summary,
                evidence=report.evidence,
                insufficient_data=report.insufficient_data,
            )

        # 2b. Fast-path deterministic Admin queries via AIToolExecutor (0 Gemini tokens)
        direct_calls = _match_direct_tools(normalized, now_vn=self._clock_vn())
        if direct_calls is not None:
            direct_results: list[ToolResult] = []
            for tool_id, arguments in direct_calls:
                bound.budget.check_deadline()
                result, _payload = await run_in_threadpool(
                    self._execute_tool_sync,
                    bound,
                    tool_id=tool_id,
                    arguments=arguments,
                )
                bound.budget.check_deadline()
                direct_results.append(result)
            answer, insufficient = _format_direct_answers(direct_results)
            bound.budget.check_deadline()
            return AIAskResponse(
                answer=answer,
                evidence=[_build_evidence(res) for res in direct_results],
                insufficient_data=insufficient,
            )

        # 3. Complex natural-language execution via Gemini Function Calling
        provider = self._provider_factory()
        collected_results: list[ToolResult] = []
        turn = await provider.generate_turn(
            message, timeout_seconds=self._remaining_provider_timeout(bound)
        )
        bound.budget.check_deadline()

        max_rounds = bound.budget.max_calls
        rounds = 0
        while turn.function_calls:
            rounds += 1
            if rounds > max_rounds:
                break
            tool_responses: list[ToolResponseItem] = []
            for call in turn.function_calls:
                bound.budget.check_deadline()
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
                bound.budget.check_deadline()
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
            bound.budget.check_deadline()

        if turn.function_calls:
            raise GeminiProviderError(
                "AI yêu cầu vượt quá số lượt gọi công cụ tối đa trong một yêu cầu."
            )

        if not collected_results:
            bound.budget.check_deadline()
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
        bound.budget.check_deadline()
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
