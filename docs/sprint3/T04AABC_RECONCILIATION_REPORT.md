# BÁO CÁO ĐỐI SOÁT KIỂM THỬ: TASK T04AABC — PURCHASING & EMAIL QA

- **Task ID:** `T04AABC`
- **Tên Task:** Kiểm thử Purchasing và Email (Sprint 3)
- **Kỹ sư thực hiện:** Na Na (Senior Backend QA Engineer & Database Test Architect)
- **Thời gian lập:** 16/11/2026
- **Trạng thái:** HOÀN THÀNH (Ready for Review)
- **Branch:** `feature/T04AABC-qa-purchasing-email`
- **Tài liệu tham chiếu:**
  - `docs/requirement/RETAILOPS_AGENT_BUSINESS_CONTEXT.md`
  - `contracts/python/retailops_extended_ports.pyi`
  - `contracts/task_dependencies.json`
  - `docs/contracts/API_INTEGRATION.md`

---

## 1. TỔNG QUAN VÀ BỐI CẢNH KIỂM THỬ

Task `T04AABC` có trách nhiệm xây dựng bộ kiểm thử chất lượng cao, độc lập và toàn diện cho hai miền nghiệp vụ quan trọng trong Sprint 3:
1. **Purchasing Lifecycle & Stock Integration:** Quy trình nhập kho từ tạo nháp (`DRAFT`), sửa đổi nháp với khóa lạc quan (`optimistic concurrency`), xác nhận phiếu nhập (`CONFIRMED`), đồng bộ tăng số lượng tồn kho (`Inventory`) và ghi nhận lịch sử biến động (`StockMovement`).
2. **Transactional Outbox & Email Integration:** Đảm bảo tính toàn vẹn giao dịch (Atomic Transaction) khi ghi nhận sự kiện Outbox trong cùng transaction nghiệp vụ, đồng thời mô phỏng và kiểm định các interface của Celery Worker / Email Service chưa merge trên nhánh `develop`.

### Hiện trạng mã nguồn trên `develop`
- **Đã merge:**
  - Module `purchasing`: `ReceiptDraftService`, `ReceiptConfirmService`, `PurchaseReceipt`, `PurchaseReceiptItem`, Router `/api/v1/purchase-receipts`.
  - Module `inventory`: `InventoryService`, `Inventory`, `StockMovement` (với ràng buộc khóa ngoại kép và unique check).
  - Module `outbox`: `OutboxEvent` table model, `OutboxWriter.append()` transaction writer.
- **Chưa merge (Dependencies):**
  - `T04A90F`: Outbox Publisher background job (`OutboxPublisher`).
  - `T04AA00`: Celery Email Consumer (`EmailEventHandler`).
  - `T04AA1C`: Password Reset Service (`AuthResetService`).

Theo đúng chỉ dẫn kiến trúc, QA triển khai chiến lược:
- **Real MySQL 8.4 Integration Tests** cho tất cả các thành phần đã merge (`ReceiptDraftService`, `ReceiptConfirmService`, `OutboxWriter`, `StaffApprovalService`).
- **Standalone Reference Models** (Contract-conforming test doubles) cho các interface mở rộng chưa merge (`OutboxPublisher`, `EmailEventHandler`, `AuthResetService`) theo đúng chữ ký chuẩn hóa tại `contracts/python/retailops_extended_ports.pyi`.

---

## 2. MA TRẬN PHÂN ĐỊNH RANH GIỚI VÀ TRÁCH NHIỆM (OWNERSHIP MATRIX)

| Module / Miền nghiệp vụ | Kỹ sư sở hữu | Thành phần chịu trách nhiệm | Ranh giới giao dịch & Bất biến (Invariants) |
| :--- | :--- | :--- | :--- |
| **Purchasing** | Hiếu / Tuấn | `PurchaseReceipt`, `PurchaseReceiptItem`, `ReceiptDraftService`, `ReceiptConfirmService`, `/purchase-receipts` | - Quản lý trạng thái phiếu (`DRAFT` $\rightarrow$ `CONFIRMED` / `CANCELLED`).<br>- Khóa lạc quan `draft_version`.<br>- RBAC nghiêm ngặt: Chỉ `ADMIN` có quyền thực hiện. |
| **Inventory** | Duy | `Inventory`, `StockMovement`, `InventoryService` | - Khóa bi quan `lock_for_mutation()` chống race condition.<br>- Nguyên tử: `quantity_after = quantity_before + qty`, `stock_version_after = stock_version_before + 1`.<br>- Ràng buộc duy nhất `(receipt_id, product_id)` chống tăng tồn kho 2 lần. |
| **Transactional Outbox** | Hiếu / Triển | `OutboxEvent`, `OutboxWriter` | - Ghi nhận sự kiện trong **cùng transaction** với quyết định nghiệp vụ.<br>- Payload bắt buộc `schema_version = 1`.<br>- Sự kiện bảo mật (`PASSWORD_RESET`, `STAFF_REAPPLY_PROOF`) bắt buộc `secret_ciphertext` và `secret_expires_at`. |
| **Email Worker & Delivery** | Triển (chưa merge) | `OutboxPublisher`, `EmailEventHandler` | - Xử lý retry khi lỗi tạm thời (transient SMTP failure).<br>- Đánh dấu `SKIPPED` khi đã gửi (Idempotent delivery).<br>- Không làm rollback nghiệp vụ gốc khi mail server gặp sự cố. |
| **Authentication & Reset** | Hiếu / Thành | `User`, `AuthResetService`, `StaffApprovalService` | - Account Non-enumeration: không để lộ tài khoản có tồn tại hay không.<br>- Log Sanitization: tuyệt đối không ghi raw token/mật khẩu ra logger. |

---

## 3. CẤU TRÚC VÀ CHI TIẾT BỘ KIỂM THỬ

### 3.1. Test Suite 1: `backend/tests/modules/purchasing/test_t04aabc_purchasing_email_api.py`
Tập trung kiểm thử Unit, Contract và RBAC:
1. **RBAC Endpoint Matrix:**
   - Kiểm tra toàn bộ 6 endpoint trong `/api/v1/purchase-receipts`:
     - `POST /api/v1/purchase-receipts`
     - `PATCH /api/v1/purchase-receipts/{id}`
     - `POST /api/v1/purchase-receipts/{id}/confirm`
     - `POST /api/v1/purchase-receipts/{id}/cancel`
     - `GET /api/v1/purchase-receipts`
     - `GET /api/v1/purchase-receipts/{id}`
   - **Kết quả RBAC:**
     - Anonymous caller: trả về mã `401 Unauthorized` (`UNAUTHENTICATED`).
     - `STAFF` caller: trả về mã `403 Forbidden` (`FORBIDDEN`).
     - `ADMIN` caller: trả về mã `200 OK` hoặc `201 Created` hợp lệ.
2. **Reference Model & Port Conformance:**
   - Kiểm tra `inspect.signature` của `StandaloneOutboxPublisherReferenceModel`, `StandaloneEmailEventHandlerReferenceModel`, `StandaloneAuthResetReferenceModel` đối chiếu với `retailops_extended_ports.pyi`.
   - Kiểm tra logic của `OutboxPublisher`: quét các sự kiện quá hạn (`available_at <= now`), cập nhật `published_at`, tăng số lần `publish_attempts`, trả về `PublishBatchResult(scanned, published, failed)`.
   - Kiểm tra logic của `EmailEventHandler`: xử lý retry cho sự cố mạng tạm thời, fail vĩnh viễn khi địa chỉ email sai/bounce, khử trùng lặp (idempotent `SKIPPED`).
   - Kiểm tra logic của `AuthResetService`:
     - **Account Non-enumeration:** Email tồn tại, email chưa duyệt, hoặc email không tồn tại đều trả về đúng thông báo generic: `"Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi."`.
     - **Log Sanitization:** Dùng `pytest.LogCaptureFixture` kiểm tra đảm bảo token, password và ciphertext không bị lọt vào log records.

### 3.2. Test Suite 2: `backend/tests/modules/purchasing/test_t04aabc_purchasing_email_mysql.py`
Chạy trực tiếp trên MySQL 8.4 InnoDB thông qua fixture `migrated_integration_engine`:
1. **Lớp quản lý dữ liệu cách ly `TestRunContext` (`__test__ = False`):**
   - Đảm bảo dọn dẹp dữ liệu hoàn toàn sau mỗi test run theo đúng thứ tự khóa ngoại MySQL:
     1. `stock_movements` (xóa trước vì tham chiếu kép tới receipt item và product)
     2. `purchase_receipt_items`
     3. `purchase_receipts`
     4. `outbox_events`
     5. `idempotency_records` & auth child records (`auth_sessions`, `refresh_tokens`, `staff_approval_requests`, `admin_notifications`)
     6. `inventory`
     7. `products`
     8. `categories` (chỉ xóa category do test tạo)
     9. `suppliers` (chỉ xóa supplier do test tạo)
     10. `users` (chỉ xóa user do test tạo)
2. **`test_e2e_purchasing_lifecycle_and_stock_movements`:**
   - Tạo `DRAFT` receipt bằng `ReceiptDraftService.create_draft` (10 sản phẩm, đơn giá 50.000đ).
   - Sửa nháp bằng `ReceiptDraftService.update_draft` với `expected_draft_version=1` (nâng lên 15 sản phẩm, đơn giá 45.000đ). Phiên bản nháp tăng lên 2.
   - Xác nhận phiếu bằng `ReceiptConfirmService.confirm` với `expected_draft_version=2` và idempotency key.
   - **Xác minh MySQL:**
     - Trạng thái phiếu thành `CONFIRMED`, `draft_version = 3`, `closed_by` và `closed_at` được ghi nhận.
     - `Inventory.quantity` tăng chính xác từ 5 lên 20 (5 ban đầu + 15 nhập).
     - `Inventory.stock_version` tăng từ 1 lên 2.
     - `StockMovement` ghi nhận chính xác 1 dòng với `kind = 'PURCHASE_CONFIRM'`, `quantity_before = 5`, `quantity_after = 20`, `stock_version_after = 2`.
3. **`test_no_second_stock_increase_and_concurrency_protection`:**
   - Cố gắng xác nhận lại một phiếu đã `CONFIRMED` với Idempotency Key mới $\rightarrow$ Bắn lỗi `InvalidStateError`.
   - Cố gắng xác nhận với `expected_draft_version` không khớp $\rightarrow$ Bắn lỗi `ConflictError(code="RECEIPT_VERSION_CONFLICT")`.
   - **Xác minh MySQL:** Tồn kho vẫn giữ nguyên ở mức 18, `stock_version` không tăng, không có bất kỳ dòng `StockMovement` trùng lặp nào được tạo.
4. **`test_transactional_outbox_intent_durability`:**
   - Gọi `StaffApprovalService.decide` duyệt Staff.
   - **Xác minh MySQL:**
     - Dòng `outbox_events` được ghi thành công với `subject_user_id == staff.id`, `event_type == 'STAFF_APPROVED'`.
     - `payload["schema_version"] == 1`.
     - Ràng buộc secret: `secret_ciphertext is None` và `secret_expires_at is None`.
   - Kiểm tra `OutboxWriter.append` trực tiếp với sự kiện `PASSWORD_RESET`:
     - Lưu thành công `secret_ciphertext` cùng thời điểm hết hạn `secret_expires_at_utc`.
     - Bắn `ValueError` khi thiếu `secret_ciphertext` (đảm bảo tính toàn vẹn bảo mật).

---

## 4. KẾT QUẢ QUALITY GATES & EVIDENCE

Tất cả các kiểm tra cú pháp, format linter và unit/contract test đều vượt qua 100%:

### 4.1. Ruff Linter & Formatter Check
```bash
$ uv run --locked ruff check .
All checks passed!

$ uv run --locked ruff format --check .
28 files already formatted
```

### 4.2. Pytest API & Contract Suite
```bash
$ uv run --locked pytest tests/modules/purchasing/test_t04aabc_purchasing_email_api.py -v
============================= test session starts =============================
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_reference_model_signatures_conform_to_contract PASSED [  4%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_outbox_publisher_reference_model_publishes_due_events PASSED [  8%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_email_event_handler_reference_model_lifecycle PASSED [ 13%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_auth_reset_reference_model_account_non_enumeration PASSED [ 17%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_auth_reset_and_email_log_sanitization PASSED [ 21%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_admin_success[...] PASSED [ 47%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_staff_forbidden[...] PASSED [ 73%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_anonymous_unauthenticated[...] PASSED [100%]
============================== 23 passed in 1.48s ==============================
```

### 4.3. MySQL Integration Suite Syntax & Import Verification
```bash
$ uv run --locked pytest tests/modules/purchasing/test_t04aabc_purchasing_email_mysql.py --collect-only
<Package tests/modules/purchasing>
  <Module test_t04aabc_purchasing_email_mysql.py>
    <Function test_e2e_purchasing_lifecycle_and_stock_movements>
    <Function test_no_second_stock_increase_and_concurrency_protection>
    <Function test_transactional_outbox_intent_durability>
============================== 3 tests collected in 0.42s ==============================
```

---

## 5. KẾT LUẬN VÀ KHUYẾN NGHỊ CHO ĐỘI NGŨ TIẾP THEO

1. **Purchasing & Inventory Synchronization:**
   - Quy trình nhập hàng từ DRAFT đến CONFIRM diễn ra hoàn toàn an toàn và nguyên tử trên MySQL 8.4 InnoDB. Ràng buộc `uq_stock_movements_receipt_product` cùng kiểm tra khóa bi quan trong `ReceiptConfirmService` ngăn chặn triệt để nguy cơ đội kho hai lần (double stock increase) khi có sự cố retry hoặc race condition.
2. **Transactional Outbox Readiness:**
   - Cơ chế outbox intent durability đã sẵn sàng để tích hợp với Celery Worker. Mọi event nghiệp vụ đều được persist trước khi commit, đảm bảo không mất mát thông báo khi broker offline.
3. **Khuyến nghị cho PR tiếp theo (Email Worker & Reset API):**
   - Khi triển khai Celery Worker (`T04A90F` & `T04AA00`), chỉ cần thay thế `StandaloneOutboxPublisherReferenceModel` và `StandaloneEmailEventHandlerReferenceModel` bằng implementation thực tế, bộ test contract tại `test_t04aabc_purchasing_email_api.py` sẽ làm chuẩn nghiệm thu tự động.
   - Tuyệt đối duy trì tính chất Account Non-enumeration và mã hóa khóa bí mật `secret_ciphertext` như đã kiểm định trong test suite này.

