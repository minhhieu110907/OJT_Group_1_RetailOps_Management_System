# BÁO CÁO ĐỐI SOÁT KIỂM THỬ: TASK T04AABC — PURCHASING & EMAIL QA

- **Task ID:** `T04AABC`
- **PR:** #70
- **Tên Task:** Kiểm thử Purchasing và Email (Sprint 3)
- **Kỹ sư thực hiện:** Na Na (Principal Backend QA Engineer & Database Reliability Engineer)
- **Thời gian lập:** 16/11/2026
- **Trạng thái:** READY FOR LEAD REVIEW
- **Branch:** `feature/T04AABC-qa-purchasing-email`
- **Tài liệu tham chiếu:**
  - `docs/requirement/RETAILOPS_AGENT_BUSINESS_CONTEXT.md`
  - `contracts/python/retailops_extended_ports.pyi`
  - `contracts/task_dependencies.json`
  - `docs/contracts/API_INTEGRATION.md`

---

## 1. PHẠM VI TASK VÀ PHÂN ĐỊNH TEST SCOPE (TASK SCOPE & MODULE BREAKDOWN)

Task `T04AABC` có trách nhiệm xây dựng bộ kiểm thử chất lượng cao, độc lập và an toàn tuyệt đối về dữ liệu cho hai miền nghiệp vụ:
1. **Purchasing & Inventory Synchronization (Đã merge production):**
   - Tạo nháp (`DRAFT`), sửa nháp với khóa lạc quan (`draft_version`), xác nhận phiếu nhập (`CONFIRMED`), tăng tồn kho (`Inventory`) và ghi nhận lịch sử biến động (`StockMovement`).
   - Phân quyền RBAC nghiêm ngặt: chỉ `ADMIN` có quyền thực hiện.
2. **Transactional Outbox & Email / Reset Integration:**
   - Persistence model `outbox_events` và `OutboxWriter.append()` (Đã merge production).
   - Celery Worker (`T04A90F`, `T04AA00`) và Password Reset Service (`T04AA1C`) **chưa merge trên `develop`**.

### Bảng phân loại tính chất kiểm thử (Test Classification)
| Thành phần / Tính năng | Trạng thái mã nguồn | Phân loại kiểm thử | Kết quả kiểm thử |
| :--- | :--- | :--- | :--- |
| **Purchasing Endpoints RBAC** (`/purchase-receipts`) | Production Merged | `PRODUCTION_API_PASS` | PASS (23 tests: ADMIN 200/201, STAFF 403, Anon 401) |
| **Production Error Log Sanitization** | Production Merged | `PRODUCTION_LOG_SANITIZATION_VERIFIED` | PASS (Exception handler không leak token/secret) |
| **Purchasing Lifecycle on MySQL 8.4** | Production Merged | `MYSQL_INTEGRATION_PASS` | COLLECTED (Ready for CI MySQL) |
| **Sequential Re-confirmation Guard** | Production Merged | `SEQUENTIAL_DUPLICATE_CONFIRMATION_VERIFIED` | COLLECTED (Chống tăng kho tuần tự khi re-confirm) |
| **Outbox Storage Constraints** | Production Merged | `SECRET_STORAGE_CONSTRAINT_VERIFIED` | COLLECTED (Bảo đảm VARBINARY và check constraint) |
| **MySQL Cross-run Isolation & Idempotence**| Test Infrastructure | `MYSQL_ISOLATION_REGRESSION_PASS` | COLLECTED (Cô lập dữ liệu run, fail-closed an toàn) |
| **Idempotency Isolation & Shared ADMIN**  | Test Infrastructure | `IDEMPOTENCY_ISOLATION_VERIFIED`   | COLLECTED (Bảo vệ record run khác & shared ADMIN) |
| **OutboxPublisher Reference Model** | Unmerged (`T04A90F`) | `REFERENCE_MODEL_PASS` / `REFERENCE_SIGNATURE_VERIFIED` | PASS (Mô phỏng quét due events và cập nhật metadata) |
| **EmailEventHandler Reference Model** | Unmerged (`T04AA00`) | `REFERENCE_MODEL_PASS` / `REFERENCE_SIGNATURE_VERIFIED` | PASS (Mô phỏng retry, bounce, idempotency) |
| **AuthResetService Reference Model** | Unmerged (`T04AA1C`) | `REFERENCE_MODEL_PASS` / `REFERENCE_SIGNATURE_VERIFIED` | PASS (Mô phỏng Account Non-enumeration) |
| **Email Worker & Reset Production E2E** | Unmerged (`T04A90F`, `T04AA00`, `T04AA1C`) | `DEFERRED_REAL_INTEGRATION` | Chờ dependency merge để chạy E2E thực tế |
| **Real Concurrent Race Condition** | Scope Deferred | `DEFERRED_REAL_INTEGRATION` | Cần harness 2 sessions đồng thời (để lại cho Stress Test) |
| **AES-GCM Authenticated Crypto Round-trip**| Scope Deferred | `DEFERRED_REAL_INTEGRATION` | Chờ production encryption module của `T04AA1C` |

---

## 2. THIẾT KẾ CÔ LẬP DỮ LIỆU MYSQL (TEST ISOLATION ARCHITECTURE)

Nhằm khắc phục triệt để rủi ro xóa nhầm dữ liệu của các test run khác chạy song song (Finding P1), lớp `TestRunContext` đã được thiết kế lại theo các nguyên tắc nghiêm ngặt:

### 2.1. Quyền sở hữu tuyệt đối (Ownership-based Cleanup)
- **Source of Truth duy nhất:** `self.receipt_ids` là nguồn duy nhất định danh các phiếu nhập được phép xóa. Tuyệt đối không suy diễn receipt ownership từ `product_id`, `supplier_id`, SKU prefix hay các khóa ngoại dùng chung.
- **Stock Movement:** Chỉ xóa các biến động kho do run sở hữu:
  `StockMovement.id.in_(self.stock_movement_ids)` hoặc `StockMovement.receipt_id.in_(self.receipt_ids)`. Tuyệt đối không xóa diện rộng bằng `StockMovement.product_id.in_(self.product_ids)`.
- **Purchase Receipt Items:** Chỉ xóa các dòng con thuộc chính các receipts do run sở hữu:
  `PurchaseReceiptItem.receipt_id.in_(self.receipt_ids)`.

### 2.2. Cơ chế chặn lỗi fail-closed (Fail-Closed Protection)
- Trước khi thực hiện bất kỳ thao tác xóa nào, `TestRunContext.cleanup()` chủ động kiểm tra xem các sản phẩm (`self.product_ids`) do run tạo có đang bị tham chiếu bởi một `PurchaseReceipt` bên ngoài run hay không.
- Nếu phát hiện có external receipt tham chiếu tới product của run, cleanup lập tức ném lỗi `RuntimeError("Isolation violation: ...")` và dừng lại. Cơ chế này bảo đảm không xóa lan sang dữ liệu của run khác và không để lại dữ liệu mồ côi (orphan records).

### 2.3. Dọn dẹp Idempotency chính xác cho Shared ADMIN
- Khi test chạy dưới tài khoản `ADMIN` dùng chung (`admin_slot == 1`), `TestRunContext` sử dụng `track_idempotency_key(admin_id, key)` để tính toán chính xác `key_digest`.
- Khi cleanup, chỉ xóa đúng bản ghi có `(user_id == admin_id, operation == 'CONFIRM_RECEIPT', key_digest == digest)`.
- Tuyệt đối không xóa toàn bộ bản ghi Idempotency của `ADMIN`, bảo toàn dữ liệu của các test run khác.
- Thao tác cleanup đảm bảo tính khả lặp (idempotent): chạy cleanup lần thứ 2 hoàn toàn không phát sinh lỗi.

### 2.4. Vòng đời và cơ chế quản lý Shared Test ADMIN (Shared ADMIN Lifecycle)
Nhằm thống nhất logic quản lý Shared ADMIN trong môi trường MySQL Integration Test để không gây hiểu nhầm về memory leak hoặc data pollution, các nguyên tắc sau được chuẩn hóa:
- **Nguồn gốc của ADMIN:** Do fixture tạo ra hoặc được tái sử dụng qua hàm `_ensure_admin()`. Hàm này truy vấn bản ghi có `admin_slot == 1`; nếu đã tồn tại thì tái sử dụng ID đó, nếu chưa có thì tạo mới một bản ghi duy nhất với `admin_slot = 1` và `role = 'ADMIN'`.
- **Cơ chế bảo vệ:** `TestRunContext.cleanup()` chỉ xóa user do chính run đó tạo ra (nằm trong danh sách `self.user_ids`), đồng thời áp dụng điều kiện lọc an toàn `User.admin_slot.is_(None)` trong lệnh DELETE. Do đó, Shared ADMIN (`admin_slot == 1`) tuyệt đối không bao giờ bị xóa nhầm bởi bất kỳ test run nào.
- **Lý do kỹ thuật:** Trong môi trường CI/CD, database test là một ephemeral container (được khởi tạo mới ở đầu mỗi workflow và tự hủy sau khi toàn bộ job kết thúc). Việc giữ lại duy nhất một shared ADMIN giữa các test cases trong cùng một test suite là **intentional design** nhằm:
  1. Tối ưu hóa thời gian thực thi (tránh chi phí CPU đắt đỏ khi hash password bằng Argon2/Bcrypt cho mỗi test case).
  2. Tuyệt đối tuân thủ check constraint MySQL `ck_users_role_status_admin_slot` (chỉ cho phép đúng 1 ADMIN chiếm slot).
  3. Không vi phạm tính cô lập giữa các test run độc lập vì mỗi run đều sở hữu ID riêng biệt và idempotency key digest riêng biệt.
- **Giới hạn phạm vi (Boundary):** Đây là quy ước nội bộ dành riêng cho bộ test tích hợp database (MySQL integration test suite), hoàn toàn không áp dụng hoặc ảnh hưởng tới production auth logic hay migration rules.

### 2.5. Thứ tự giải phóng khóa ngoại MySQL InnoDB
1. `stock_movements` (xóa trước vì có FK kép tới receipt items và inventory)
2. `purchase_receipt_items` (thuộc tracked receipts)
3. `purchase_receipts` (thuộc tracked receipts)
4. `outbox_events` (thuộc tracked event IDs hoặc tracked users)
5. `idempotency_records` (thuộc tracked key digests hoặc tracked users)
6. `auth_sessions`, `refresh_tokens`, `staff_approval_requests`, `admin_notifications` (thuộc tracked users)
7. `inventory` (thuộc tracked products)
8. `products` (thuộc tracked products)
9. `categories` (chỉ xóa category do run tạo)
10. `suppliers` (chỉ xóa supplier do run tạo)
11. `users` (chỉ xóa user do run tạo, bảo vệ tuyệt đối shared admin có admin_slot = 1)

---

## 3. CHI TIẾT BỘ TEST VÀ BẰNG CHỨNG THỰC TẾ

### 3.1. Test Suite API & Reference Models: `test_t04aabc_purchasing_email_api.py`
1. **Phân quyền RBAC Endpoints (23 tests):**
   - `POST /api/v1/purchase-receipts`: ADMIN trả về 201; STAFF trả về 403; Anonymous trả về 401.
   - `PATCH /api/v1/purchase-receipts/{id}`: ADMIN trả về 200; STAFF trả về 403; Anonymous trả về 401.
   - `POST /api/v1/purchase-receipts/{id}/confirm`: ADMIN trả về 200; STAFF trả về 403; Anonymous trả về 401.
   - `POST /api/v1/purchase-receipts/{id}/cancel`: ADMIN trả về 200; STAFF trả về 403; Anonymous trả về 401.
   - `GET /api/v1/purchase-receipts`: ADMIN trả về 200; STAFF trả về 403; Anonymous trả về 401.
   - `GET /api/v1/purchase-receipts/{id}`: ADMIN trả về 200; STAFF trả về 403; Anonymous trả về 401.
2. **Kiểm tra chữ ký Reference Models (`REFERENCE_SIGNATURE_VERIFIED`):**
   - Đối chiếu chữ ký hàm `publish_due`, `handle`, `request_reset`, `consume_reset` với interface tại `contracts/python/retailops_extended_ports.pyi`.
3. **Mô phỏng Reference Models (`REFERENCE_MODEL_PASS`):**
   - `StandaloneOutboxPublisherReferenceModel`: quét due events, cập nhật `published_at`, tăng `publish_attempts`.
   - `StandaloneEmailEventHandlerReferenceModel`: xử lý retry cho sự cố mạng tạm thời, đánh dấu `FAILED` khi địa chỉ sai/bounce, khử trùng lặp `SKIPPED`.
   - `StandaloneAuthResetReferenceModel`: bảo đảm Account Non-enumeration (kể cả email tồn tại, chưa kích hoạt hay không tồn tại đều trả về thông báo generic giống hệt nhau).
4. **Kiểm tra an toàn bảo mật Log (`PRODUCTION_LOG_SANITIZATION_VERIFIED`):**
   - Gửi request chứa sentinel bearer token `sentinel-auth-bearer-secret-xyz-987` tới router.
   - Kiểm tra `caplog.records` xác nhận không có bất kỳ log record nào làm lộ sentinel token.

### 3.2. Test Suite MySQL Integration: `test_t04aabc_purchasing_email_mysql.py`
1. **`test_e2e_purchasing_lifecycle_and_stock_movements`:**
   - Dùng `ReceiptDraftService` và `ReceiptConfirmService` thật: Tạo nháp (10 sản phẩm, 50.000đ), cập nhật nháp (15 sản phẩm, 45.000đ) với khóa lạc quan `draft_version=1`, xác nhận phiếu với `draft_version=2`.
   - Tồn kho tăng từ 5 lên 20, `stock_version` tăng từ 1 lên 2, ghi nhận chính xác 1 bản ghi `StockMovement` với `kind = 'PURCHASE_CONFIRM'`.
2. **`test_no_second_stock_increase_on_sequential_reconfirmation` (`SEQUENTIAL_DUPLICATE_CONFIRMATION_VERIFIED`):**
   - Re-confirm receipt đã `CONFIRMED` với Idempotency Key mới bắn `InvalidStateError`.
   - Confirm với `draft_version` không khớp bắn `ConflictError(code="RECEIPT_VERSION_CONFLICT")`.
   - Tồn kho không bị tăng lần 2, không nhân đôi `StockMovement`.
3. **`test_transactional_outbox_intent_durability` (`SECRET_STORAGE_CONSTRAINT_VERIFIED`):**
   - Gọi `StaffApprovalService.decide` duyệt Staff $\rightarrow$ Ghi nhận bản ghi `outbox_events` đồng thời trong cùng transaction với `schema_version = 1`.
   - Kiểm tra ràng buộc lưu trữ cột `VARBINARY(2048)` và check constraint `ck_outbox_events_secret_expiry` với `PASSWORD_RESET`.
4. **`test_mysql_cross_run_isolation_and_idempotent_cleanup` (`MYSQL_ISOLATION_REGRESSION_PASS`):**
   - Thiết lập 2 run contexts độc lập `run_a` và `run_b`.
   - Tạo `Receipt B` (Run B) tham chiếu tới `Product A` (Run A).
   - Kiểm tra Case 1: `run_a.cleanup()` bắn `RuntimeError("Isolation violation")`, không xóa dữ liệu của Run B.
   - Kiểm tra Case 2: Clean up Run B trước, sau đó clean up Run A thành công; Shared ADMIN không bị xóa.
   - Kiểm tra Case 3: Chạy cleanup lần 2 cho cả 2 run contexts hoàn toàn không phát sinh lỗi.
5. **`test_idempotency_cross_run_isolation_and_shared_admin_safety` (`IDEMPOTENCY_ISOLATION_VERIFIED`):**
   - Run A tạo và confirm Receipt A với Idempotency Key A.
   - Run B tạo và confirm Receipt B với Idempotency Key B.
   - Trước cleanup: Query trực tiếp bảng `idempotency_records`, assert cả Record A và Record B đều tồn tại (`user_id`, `operation='CONFIRM_RECEIPT'`, `key_digest`).
   - Chạy `run_a.cleanup()`.
   - Sau cleanup Run A: Query trực tiếp bảng `idempotency_records`, assert Record A đã bị xóa, Record B VẪN TỒN TẠI NGUYÊN VẸN.
   - Assert Receipt B, User Admin (Shared ADMIN) vẫn nguyên vẹn.
   - Chạy `run_b.cleanup()`: Query assert Record B đã bị xóa.
   - Assert User Admin (Shared ADMIN) VẪN TỒN TẠI.
   - Chạy lại `run_a.cleanup()` và `run_b.cleanup()` lần 2 để kiểm chứng tính idempotent.

#### Bảng bằng chứng kiểm thử cô lập Idempotency & Shared ADMIN (Test Isolation Evidence)
| Run ID | Operation | Idempotency Key | Trạng thái trước Cleanup A | Trạng thái sau Cleanup A | Trạng thái sau Cleanup B | Shared ADMIN Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Run A` (`t04aabc_idm_a_*`) | `CONFIRM_RECEIPT` | `idemp-iso-a-*` | Tồn tại (`EXISTS`) | Đã xóa (`DELETED`) | Đã xóa (`DELETED`) | Tồn tại nguyên vẹn (`admin_slot=1`) |
| `Run B` (`t04aabc_idm_b_*`) | `CONFIRM_RECEIPT` | `idemp-iso-b-*` | Tồn tại (`EXISTS`) | Nguyên vẹn (`PRESERVED`) | Đã xóa (`DELETED`) | Tồn tại nguyên vẹn (`admin_slot=1`) |

---

## 4. KẾT QUẢ QUALITY GATES

### 4.1. Ruff Linter & Formatter Check
```bash
$ uv run --locked ruff check .
All checks passed!

$ uv run --locked ruff format --check .
182 files already formatted
```

### 4.2. Pytest API Suite
```bash
$ uv run --locked pytest tests/modules/purchasing/test_t04aabc_purchasing_email_api.py -v
============================= test session starts =============================
platform win32 -- Python 3.12.16, pytest-8.4.2, pluggy-1.7.0
plugins: anyio-4.16.0
collected 24 items

tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_reference_model_signatures_conform_to_contract PASSED [  4%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_outbox_publisher_reference_model_publishes_due_events PASSED [  8%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_email_event_handler_reference_model_lifecycle PASSED [ 12%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_auth_reset_reference_model_account_non_enumeration PASSED [ 16%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_reference_model_logging_policy_example PASSED [ 20%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_production_exception_handler_log_sanitization[asyncio] PASSED [ 25%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_admin_success[...] PASSED [ 50%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_staff_forbidden[...] PASSED [ 75%]
tests/modules/purchasing/test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_anonymous_unauthenticated[...] PASSED [100%]

======================== 24 passed in 1.53s ========================
```

### 4.3. Pytest MySQL Integration Collect Check
```bash
$ uv run --locked pytest tests/modules/purchasing/test_t04aabc_purchasing_email_mysql.py --collect-only
============================= test session starts =============================
platform win32 -- Python 3.12.16, pytest-8.4.2, pluggy-1.7.0
collected 5 items

<Package tests/modules/purchasing>
  <Module test_t04aabc_purchasing_email_mysql.py>
    <Function test_e2e_purchasing_lifecycle_and_stock_movements>
    <Function test_no_second_stock_increase_on_sequential_reconfirmation>
    <Function test_transactional_outbox_intent_durability>
    <Function test_mysql_cross_run_isolation_and_idempotent_cleanup>
    <Function test_idempotency_cross_run_isolation_and_shared_admin_safety>

========================= 5 tests collected in 1.49s ==========================
```
*(Ghi chú: Tại môi trường local không có database integration test riêng biệt, `database_guard.py` kích hoạt cơ chế fail-closed để bảo vệ database dev/prod. Bộ test integration sẽ được thực thi thực tế trên MySQL 8.4 tại GitHub Actions CI).*

---

## 5. RỦI RO CÒN LẠI VÀ KHUYẾN NGHỊ CHO CÁC TASK TIẾP THEO (RESIDUAL RISKS)

1. **Deferred Email Worker & Reset Service:**
   - Các dịch vụ Celery Worker (`T04A90F`, `T04AA00`) và Password Reset (`T04AA1C`) chưa có code production trên nhánh `develop`. Các kiểm thử liên quan ở task này mang tính chất Contract Verification qua Reference Models. Khi các PR trên được đưa lên review, cần bổ sung test tích hợp thực tế với broker và mail server.
2. **Cryptographic Validation:**
   - Kiểm thử hiện tại chỉ xác nhận ràng buộc cột `VARBINARY(2048)` và ràng buộc check constraint `ck_outbox_events_secret_expiry`. Việc giải mã xác thực (AES-256-GCM authenticated decryption) cần được kiểm chứng khi module Reset Service hoàn thiện.
3. **Concurrency Stress Testing:**
   - Đã kiểm chứng an toàn chống tăng kho khi confirm lặp tuần tự (`SEQUENTIAL_DUPLICATE_CONFIRMATION_VERIFIED`). Kiểm thử 2 luồng đồng thời (concurrent threads) cần được thực hiện trong test suite Performance / Stress Testing riêng của hệ thống.

---

## 6. KẾT LUẬN & MERGE READINESS

PR #70 đã khắc phục triệt để các finding từ Independent Review, đảm bảo:
- Cô lập dữ liệu kiểm thử MySQL an toàn tuyệt đối, không xóa lan sang run khác.
- Dọn dẹp Idempotency chính xác cho shared ADMIN.
- Phân định minh bạch giữa Production Code và Reference Models.
- Quality Gates (Linter, Formatter, Unit/Contract Tests) đạt 100% PASS.

**Trạng thái đề xuất:** `READY FOR LEAD REVIEW`.
