# T04AB0B — AI Gợi Ý Nhập Hàng (Read-Only Reorder Advisor)

- **Task ID**: `T04AB0B`
- **Task name**: AI gợi ý nhập hàng
- **Owner**: Cao Nguyễn Anh Dương
- **Branch**: `feature/t04ab0b-ai-reorder-advisor`
- **Contract**: `POST /api/v1/ai/query` (`AIQueryRequest` -> `AIAskResponse`), `ReadOnlyReorderAdvisor.suggest -> ReorderSuggestionReport` (evidence-only DTO)

## 1. Repository Findings
- **AI Architecture (`backend/app/modules/ai/`)**: Modular Monolith với `router.py` (`require_active_admin`, Redis rate limit `10/min/user`, Redis concurrency guard `1 inflight/user`, fail-closed), `tool_executor.py` (`AIToolExecutor` với 4 tool chỉ đọc trong allowlist, kiểm tra `ADMIN` tại mỗi lần gọi, `max_calls=3`, `max_output_bytes=32768`, `deadline=15s`), `orchestrator.py` (`AIOrchestrator` hybrid routing + Gemini), và `gemini_provider.py`.
- **Reused Dependencies**: `InventoryQueryService.get_low_stock` (`DEFAULT_LOW_STOCK_THRESHOLD = 5`), `ProductAnalyticsService.top`, `ProductAnalyticsService.slow` thông qua `AIToolExecutor`.
- **Docker Fix (`gemini_provider.py`)**: Bổ sung fallback schema chuẩn của 4 tool khi container Docker không mount thư mục `contracts/ai_tool_schemas.json` ở root `/contracts/`.

## 2. Implementation
### Files Added
- `backend/app/modules/ai/reorder_advisor.py`:
  - `ReadOnlyReorderAdvisor.suggest(...)` phân loại:
    - `PRIORITY_RESTOCK`: tồn thấp (`quantity <= threshold`) và có lượng bán dương trong kỳ (`sold_units > 0`), tính `average_daily_sales = round(sold_units / analysis_days, 2)` và `suggested_quantity = max(1, threshold - quantity, sold_units - quantity)` kèm giả định minh bạch (chưa tính lead time / safety stock).
    - `LOW_STOCK_NO_SALES_HISTORY`: tồn thấp nhưng thiếu dữ liệu bán -> `suggested_quantity=None` (không bịa số lượng), `insufficient_data=True`.
    - `SLOW_MOVING_HOLD`: nằm trong `get_slow_products` (`<= 2` đơn vị / 30 ngày) -> `suggested_quantity=None`, không ưu tiên nhập thêm.
    - `NO_CANDIDATES`: không có sản phẩm dưới/bằng ngưỡng tồn thấp -> trả danh sách rỗng rõ ràng.
  - Xử lý `SOURCE_ERROR`, `PARTIAL_DATA`, và dữ liệu tool malformed mà không biến lỗi DB thành kết quả rỗng giả.
  - `run_reorder_advisor_via_executor(...)` luôn đi qua `AIToolExecutor` và không nuốt `ForbiddenError`, `DomainValidationError`, `RateLimitedError` hay budget/deadline errors.
- `backend/tests/modules/ai/test_reorder_advisor.py`: Unit, HTTP authorization (`401`/`403`/`422`), prompt injection, và read-only DB invariant tests.

### Files Modified
- `backend/app/modules/ai/orchestrator.py`: Tích hợp route câu hỏi gợi ý nhập hàng qua `ReadOnlyReorderAdvisor` sử dụng `bound.executor.execute(...)` (tối đa 3 tool calls trong allowlist, tôn trọng `ToolBudget` và `deadline`).
- `backend/app/modules/ai/gemini_provider.py`: Thêm `_FALLBACK_TOOL_INPUT_SCHEMAS` khớp 100% `contracts/ai_tool_schemas.json` khi chạy trong container Docker không có `/contracts/`.

## 3. Test Results
- `ruff format --check app/modules/ai tests/modules/ai` -> **PASS** (17 files already formatted)
- `ruff check app/modules/ai tests/modules/ai` -> **PASS** (All checks passed!)
- `pytest tests/modules/ai/test_reorder_advisor.py tests/modules/ai/test_gemini_orchestrator.py tests/modules/ai/test_tool_executor.py tests/modules/ai/test_dependencies.py -v` -> **49 passed**
- **Live Docker E2E Smoke Test (`POST http://127.0.0.1:8001/api/v1/ai/query` với MySQL 8.4 + Redis + `gemini-3.1-flash-lite`)**:
  - `"Sản phẩm bán chạy 7 ngày qua"` -> **`200 OK`** (Live Gemini Function Calling + `get_top_products`)
  - `"Gợi ý nhập hàng"` -> **`200 OK`** (`ReadOnlyReorderAdvisor` + `get_low_stock`, `get_top_products`, `get_slow_products`, `period=null` cho inventory snapshot, `insufficient_data=true` do `SK01` thiếu lịch sử bán)

## 4. Security & Read-Only Verification
- **ADMIN-only**: `STAFF` bị `403`, unauthenticated bị `401`, extra fields (`role`, `actor_id`) bị `422`.
- **Prompt Injection**: Yêu cầu tạo phiếu nhập (`create_purchase_receipt`) qua Gemini bị `DomainValidationError` (`422`); yêu cầu tạo phiếu nhập kèm câu hỏi gợi ý nhập hàng chỉ chạy 3 tool read-only và từ chối thao tác ghi.
- **Read-Only Invariant**: Đã xác minh trước và sau `POST /api/v1/ai/query`, `Inventory.quantity`, `Inventory.stock_version`, `StockMovement`, `PurchaseReceipt`, `PurchaseReceiptItem`, `Order` không thay đổi.
