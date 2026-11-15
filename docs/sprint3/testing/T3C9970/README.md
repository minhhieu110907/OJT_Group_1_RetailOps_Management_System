# TASK T3C9970 — TEST CASES & TEST LOG

**Người thực hiện:** Cao Nguyễn Anh Dương — Mã sinh viên: `B25DTCN165`  
**Nhánh làm việc:** `feature/t3c9970-test-cases`  
**Nhánh gốc & phụ thuộc:** Tạo từ `feature/t04a7df-receipt-confirmation` (**phụ thuộc PR #55** để có API `POST /api/v1/purchase-receipts/{receipt_id}/confirm`).

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

## 2. Môi trường kiểm thử

- **Backend API:** Docker Compose service `backend` (FastAPI + Uvicorn) tại `http://127.0.0.1:8001/api/v1` (healthcheck `200 OK {"status":"ok"}`).
- **Database & Cache:** Docker Compose `mysql:8.4` (healthy, Alembic migration `head` = `20261113_01`) và `redis:8.4-alpine` (healthy).
- **Unit tests (non-integration):**
  ```powershell
  cd backend
  uv run --locked pytest tests/modules/inventory/ tests/modules/purchasing/ -m "not integration" -q
  ```
  Kết quả thực tế: **`58 passed, 32 deselected in 3.34s`**.

---

## 3. Cách chạy lại kiểm thử

1. Khởi động Docker Compose và chạy migration:
   ```powershell
   docker compose up -d --build backend
   docker compose exec -T backend .venv/bin/alembic upgrade head
   ```
2. Kiểm tra healthcheck:
   ```powershell
   curl.exe -s -i http://127.0.0.1:8001/api/v1/health
   ```
3. Đăng nhập `ADMIN` và `STAFF` qua `POST /api/v1/auth/login` để lấy Bearer token, sau đó gọi các endpoint theo kịch bản trong `T3C9970_Test_Cases_and_Test_Log.xlsx` (tạo category, supplier, product, purchase receipt mẫu rồi thực thi `TC001`–`TC040`).
4. Xuất lại file Excel (nếu cập nhật kết quả):
   ```powershell
   cd backend
   uv run --with openpyxl python <path-to-generator-script>
   ```

---

## 4. Tổng kết kết quả kiểm thử (2026-11-16)

- **Tổng số Test Case:** `40` (`TC001` – `TC040`)
  - **Pass:** `40` (`100.0%`)
  - **Fail:** `0`
  - **Not Run:** `0`
- **Bug phát hiện:** `0` (chi tiết xem sheet `Bug List` trong file Excel).
- **Tài liệu & Bằng chứng:**
  - Workbook Excel (4 sheet: `Test Cases`, `Test Log`, `Bug List`, `Test Summary`): [T3C9970_Test_Cases_and_Test_Log.xlsx](T3C9970_Test_Cases_and_Test_Log.xlsx)
  - Evidence HTTP request/response (đã redact toàn bộ token, password, cookie, CSRF): `docs/sprint3/testing/T3C9970/evidence/TC001/` đến `TC040/`.

---

## 5. Hạn chế ghi nhận

1. Trong `compose.yaml` của nhánh hiện tại, cổng MySQL `3306` không publish ra host (`13306`), nên chạy `pytest -m integration` trực tiếp từ máy host gặp `ConnectionRefusedError`; thay vào đó toàn bộ `40` test case đã được thực thi qua HTTP thật tới container `backend` kết nối trực tiếp tới `mysql:8.4` và `redis:8.4` trong Docker.
2. Máy local chưa cài LibreOffice (`soffice`), nên file `.xlsx` được kiểm tra cấu trúc, công thức (`COUNTIF`/`COUNTIFS`), Data Validation và Conditional Formatting bằng `openpyxl`.
