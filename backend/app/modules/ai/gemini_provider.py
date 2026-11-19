"""Google Gemini LLM provider for RetailOps AI Assistant (isolated from DB)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import PROJECT_ROOT
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

APPROVED_TOOL_NAMES: tuple[str, ...] = (
    "get_sales_summary",
    "get_top_products",
    "get_slow_products",
    "get_low_stock",
)

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "get_sales_summary": (
        "Lấy tổng hợp doanh thu (VND), số đơn hoàn thành, số đơn hủy và giá trị "
        "đơn trung bình (AOV) trong khoảng ngày YYYY-MM-DD (múi giờ Việt Nam)."
    ),
    "get_top_products": (
        "Lấy danh sách sản phẩm bán chạy nhất theo số lượng bán và doanh thu "
        "trong N ngày gần nhất (days: 1..90, limit: 1..20)."
    ),
    "get_slow_products": (
        "Lấy danh sách sản phẩm bán chậm hoặc tồn kho lâu chưa bán được "
        "(days: 1..90, limit: 1..20)."
    ),
    "get_low_stock": (
        "Lấy danh sách sản phẩm có tồn kho thấp hơn hoặc bằng ngưỡng cảnh báo "
        "(limit: 1..20)."
    ),
}

_SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý phân tích vận hành cửa hàng RetailOps dành riêng cho quản trị viên. "
    "Chỉ sử dụng 4 công cụ được cung cấp để tra cứu số liệu thực tế của cửa hàng. "
    "Tuyệt đối không bịa đặt số liệu, không suy đoán giá trị không có trong kết quả "
    "công cụ, không trả về SQL hay thông tin nội bộ hệ thống. "
    "Nếu dữ liệu từ công cụ rỗng hoặc không đủ để kết luận, hãy nêu rõ phần dữ liệu "
    "còn thiếu bằng tiếng Việt ngắn gọn, rõ ràng."
)


class GeminiProviderError(AppException):
    """Raised when Gemini authentication, network, or response payload fails."""

    def __init__(
        self,
        message: str = "Dịch vụ AI tạm thời không khả dụng.",
    ) -> None:
        super().__init__("AI_PROVIDER_UNAVAILABLE", message, 503)


class GeminiTimeoutError(AppException):
    """Raised when Gemini does not respond within the configured timeout."""

    def __init__(
        self,
        message: str = "Dịch vụ AI phản hồi quá thời gian cho phép.",
    ) -> None:
        super().__init__("AI_PROVIDER_TIMEOUT", message, 504)


class GeminiQuotaExceededError(AppException):
    """Raised when Gemini API quota or rate limit is exhausted."""

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            "AI_QUOTA_EXHAUSTED",
            "Hạn mức dịch vụ AI tạm thời đã hết. Vui lòng thử lại sau.",
            429,
            headers={"Retry-After": str(max(1, retry_after))},
        )


@dataclass(frozen=True)
class ProviderFunctionCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProviderTurnResponse:
    text: str | None
    function_calls: tuple[ProviderFunctionCall, ...]
    conversation_state: Any = None


@dataclass(frozen=True)
class ToolResponseItem:
    name: str
    payload: dict[str, Any]


class LLMProvider(Protocol):
    """Abstract provider interface for dependency injection and unit testing."""

    async def generate_turn(
        self,
        user_message: str,
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse: ...

    async def submit_tool_results(
        self,
        conversation_state: Any,
        tool_responses: tuple[ToolResponseItem, ...],
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse: ...


@lru_cache(maxsize=1)
def load_approved_tool_schemas(
    contracts_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load the 4 frozen tool input JSON schemas from contracts/ai_tool_schemas.json."""
    path = contracts_path or (PROJECT_ROOT / "contracts" / "ai_tool_schemas.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    tools = raw.get("tools", {})
    schemas: dict[str, dict[str, Any]] = {}
    for name in APPROVED_TOOL_NAMES:
        tool_def = tools.get(name)
        if not isinstance(tool_def, dict) or not isinstance(
            tool_def.get("input"), dict
        ):
            raise RuntimeError(f"Missing approved tool contract for {name}")
        schemas[name] = tool_def["input"]
    return schemas


def build_gemini_function_declarations() -> list[types.FunctionDeclaration]:
    """Build Gemini FunctionDeclarations strictly for the 4 approved tools."""
    schemas = load_approved_tool_schemas()
    declarations: list[types.FunctionDeclaration] = []
    for name in APPROVED_TOOL_NAMES:
        input_schema = dict(schemas[name])
        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=_TOOL_DESCRIPTIONS[name],
                parameters_json_schema=input_schema,
            )
        )
    return declarations


class GeminiProvider:
    """Google Gemini SDK adapter with strict timeout and zero DB/secret leakage."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise GeminiProviderError()
        if not model or not model.strip():
            raise GeminiProviderError()
        self._model = model.strip()
        self._default_timeout = max(0.5, float(timeout_seconds))
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=max(1000, int(self._default_timeout * 1000))
            ),
        )
        self._tools = [
            types.Tool(function_declarations=build_gemini_function_declarations())
        ]

    def _build_config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            temperature=0.0,
            tools=self._tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )

    async def generate_turn(
        self,
        user_message: str,
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse:
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        ]
        return await self._call_gemini(contents, timeout_seconds=timeout_seconds)

    async def submit_tool_results(
        self,
        conversation_state: Any,
        tool_responses: tuple[ToolResponseItem, ...],
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse:
        if not isinstance(conversation_state, list):
            raise GeminiProviderError("Trạng thái hội thoại AI không hợp lệ.")
        response_parts = [
            types.Part.from_function_response(name=item.name, response=item.payload)
            for item in tool_responses
        ]
        next_contents = [
            *conversation_state,
            types.Content(role="user", parts=response_parts),
        ]
        return await self._call_gemini(next_contents, timeout_seconds=timeout_seconds)

    async def _call_gemini(
        self,
        contents: list[types.Content],
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse:
        effective_timeout = max(0.1, min(self._default_timeout, float(timeout_seconds)))
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=self._build_config(),
                ),
                timeout=effective_timeout,
            )
        except TimeoutError as error:
            logger.warning("Gemini request timed out after %.2fs", effective_timeout)
            raise GeminiTimeoutError() from error
        except genai_errors.APIError as error:
            status_code = getattr(error, "code", None)
            if status_code == 429:
                logger.warning("Gemini API quota exceeded (status=429)")
                raise GeminiQuotaExceededError() from error
            if status_code in {401, 403}:
                logger.error(
                    "Gemini API authentication rejected (status=%s)", status_code
                )
                raise GeminiProviderError() from error
            logger.warning("Gemini API error (status=%s)", status_code)
            raise GeminiProviderError() from error
        except (OSError, ValueError) as error:
            logger.warning("Gemini transport/client error: %s", type(error).__name__)
            raise GeminiProviderError() from error

        return self._parse_response(contents, response)

    def _parse_response(
        self,
        prior_contents: list[types.Content],
        response: types.GenerateContentResponse,
    ) -> ProviderTurnResponse:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            raise GeminiProviderError("Dịch vụ AI trả về phản hồi rỗng.")
        model_content = getattr(candidates[0], "content", None)
        if model_content is None:
            raise GeminiProviderError("Dịch vụ AI trả về nội dung không hợp lệ.")

        parsed_calls: list[ProviderFunctionCall] = []
        raw_calls = getattr(response, "function_calls", None) or []
        for fc in raw_calls:
            name = getattr(fc, "name", None)
            args = getattr(fc, "args", None)
            if not isinstance(name, str) or not name.strip():
                raise GeminiProviderError("Dịch vụ AI trả về tên công cụ không hợp lệ.")
            if args is None:
                args_dict: dict[str, Any] = {}
            elif isinstance(args, dict):
                args_dict = dict(args)
            else:
                raise GeminiProviderError(
                    "Dịch vụ AI trả về tham số công cụ không hợp lệ."
                )
            parsed_calls.append(
                ProviderFunctionCall(name=name.strip(), arguments=args_dict)
            )

        text_value: str | None = None
        if not parsed_calls:
            raw_text = getattr(response, "text", None)
            if isinstance(raw_text, str) and raw_text.strip():
                text_value = raw_text.strip()
            else:
                raise GeminiProviderError("Dịch vụ AI không trả về câu trả lời hợp lệ.")

        updated_state = [*prior_contents, model_content]
        return ProviderTurnResponse(
            text=text_value,
            function_calls=tuple(parsed_calls),
            conversation_state=updated_state,
        )
