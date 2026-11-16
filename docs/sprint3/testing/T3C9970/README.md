# TASK T3C9970 — TEST CASES & TEST LOG

**Người thực hiện:** Cao Nguyễn Anh Dương — Mã sinh viên: `B25DTCN165`  
**Nhánh làm việc:** `feature/t3c9970-test-cases`  
**Lịch sử nhánh & phụ thuộc:** Nhánh được khởi tạo từ `feature/t04a7df-receipt-confirmation` và đã merge `origin/develop` (`ed52c74`) tại `a02bed0`. **PR #55 (`T04A7DF`, merge commit `b28ee1f`) hiện đã MERGED vào `develop`**, không còn là dependency đang chờ merge.

---

## 1. Phạm vi kiểm thử

- **Inventory (`T04A653` + `T04A758`):**
  - `GET /api/v1/inventory` (phân trang, lọc `category_id`, `status`, `in_stock`, RBAC `ADMIN` / `STAFF`)
  - `GET /api/v1/inventory/{product_id}` (xem chi tiết tồn kho, `404`, boundary `product_id`, Auth `401`)
  - `POST /api/v1/inventory/{product_id}/adjustments` (kiểm kê tăng/giảm/về `0`, `expected_stock_version` conflict, `Idempotency-Key` replay / thiếu key / reuse mismatch, boundary `-1` và `> MAX_STOCK_QUANTITY`, `reason` rỗng, `401`, `403` với `STAFF`)
- **Purchase Receipt Confirmation (`T04A7DF`):**
  - `POST /api/v1/purchase-receipts/{receipt_id}/confirm` (xác nhận phiếu `DRAFT` hợp lệ + cộng tồn kho, `Idempotency-Key` replay / thiếu key / reuse mismatch, `expected_draft_version` conflict, từ chối phiếu `CONFIRMED` / `CANCELLED`, từ chối `Supplier` `INACTIVE`, từ chối `Product` `INACTIVE`, `404`, `401`, `403` với `STAFF`)
- **Ngoài phạm vi:** Không kiểm thử `GET /api/v1/inventory/low-stock` và `GET /api/v1/stock-movements` (thuộc task `T04A78E` của thành viên khác).

---

## 2. Môi trường kiểm thử (lần chạy tạo evidence gốc)

- **Backend API:** Docker Compose service `backend` (FastAPI + Uvicorn) tại `http://127.0.0.1:8001/api/v1` (healthcheck `200 OK {"status":"ok"}`).
- **Database & Cache:** Docker Compose `mysql:8.4` (Alembic migration `head` = `20261113_01`) và `redis:8.4-alpine`.
- **Unit tests (non-integration) cho `inventory` & `purchasing`:**
  ```powershell
  cd backend
  uv run --locked pytest tests/modules/inventory/ tests/modules/purchasing/ -m "not integration" -q
  ```
  Kết quả đã ghi nhận: `58 passed, 32 deselected in 3.34s`.
- **Lưu ý vòng Evidence Audit:** `NOT RE-EXECUTED — EVIDENCE AUDIT ONLY` (không chạy lại 40 HTTP mutation test lên database hiện hữu; chỉ kiểm toán workbook và 80 file evidence đã lưu).

---

## 3. Kiểm tra & tái lập tài liệu

- Workbook `T3C9970_Test_Cases_and_Test_Log.xlsx` là **artifact đã được tạo sẵn** trong repository (không có generator script riêng được commit trong repo).
- Có thể kiểm tra cấu trúc workbook, công thức (`COUNTIF`/`COUNTIFS`), Data Validation và Conditional Formatting bằng Python (`openpyxl`) mà không cần LibreOffice:
  ```powershell
  cd backend
  uv run --with openpyxl python -c "import openpyxl; wb=openpyxl.load_workbook('../docs/sprint3/testing/T3C9970/T3C9970_Test_Cases_and_Test_Log.xlsx', data_only=False); print('Sheets:', wb.sheetnames); print('TC rows:', wb['Test Cases'].max_row - 1); print('Summary:', [wb['Test Summary'][f'B{r}'].value for r in range(6,12)])"
  ```
- **Lưu ý tính toán công thức:** Cú pháp công thức và cấu trúc sheet đã được xác minh bằng `openpyxl`; việc mở/recalculate bằng Excel/LibreOffice GUI chưa thực hiện trên máy local do chưa cài `soffice`.

---

## 4. Tổng kết kết quả kiểm toán (40 Test Cases)

- **Tổng số Test Case:** `40` (`TC001` – `TC040`)
  - **Pass (`VERIFIED PASS`):** `38` (`TC001`–`TC033`, `TC036`–`TC040`)
  - **Partially Verified (`PARTIALLY VERIFIED`):** `2` (`TC034`, `TC035`)
  - **Fail:** `0`
  - **Not Run:** `0`
- **Chi tiết 2 case `PARTIALLY VERIFIED`:**
  - `TC034` (xác nhận phiếu đã `CONFIRMED`) & `TC035` (xác nhận phiếu đã `CANCELLED`): Cả hai đều gửi `expected_draft_version=1` (version cũ trước khi confirm/cancel) nên trả `HTTP 409 RECEIPT_VERSION_CONFLICT` thay vì đi tới nhánh `INVALID_STATE`. Vì vậy đã chứng minh hệ thống từ chối `409` trên phiếu đã đóng qua cơ chế version, nhưng chưa chứng minh được nhánh `INVALID_STATE` khi gửi đúng `expected_draft_version=2`.
- **Idempotency, Atomicity, Concurrency & Security Audit:**
  - **Idempotency replay (`TC016`→`TC017`, `TC029`→`TC030`):** Cả bản gốc và bản replay đều được ghi nhận với cùng `Idempotency-Key`, cùng payload và cùng `audit_id` / `stock_version` (`TC016`/`TC017`) hoặc `id` / `draft_version` / `closed_at` (`TC029`/`TC030`). Same-key different-payload (`TC018`, `TC032`) trả `409 IDEMPOTENCY_KEY_REUSED`.
  - **Transaction atomicity (`TC029`):** `HAPPY PATH VERIFIED` (status `CONFIRMED`, `closed_at` được gán, `TC030` xác nhận tồn kho tăng từ `0` lên `10` và không cộng trùng). Rollback khi lỗi giữa transaction được kiểm thử ở `tests/modules/purchasing/test_receipt_confirmation_mysql.py`, không có trong bộ HTTP thủ công này.
  - **Concurrency (`TC022`, `TC033`):** Mới dừng ở **sequential optimistic-locking conflict** (`STALE_STOCK_VERSION`, `RECEIPT_VERSION_CONFLICT`), chưa có bằng chứng concurrent barrier test trong evidence HTTP.
  - **Security & Redaction:** Đã rà soát toàn bộ `80/80` file evidence (`TC001`–`TC040`); không phát hiện JWT, password, session cookie hay CSRF token lộ lọt (`Authorization: Bearer <REDACTED_TOKEN>`).
- **Tài liệu & Bằng chứng:**
  - Workbook Excel (4 sheet: `Test Cases`, `Test Log`, `Bug List`, `Test Summary`): [T3C9970_Test_Cases_and_Test_Log.xlsx](T3C9970_Test_Cases_and_Test_Log.xlsx)
  - Evidence HTTP request/response: `docs/sprint3/testing/T3C9970/evidence/TC001/` đến `TC040/`.
