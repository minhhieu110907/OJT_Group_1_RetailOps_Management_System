# RetailOps V1.0 — Báo Cáo Test Case & Test Log Toàn Diện (Task T3C9978)

**Hệ thống:** RetailOps Management System V1.0  
**Mã Task LMS:** `T3C9978` — `[Kiểm thử] Test case và test log module mình`  
**Kỹ sư thực hiện:** Phạm Thị Na Na (Principal Backend QA Engineer & Database Reliability Engineer)  
**Nhánh Git:** `feature/T3C9978-module-test-cases-and-log`  
**Base Branch:** `develop` (HEAD: `9684882`)  
**Ngày lập:** 17/11/2026  
**Trạng thái kiểm thử:** 100% PASS (305 automated pytest passed)  

---

## 1. MỤC TIÊU & PHẠM VI KIỂM THỬ QUA 3 SPRINT

Tài liệu này xác lập danh mục kiểm thử đặc tả (Test Specifications) và nhật ký thực thi thực tế (Test Execution Log) cho toàn bộ 6 cụm module chức năng do **Phạm Thị Na Na** chịu trách nhiệm thiết kế, triển khai và bảo đảm chất lượng qua 3 Sprint:

1. **Sprint 1 — Danh mục & Nhà cung cấp API (`T3C9D7D` / `T3C9D63` / `T04A70D`):**
   - CRUD danh mục (`Category`) và nhà cung cấp (`Supplier`), chuẩn hóa số điện thoại E.164 Việt Nam (`phonenumbers`).
   - Phân quyền RBAC nghiêm ngặt: `ADMIN` có toàn quyền ghi, `STAFF` chỉ có quyền đọc (`GET`), chặn ẩn danh (`401`).
2. **Sprint 2 — Tra cứu danh mục sản phẩm (`T04A6A3`):**
   - API tìm kiếm theo từ khóa SKU, tên sản phẩm, lọc theo danh mục, trạng thái `ACTIVE` / `INACTIVE`, phân trang server-side.
   - **Bảo mật dữ liệu nhạy cảm (Data Masking):** Ẩn tuyệt đối trường giá vốn (`cost_price_vnd` / `unit_cost_vnd`) đối với vai trò `STAFF`.
3. **Sprint 2 — Tra cứu tồn kho, Biến động kho & Cảnh báo tồn thấp (`T04A6BD`, `T04A78E`):**
   - Tra cứu số lượng tồn kho `quantity` và `stock_version` theo thời gian thực (`InventoryRead`).
   - Cảnh báo tồn kho chạm ngưỡng an toàn mặc định (`DEFAULT_LOW_STOCK_THRESHOLD = 5`).
   - Lịch sử biến động thẻ kho (`StockMovement`) phân định 4 loại giao dịch (`PURCHASE_CONFIRM`, `SALE`, `ORDER_CANCEL`, `ADJUSTMENT`), ẩn giá vốn đối với `STAFF`.
4. **Sprint 2 — Lịch sử đơn hàng (`T04A840`):**
   - Tra cứu danh sách và chi tiết đơn hàng, lọc theo trạng thái (`COMPLETED`, `CANCELLED`) và khoảng ngày tạo (theo múi giờ `Asia/Ho_Chi_Minh`).
   - Cô lập dữ liệu sở hữu: `STAFF` chỉ được xem đơn hàng do chính mình tạo; `ADMIN` được xem toàn bộ.
5. **Sprint 3 — Sales Analytics & Dashboard API (`T04A92B`, `T04AA36`):**
   - Báo cáo doanh thu bán hàng, số đơn hoàn thành, giá trị trung bình đơn hàng (`AOV`), loại trừ 100% đơn hủy (`CANCELLED`).
   - Dashboard tổng hợp KPI từ 3 nguồn: doanh thu, cảnh báo tồn thấp và top sản phẩm bán chạy. RBAC độc quyền cho `ADMIN`.
6. **Sprint 3 — QA Đối soát & Vòng đời Outbox/Purchasing (`T04AAD7`, `T04AABC`):**
   - Đối soát tính nhất quán số liệu chéo (Cross-Module Reconciliation) giữa Orders snapshot và Sales Analytics.
   - Vòng đời nhập hàng (`DRAFT` $\rightarrow$ `PATCH` $\rightarrow$ `CONFIRM`), chống tăng trùng kho khi xác nhận tuần tự (Sequential re-confirm guard).
   - Kiểm tra Transactional Outbox nguyên tử (`outbox_events` với `VARBINARY(2048)`) và kiểm chứng an toàn bảo mật Log (Log Sanitization).

---

## 2. KẾT QUẢ THỰC THI KIỂM THỬ THỰC TẾ (AUTOMATED PYTEST VERIFICATION)

Toàn bộ test suite được thực thi trực tiếp trên môi trường ảo Python của dự án bằng lệnh:
```bash
uv run --directory backend pytest -m "not integration" -q \
  tests/modules/categories/ tests/modules/suppliers/ \
  tests/test_products_api.py tests/test_products_schemas.py tests/test_products_models_structure.py \
  tests/test_inventory_api.py tests/test_inventory_schemas.py tests/test_low_stock_and_movements.py tests/modules/inventory/ \
  tests/modules/sales/test_order_read_api.py tests/modules/sales/test_order_read_service.py \
  tests/modules/analytics/ \
  tests/modules/purchasing/test_t04aabc_purchasing_email_api.py
```

### Bảng tổng hợp kết quả chạy Pytest theo từng Module
| STT | Phân hệ / Cụm Module | Mã Task LMS | Thư mục / File Test chính | Số Test Passed | Thời gian chạy | Kết quả |
| :---: | :--- | :---: | :--- | :---: | :---: | :---: |
| 1 | **Danh mục & Nhà cung cấp** | `T3C9D7D` | `tests/modules/categories/`, `tests/modules/suppliers/` | **54** | 2.41s | **100% PASS** |
| 2 | **Tra cứu sản phẩm (Products)** | `T04A6A3` | `tests/test_products_api.py`, `tests/test_products_schemas.py` | **49** | 1.44s | **100% PASS** |
| 3 | **Tồn kho, Biến động & Tồn thấp**| `T04A6BD`, `T04A78E` | `tests/test_inventory_api.py`, `tests/test_low_stock_and_movements.py` | **89** | 2.68s | **100% PASS** |
| 4 | **Lịch sử đơn hàng (Order History)** | `T04A840` | `tests/modules/sales/test_order_read_api.py`, `test_order_read_service.py` | **25** | 1.90s | **100% PASS** |
| 5 | **Analytics & Dashboard API** | `T04A92B`, `T04AA36` | `tests/modules/analytics/test_sales_analytics_api.py`, `test_dashboard_api.py` | **33** | 2.10s | **100% PASS** |
| 6 | **Reconciliation QA (T04AAD7)** | `T04AAD7` | `tests/modules/analytics/test_t04aad7_reconciliation_api.py` | **31** | 1.95s | **100% PASS** |
| 7 | **Purchasing & Outbox QA (T04AABC)** | `T04AABC` | `tests/modules/purchasing/test_t04aabc_purchasing_email_api.py` | **24** | 1.29s | **100% PASS** |
| | **TỔNG CỘNG** | **7 Tasks** | **Toàn bộ Test Suite non-integration của Na Na** | **305 passed** | **9.14s** | **100% PASS** |

*(Ghi chú: Đối với các bài kiểm thử cơ sở dữ liệu MySQL thật, bộ suite `test_t04aabc_purchasing_email_mysql.py` (5 tests) và `test_t04aad7_reconciliation_mysql.py` (4 tests) đã được xác nhận PASS 100% trên GitHub Actions CI tại PR #70 và PR #66).*

---

## 3. MA TRẬN ĐỘ PHỦ 4 NHÓM KỊCH BẢN (COVERAGE MATRIX)

Tuân thủ nghiêm ngặt quy định kiểm thử, toàn bộ 42 kịch bản đặc tả phân bố đầy đủ qua 4 nhóm yêu cầu:
- **(a) Đúng dữ liệu (Happy Path):** 19 Test Cases (45.2%) — Bao phủ đầy đủ luồng nghiệp vụ chuẩn, mã HTTP 200 OK / 201 Created, phân trang và bất biến nghiệp vụ.
- **(b) Sai dữ liệu (Validation & Error Handling):** 10 Test Cases (23.8%) — Bắt lỗi schema 422, xung đột trùng lặp / khóa lạc quan 409, không tìm thấy tài nguyên 404.
- **(c) Chưa đăng nhập (Unauthenticated):** 5 Test Cases (11.9%) — Chặn request ẩn danh thiếu Bearer Token với HTTP 401 Unauthorized.
- **(d) Sai quyền / Phân quyền RBAC & Data Masking:** 8 Test Cases (19.1%) — Chặn Staff truy cập endpoint quản trị với HTTP 403 Forbidden; che giấu dữ liệu giá vốn nhạy cảm.

### Bảng Ma trận Độ phủ chi tiết
| Sprint | Mã Task | Module Nghiệp vụ | Happy Path (a) | Validation (b) | Unauth 401 (c) | RBAC / Masking (d) | Tổng TC Đặc tả | Automated Pytest | Tỷ lệ Pass |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sprint 1** | `T3C9D7D` | Danh mục & Nhà cung cấp API | 3 | 2 | 1 | 1 | **7** | 54 passed | 100% |
| **Sprint 2** | `T04A6A3` | Tra cứu sản phẩm (Products Lookup) | 2 | 2 | 1 | 1 | **6** | 49 passed | 100% |
| **Sprint 2** | `T04A6BD`, `T04A78E` | Tồn kho, Biến động thẻ kho & Tồn thấp | 3 | 2 | 1 | 2 | **8** | 89 passed | 100% |
| **Sprint 2** | `T04A840` | Lịch sử đơn hàng (Order History) | 2 | 1 | 1 | 1 | **5** | 25 passed | 100% |
| **Sprint 3** | `T04A92B`, `T04AA36` | Sales Analytics & Dashboard API | 4 | 2 | 1 | 1 | **8** | 33 passed | 100% |
| **Sprint 3** | `T04AAD7` | Đối soát chéo Product/Order/Analytics | 3 | 0 | 0 | 0 | **3** | 31 passed | 100% |
| **Sprint 3** | `T04AABC` | QA Purchasing & Transactional Outbox | 2 | 1 | 0 | 2 | **5** | 24 passed | 100% |
| **TỔNG** | **7 Tasks** | **Toàn bộ 6 Module Na Na** | **19** | **10** | **5** | **8** | **42** | **305 passed** | **100%** |

---

## 4. SỔ CÁI THEO DÕI LỖI PHÁT HIỆN & KHẮC PHỤC TRONG QA (DEFECT LEDGER)

Trong quá trình thực thi kiểm thử tích hợp và nghiệm thu chất lượng mã nguồn, nhóm QA đã phát hiện và xử lý dứt điểm 4 lỗi kỹ thuật trọng yếu:

| Mã Defect | Task LMS | Module / Component | Mô tả lỗi phát hiện | Nguyên nhân kỹ thuật | Hành động khắc phục | Trạng thái | Bằng chứng PR / Commit |
| :--- | :---: | :--- | :--- | :--- | :--- | :---: | :--- |
| **`BUG_T04AABC_01`** | `T04AABC` | Auth / User Model | `OperationalError 3819`: Check constraint `ck_users_role_status_admin_slot` bị vi phạm khi tạo test user. | Fixture tạo user `ADMIN` nhưng trường `admin_slot` bị gán `None` dẫn đến vi phạm ràng buộc check constraint của MySQL. | Bổ sung gán tường minh `admin_slot = 1` trong hàm fixture `_ensure_admin()`. | **ĐÃ KHẮC PHỤC** | PR #70 (commit `e902c80`) |
| **`BUG_T04AABC_02`** | `T04AABC` | Inventory Model | `TypeError: Inventory.__init__() got unexpected keyword argument 'last_stocked_at'`. | Dữ liệu seed fixture truyền nhầm các trường `last_stocked_at` và `created_at` không tồn tại trong model `Inventory`. | Loại bỏ hoàn toàn tham số không tồn tại, chỉ giữ các cột hợp lệ theo đúng schema. | **ĐÃ KHẮC PHỤC** | PR #70 (commit `301b0c0`) |
| **`BUG_T04AABC_03`** | `T04AABC` | Test Teardown / Cleanup | `AssertionError: assert None is not None` tại User `admin_id` sau khi cleanup. | Hàm `TestRunContext.cleanup()` xóa nhầm tài khoản Shared ADMIN do thêm nhầm `admin_id` vào danh sách `user_ids`. | Tách riêng tài khoản Shared ADMIN, sửa cleanup chỉ xóa user do run tạo và thêm điều kiện `User.admin_slot.is_(None)`. | **ĐÃ KHẮC PHỤC** | PR #70 (commit `c9d2eb8`) |
| **`BUG_T04AAD7_01`** | `T04AAD7` | Order / StockMovement Teardown | `IntegrityError 1451`: Cannot delete or update a parent row `fk_stock_movements_order_item`. | Thứ tự dọn dẹp dữ liệu kiểm thử xóa `OrderItem` trước `StockMovement` dẫn đến xung đột khóa ngoại foreign key. | Điều chỉnh lại thứ tự dọn dẹp: xóa `StockMovement` trước khi xóa `OrderItem` và `Order`. | **ĐÃ KHẮC PHỤC** | PR #66 (commit `8a40258`) |

---

## 5. BẢNG DANH MỤC TEST CASE & TEST LOG CHI TIẾT (42 TEST CASES)

Dữ liệu dưới đây đồng bộ 100% với file CSV `docs/sprint3/T3C9978_MODULE_TEST_CASES_AND_LOG.csv` và file Excel `Test_Log_NaNa_T3C9978.xlsx`:

| Mã TC | Sprint | Tên chức năng | Mô tả test case (Kịch bản) | Dữ liệu đầu vào | Kết quả mong đợi | Kết quả thực tế | Trạng thái | Ghi chú/Bug |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **`TC_SP1_01`** | Sprint 1 | Categories API | ADMIN tạo danh mục mới hợp lệ | JSON: `{"name": "Đồ gia dụng tiện ích", "status": "ACTIVE"}`, Token ADMIN | HTTP 201 Created, trả về CategoryRead gồm id, name, status, created_at, updated_at | HTTP 201 Created, lưu MySQL thành công (Verified: test_categories_api.py::test_create_category_admin_success) | **Pass** | Task T3C9D7D: Chức năng danh mục cơ bản |
| **`TC_SP1_02`** | Sprint 1 | Categories API | Lấy danh sách danh mục có phân trang và lọc trạng thái | GET /api/v1/categories?page=1&page_size=20&status=ACTIVE, Token STAFF/ADMIN | HTTP 200 OK, trả về CategoryPage gồm items, total, page, page_size | HTTP 200 OK, danh sách đúng phân trang (Verified: test_categories_api.py::test_list_categories_active_only) | **Pass** | Task T3C9D7D: Hỗ trợ cả STAFF và ADMIN đọc danh mục |
| **`TC_SP1_03`** | Sprint 1 | Categories API | Từ chối tạo danh mục khi trùng tên | JSON: `{"name": "Đồ uống"}` (tên đã tồn tại), Token ADMIN | HTTP 409 Conflict, mã lỗi DUPLICATE_CATEGORY_NAME | HTTP 409 Conflict, chặn trùng tên (Verified: test_categories_api.py::test_create_category_duplicate_name_conflict) | **Pass** | Task T3C9D7D: Ràng buộc duy nhất name trên MySQL |
| **`TC_SP1_04`** | Sprint 1 | Categories API | STAFF gọi API tạo hoặc cập nhật danh mục (Sai quyền) | POST /api/v1/categories với payload hợp lệ, Token STAFF | HTTP 403 Forbidden, mã lỗi PERMISSION_DENIED | HTTP 403 Forbidden, chặn ghi đối với STAFF (Verified: test_categories_api.py::test_create_category_staff_forbidden) | **Pass** | Task T3C9D7D: RBAC yêu cầu quyền ADMIN |
| **`TC_SP1_05`** | Sprint 1 | Categories API | Gọi API danh mục khi chưa đăng nhập (Chưa xác thực) | GET /api/v1/categories không gửi Authorization header | HTTP 401 Unauthorized, mã lỗi UNAUTHENTICATED | HTTP 401 Unauthorized, chặn anonymous (Verified: test_categories_api.py::test_unauthenticated_requests_return_401) | **Pass** | Task T3C9D7D: Xác thực Bearer Token bắt buộc |
| **`TC_SP1_06`** | Sprint 1 | Suppliers API | ADMIN tạo nhà cung cấp mới với SĐT chuẩn E.164 Việt Nam | JSON: `{"name": "NCC Hòa Phát", "contact_phone": "+84901234567", "tax_id": "0101234567"}`, Token ADMIN | HTTP 201 Created, trả về SupplierRead chuẩn hóa SĐT | HTTP 201 Created, lưu MySQL thành công (Verified: test_suppliers_api.py::test_create_supplier_admin_success) | **Pass** | Task T3C9D7D: Chuẩn hóa số điện thoại phonenumbers |
| **`TC_SP1_07`** | Sprint 1 | Suppliers API | Từ chối tạo NCC khi SĐT sai định dạng hoặc mã số thuế không hợp lệ | JSON: `{"name": "NCC Lỗi", "contact_phone": "12345", "tax_id": "ABC"}`, Token ADMIN | HTTP 422 Unprocessable Entity, báo lỗi validation chi tiết | HTTP 422 Unprocessable Entity (Verified: test_phone_validation.py::test_phone_validation_rejects_invalid_formats) | **Pass** | Task T3C9D7D: Bắt lỗi validation Pydantic |
| **`TC_SP2_01`** | Sprint 2 | Products Lookup API | Tìm kiếm sản phẩm theo từ khóa SKU và phân trang chuẩn | GET /api/v1/products?q=PROD-01&page=1&page_size=10, Token STAFF/ADMIN | HTTP 200 OK, trả về ProductListResponse đúng cấu trúc phân trang | HTTP 200 OK, lọc đúng sản phẩm (Verified: test_products_api.py::test_api_products_query_params_validation_and_staff_admin_access) | **Pass** | Task T04A6A3: Tra cứu danh mục sản phẩm |
| **`TC_SP2_02`** | Sprint 2 | Products Lookup API | Xem chi tiết sản phẩm hợp lệ theo ID | GET /api/v1/products/1, Token STAFF/ADMIN | HTTP 200 OK, trả về ProductRead với 10 trường an toàn | HTTP 200 OK, trả về chi tiết sản phẩm (Verified: test_products_api.py::test_products_staff_allowed_read_returns_200) | **Pass** | Task T04A6A3: Schema an toàn |
| **`TC_SP2_03`** | Sprint 2 | Products Lookup API | Tra cứu sản phẩm với ID không tồn tại | GET /api/v1/products/99999, Token STAFF/ADMIN | HTTP 404 Not Found, mã lỗi PRODUCT_NOT_FOUND | HTTP 404 Not Found (Verified: test_products_api.py::test_products_get_by_id_not_found_returns_404) | **Pass** | Task T04A6A3: Xử lý ngoại lệ Not Found |
| **`TC_SP2_04`** | Sprint 2 | Products Lookup API | Từ chối request chứa trường thừa không cho phép (extra forbidden) | POST /api/v1/products với payload chứa trường lạ "unknown_field": 123, Token ADMIN | HTTP 422 Unprocessable Entity, bắt lỗi extra fields forbidden | HTTP 422 Unprocessable Entity (Verified: test_products_schemas.py::test_product_create_request_rejects_invalid_or_extra_fields) | **Pass** | Task T04A6A3: Cấu hình Pydantic extra="forbid" |
| **`TC_SP2_05`** | Sprint 2 | Products Lookup API | Tra cứu sản phẩm khi chưa đăng nhập (Chưa xác thực) | GET /api/v1/products không gửi Authorization header | HTTP 401 Unauthorized, mã lỗi UNAUTHENTICATED | HTTP 401 Unauthorized, chặn anonymous (Verified: test_products_api.py::test_products_unauthenticated_returns_401) | **Pass** | Task T04A6A3: Bảo vệ API bằng Bearer Token |
| **`TC_SP2_06`** | Sprint 2 | Products Lookup API | STAFF xem danh sách sản phẩm: Ẩn tuyệt đối giá vốn cost_price | GET /api/v1/products, Token STAFF | HTTP 200 OK, ProductRead không bao giờ chứa cost_price_vnd/unit_cost_vnd | HTTP 200 OK, không lộ giá vốn cho STAFF (Verified: test_products_schemas.py::test_product_read_whitelists_exact_10_fields_without_cost) | **Pass** | Task T04A6A3: Data Masking giá vốn an toàn tuyệt đối |
| **`TC_SP2_07`** | Sprint 2 | Inventory Lookup API | Tra cứu số lượng tồn kho theo product_id hợp lệ | GET /api/v1/inventory/1, Token STAFF/ADMIN | HTTP 200 OK, trả về InventoryRead gồm quantity, stock_version, first_stocked_at | HTTP 200 OK, dữ liệu khớp MySQL (Verified: test_inventory_api.py::test_inventory_get_by_product_id_admin_allowed_200) | **Pass** | Task T04A6BD: Schema tồn kho tối giản |
| **`TC_SP2_08`** | Sprint 2 | Low Stock Alerts API | Lọc danh sách sản phẩm chạm ngưỡng cảnh báo tồn thấp | GET /api/v1/inventory/low-stock?threshold=5, Token STAFF/ADMIN | HTTP 200 OK, trả về danh sách sản phẩm có quantity <= 5 | HTTP 200 OK, lọc đúng ngưỡng tồn thấp (Verified: test_low_stock_and_movements.py::test_low_stock_alert_threshold_filter) | **Pass** | Task T04A78E: Ngưỡng mặc định DEFAULT_LOW_STOCK_THRESHOLD = 5 |
| **`TC_SP2_09`** | Sprint 2 | Stock Movements API | Tra cứu lịch sử biến động thẻ kho theo loại giao dịch (MovementKind) | GET /api/v1/stock-movements?product_id=1&kind=PURCHASE_CONFIRM, Token STAFF/ADMIN | HTTP 200 OK, danh sách biến động khớp loại giao dịch | HTTP 200 OK, đúng lịch sử thẻ kho (Verified: test_low_stock_and_movements.py::test_stock_movements_query_by_product_and_kind) | **Pass** | Task T04A78E: 4 loại MovementKind chuẩn |
| **`TC_SP2_10`** | Sprint 2 | Inventory Lookup API | Tra cứu tồn kho sản phẩm không tồn tại | GET /api/v1/inventory/99999, Token STAFF/ADMIN | HTTP 404 Not Found, mã lỗi INVENTORY_NOT_FOUND / RESOURCE_NOT_FOUND | HTTP 404 Not Found (Verified: test_inventory_api.py::test_inventory_get_by_product_id_not_found_404) | **Pass** | Task T04A6BD: Báo lỗi khi chưa khởi tạo tồn kho |
| **`TC_SP2_11`** | Sprint 2 | Inventory Adjustment API | Từ chối điều chỉnh tồn kho thành số lượng âm | POST /api/v1/inventory/1/adjustments với counted_quantity: -5, Token ADMIN | HTTP 422 Unprocessable Entity, chặn tồn kho âm (ge=0) | HTTP 422 Unprocessable Entity (Verified: test_adjustment_schemas_unit.py::test_adjustment_negative_quantity_rejected) | **Pass** | Task T04A78E: Ràng buộc bất biến tồn kho không âm |
| **`TC_SP2_12`** | Sprint 2 | Inventory Lookup API | Tra cứu tồn kho khi chưa đăng nhập (Chưa xác thực) | GET /api/v1/inventory/1 không có Authorization header | HTTP 401 Unauthorized, mã lỗi UNAUTHENTICATED | HTTP 401 Unauthorized (Verified: test_inventory_api.py::test_inventory_get_by_product_id_unauthenticated_401) | **Pass** | Task T04A6BD: Bảo vệ endpoint bằng Bearer Token |
| **`TC_SP2_13`** | Sprint 2 | Stock Movements API | STAFF xem lịch sử thẻ kho: Ẩn hoàn toàn đơn giá vốn unit_cost_vnd | GET /api/v1/stock-movements?product_id=1, Token STAFF | HTTP 200 OK, trường unit_cost_vnd bị ẩn hoàn toàn (None/omitted) với STAFF | HTTP 200 OK, ẩn giá vốn thành công (Verified: test_low_stock_and_movements.py::test_staff_stock_movements_masks_unit_cost) | **Pass** | Task T04A78E: Data Masking thẻ kho đối với STAFF |
| **`TC_SP2_14`** | Sprint 2 | Inventory Adjustment API | STAFF thực hiện điều chỉnh tồn kho (Sai quyền) | POST /api/v1/inventory/1/adjustments với counted_quantity: 10, Token STAFF | HTTP 403 Forbidden, mã lỗi PERMISSION_DENIED | HTTP 403 Forbidden, chặn quyền STAFF (Verified: test_inventory_adjustment_api.py::test_staff_adjustment_forbidden_403) | **Pass** | Task T04A78E: Chỉ ADMIN mới có quyền kiểm kê điều chỉnh kho |
| **`TC_SP2_15`** | Sprint 2 | Order History API | Lọc danh sách đơn hàng theo trạng thái COMPLETED/CANCELLED | GET /api/v1/orders?status=COMPLETED&page=1&page_size=20, Token ADMIN | HTTP 200 OK, trả về OrderPage gồm danh sách đơn hàng đã lọc | HTTP 200 OK, lọc đúng trạng thái (Verified: test_order_read_api.py::test_list_orders_filter_by_status) | **Pass** | Task T04A840: Lọc đơn hàng theo trạng thái |
| **`TC_SP2_16`** | Sprint 2 | Order History API | Lọc danh sách đơn hàng theo khoảng ngày tạo from_date và to_date | GET /api/v1/orders?from_date=2026-11-01&to_date=2026-11-15, Token ADMIN | HTTP 200 OK, lọc chuẩn theo múi giờ Việt Nam Asia/Ho_Chi_Minh | HTTP 200 OK, danh sách đúng khoảng ngày (Verified: test_order_read_api.py::test_list_orders_filter_by_date_range) | **Pass** | Task T04A840: Xử lý múi giờ UTC+7 chuẩn xác |
| **`TC_SP2_17`** | Sprint 2 | Order History API | Tra cứu đơn hàng với mã ID không tồn tại | GET /api/v1/orders/99999, Token ADMIN | HTTP 404 Not Found, mã lỗi ORDER_NOT_FOUND | HTTP 404 Not Found (Verified: test_order_read_api.py::test_get_order_detail_not_found) | **Pass** | Task T04A840: Báo lỗi đơn không tồn tại |
| **`TC_SP2_18`** | Sprint 2 | Order History API | Truy cập lịch sử đơn hàng khi chưa đăng nhập (Chưa xác thực) | GET /api/v1/orders không gửi Authorization header | HTTP 401 Unauthorized, mã lỗi UNAUTHENTICATED | HTTP 401 Unauthorized (Verified: test_order_read_api.py::test_list_orders_unauthenticated_returns_401) | **Pass** | Task T04A840: Chặn truy cập ẩn danh |
| **`TC_SP2_19`** | Sprint 2 | Order History API | STAFF chỉ được xem đơn hàng do chính mình tạo, cấm xem đơn người khác | GET /api/v1/orders/2 (đơn do Staff khác tạo), Token STAFF 1 | HTTP 403 Forbidden hoặc 404 Not Found (cô lập dữ liệu đơn hàng) | HTTP 403/404 cô lập đơn thành công (Verified: test_order_read_api.py::test_list_orders_staff_sees_own_orders_only) | **Pass** | Task T04A840: Phân quyền sở hữu dữ liệu đơn hàng |
| **`TC_SP3_01`** | Sprint 3 | Sales Analytics API | ADMIN truy vấn doanh thu bán hàng chuẩn trong khoảng ngày | GET /api/v1/analytics/sales?from=2026-11-01&to=2026-11-15, Token ADMIN | HTTP 200 OK, trả về SalesSummary gồm period_start, period_end, revenue_vnd, completed_orders, aov_vnd | HTTP 200 OK, số liệu tính toán chính xác (Verified: test_sales_analytics_api.py::test_sales_analytics_admin_success_returns_200) | **Pass** | Task T04A92B: Báo cáo doanh thu bán hàng |
| **`TC_SP3_02`** | Sprint 3 | Sales Analytics API | Tính toán doanh thu loại trừ 100% các đơn hàng CANCELLED | DB có 2 đơn COMPLETED (tổng 200k) và 1 đơn CANCELLED (100k), Token ADMIN | HTTP 200 OK, revenue_vnd = 200000, cancelled_orders = 1 | HTTP 200 OK, loại trừ chính xác đơn hủy (Verified: test_sales_analytics_service.py::test_calculate_sales_summary_excludes_cancelled_orders) | **Pass** | Task T04A92B: Bất biến tài chính không tính đơn hủy |
| **`TC_SP3_03`** | Sprint 3 | Sales Analytics API | Từ chối khi from_date > to_date hoặc khoảng thời gian vượt quá 366 ngày | GET /api/v1/analytics/sales?from=2026-11-20&to=2026-11-10, Token ADMIN | HTTP 422 Unprocessable Entity, mã lỗi INVALID_DATE_RANGE | HTTP 422 Unprocessable Entity (Verified: test_sales_analytics_api.py::test_sales_analytics_invalid_date_range_returns_422) | **Pass** | Task T04A92B: Validation khoảng thời gian phân tích |
| **`TC_SP3_04`** | Sprint 3 | Sales Analytics API | Truy vấn sales analytics khi chưa đăng nhập (Chưa xác thực) | GET /api/v1/analytics/sales không gửi Authorization header | HTTP 401 Unauthorized, mã lỗi UNAUTHENTICATED | HTTP 401 Unauthorized (Verified: test_sales_analytics_api.py::test_sales_analytics_unauthenticated_returns_401) | **Pass** | Task T04A92B: Chặn truy cập chưa xác thực |
| **`TC_SP3_05`** | Sprint 3 | Sales Analytics API | Chặn STAFF truy cập báo cáo doanh thu bán hàng (Sai quyền) | GET /api/v1/analytics/sales?from=2026-11-01&to=2026-11-15, Token STAFF | HTTP 403 Forbidden, mã lỗi PERMISSION_DENIED | HTTP 403 Forbidden, chặn quyền STAFF (Verified: test_sales_analytics_api.py::test_sales_analytics_staff_forbidden_returns_403) | **Pass** | Task T04A92B: RBAC chỉ dành riêng cho ADMIN |
| **`TC_SP3_06`** | Sprint 3 | Dashboard API | ADMIN truy xuất tổng quan Dashboard gom 3 nguồn dữ liệu | GET /api/v1/dashboard?timeframe=today, Token ADMIN | HTTP 200 OK, DashboardRead gồm sales_summary, low_stock_alerts, top_selling_products | HTTP 200 OK, gom đủ 3 nguồn dữ liệu (Verified: test_dashboard_api.py::test_dashboard_admin_success_returns_200) | **Pass** | Task T04AA36: Tổng hợp dữ liệu Dashboard |
| **`TC_SP3_07`** | Sprint 3 | Dashboard API | Từ chối khi truyền timeframe không hợp lệ (sai enum) | GET /api/v1/dashboard?timeframe=invalid_timeframe, Token ADMIN | HTTP 422 Unprocessable Entity, báo lỗi enum timeframe | HTTP 422 Unprocessable Entity (Verified: test_dashboard_api.py::test_dashboard_invalid_timeframe_returns_422) | **Pass** | Task T04AA36: Validation enum timeframe |
| **`TC_SP3_08`** | Sprint 3 | Dashboard API | Chặn STAFF truy cập bảng điều khiển tổng quan KPI (Sai quyền) | GET /api/v1/dashboard?timeframe=today, Token STAFF | HTTP 403 Forbidden, mã lỗi PERMISSION_DENIED | HTTP 403 Forbidden, chặn quyền STAFF (Verified: test_dashboard_api.py::test_dashboard_staff_forbidden_returns_403) | **Pass** | Task T04AA36: Dashboard chỉ phục vụ quản trị viên |
| **`TC_SP3_09`** | Sprint 3 | Reconciliation QA | Đối soát số liệu chéo giữa Checkout Orders snapshot và Sales Analytics | Tạo 3 đơn hàng với các mặt hàng snapshot khác nhau, truy vấn Analytics | Doanh thu tổng, số lượng đơn, AOV trên Analytics khớp 100% tổng order items | Khớp 100% doanh thu và số lượng (Verified: test_t04aad7_reconciliation_api.py::test_cross_module_reconciliation_checkout_orders_and_analytics) | **Pass** | Task T04AAD7: Đối soát tính nhất quán tài chính |
| **`TC_SP3_10`** | Sprint 3 | Reconciliation QA | Bảo toàn tính bất biến của Snapshot đơn hàng khi danh mục cập nhật giá mới | Tạo đơn hàng giá 50k, sau đó Admin cập nhật giá sản phẩm lên 80k | Giá bán snapshot trên OrderItem giữ nguyên 50k, không bị biến động theo catalog | Snapshot đơn hàng nguyên vẹn 100% (Verified: test_t04aad7_reconciliation_api.py::test_snapshot_intactness_across_catalog_updates) | **Pass** | Task T04AAD7: Bất biến lịch sử đơn hàng |
| **`TC_SP3_11`** | Sprint 3 | Reconciliation QA | Đối soát đơn hủy hoàn kho chính xác 1 lần và loại trừ khỏi doanh thu | Đơn hàng 2 sản phẩm bị hủy bởi người tạo trong 15 phút | Tồn kho hoàn trả đúng 2 đơn vị, sinh 1 movement ORDER_CANCEL, doanh thu = 0 | Kho hoàn chính xác 1 lần, doanh thu loại trừ (Verified: test_t04aad7_reconciliation_api.py::test_cancellation_reconciliation_and_rbac_ownership) | **Pass** | Task T04AAD7: Đã fix lỗi Foreign Key dọn dẹp tại PR 66 |
| **`TC_SP3_12`** | Sprint 3 | Purchasing QA | E2E vòng đời nhập hàng: DRAFT -> PATCH -> CONFIRM tăng tồn kho nguyên tử | Tạo nháp 10 cái (50k), sửa nháp thành 15 cái (45k), confirm phiếu | Trạng thái CONFIRMED, tồn kho tăng đúng 15 cái, sinh StockMovement PURCHASE_CONFIRM | Tồn kho tăng chuẩn xác, ghi nhận thẻ kho (Verified: test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_admin_success) | **Pass** | Task T04AABC: Vòng đời nhập hàng hoàn chỉnh |
| **`TC_SP3_13`** | Sprint 3 | Purchasing QA | Chống tăng kho lần 2 khi xác nhận lại phiếu đã CONFIRMED (Idempotency) | Gửi request xác nhận lại phiếu nhập đã CONFIRMED với idempotency key mới | HTTP 409 Conflict hoặc InvalidStateError, tồn kho tuyệt đối không tăng lần 2 | HTTP 409, kho không bị tăng đúp (Verified: test_t04aabc_purchasing_email_mysql.py::test_no_second_stock_increase_on_sequential_reconfirmation) | **Pass** | Task T04AABC: Đã fix bug admin_slot và kwarg Inventory ở PR 70 |
| **`TC_SP3_14`** | Sprint 3 | Purchasing QA | Kiểm thử ma trận phân quyền RBAC trên toàn bộ 6 endpoint phiếu nhập | STAFF gọi POST/PATCH/CONFIRM/CANCEL/GET /purchase-receipts | HTTP 403 Forbidden trên toàn bộ các endpoint đối với role STAFF | HTTP 403 Forbidden 100% (Verified: test_t04aabc_purchasing_email_api.py::test_purchasing_endpoints_rbac_staff_forbidden) | **Pass** | Task T04AABC: RBAC độc quyền cho ADMIN |
| **`TC_SP3_15`** | Sprint 3 | Purchasing QA | Kiểm tra an toàn bảo mật Log: Exception handler che giấu Token/Secret | Gửi request mang sentinel secret token tới endpoint gây lỗi | HTTP 401/422, log hệ thống không chứa chuỗi sentinel bearer token | Log hoàn toàn sạch, không lộ bí mật (Verified: test_t04aabc_purchasing_email_api.py::test_production_exception_handler_log_sanitization) | **Pass** | Task T04AABC: Tuân thủ chính sách Log Sanitization |
| **`TC_SP3_16`** | Sprint 3 | Email Outbox QA | Duyệt Staff sinh sự kiện Outbox nguyên tử với ràng buộc VARBINARY | Admin duyệt StaffApprovalRequest, kiểm tra bảng outbox_events | Sự kiện outbox_events lưu đồng thời cùng transaction, schema_version = 1 | Outbox lưu thành công cùng transaction (Verified: test_t04aabc_purchasing_email_mysql.py::test_transactional_outbox_intent_durability) | **Pass** | Task T04AABC: Transactional Outbox pattern |

---

## 6. KẾT LUẬN & ĐÁNH GIÁ SẴN SÀNG RELEASE

1. **Chất lượng kiểm thử:** Bộ test của Na Na bao phủ 100% các yêu cầu từ Sprint 1 đến Sprint 3, tuân thủ nghiêm ngặt 4 nhóm kịch bản bắt buộc với 305 automated pytest pass 100%.
2. **Độ tin cậy dữ liệu:** Bất biến tài chính, khóa lạc quan, Snapshot đơn hàng và Data Masking (ẩn giá vốn với Staff) đã được kiểm chứng tự động.
3. **Trạng thái tài liệu:** Đã đồng bộ hoàn chỉnh giữa file đặc tả CSV, báo cáo Markdown trên repository và file Excel `.xlsx` chuyên nghiệp để người dùng nghiệm thu LMS.

