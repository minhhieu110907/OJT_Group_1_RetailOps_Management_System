# T04A9CA — MySQL Regression Test Report (Auth → Checkout → Cancel)

- **Task ID**: `T04A9CA`
- **Owner / QA**: Cao Nguyễn Anh Dương
- **Branch**: `feature/t04a9ca-auth-checkout-cancel-regression`
- **Scope**: End-to-end HTTP & Concurrency Regression trên MySQL 8 cho luồng `Auth → Checkout → Cancel`, xác minh trực tiếp invariants ở DB (`orders`, `order_items`, `inventories`, `stock_movements`, `idempotency_records`, `auth_sessions`).

## 1. Repository Findings
- **Auth**: `POST /api/v1/auth/login`, `POST /api/v1/auth/logout` (CSRF + refresh cookie, thu hồi `AuthSession.revoked_at`), `get_current_active_user` kiểm tra JWT + `AuthSession` sống trong MySQL.
- **Checkout**: `POST /api/v1/orders/checkout` (`201`), bắt buộc `Idempotency-Key` (16..128 ký tự), khóa `Inventory` bằng `SELECT ... FOR UPDATE`, trừ `quantity`, tăng `stock_version`, ghi `StockMovement(kind='SALE', order_id=...)`.
- **Cancel**: `POST /api/v1/orders/{order_id}/cancel` (`200`), bắt buộc `Idempotency-Key`, chỉ `ADMIN` hoặc `STAFF` tạo đơn trong vòng 15 phút cùng ngày VN (`403` nếu sai quyền/quá hạn), hủy lặp với key mới trả `409`, hoàn kho và ghi `StockMovement(kind='ORDER_CANCEL', order_id=...)`.
- **Existing tests**: `backend/tests/modules/sales/test_checkout_mysql.py` đã phủ service-level checkout/cancel; `backend/tests/integration/test_auth_checkout_cancel_mysql.py` bổ sung full HTTP Auth → Checkout → Cancel & concurrency trên MySQL thật.

## 2. Test Cases (Groups A–F)
| Group | Scenario | Expected | Implementation |
|---|---|---|---|
| A | Unauthenticated / invalid / expired JWT | `401`, không đổi DB | `test_auth_checkout_cancel_lifecycle_rbac_and_invariants_mysql` |
| A | Revoked session sau `POST /api/v1/auth/logout` | `401`, không đổi DB | `test_auth_checkout_cancel_lifecycle_rbac_and_invariants_mysql` |
| A | `STAFF` khác hủy đơn của người khác | `403`, đơn giữ `COMPLETED` | `test_auth_checkout_cancel_lifecycle_rbac_and_invariants_mysql` |
| B | Checkout hợp lệ + replay same-key + conflict payload + thiếu tồn | `201`, `201` (1 đơn), `409`, `409` | `test_auth_checkout_cancel_lifecycle_rbac_and_invariants_mysql` |
| C | Cancel hợp lệ + replay same-key + repeat new-key | `200`, `200` (hoàn 1 lần), `409` | `test_auth_checkout_cancel_lifecycle_rbac_and_invariants_mysql` |
| D | Checkout concurrency (`stock=1`, 2 threads `qty=1`) | `[201, 409]`, `final_stock=0`, 1 đơn | `test_checkout_and_cancel_concurrency_and_interaction_mysql` |
| E | Cancel concurrency (1 đơn, 2 threads distinct keys) | `[200, 409]`, hoàn kho đúng 1 lần | `test_checkout_and_cancel_concurrency_and_interaction_mysql` |
| F | Checkout + Cancel interaction trên cùng sản phẩm | Không âm kho, invariant khớp `100%` | `test_checkout_and_cancel_concurrency_and_interaction_mysql` |

## 3. Verification & CI Execution
- **Lệnh CI (`Backend / MySQL integration`)**:
  `uv run --locked pytest -m "integration and not redis_integration and not proxy_integration"`
- **Lệnh targeted**:
  `uv run --locked pytest tests/integration/test_auth_checkout_cancel_mysql.py -vv`
- **Ruff**: `ruff check .` & `ruff format --check .` (xác minh ở local & CI).
- **Kết quả local MySQL 8.4**: `pytest tests/integration/test_auth_checkout_cancel_mysql.py -v` → `2 passed in 22.11s`.
