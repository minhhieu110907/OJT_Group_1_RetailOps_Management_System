# RetailOps V1.0 — Tài liệu Test Case & Test Log Module Cá Nhân

**Hệ thống:** RetailOps Management System V1.0  
**Mã Task LMS:** `T3C9972` — `[Kiểm thử] Test case và test log module mình`  
**Sinh viên thực hiện:** Vũ Hoàng Lan Anh  
**Mã sinh viên:** `B25DTCN143`  
**Nhánh Git:** `feature/t3c9972-module-test-cases-and-log`  
**Target Base Branch:** `develop` (HEAD: `b0d4dc9`)  
**Các module phụ trách:**
1. **Module Products Catalog (Sprint 1 — `T3C9AEB`):** Quản lý danh mục sản phẩm, tính duy nhất của mã SKU (hệ thống không sử dụng trường Barcode), thiết kế schema `ProductRead` an toàn tuyệt đối không chứa trường giá vốn (`cost_price_vnd` / `unit_cost_vnd` / `cost`) đối với mọi vai trò người dùng, tạo tồn kho 0 nguyên tử đi kèm.
2. **Module Purchasing & Receipts (Sprint 2 — `T04A6D7`, `T04A772`):** Lập phiếu nhập nháp, tự động gộp dòng sản phẩm trùng giá (Item Merging), khóa lạc quan (`draft_version`), hủy phiếu nháp không đổi tồn kho, tra cứu/lọc danh sách phiếu nhập theo ngày Việt Nam và chi tiết phiếu.

---

## 1. Danh mục 36 Test Cases Chi tiết (Test Specifications)

Tuân thủ nghiêm ngặt 4 nhóm yêu cầu bắt buộc của đề bài kiểm thử:
- **(a) Đúng dữ liệu (Happy Path):** Dữ liệu hợp lệ, trả về HTTP `200 OK` hoặc `201 Created`, đúng cấu trúc DTO và bất biến nghiệp vụ.
- **(b) Sai dữ liệu (Validation & Conflict):** Dữ liệu không hợp lệ trả về HTTP `422 Unprocessable Entity`; xung đột khóa lạc quan / trùng SKU trả về HTTP `409 Conflict`; không tìm thấy tài nguyên trả về HTTP `404 Not Found`.
- **(c) Chưa đăng nhập (Unauthorized):** Không có cookie xác thực, token hết hạn hoặc tài khoản bị vô hiệu hóa trả về HTTP `401 Unauthorized`.
- **(d) Sai quyền (Forbidden & Data Masking):** User role `STAFF` cố gắng thực hiện các thao tác chỉ dành cho `ADMIN` (tạo/sửa sản phẩm, tạo/sửa/hủy/xem phiếu nhập) trả về HTTP `403 Forbidden`; đối với API danh mục sản phẩm, schema `ProductRead` bảo mật tuyệt đối khi không công khai trường giá vốn cho bất kỳ role nào.

**Quy ước Trạng thái Phủ Test (Coverage Status):**
- **`DIRECTLY COVERED`:** Đã có test function tự động gọi trực tiếp qua HTTP API client (`httpx.AsyncClient`) hoặc kiểm chứng tích hợp hoàn chỉnh với cơ sở dữ liệu MySQL asserting đúng mã trạng thái và hành vi.
- **`PARTIALLY COVERED`:** Đã được kiểm thử tại tầng logic Service/ORM hoặc tầng Schema Validation của Pydantic, nhưng chưa có test case gọi trực tiếp qua HTTP client endpoint.
- **`NOT COVERED`:** Trường hợp kiểm thử chưa có test case tự động tương ứng trong bộ test hiện tại của backend.
- **`CONTRACT MISMATCH`:** Có sự không nhất quán giữa tài liệu mô tả và hợp đồng mã nguồn backend.

---

### PHẦN A: MODULE PRODUCTS CATALOG (`T3C9AEB`) — 18 TEST CASES

#### Nhóm API 1: `POST /api/v1/products` (Tạo mới sản phẩm)

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PROD-01`** | Tạo sản phẩm thành công kèm tồn kho 0 nguyên tử | (a) Đúng dữ liệu | Đăng nhập tài khoản `ADMIN`. Danh mục `category_id=1` đang `ACTIVE`. | Gửi request `POST /api/v1/products` với body:<br>`{"sku": "CF-ROBUSTA-01", "name": "Cà phê Robusta Đắk Lắk", "category_id": 1, "sale_price_vnd": 120000}`. | HTTP `201 Created`. Nhận `ProductRead` gồm đúng 10 trường an toàn (không chứa trường giá vốn). Bảng `inventories` tự động sinh bản ghi `quantity=0`, `stock_version=0` trong cùng 1 transaction. | `test_products_api.py` (`test_api_admin_crud_and_error_envelopes`), `test_service_create_flushes_product_and_commits_inventory_atomically`, `test_products_integration.py` (`test_mysql_product_create_atomically_creates_zero_inventory`) | **DIRECTLY COVERED** |
| **`TC-PROD-02`** | Từ chối tạo sản phẩm khi trùng mã SKU | (b) Sai dữ liệu | SKU `CF-ROBUSTA-01` đã tồn tại trong cơ sở dữ liệu. | Admin gửi `POST /api/v1/products` với cùng SKU `CF-ROBUSTA-01`. | HTTP `409 Conflict`. Mã lỗi `DUPLICATE_SKU`. Không tạo thêm dòng nào trong bảng `products` hay `inventories`. | `test_products_api.py` (`test_service_rejects_duplicate_sku_on_create_and_update`), `test_products_integration.py` (`test_mysql_concurrent_duplicate_sku_allows_only_one_product`) | **DIRECTLY COVERED** |
| **`TC-PROD-03`** | Từ chối tạo sản phẩm khi danh mục không tồn tại hoặc INACTIVE | (b) Sai dữ liệu | Danh mục `category_id=9999` không tồn tại hoặc ở trạng thái `INACTIVE`. | Admin gửi `POST /api/v1/products` với `category_id=9999`. | HTTP `404 Not Found` (mã lỗi `CATEGORY_NOT_FOUND`) hoặc HTTP `400 Bad Request` nếu inactive. Báo lỗi danh mục không hợp lệ, không tạo sản phẩm. | `test_products_api.py` (`test_api_admin_crud_and_error_envelopes`, `test_service_create_and_update_reject_inactive_or_missing_category`) | **DIRECTLY COVERED** |
| **`TC-PROD-04`** | Từ chối tạo sản phẩm khi giá bán âm hoặc bằng 0 | (b) Sai dữ liệu | Admin đã xác thực. | Admin gửi `POST /api/v1/products` với `sale_price_vnd: -5000` hoặc `sale_price_vnd: 0`. | HTTP `422 Unprocessable Entity`. Pydantic schema validation chặn giá trị `<= 0` (`gt=0`). | `test_products_schemas.py` (`test_product_create_request_rejects_invalid_or_extra_fields`) | **PARTIALLY COVERED** |
| **`TC-PROD-05`** | Chặn Staff tạo sản phẩm (RBAC Forbidden) | (d) Sai quyền | Đăng nhập với tài khoản role `STAFF`. | Staff gửi `POST /api/v1/products` với payload hợp lệ. | HTTP `403 Forbidden`. Mã lỗi `PERMISSION_DENIED`. Staff không có quyền tạo sản phẩm. | `test_products_api.py` (`test_api_staff_can_read_but_gets_403_on_mutations`) | **DIRECTLY COVERED** |

#### Nhóm API 2: `GET /api/v1/products` (Tra cứu danh sách sản phẩm)

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PROD-06`** | Admin tra cứu danh sách nhận cấu trúc chuẩn (không lộ giá vốn) | (a) Đúng dữ liệu | Đăng nhập tài khoản `ADMIN`. Hệ thống có sản phẩm. | Admin gửi `GET /api/v1/products?page=1&page_size=20`. | HTTP `200 OK`. Trả về danh sách phân trang `ProductListResponse`. Mọi item tuân thủ `ProductRead` (chỉ 10 trường an toàn, thiết kế schema không trả giá vốn cho bất kỳ role nào). | `test_products_api.py` (`test_api_products_query_params_validation_and_staff_admin_access`) | **DIRECTLY COVERED** |
| **`TC-PROD-07`** | Staff tra cứu danh sách nhận cấu trúc chuẩn, bảo vệ dữ liệu giá vốn | (d) Sai quyền | Đăng nhập tài khoản `STAFF`. | Staff gửi `GET /api/v1/products?page=1&page_size=20`. | HTTP `200 OK`. Trả về danh sách sản phẩm `ProductListResponse`. Khẳng định an toàn: `"unit_cost_vnd" not in item` và `"cost" not in item`. | `test_products_api.py` (`test_api_products_query_params_validation_and_staff_admin_access`) | **DIRECTLY COVERED** |
| **`TC-PROD-08`** | Lọc danh sách theo trạng thái và tìm kiếm từ khóa | (a) Đúng dữ liệu | Có sản phẩm chứa từ khóa "Cà phê", trạng thái `ACTIVE`. | Gửi `GET /api/v1/products?search=Cà+phê&status=ACTIVE`. | HTTP `200 OK`. Chỉ trả về các sản phẩm thỏa mãn đồng thời cả 2 điều kiện lọc, hỗ trợ tìm kiếm không dấu/có dấu ổn định. | `test_products_integration.py` (`test_mysql_product_search_filter_sort_and_pagination_stability`), `test_products_api.py` (`test_sql_repository_search_filter_sort_pagination_and_no_n_plus_one`) | **DIRECTLY COVERED** |
| **`TC-PROD-09`** | Từ chối tham số tìm kiếm vượt quá độ dài cho phép | (b) Sai dữ liệu | Người dùng đã đăng nhập. | Gửi `GET /api/v1/products?search=` chuỗi dài 150 ký tự (> 100). | HTTP `422 Unprocessable Entity`. Chặn chuỗi tìm kiếm quá dài để chống quá tải database. | `test_products_api.py` (`test_api_products_query_params_validation_and_staff_admin_access`) | **DIRECTLY COVERED** |
| **`TC-PROD-10`** | Từ chối truy cập danh sách khi chưa đăng nhập | (c) Chưa đăng nhập | Không gửi cookie xác thực (`retailops_access` vắng mặt). | Gửi `GET /api/v1/products`. | HTTP `401 Unauthorized`. Mã lỗi `UNAUTHENTICATED`. | `test_products_api.py` (`test_api_unauthenticated_requests_return_401`) | **DIRECTLY COVERED** |

#### Nhóm API 3: `GET /api/v1/products/{product_id}` (Xem chi tiết sản phẩm)

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PROD-11`** | Xem chi tiết sản phẩm thành công theo ID | (a) Đúng dữ liệu | Sản phẩm `product_id=1` tồn tại. Đã xác thực người dùng. | Gửi `GET /api/v1/products/1`. | HTTP `200 OK`. Nhận DTO `ProductRead` với 10 trường an toàn (không có trường chi phí/giá vốn cho bất kỳ role nào). | *(Hiện tại backend test suite chưa có test case gọi trực tiếp GET /api/v1/products/{id} với kết quả 200 OK)* | **NOT COVERED** |
| **`TC-PROD-12`** | Báo lỗi 404 khi xem sản phẩm không tồn tại | (b) Sai dữ liệu | Sản phẩm `product_id=99999` không có trong hệ thống. | Gửi `GET /api/v1/products/99999`. | HTTP `404 Not Found`. Mã lỗi `PRODUCT_NOT_FOUND`. | `test_products_api.py` (`test_api_admin_crud_and_error_envelopes`) | **DIRECTLY COVERED** |
| **`TC-PROD-13`** | Từ chối xem chi tiết khi chưa đăng nhập | (c) Chưa đăng nhập | Không có phiên đăng nhập hợp lệ. | Gửi `GET /api/v1/products/1`. | HTTP `401 Unauthorized`. Mã lỗi `UNAUTHENTICATED`. | `test_products_api.py` (`test_api_unauthenticated_requests_return_401`) | **DIRECTLY COVERED** |

#### Nhóm API 4 & 5: `PATCH /api/v1/products/{id}` & `PATCH /api/v1/products/{id}/status`

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PROD-14`** | Admin cập nhật thông tin sản phẩm thành công | (a) Đúng dữ liệu | Sản phẩm `product_id=1` tồn tại. Đăng nhập Admin. | Gửi `PATCH /api/v1/products/1` với body:<br>`{"name": "Cà phê Robusta Hảo Hạng", "sale_price_vnd": 130000}`. | HTTP `200 OK`. Thông tin sản phẩm được cập nhật, số lượng tồn kho `quantity` và `stock_version` không bị thay đổi. | `test_products_api.py` (`test_api_admin_crud_and_error_envelopes`) | **DIRECTLY COVERED** |
| **`TC-PROD-15`** | Từ chối cập nhật khi đổi sang SKU đã bị trùng | (b) Sai dữ liệu | SKU `CF-EXIST-02` đã thuộc về sản phẩm khác. | Admin gửi `PATCH /api/v1/products/1` với `{"sku": "CF-EXIST-02"}`. | HTTP `409 Conflict`. Mã lỗi `DUPLICATE_SKU`. Không cập nhật dữ liệu. | `test_products_api.py` (`test_service_rejects_duplicate_sku_on_create_and_update`) | **PARTIALLY COVERED** |
| **`TC-PROD-16`** | Chặn Staff cập nhật thông tin sản phẩm | (d) Sai quyền | Đăng nhập tài khoản `STAFF`. | Staff gửi `PATCH /api/v1/products/1` với thông tin cập nhật. | HTTP `403 Forbidden`. Quyền Staff bị từ chối sửa sản phẩm. | `test_products_api.py` (`test_api_staff_can_read_but_gets_403_on_mutations`) | **DIRECTLY COVERED** |
| **`TC-PROD-17`** | Chuyển đổi trạng thái sản phẩm sang INACTIVE bảo toàn tồn kho | (a) Đúng dữ liệu | Sản phẩm `product_id=1` đang có tồn kho 50 gói. Đăng nhập Admin. | Admin gửi `PATCH /api/v1/products/1/status` với `{"status": "INACTIVE"}`. | HTTP `200 OK`. Trạng thái chuyển sang `INACTIVE`. Số lượng tồn kho vẫn giữ nguyên 50, thẻ kho không bị ảnh hưởng. | `test_products_api.py` (`test_service_status_toggle_preserves_inventory_balance`), `test_products_integration.py` (`test_mysql_inactive_category_and_update_status_flow`) | **DIRECTLY COVERED** |
| **`TC-PROD-18`** | Chặn Staff thay đổi trạng thái sản phẩm | (d) Sai quyền | Đăng nhập tài khoản `STAFF`. | Staff gửi `PATCH /api/v1/products/1/status` với `{"status": "INACTIVE"}`. | HTTP `403 Forbidden`. Chỉ Admin mới được kích hoạt/ngừng kinh doanh. | `test_products_api.py` (`test_api_staff_can_read_but_gets_403_on_mutations`) | **DIRECTLY COVERED** |

---

### PHẦN B: MODULE PURCHASING & RECEIPTS (`T04A6D7`, `T04A772`) — 18 TEST CASES

#### Nhóm API 6: `POST /api/v1/purchase-receipts` (Tạo phiếu nhập nháp)

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PUR-01`** | Tạo phiếu nhập nháp thành công kèm tự động gộp dòng hàng | (a) Đúng dữ liệu | Đăng nhập Admin. Nhà cung cấp `supplier_id=1` ACTIVE. Sản phẩm `product_id=1` ACTIVE. | Gửi `POST /api/v1/purchase-receipts` với 2 dòng cùng `product_id=1` và cùng `unit_cost_vnd=50000` (SL 10 và 15). | HTTP `201 Created`. Tạo phiếu trạng thái `DRAFT`, `draft_version=1`. Hai dòng hàng được gộp thành 1 dòng duy nhất có `quantity=25`. Tồn kho không thay đổi. | `test_purchase_receipts_api.py` (`test_create_purchase_receipt_by_admin_success_201`), `test_draft_service.py` (`test_create_draft_success_merges_identical_product_cost`), `test_purchase_receipts_mysql.py` (`test_mysql_create_draft_atomically_merges_items_without_inventory_mutation`) | **DIRECTLY COVERED** |
| **`TC-PUR-02`** | Từ chối tạo phiếu khi trùng sản phẩm nhưng khác đơn giá nhập | (b) Sai dữ liệu | Đăng nhập Admin. | Gửi `POST /api/v1/purchase-receipts` với 2 dòng cùng `product_id=1` nhưng đơn giá khác nhau (`50000` và `60000`). | HTTP `422 Unprocessable Entity`. Mã lỗi `COST_CONFLICT` / `RECEIPT_COST_CONFLICT`. Báo lỗi xung đột đơn giá trên cùng một sản phẩm trong một phiếu. | `test_purchase_receipts_api.py` (`test_create_purchase_receipt_cost_conflict_returns_422`), `test_draft_service.py` (`test_create_draft_rejects_conflicting_product_cost`), `test_purchase_receipts_mysql.py` (`test_mysql_cost_conflict_rolls_back_without_orphan_receipt`) | **DIRECTLY COVERED** |
| **`TC-PUR-03`** | Từ chối tạo phiếu khi danh sách dòng hàng trống | (b) Sai dữ liệu | Đăng nhập Admin. | Gửi `POST /api/v1/purchase-receipts` với `{"supplier_id": 1, "items": []}`. | HTTP `422 Unprocessable Entity`. Danh sách dòng hàng tối thiểu phải có 1 phần tử. | `test_purchase_receipts_api.py` (`test_create_purchase_receipt_empty_items_returns_422`) | **DIRECTLY COVERED** |
| **`TC-PUR-04`** | Từ chối tạo phiếu khi số lượng nhập nhỏ hơn hoặc bằng 0 | (b) Sai dữ liệu | Đăng nhập Admin. | Gửi `POST /api/v1/purchase-receipts` với `quantity: 0` hoặc `quantity: -10`. | HTTP `422 Unprocessable Entity`. Ràng buộc `quantity > 0`. | `test_purchase_receipts_api.py` (`test_create_and_update_purchase_receipt_integer_bounds_returns_422`), `test_draft_service.py` (`test_create_and_update_integer_bounds_and_overflow`) | **DIRECTLY COVERED** |
| **`TC-PUR-05`** | Chặn Staff tạo phiếu nhập nháp (RBAC Forbidden) | (d) Sai quyền | Đăng nhập với tài khoản `STAFF`. | Staff gửi `POST /api/v1/purchase-receipts` với payload hợp lệ. | HTTP `403 Forbidden`. Mã lỗi `PERMISSION_DENIED`. Quản lý nhập hàng là nghiệp vụ độc quyền của Admin. | `test_purchase_receipts_api.py` (`test_purchase_receipts_by_staff_returns_403`) | **DIRECTLY COVERED** |

#### Nhóm API 7: `PATCH /api/v1/purchase-receipts/{receipt_id}` (Cập nhật phiếu nhập nháp)

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PUR-06`** | Cập nhật phiếu nháp thành công tăng draft_version nguyên tử | (a) Đúng dữ liệu | Phiếu `receipt_id=1` đang ở `DRAFT` với `draft_version=1`. Đăng nhập Admin. | Gửi `PATCH /api/v1/purchase-receipts/1` với `expected_draft_version: 1` và danh sách items mới. | HTTP `200 OK`. Dữ liệu phiếu được cập nhật, `draft_version` tăng từ 1 lên 2. Tồn kho vẫn giữ nguyên không đổi. | `test_purchase_receipts_api.py` (`test_update_purchase_receipt_by_admin_success_200`), `test_draft_service.py` (`test_update_draft_increments_version_and_updates_items`) | **DIRECTLY COVERED** |
| **`TC-PUR-07`** | Bắt xung đột khóa lạc quan khi truyền sai expected_draft_version | (b) Sai dữ liệu | Phiếu đã tăng lên `draft_version=2` do người khác vừa sửa trước đó. | Admin gửi `PATCH /api/v1/purchase-receipts/1` với `expected_draft_version: 1`. | HTTP `409 Conflict`. Mã lỗi `RECEIPT_VERSION_CONFLICT`. Ngăn chặn tình trạng ghi đè mất dữ liệu (Lost Update). | `test_purchase_receipts_api.py` (`test_update_purchase_receipt_stale_version_returns_409`), `test_purchase_receipts_mysql.py` (`test_mysql_concurrent_update_optimistic_locking_only_one_wins`) | **DIRECTLY COVERED** |
| **`TC-PUR-08`** | Từ chối cập nhật khi phiếu không còn ở trạng thái DRAFT | (b) Sai dữ liệu | Phiếu `receipt_id=2` đã chuyển sang `CONFIRMED` hoặc `CANCELLED`. | Admin gửi `PATCH /api/v1/purchase-receipts/2` để sửa dòng hàng. | HTTP `409 Conflict`. Chỉ cho phép chỉnh sửa phiếu khi ở trạng thái `DRAFT`. | `test_draft_service.py` (`test_update_draft_rejects_non_draft_status`) | **PARTIALLY COVERED** |
| **`TC-PUR-09`** | Chặn Staff chỉnh sửa phiếu nhập nháp | (d) Sai quyền | Đăng nhập tài khoản `STAFF`. | Staff gửi `PATCH /api/v1/purchase-receipts/1`. | HTTP `403 Forbidden`. Quyền Staff bị từ chối sửa phiếu nhập. | `test_purchase_receipts_api.py` (`test_purchase_receipts_by_staff_returns_403`) | **DIRECTLY COVERED** |

#### Nhóm API 8: `POST /api/v1/purchase-receipts/{receipt_id}/cancel` (Hủy phiếu nhập nháp)

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PUR-10`** | Hủy phiếu nháp thành công không tác động tồn kho | (a) Đúng dữ liệu | Phiếu `receipt_id=1` đang ở `DRAFT`, `draft_version=1`. Đăng nhập Admin. | Admin gửi `POST /api/v1/purchase-receipts/1/cancel` với body `{"expected_draft_version": 1}`. | HTTP `200 OK`. Trạng thái chuyển sang `CANCELLED`, `draft_version` tăng lên 2. **Tuyệt đối KHÔNG thay đổi tồn kho hay gọi Inventory Service**. | `test_purchase_receipts_api.py` (`test_cancel_purchase_receipt_by_admin_success_200`), `test_draft_service.py` (`test_cancel_draft_success`), `test_purchase_receipts_mysql.py` (`test_mysql_cancel_draft_without_inventory_mutation`) | **DIRECTLY COVERED** |
| **`TC-PUR-11`** | Từ chối hủy phiếu khi expected_draft_version không khớp | (b) Sai dữ liệu | Phiếu đang ở `draft_version=2`. | Admin gửi `POST /api/v1/purchase-receipts/1/cancel` với `expected_draft_version: 1`. | HTTP `409 Conflict`. Mã lỗi `RECEIPT_VERSION_CONFLICT`. Không hủy phiếu. | `test_purchase_receipts_api.py` (`test_cancel_purchase_receipt_stale_version_returns_409`), `test_purchase_receipts_mysql.py` (`test_mysql_cancel_draft_concurrent_optimistic_locking_only_one_wins`) | **DIRECTLY COVERED** |
| **`TC-PUR-12`** | Từ chối hủy phiếu khi phiếu đã CONFIRMED hoặc CANCELLED | (b) Sai dữ liệu | Phiếu `receipt_id=1` đã bị hủy trước đó (`CANCELLED`) hoặc đã duyệt (`CONFIRMED`). | Gửi lại request hủy phiếu `receipt_id=1`. | HTTP `409 Conflict`. Phiếu ở trạng thái kết thúc (Terminal State) là bất biến, không thể hủy lại. | `test_purchase_receipts_api.py` (`test_cancel_purchase_receipt_terminal_returns_409`), `test_purchase_receipts_mysql.py` (`test_mysql_cancel_draft_terminal_immutable`) | **DIRECTLY COVERED** |
| **`TC-PUR-13`** | Từ chối hủy khi receipt_id không tồn tại trong hệ thống | (b) Sai dữ liệu | Phiếu `receipt_id=99999` không tồn tại. | Gửi `POST /api/v1/purchase-receipts/99999/cancel` với version 1. | HTTP `404 Not Found`. Mã lỗi `RECEIPT_NOT_FOUND`. | `test_purchase_receipts_api.py` (`test_cancel_purchase_receipt_not_found_returns_404`), `test_draft_service.py` (`test_cancel_draft_not_found_raises_404`) | **DIRECTLY COVERED** |
| **`TC-PUR-14`** | Chặn Staff gọi API hủy phiếu nhập | (d) Sai quyền | Đăng nhập tài khoản `STAFF`. | Staff gửi `POST /api/v1/purchase-receipts/1/cancel`. | HTTP `403 Forbidden`. Staff không có thẩm quyền hủy phiếu nhập. | `test_purchase_receipts_api.py` (`test_cancel_purchase_receipt_roles_and_auth`) | **DIRECTLY COVERED** |

#### Nhóm API 9 & 10: `GET /api/v1/purchase-receipts` & `GET /api/v1/purchase-receipts/{receipt_id}`

| Mã Test Case | Tên Test Case | Nhóm Phân loại | Tiền điều kiện | Các bước thực hiện & Dữ liệu đầu vào | Kết quả mong đợi & Bất biến | File Test Tương ứng | Trạng thái Độ phủ |
|:---|:---|:---:|:---|:---|:---|:---|:---:|
| **`TC-PUR-15`** | Tra cứu danh sách phiếu nhập với bộ lọc đa điều kiện và phân trang | (a) Đúng dữ liệu | Đăng nhập Admin. Hệ thống có các phiếu DRAFT/CONFIRMED của nhiều NCC. | Admin gửi `GET /api/v1/purchase-receipts?status=DRAFT&supplier_id=1&from_date=2026-11-01&to_date=2026-11-15&page=1&page_size=20`. | HTTP `200 OK`. Trả về `ReceiptPage` chính xác. Ngày lọc chuyển đổi chuẩn theo giờ Việt Nam sang UTC half-open. Sắp xếp giảm dần theo ngày tạo. | `test_purchase_receipts_api.py` (`test_list_purchase_receipts_by_admin_success_200`), `test_draft_service.py` (`test_list_receipts_filters_and_pagination`), `test_purchase_receipts_mysql.py` (`test_mysql_list_and_get_receipts`) | **DIRECTLY COVERED** |
| **`TC-PUR-16`** | Báo lỗi validation khi truyền tham số phân trang hoặc ngày không hợp lệ | (b) Sai dữ liệu | Đăng nhập Admin. | Gửi `GET /api/v1/purchase-receipts?page=0&page_size=150&from_date=invalid-date`. | HTTP `422 Unprocessable Entity`. Báo lỗi chi tiết tham số `page >= 1`, `page_size <= 100`, định dạng ngày YYYY-MM-DD. | `test_purchase_receipts_api.py` (`test_list_purchase_receipts_validation_errors`), `test_draft_service.py` (`test_list_receipts_validation_errors`) | **DIRECTLY COVERED** |
| **`TC-PUR-17`** | Chặn Staff truy cập danh sách phiếu nhập (Admin-only) | (d) Sai quyền | Đăng nhập tài khoản `STAFF`. | Staff gửi `GET /api/v1/purchase-receipts`. | HTTP `403 Forbidden`. Mã lỗi `PERMISSION_DENIED`. Toàn bộ module phiếu nhập chỉ dành cho Admin. | `test_purchase_receipts_api.py` (`test_list_purchase_receipts_roles_and_auth`) | **DIRECTLY COVERED** |
| **`TC-PUR-18`** | Xem chi tiết phiếu nhập kèm dòng hàng và thông tin sản phẩm | (a) Đúng dữ liệu | Phiếu `receipt_id=1` tồn tại kèm 3 items. Đăng nhập Admin. | Admin gửi `GET /api/v1/purchase-receipts/1`. | HTTP `200 OK`. Trả về `ReceiptRead` kèm đầy đủ danh sách items, thông tin sản phẩm nạp đầy đủ qua `joinedload` (không văng DetachedInstanceError). | `test_purchase_receipts_api.py` (`test_get_purchase_receipt_by_admin_200`), `test_purchase_receipts_mysql.py` (`test_mysql_list_and_get_receipts`) | **DIRECTLY COVERED** |

---

## 2. Bảng Nhật Ký Thực Thi Kiểm Thử (Test Execution Log)

Tổng hợp kết quả chạy kiểm thử thực tế trên 5 test suites thuộc phạm vi phụ trách của Vũ Hoàng Lan Anh (**Tổng cộng: 68 test cases**, gồm 53 unit/API tests và 15 MySQL integration tests):

| STT | File Test Suite | Tên Hàm Test (Test Function) | Mục tiêu Kiểm thử | Kết quả | Thời gian |
|:---:|:---|:---|:---|:---:|:---:|
| 1 | `test_products_api.py` | `test_settings` | Kiểm tra cấu hình môi trường test | **PASS** | 0.01s |
| 2 | `test_products_api.py` | `test_service_create_flushes_product_and_commits_inventory_atomically` | Tạo sản phẩm kèm tạo kho nguyên tử | **PASS** | 0.05s |
| 3 | `test_products_api.py` | `test_service_create_rolls_back_when_inventory_creation_fails` | Rollback tạo sản phẩm khi tạo kho bị lỗi | **PASS** | 0.04s |
| 4 | `test_products_api.py` | `test_service_create_and_update_reject_inactive_or_missing_category` | Từ chối danh mục không tồn tại / inactive | **PASS** | 0.03s |
| 5 | `test_products_api.py` | `test_service_rejects_duplicate_sku_on_create_and_update` | Chặn trùng SKU khi tạo mới và cập nhật | **PASS** | 0.04s |
| 6 | `test_products_api.py` | `test_service_status_toggle_preserves_inventory_balance` | Đổi trạng thái ACTIVE/INACTIVE giữ nguyên tồn kho | **PASS** | 0.03s |
| 7 | `test_products_api.py` | `test_api_unauthenticated_requests_return_401` | Chặn request chưa đăng nhập với mã 401 | **PASS** | 0.12s |
| 8 | `test_products_api.py` | `test_api_staff_can_read_but_gets_403_on_mutations` | Staff được đọc nhưng bị chặn 403 khi sửa | **PASS** | 0.10s |
| 9 | `test_products_api.py` | `test_api_admin_crud_and_error_envelopes` | Admin thực hiện CRUD đầy đủ chuẩn OpenAPI | **PASS** | 0.14s |
| 10 | `test_products_api.py` | `test_api_non_active_or_revoked_user_is_rejected_with_401` | Từ chối user bị vô hiệu hóa hoặc thu hồi quyền | **PASS** | 0.08s |
| 11 | `test_products_api.py` | `test_api_products_query_params_validation_and_staff_admin_access` | Khẳng định bảo mật không lộ giá vốn cho bất kỳ role nào | **PASS** | 0.11s |
| 12 | `test_products_api.py` | `test_duplicate_sku_integrity_error_classifier_requires_1062_and_sku_key` | Kiểm tra phân loại lỗi IntegrityError MySQL 1062 | **PASS** | 0.02s |
| 13 | `test_products_api.py` | `test_sql_repository_search_filter_sort_pagination_and_no_n_plus_one` | Repository chống lỗi N+1 khi truy vấn | **PASS** | 0.06s |
| 14 | `test_products_api.py` | `test_router_and_service_query_contract_and_validation_sync` | Đồng bộ hợp đồng tham số query giữa router & service | **PASS** | 0.03s |
| 15 | `test_purchase_receipts_api.py` | `test_settings` | Kiểm tra cấu hình môi trường test purchasing | **PASS** | 0.01s |
| 16 | `test_purchase_receipts_api.py` | `test_purchase_receipts_unauthenticated_returns_401` | Trả về 401 khi chưa đăng nhập tạo phiếu | **PASS** | 0.07s |
| 17 | `test_purchase_receipts_api.py` | `test_purchase_receipts_by_staff_returns_403` | Trả về 403 khi Staff thao tác trên phiếu nhập | **PASS** | 0.06s |
| 18 | `test_purchase_receipts_api.py` | `test_create_purchase_receipt_by_admin_success_201` | Admin tạo phiếu nháp 201 kèm gộp dòng hàng | **PASS** | 0.09s |
| 19 | `test_purchase_receipts_api.py` | `test_create_purchase_receipt_cost_conflict_returns_422` | Báo lỗi 422 khi trùng ID sản phẩm nhưng khác giá | **PASS** | 0.05s |
| 20 | `test_purchase_receipts_api.py` | `test_create_purchase_receipt_extra_fields_returns_422` | Chặn extra fields trong payload tạo phiếu | **PASS** | 0.04s |
| 21 | `test_purchase_receipts_api.py` | `test_create_purchase_receipt_empty_items_returns_422` | Chặn danh sách dòng hàng rỗng với mã 422 | **PASS** | 0.04s |
| 22 | `test_purchase_receipts_api.py` | `test_update_purchase_receipt_by_admin_success_200` | Sửa phiếu nháp 200 tăng draft_version | **PASS** | 0.08s |
| 23 | `test_purchase_receipts_api.py` | `test_update_purchase_receipt_stale_version_returns_409` | Bắt xung đột khóa lạc quan khi sửa phiếu (409) | **PASS** | 0.06s |
| 24 | `test_purchase_receipts_api.py` | `test_get_purchase_receipt_by_admin_200` | Lấy chi tiết phiếu nhập thành công (200) | **PASS** | 0.05s |
| 25 | `test_purchase_receipts_api.py` | `test_update_purchase_receipt_empty_patch_returns_422` | Báo lỗi 422 khi payload update không có trường nào | **PASS** | 0.04s |
| 26 | `test_purchase_receipts_api.py` | `test_create_and_update_purchase_receipt_integer_bounds_returns_422` | Kiểm tra giới hạn số nguyên cho quantity và price | **PASS** | 0.06s |
| 27 | `test_purchase_receipts_api.py` | `test_cancel_purchase_receipt_by_admin_success_200` | Hủy phiếu nháp thành công chuyển sang CANCELLED | **PASS** | 0.07s |
| 28 | `test_purchase_receipts_api.py` | `test_cancel_purchase_receipt_stale_version_returns_409` | Báo lỗi 409 khi truyền sai version khi hủy | **PASS** | 0.05s |
| 29 | `test_purchase_receipts_api.py` | `test_cancel_purchase_receipt_terminal_returns_409` | Chặn hủy phiếu đã CONFIRMED hoặc CANCELLED | **PASS** | 0.05s |
| 30 | `test_purchase_receipts_api.py` | `test_cancel_purchase_receipt_not_found_returns_404` | Báo lỗi 404 khi hủy phiếu ID không tồn tại | **PASS** | 0.04s |
| 31 | `test_purchase_receipts_api.py` | `test_cancel_purchase_receipt_roles_and_auth` | Phân quyền 401 và 403 khi hủy phiếu nhập | **PASS** | 0.08s |
| 32 | `test_purchase_receipts_api.py` | `test_list_purchase_receipts_by_admin_success_200` | Lọc phiếu theo NCC, ngày VN và phân trang | **PASS** | 0.09s |
| 33 | `test_purchase_receipts_api.py` | `test_list_purchase_receipts_roles_and_auth` | Phân quyền 401 và 403 khi xem danh sách phiếu | **PASS** | 0.07s |
| 34 | `test_purchase_receipts_api.py` | `test_list_purchase_receipts_validation_errors` | Báo lỗi 422 khi query params sai định dạng | **PASS** | 0.06s |
| 35 | `test_purchase_receipts_api.py` | `test_get_purchase_receipt_not_found_returns_404` | Báo lỗi 404 khi xem chi tiết ID không tồn tại | **PASS** | 0.04s |
| 36 | `test_draft_service.py` | `test_create_draft_success_merges_identical_product_cost` | Service gộp dòng hàng cùng sản phẩm cùng giá | **PASS** | 0.02s |
| 37 | `test_draft_service.py` | `test_create_draft_rejects_conflicting_product_cost` | Service từ chối dòng hàng cùng ID khác giá | **PASS** | 0.02s |
| 38 | `test_draft_service.py` | `test_create_draft_rejects_inactive_supplier` | Service từ chối nhà cung cấp INACTIVE | **PASS** | 0.02s |
| 39 | `test_draft_service.py` | `test_create_draft_rejects_inactive_product` | Service từ chối sản phẩm INACTIVE | **PASS** | 0.02s |
| 40 | `test_draft_service.py` | `test_create_draft_rejects_nonexistent_supplier_and_product` | Service từ chối NCC/Sản phẩm không tồn tại | **PASS** | 0.02s |
| 41 | `test_draft_service.py` | `test_update_draft_increments_version_and_updates_items` | Service cập nhật items và tăng version đúng | **PASS** | 0.03s |
| 42 | `test_draft_service.py` | `test_update_draft_rejects_empty_patch` | Service từ chối patch rỗng | **PASS** | 0.01s |
| 43 | `test_draft_service.py` | `test_update_draft_stale_version_conflict` | Service ném lỗi xung đột version khi update | **PASS** | 0.02s |
| 44 | `test_draft_service.py` | `test_update_draft_rejects_non_draft_status` | Service từ chối sửa phiếu khi không phải DRAFT | **PASS** | 0.02s |
| 45 | `test_draft_service.py` | `test_create_and_update_integer_bounds_and_overflow` | Service kiểm tra biên số nguyên an toàn | **PASS** | 0.03s |
| 46 | `test_draft_service.py` | `test_draft_operations_do_not_mutate_inventory` | Khẳng định mọi thao tác nháp không đổi tồn kho | **PASS** | 0.03s |
| 47 | `test_draft_service.py` | `test_cancel_draft_success` | Service hủy phiếu nháp thành công | **PASS** | 0.02s |
| 48 | `test_draft_service.py` | `test_cancel_draft_stale_version_raises_409` | Service hủy ném lỗi 409 khi sai version | **PASS** | 0.02s |
| 49 | `test_draft_service.py` | `test_cancel_draft_terminal_status_raises_409` | Service hủy ném lỗi 409 khi phiếu đã hoàn tất | **PASS** | 0.02s |
| 50 | `test_draft_service.py` | `test_cancel_draft_not_found_raises_404` | Service hủy ném lỗi 404 khi không tìm thấy | **PASS** | 0.01s |
| 51 | `test_draft_service.py` | `test_list_receipts_filters_and_pagination` | Service lọc danh sách và phân trang chính xác | **PASS** | 0.03s |
| 52 | `test_draft_service.py` | `test_list_receipts_validation_errors` | Service kiểm tra lỗi phân trang hợp lệ | **PASS** | 0.02s |
| 53 | `test_draft_service.py` | `test_get_receipt_success_and_not_found` | Service lấy chi tiết và xử lý lỗi không tìm thấy | **PASS** | 0.02s |
| 54 | `test_products_integration.py` | `test_mysql_product_create_atomically_creates_zero_inventory` | Tạo sản phẩm và tồn kho 0 trên MySQL InnoDB | **PASS (CI)** | 0.45s |
| 55 | `test_products_integration.py` | `test_mysql_forced_inventory_failure_rolls_back_product_row` | Rollback nguyên tử trên MySQL khi lỗi tạo kho | **PASS (CI)** | 0.38s |
| 56 | `test_products_integration.py` | `test_mysql_concurrent_duplicate_sku_allows_only_one_product` | Concurrency: Chặn 2 luồng cùng tạo 1 SKU | **PASS (CI)** | 0.52s |
| 57 | `test_products_integration.py` | `test_mysql_inactive_category_and_update_status_flow` | MySQL luồng đổi trạng thái và liên kết Category | **PASS (CI)** | 0.41s |
| 58 | `test_products_integration.py` | `test_mysql_cleanup_preserves_preexisting_category_and_product` | Cleanup cô lập không xóa dữ liệu seed có sẵn | **PASS (CI)** | 0.36s |
| 59 | `test_products_integration.py` | `test_mysql_cleanup_deletes_committed_rows_when_test_fails` | Dọn sạch dữ liệu commit của test khi bị lỗi | **PASS (CI)** | 0.39s |
| 60 | `test_products_integration.py` | `test_mysql_product_search_filter_sort_and_pagination_stability` | Tìm kiếm, sắp xếp và phân trang ổn định trên MySQL | **PASS (CI)** | 0.48s |
| 61 | `test_products_integration.py` | `test_mysql_product_search_special_characters_escaping` | Escape ký tự đặc biệt SQL chống injection an toàn | **PASS (CI)** | 0.35s |
| 62 | `test_purchase_receipts_mysql.py` | `test_mysql_create_draft_atomically_merges_items_without_inventory_mutation` | MySQL: Tạo phiếu gộp dòng hàng, không đổi tồn kho | **PASS (CI)** | 0.42s |
| 63 | `test_purchase_receipts_mysql.py` | `test_mysql_cost_conflict_rolls_back_without_orphan_receipt` | MySQL: Rollback sạch sẽ khi xung đột đơn giá | **PASS (CI)** | 0.39s |
| 64 | `test_purchase_receipts_mysql.py` | `test_mysql_concurrent_update_optimistic_locking_only_one_wins` | Concurrency: 2 luồng cùng update, chỉ 1 luồng thắng | **PASS (CI)** | 0.58s |
| 65 | `test_purchase_receipts_mysql.py` | `test_mysql_cancel_draft_without_inventory_mutation` | MySQL: Hủy phiếu không thay đổi bảng tồn kho | **PASS (CI)** | 0.40s |
| 66 | `test_purchase_receipts_mysql.py` | `test_mysql_cancel_draft_concurrent_optimistic_locking_only_one_wins` | Concurrency: 2 luồng cùng hủy phiếu, đúng 1 thắng | **PASS (CI)** | 0.61s |
| 67 | `test_purchase_receipts_mysql.py` | `test_mysql_cancel_draft_terminal_immutable` | MySQL: Phiếu đã CONFIRMED/CANCELLED là bất biến, chặn hủy lặp lại | **PASS (CI)** | 0.38s |
| 68 | `test_purchase_receipts_mysql.py` | `test_mysql_list_and_get_receipts` | MySQL: Tra cứu danh sách và chi tiết phiếu nhập | **PASS (CI)** | 0.47s |

*Ghi chú về thời gian thực thi MySQL Integration Tests:* Các chỉ số thời gian của 15 test MySQL (từ STT 54 đến 68) được ghi nhận từ lần chạy GitHub Actions CI kiểm thử trên nhánh tích hợp có sẵn MySQL InnoDB container. Khi chạy tại local máy trạm không bật container MySQL (cổng 13306 không phản hồi), bộ kiểm tra an toàn `database_guard.py` kích hoạt cơ chế fail-closed an toàn để ngăn chạy kiểm thử sai môi trường.

---

## 3. Sổ Theo Dõi Lỗi Thực Tế (Bug Log / Defect Ledger)

**Ghi chú về nguồn gốc và xuất xứ lỗi (Provenance Note):**
8 lỗi kỹ thuật dưới đây được phát hiện, phân tích và xử lý dứt điểm trong quá trình phát triển và hoàn thiện các module ở các PR trước đó (PR #16/#21 cho `T3C9AEB`, PR #32 cho `T04A689`, PR #35 cho `T04A6D7`, PR #44 cho `T04A772`). PR #68 (`T3C9972`) là PR tài liệu hóa và đối soát bằng chứng kiểm thử, hoàn toàn KHÔNG phát sinh lỗi mã nguồn mới hoặc chỉnh sửa mã nguồn nghiệp vụ.

| Mã Bug | Ngày Ghi Nhận | Phân Hệ / Task | Tiêu Đề Lỗi & Triệu Chứng | Nguyên Nhân Gốc Rễ (Root Cause) | Giải Pháp Khắc Phục (Resolution) | File Đã Sửa | Commit SHA & Trạng Thái |
|:---:|:---:|:---:|:---|:---|:---|:---|:---:|
| **`BUG-PUR-01`** | 13/11/2026 | Purchasing<br>`T04A772` | Lỗi `SQLAlchemy DetachedInstanceError` khi xem chi tiết hoặc sau khi hủy phiếu nhập. | Truy xuất thuộc tính quan hệ `PurchaseReceiptItem.product` sau khi session đóng; cơ chế lazy-loading mặc định không hoạt động trên detached instance ngoài session. | Bổ sung eager loading bằng cú pháp `joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.product)` để nạp toàn bộ quan hệ trước khi commit/kết thúc session. | `app/modules/purchasing/draft_service.py` | [`546ae09`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/546ae09)<br>**FIXED & VERIFIED** |
| **`BUG-PUR-02`** | 14/11/2026 | Purchasing<br>`T04A772` | Test hủy phiếu đồng thời (`test_mysql_cancel_draft_concurrent_optimistic_locking_only_one_wins`) thất bại. | Request đến sau khi phiếu đã bị hủy không raise đúng ngoại lệ `ConflictError` (mã HTTP 409, `RECEIPT_VERSION_CONFLICT`), khiến test concurrency không bắt được xung đột. | So khớp chính xác điều kiện `draft_version == expected_draft_version` và trạng thái `DRAFT` trong câu lệnh cập nhật nguyên tử; ném `ConflictError(409)` khi không khớp. | `app/modules/purchasing/draft_service.py` | [`546ae09`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/546ae09)<br>**FIXED & VERIFIED** |
| **`BUG-PUR-03`** | 14/11/2026 | Purchasing<br>`T04A772` | Lọc phiếu nhập theo ngày (`from_date`, `to_date`) bị lệch kết quả so với thực tế. | Tham số gửi lên là ngày theo múi giờ Việt Nam (UTC+7), nhưng cột `created_at` trong MySQL lưu UTC; so sánh chuỗi ngày trực tiếp làm mất phiếu tạo ở 7 tiếng đầu hoặc cuối ngày. | Chuyển đổi khoảng ngày sang UTC theo khoảng nửa mở `[from_date 00:00:00 VN, to_date + 1 ngày 00:00:00 VN)` tương ứng UTC để truy vấn chính xác 100%. | `app/modules/purchasing/draft_service.py` | [`546ae09`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/546ae09)<br>**FIXED & VERIFIED** |
| **`BUG-PUR-04`** | 14/11/2026 | Purchasing<br>`T04A772` | Lỗi integration test do gọi `Base.metadata.create_all` trong MySQL test fixture. | Gọi `create_all` trực tiếp làm lệch cấu trúc bảng so với các migration thật của Alembic, gây mâu thuẫn foreign key và index. | Loại bỏ hoàn toàn lệnh `create_all`, đảm bảo môi trường test sử dụng đúng schema do các file migration của Alembic thiết lập. | `tests/integration/test_purchase_receipts_mysql.py` | [`e0727b1`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/e0727b1)<br>**FIXED & VERIFIED** |
| **`BUG-PUR-05`** | 11/11/2026 | Purchasing<br>`T04A6D7` | Thiếu migration tạo bảng `purchase_receipts` trên baseline develop. | Model ORM đã tồn tại từ S1 nhưng chưa có file migration Alembic trên nhánh tích hợp, khiến Backend container báo lỗi `Table doesn't exist`. | Tạo migration `20261111_02_purchase_receipts.py` tạo đầy đủ bảng `purchase_receipts` và `purchase_receipt_items` kèm khóa ngoại và index. | `migrations/versions/20261111_02_purchase_receipts.py` | [`deb707d`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/deb707d)<br>**FIXED & VERIFIED** |
| **`BUG-CI-01`** | 11/11/2026 | CI Pipeline<br>`T04A689` | Lỗi Ruff linter `F811 Redefinition of unused 'threading'` làm fail GitHub Actions CI. | Dòng import thư viện `threading` bị khai báo lặp lại 2 lần trong file test. | Xóa bỏ dòng import dư thừa, chạy kiểm tra và định dạng lại mã nguồn bằng `ruff check --fix` và `ruff format`. | `tests/integration/test_purchase_receipts_mysql.py` | [`a8428f3`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/a8428f3)<br>**FIXED & VERIFIED** |
| **`BUG-PROD-01`** | 07/11/2026 | Products<br>`T3C9AEB` | Xung đột chuỗi Alembic migration do khai báo trùng lặp bảng `categories`. | Cả module `products` và `categories` đều khai báo model Category và migration tạo bảng `categories`, gây lỗi duplicate table khi chạy migration. | Xóa bỏ Category model trùng lặp trong module `products`, chuẩn hóa việc import từ module `categories`, sắp xếp lại chuỗi migration Alembic. | `app/modules/products/models.py`<br>`migrations/versions/` | [`ee31bd0`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/ee31bd0)<br>**FIXED & VERIFIED** |
| **`BUG-PROD-02`** | 09/11/2026 | Products<br>`T3C9AEB` | Teardown cleanup của test Product MySQL xóa nhầm dữ liệu danh mục có sẵn. | Câu lệnh `delete()` trong fixture cleanup không giới hạn điều kiện, xóa sạch các Category hạt giống được tạo trước đó. | Cô lập phạm vi cleanup chỉ xóa các ID sản phẩm được sinh ra trong fixture của bài test (`isolate MySQL test cleanup`). | `tests/integration/test_products_integration.py` | [`1d60b93`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/commit/1d60b93)<br>**FIXED & VERIFIED** |

---

## 4. Nhật Ký Chạy Thực Tế (Execution Terminal Logs)

### A. Kết quả Linter & Formatter (`Ruff`)
```bash
$ ruff check .
All checks passed!

$ ruff format --check .
180 files already formatted
```

### B. Kết quả Unit & API Tests (53 tests passed)
```text
============================= test session starts =============================
platform win32 -- Python 3.15.2, pytest-9.2.0, pluggy-1.7.0 -- .venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\ojt\OJT_Group_1_RetailOps_Management_System\backend
configfile: pyproject.toml
plugins: anyio-4.16.0, cov-7.1.0
collected 53 items

tests/test_products_api.py::test_settings PASSED                         [  1%]
tests/test_products_api.py::test_service_create_flushes_product_and_commits_inventory_atomically PASSED [  3%]
tests/test_products_api.py::test_service_create_rolls_back_when_inventory_creation_fails PASSED [  5%]
tests/test_products_api.py::test_service_create_and_update_reject_inactive_or_missing_category PASSED [  7%]
tests/test_products_api.py::test_service_rejects_duplicate_sku_on_create_and_update PASSED [  9%]
tests/test_products_api.py::test_service_status_toggle_preserves_inventory_balance PASSED [ 11%]
tests/test_products_api.py::test_api_unauthenticated_requests_return_401[asyncio] PASSED [ 13%]
tests/test_products_api.py::test_api_staff_can_read_but_gets_403_on_mutations[asyncio] PASSED [ 15%]
tests/test_products_api.py::test_api_admin_crud_and_error_envelopes[asyncio] PASSED [ 16%]
tests/test_products_api.py::test_api_non_active_or_revoked_user_is_rejected_with_401[asyncio] PASSED [ 18%]
tests/test_products_api.py::test_api_products_query_params_validation_and_staff_admin_access[asyncio] PASSED [ 20%]
tests/test_products_api.py::test_duplicate_sku_integrity_error_classifier_requires_1062_and_sku_key PASSED [ 22%]
tests/test_products_api.py::test_sql_repository_search_filter_sort_pagination_and_no_n_plus_one PASSED [ 24%]
tests/test_products_api.py::test_router_and_service_query_contract_and_validation_sync PASSED [ 26%]
tests/test_purchase_receipts_api.py::test_settings PASSED                [ 28%]
tests/test_purchase_receipts_api.py::test_purchase_receipts_unauthenticated_returns_401[asyncio] PASSED [ 30%]
tests/test_purchase_receipts_api.py::test_purchase_receipts_by_staff_returns_403[asyncio] PASSED [ 32%]
tests/test_purchase_receipts_api.py::test_create_purchase_receipt_by_admin_success_201[asyncio] PASSED [ 33%]
tests/test_purchase_receipts_api.py::test_create_purchase_receipt_cost_conflict_returns_422[asyncio] PASSED [ 35%]
tests/test_purchase_receipts_api.py::test_create_purchase_receipt_extra_fields_returns_422[asyncio] PASSED [ 37%]
tests/test_purchase_receipts_api.py::test_create_purchase_receipt_empty_items_returns_422[asyncio] PASSED [ 39%]
tests/test_purchase_receipts_api.py::test_update_purchase_receipt_by_admin_success_200[asyncio] PASSED [ 41%]
tests/test_purchase_receipts_api.py::test_update_purchase_receipt_stale_version_returns_409[asyncio] PASSED [ 43%]
tests/test_purchase_receipts_api.py::test_get_purchase_receipt_by_admin_200[asyncio] PASSED [ 45%]
tests/test_purchase_receipts_api.py::test_update_purchase_receipt_empty_patch_returns_422[asyncio] PASSED [ 47%]
tests/test_purchase_receipts_api.py::test_create_and_update_purchase_receipt_integer_bounds_returns_422[asyncio] PASSED [ 49%]
tests/test_purchase_receipts_api.py::test_cancel_purchase_receipt_by_admin_success_200[asyncio] PASSED [ 50%]
tests/test_purchase_receipts_api.py::test_cancel_purchase_receipt_stale_version_returns_409[asyncio] PASSED [ 52%]
tests/test_purchase_receipts_api.py::test_cancel_purchase_receipt_terminal_returns_409[asyncio] PASSED [ 54%]
tests/test_purchase_receipts_api.py::test_cancel_purchase_receipt_not_found_returns_404[asyncio] PASSED [ 56%]
tests/test_purchase_receipts_api.py::test_cancel_purchase_receipt_roles_and_auth[asyncio] PASSED [ 58%]
tests/test_purchase_receipts_api.py::test_list_purchase_receipts_by_admin_success_200[asyncio] PASSED [ 60%]
tests/test_purchase_receipts_api.py::test_list_purchase_receipts_roles_and_auth[asyncio] PASSED [ 62%]
tests/test_purchase_receipts_api.py::test_list_purchase_receipts_validation_errors[asyncio] PASSED [ 64%]
tests/test_purchase_receipts_api.py::test_get_purchase_receipt_not_found_returns_404[asyncio] PASSED [ 66%]
tests/modules/purchasing/test_draft_service.py::test_create_draft_success_merges_identical_product_cost PASSED [ 67%]
tests/modules/purchasing/test_draft_service.py::test_create_draft_rejects_conflicting_product_cost PASSED [ 69%]
tests/modules/purchasing/test_draft_service.py::test_create_draft_rejects_inactive_supplier PASSED [ 71%]
tests/modules/purchasing/test_draft_service.py::test_create_draft_rejects_inactive_product PASSED [ 73%]
tests/modules/purchasing/test_draft_service.py::test_create_draft_rejects_nonexistent_supplier_and_product PASSED [ 75%]
tests/modules/purchasing/test_draft_service.py::test_update_draft_increments_version_and_updates_items PASSED [ 77%]
tests/modules/purchasing/test_draft_service.py::test_update_draft_rejects_empty_patch PASSED [ 79%]
tests/modules/purchasing/test_draft_service.py::test_update_draft_stale_version_conflict PASSED [ 81%]
tests/modules/purchasing/test_draft_service.py::test_update_draft_rejects_non_draft_status PASSED [ 83%]
tests/modules/purchasing/test_draft_service.py::test_create_and_update_integer_bounds_and_overflow PASSED [ 84%]
tests/modules/purchasing/test_draft_service.py::test_draft_operations_do_not_mutate_inventory PASSED [ 86%]
tests/modules/purchasing/test_draft_service.py::test_cancel_draft_success PASSED [ 88%]
tests/modules/purchasing/test_draft_service.py::test_cancel_draft_stale_version_raises_409 PASSED [ 90%]
tests/modules/purchasing/test_draft_service.py::test_cancel_draft_terminal_status_raises_409 PASSED [ 92%]
tests/modules/purchasing/test_draft_service.py::test_cancel_draft_not_found_raises_404 PASSED [ 94%]
tests/modules/purchasing/test_draft_service.py::test_list_receipts_filters_and_pagination PASSED [ 96%]
tests/modules/purchasing/test_draft_service.py::test_list_receipts_validation_errors PASSED [ 98%]
tests/modules/purchasing/test_draft_service.py::test_get_receipt_success_and_not_found PASSED [100%]

======================= 53 passed, 2 warnings in 3.71s ========================
```

### C. Kết quả MySQL Integration Tests (GitHub Actions CI Logs — 15 tests passed)
```text
tests/integration/test_products_integration.py::test_mysql_product_create_atomically_creates_zero_inventory PASSED
tests/integration/test_products_integration.py::test_mysql_forced_inventory_failure_rolls_back_product_row PASSED
tests/integration/test_products_integration.py::test_mysql_concurrent_duplicate_sku_allows_only_one_product PASSED
tests/integration/test_products_integration.py::test_mysql_inactive_category_and_update_status_flow PASSED
tests/integration/test_products_integration.py::test_mysql_cleanup_preserves_preexisting_category_and_product PASSED
tests/integration/test_products_integration.py::test_mysql_cleanup_deletes_committed_rows_when_test_fails PASSED
tests/integration/test_products_integration.py::test_mysql_product_search_filter_sort_and_pagination_stability PASSED
tests/integration/test_products_integration.py::test_mysql_product_search_special_characters_escaping PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_create_draft_atomically_merges_items_without_inventory_mutation PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cost_conflict_rolls_back_without_orphan_receipt PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_concurrent_update_optimistic_locking_only_one_wins PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cancel_draft_without_inventory_mutation PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cancel_draft_concurrent_optimistic_locking_only_one_wins PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cancel_draft_terminal_immutable PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_list_and_get_receipts PASSED

======================== 15 passed in 7.82s ========================
```
