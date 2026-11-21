# T04AB0B — AI Gợi Ý Nhập Hàng (Read-Only Reorder Advisor)

- **Task ID**: `T04AB0B`
- **Task name**: AI gợi ý nhập hàng
- **Owner**: Cao Nguyễn Anh Dương
- **Branch**: `feature/t04ab0b-ai-reorder-advisor`
- **SRS**: `AI-01`, `AI-02`, `AI-03`, `AI-04`, `ENG-05`
- **Contract**: `POST /api/v1/ai/query` (`AIQueryRequest` → `AIAskResponse`), `contracts/ai_tool_schemas.json` (`version: CF-2.4-AI-ALIGNMENT-2026-11-18`, status: `TECH_LEAD_DECISIONS_LOCKED_PENDING_DUONG_ACK_AND_RUNTIME_TESTS` — Dương ACK ghi nhận trên PR #95; giữ trạng thái pending chờ Tech Lead ACK và xác nhận cuối).

## 1. Repository Findings & Architecture
- **AI Architecture (`backend/app/modules/ai/`)**: Modular Monolith gồm `router.py` (`require_active_admin`, Redis rate limit `10/min/user`, Redis concurrency guard `1 inflight/user`, fail-closed), `tool_executor.py` (`AIToolExecutor`), `orchestrator.py` (`AIOrchestrator`), `gemini_provider.py`, và `reorder_advisor.py` (`ReadOnlyReorderAdvisor`).
- **Production Execution Flow cho Reorder Advisor**:
  1. `AIOrchestrator.handle_query` phân tích intent qua `_parse_reorder_advisor_intent(normalized)`: chỉ route khi thực sự yêu cầu gợi ý nhập hàng (loại trừ câu phủ định và câu hỏi giải thích khái niệm; hỗ trợ kỳ `1–90` ngày, mặc định `7` ngày; từ chối rõ nếu ngoài khoảng `1–90` ngày thay vì âm thầm fallback về 7 ngày).
  2. `AIOrchestrator._execute_reorder_advisor_sync` gọi `bound.executor.collect_reorder_snapshot(session, context=bound.context, analysis_days=analysis_days)` trên `AIToolExecutor` (thực thi đầy đủ `context_verifier`, `_authenticate_admin`, `ToolBudget.lock`, `ToolBudget.reserve`, `ToolBudget.check_deadline` ở mỗi trang).
  3. `collect_reorder_snapshot` phân trang có giới hạn (`page_size=50, max_pages=5`, tối đa 250 bản ghi, deduplicate `product_id`) qua `InventoryQueryService.get_low_stock` (`DEFAULT_LOW_STOCK_THRESHOLD = 5`) và `ProductAnalyticsService.slow`, đồng thời gọi `ProductAnalyticsService.sold_units_for_products` (`SalesAnalyticsRepository.get_sold_units_by_product_ids`, chỉ tính đơn `COMPLETED` trong khoảng half-open `[start_utc, end_utc_exclusive)`) để lấy số lượng bán thực tế cho toàn bộ ứng viên tồn thấp.
  4. `ReadOnlyReorderAdvisor.suggest(...)` phân loại sản phẩm, tính số lượng gợi ý tham khảo `Q = max(1, threshold - current_stock, sold_units - current_stock)` chỉ khi đủ bằng chứng, và trả về `ReorderSuggestionReport` (map sang `AIAskResponse` giữ nguyên contract frontend).
- **Docker Fix (`gemini_provider.py`)**: Bổ sung `_FALLBACK_TOOL_INPUT_SCHEMAS` khớp 100% `contracts/ai_tool_schemas.json` khi container Docker không có `/contracts/`.

## 2. Classification, Partial Data & Error Handling
- **`PRIORITY_RESTOCK`**: `quantity <= threshold`, có `sold_units > 0` đã xác minh, và đã loại trừ nhóm bán chậm (nguồn `get_slow_products` đầy đủ hoặc `sold_units > 2` trong `<= 30` ngày).
- **`UNVERIFIED_SLOW_MOVING`**: `quantity <= threshold`, `1 <= sold_units <= 2`, nhưng nguồn `get_slow_products` bị truncate hoặc lỗi → `suggested_quantity = None`, `confidence = "INSUFFICIENT"`, `status = "PARTIAL_DATA"`, `insufficient_data = True` (không xếp dưới nhãn ưu tiên nhập hàng).
- **`LOW_STOCK_NO_SALES_HISTORY`**: `quantity <= threshold`, ghi nhận `0` lượt bán thực tế (`confidence = "LOW"`) hoặc thiếu dữ liệu bán (`sold_units = None`, `confidence = "INSUFFICIENT"`) → `suggested_quantity = None`.
- **`SLOW_MOVING_HOLD`**: thuộc nhóm bán chậm 30 ngày (`<= 2` đơn vị / 30 ngày) → `suggested_quantity = None`.
- **Summary Visibility**: Mỗi nhóm hiển thị tối đa 5 sản phẩm kèm tổng số lượng và số sản phẩm còn ẩn (`hiển thị 5/N sản phẩm, còn N-5 sản phẩm khác chưa liệt kê`).
- **Sanitized Source Errors**: Không trả raw exception, SQL hoặc DSN cho client; chuẩn hóa qua `_SAFE_SOURCE_ERROR_MESSAGES` và ghi structured warning `ai_reorder_source_error` (`request_id`, `tool_id`, `error_type`, `error_code`).

## 3. Files Added / Modified
- `backend/app/modules/analytics/repository.py`: thêm `SalesAnalyticsRepository.get_sold_units_by_product_ids`.
- `backend/app/modules/analytics/service.py`: thêm `ProductAnalyticsService.sold_units_for_products`.
- `backend/app/modules/ai/tool_executor.py`: thêm `ReorderSnapshot` và `AIToolExecutor.collect_reorder_snapshot`.
- `backend/app/modules/ai/reorder_advisor.py`: `ReadOnlyReorderAdvisor` và DTOs.
- `backend/app/modules/ai/orchestrator.py`: `_parse_reorder_advisor_intent` và `_execute_reorder_advisor_sync`.
- `backend/app/modules/ai/gemini_provider.py`: `_FALLBACK_TOOL_INPUT_SCHEMAS` cho môi trường Docker.
- `backend/tests/modules/ai/test_reorder_advisor.py`: 12 unit/HTTP/security/prompt-injection/read-only tests.
- `backend/tests/integration/test_reorder_advisor_mysql.py`: MySQL 8.4 integration test cho `sold_units_for_products` (half-open UTC, `COMPLETED` vs `CANCELLED`, trả đủ mọi `product_id` kể cả `0` bán) và read-only DB invariant.

## 4. Verification & Test Evidence
- `ruff format --check app/modules/ai app/modules/analytics tests/modules/ai tests/integration/test_reorder_advisor_mysql.py`: **PASS**
- `ruff check app/modules/ai app/modules/analytics tests/modules/ai tests/integration/test_reorder_advisor_mysql.py`: **PASS**
- `pytest tests/modules/ai/test_reorder_advisor.py -v`: **12 passed**
- Full backend unit/API suite (`pytest -m "not integration and not rabbitmq_integration"`): verified locally and via GitHub Actions `Backend CI / Ruff + unit`.
- MySQL 8.4 integration (`backend/tests/integration/test_reorder_advisor_mysql.py`): verified via `Backend CI / MySQL integration` on isolated `mysql:8.4` test database.
- Live Docker E2E Smoke Test (`POST http://127.0.0.1:8001/api/v1/ai/query` với MySQL 8.4 + Redis + `gemini-3.1-flash-lite`): `"Sản phẩm bán chạy 7 ngày qua"` → `200 OK`, `"Gợi ý nhập hàng"` → `200 OK`.

## 5. Known Limitations (V1 Scope)
- Giới hạn phân trang an toàn mặc định: `5 pages x 50 items = 250` sản phẩm mỗi nguồn để bảo vệ deadline 15s; vượt quá sẽ báo rõ `PARTIAL_DATA` / `insufficient_data=True`.
- Công thức đề xuất chưa bao gồm supplier lead time hoặc safety stock (đúng phạm vi V1).
- AI hoàn toàn read-only; quản trị viên tự tạo và xác nhận phiếu nhập tại mục Purchasing.
