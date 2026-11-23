# RetailOps V1.0 — Kịch bản Kiểm thử Nghiệm thu (UAT) & Bảng Theo dõi Lỗi (Sprint 3)

**Hệ thống:** RetailOps Management System V1.0<br>
**Giai đoạn:** Sprint 3 — Nghiệm thu Tích hợp & Đóng băng Release Candidate<br>
**Mã Task LMS:** `T04A996` (Tài liệu và UAT - Sprint 3) *(Chuẩn bị trực tiếp cho `T04ABC3` - Nghiệm thu release & `T04ABDD` - Báo cáo QA)*<br>
**Hợp đồng / Gate:** `GATE-E2E`, `DEPLOY`<br>
**Người phụ trách (Owner):** Lan Anh (Senior QA & Integration Reviewer)<br>
**Người đánh giá (Reviewer):** Tech Lead & Software Architect<br>
**Ngày cập nhật:** 15/11/2026<br>
**Trạng thái tài liệu:** BẢN KHỞI TẠO ĐẦU SPRINT 3 — CẬP NHẬT LIÊN TỤC (LIVING DOCUMENT)<br>
**Nhánh Git:** `feature/T04A996-docs-and-uat` (PR #63)<br>
**Target Base Branch:** `develop` (HEAD mới nhất: `b0d4dc9` — Merge PR #62)<br>
**Database Schema Revision:** `20261113_01 (head)` (Tổng cộng 11 migrations)  

---

## 1. Thông tin Quản lý Tài liệu & Quy tắc Nghiệm thu (UAT Governance & Rules)

### 1.1. Mục đích và Phạm vi
Tài liệu này xác lập quy trình kiểm thử nghiệm thu người dùng đầu cuối (End-to-End User Acceptance Testing - E2E UAT), checklist điều kiện môi trường có thể tái lập, bảng đối soát hợp đồng API (API Contract Audit), danh mục kịch bản nghiệm thu chi tiết cho 7 phân hệ nghiệp vụ, ma trận theo dõi tiến độ các task Sprint 3, và sổ cái theo dõi lỗi (Defect Ledger) phục vụ trực tiếp cho việc ký duyệt nghiệm thu và đóng băng bản phát hành `RetailOps V1.0 Release Candidate` (`T04ABC3`).

### 1.2. Quy tắc Nghiệm thu Bắt buộc (Strict Acceptance Rules — No Fake PASS)
1. **Phân Biệt Rõ Ràng Các Cấp Độ Kiểm Thử (No Conflation of Test Levels):**
   - **Automated Unit / API Test:** Kiểm thử mức hàm hoặc HTTP mock/unit. Đạt kết quả này chỉ ghi nhận `AUTOMATED_TEST_PASS`. Tuyệt đối không suy diễn thành E2E hay UAT PASS.
   - **Integration Test (MySQL / Redis):** Kiểm thử tích hợp đa luồng trên cơ sở dữ liệu thật với transaction/concurrency. Đạt kết quả này ghi nhận `INTEGRATION_TEST_PASS` cho phạm vi được kiểm chứng.
   - **Manual E2E / UAT:** Kiểm thử luồng người dùng hoàn chỉnh trên toàn bộ hệ thống thực tế (qua Nginx, FastAPI, MySQL, Redis). **Chỉ ghi `UAT_PASS` khi có đầy đủ biên bản kiểm thử thực tế, tài khoản thực hiện, mốc thời gian và bằng chứng có thể kiểm chứng.**
2. **Quy định Về Ba Lớp Trạng Thái Nghiệm Thu:**
   - `implementation_status`: `MERGED_DEVELOP` (mã nguồn đã merge vào develop) | `PR_OPEN` (PR đang mở review) | `NOT_IMPLEMENTED` (chưa triển khai).
   - `verification_level`: `AUTOMATED_TEST_PASS` | `INTEGRATION_TEST_PASS` | `NOT_VERIFIED`.
   - `uat_result`: `READY_FOR_UAT` (tính năng đã merge và pass kiểm thử tự động, sẵn sàng cho đợt manual UAT E2E ngày 24/11) | `PENDING_IMPLEMENTATION` (chưa merge xong code, chưa thể nghiệm thu).
3. **Môi trường Thực tế vs Mock/SQLite:** Tuyệt đối **không** coi kết quả chạy trên Mock API hoặc cơ sở dữ liệu SQLite in-memory là bằng chứng nghiệm thu UAT hoặc Integration Test. Mọi bằng chứng nghiệm thu bắt buộc phải được thực thi và xác thực trên **MySQL 8.4 InnoDB**, **Redis 8.4 Alpine**, và API thực tế chạy qua Reverse Proxy Nginx.
4. **Chính sách Zero Critical / High Defect:** Trước khi tiến hành đóng băng bản phát hành (`T04ABC3`), **tuyệt đối không còn bất kỳ lỗi nào ở mức Critical hoặc High đang ở trạng thái OPEN hoặc IN_PROGRESS**.

---

## 2. Checklist Khởi tạo Môi trường Chuẩn trước khi UAT (Reproducible Environment Checklist)

Trước khi tiến hành thực thi bất kỳ kịch bản UAT nào, kỹ sư QA và người kiểm thử bắt buộc phải hoàn thành bảng kiểm tra điều kiện tiên quyết sau:

| STT | Hạng mục Kiểm tra | Tiêu chuẩn Đạt yêu cầu | Lệnh Kiểm chứng Thực tế | Trạng thái | Bằng chứng Kiểm chứng Thực tế (Evidence) |
|:---:|:---|:---|:---|:---:|:---|
| 1 | **Mã nguồn Git** | Nhánh `feature/T04A996-docs-and-uat`, đồng bộ với develop mới nhất (`b0d4dc9`). | `git status --short --branch`<br>`git rev-parse HEAD`<br>`git rev-parse origin/develop` | **VERIFIED** | Đã xác minh qua Git CLI cục bộ & remote. HEAD: commit `89f210f` (merge `f9339f9` từ `origin/develop:b0d4dc9`). Cây làm việc sạch (0 uncommitted changes). |
| 2 | **Docker Containers** | 4 container khởi chạy: `mysql` (healthy), `redis` (healthy), `backend` (healthy), `nginx` (running). | `docker compose ps` | **PENDING_CHECK** | File `compose.yaml` sẵn sàng; chưa có phiên chạy `docker compose ps` ghi nhận healthy đủ 4 container trong môi trường UAT demo; cần kiểm tra khi dựng stack trước phiên UAT thực tế. |
| 3 | **Database Revision** | Schema MySQL đã áp dụng đủ 11 migrations lên revision mới nhất của Sprint 3. | `docker compose run --rm --no-deps backend alembic current`<br>*(Kết quả: `20261113_01 (head)`)* | **PENDING_CHECK**<br>*(CI: VERIFIED)* | Đã xác minh trên GitHub Actions CI Backend (PR #44, commit `b0d4dc9` áp dụng đủ 11 migrations tới `20261113_01`). Cần kiểm chứng lại trên container MySQL demo cục bộ trước phiên UAT. |
| 4 | **Admin Seed** | 1 tài khoản quản trị viên duy nhất (`ADMIN`, trạng thái `ACTIVE`), mật khẩu đạt chuẩn. | `docker compose run --rm --no-deps -e RETAILOPS_ADMIN_SEED_EMAIL -e RETAILOPS_ADMIN_SEED_PASSWORD backend python -m app.modules.auth.seed` | **PENDING_CHECK** | Script `app/modules/auth/seed.py` đã sẵn sàng và idempotent; cần thực thi và ghi nhận log nạp thành công khi khởi tạo môi trường UAT demo. |
| 5 | **Categories Seed** | 5 danh mục hàng hóa chuẩn từ code: "Đồ uống", "Bánh kẹo & Đồ ăn vặt", "Thực phẩm đóng hộp", "Hóa mỹ phẩm & Tẩy rửa", "Đồ gia dụng tiện ích". | `docker compose run --rm --no-deps backend python -m app.modules.categories.seed` | **PENDING_CHECK** | Script `app/modules/categories/seed.py` định nghĩa 5 danh mục chuẩn; cần thực thi và xác nhận nạp thành công khi khởi tạo môi trường UAT demo. |
| 6 | **Suppliers Seed** | 3 nhà cung cấp chuẩn từ code: "Công ty TNHH Phân phối Nước giải khát Việt", "Công ty Cổ phần Thực phẩm An Toàn", "Đại lý Phân phối Hàng gia dụng Miền Bắc". | `docker compose run --rm --no-deps backend python -m app.modules.suppliers.seed` | **PENDING_CHECK** | Script `app/modules/suppliers/seed.py` định nghĩa 3 nhà cung cấp chuẩn; cần thực thi và xác nhận nạp thành công khi khởi tạo môi trường UAT demo. |
| 7 | **Proxy & Ingress** | Cổng Nginx mở tại `http://127.0.0.1:80` (hoặc `8080`), API health phản hồi `{"status":"ok"}`. | `curl -fsS http://127.0.0.1:80/api/v1/health` | **PENDING_CHECK** | File cấu hình `docker/nginx/nginx.conf` và route `/api/v1/health` đã được khai báo; cần thực hiện probe HTTP thực tế khi Nginx container đang chạy. |
| 8 | **Test Network (CI Overlay)** | Mạng `application` chuyển `internal: false`, Redis mở `16379`, MySQL test db `retailops_test`. | `docker compose -f compose.yaml -f compose.ci.yaml up -d`<br>`pytest tests/integration/test_purchase_receipts_mysql.py` | **VERIFIED**<br>*(CI Environment)* | GitHub Actions Backend CI (`compose.ci.yaml`), suite `test_purchase_receipts_mysql.py` (7 tests) pass 100% trên commit `b0d4dc9`. Cần khởi chạy host overlay khi thực hiện integration test cục bộ. |

---

## 3. Bảng Đối Soát Hợp Đồng API (API Contract Audit)

Bảng đối soát chi tiết giữa đặc tả tài liệu UAT và mã nguồn thực tế trên `develop` / `contracts/openapi.yaml`:

| Module | Yêu cầu Kịch bản | Endpoint / Schema Sai Lệch (Cũ) | Endpoint / Schema Chuẩn Xác (Đã Sửa) | Nguồn Đối Soát (Source of Truth) |
|:---|:---|:---|:---|:---|
| **AUTH** | Đăng ký nhân viên | Nhận `full_name`, trả HTTP `200` | Schema chỉ nhận `email`, `password`. Trả về HTTP `202 Accepted` | `backend/app/modules/auth/router.py:33`<br>`schemas.py:135` |
| **CATEGORY** | Cập nhật danh mục | Dùng HTTP method `PUT` | Bắt buộc dùng `PATCH /api/v1/categories/{id}` | `backend/app/modules/categories/router.py:94` |
| **INVENTORY** | Điều chỉnh tồn kho | Nhận `quantity_delta` | `POST /api/v1/inventory/{product_id}/adjustments`, nhận `counted_quantity` & `expected_stock_version` | `backend/app/modules/inventory/router.py:115`<br>`schemas.py:100` |
| **INVENTORY** | Cảnh báo tồn thấp | Cấu hình `reorder_point = 10` | Ngưỡng an toàn cố định trong code: `DEFAULT_LOW_STOCK_THRESHOLD = 5` | `backend/app/modules/inventory/schemas.py:21` |
| **INVENTORY** | Schema tồn kho | Giả định có `reserved`, `available` | `InventoryRead` chỉ gồm: `quantity`, `stock_version`, `first_stocked_at` (không có reserved/available) | `backend/app/modules/inventory/schemas.py:33` |
| **INVENTORY** | Lịch sử biến động | Gọi `/inventory/{id}/movements` | Router riêng: `GET /api/v1/stock-movements?product_id={id}` | `backend/app/modules/inventory/router.py:172` |
| **POS / ORDER** | Chặn bán vượt tồn | Trả HTTP `400 Bad Request` | Trả HTTP `409 Conflict`, mã lỗi `INSUFFICIENT_STOCK` | `backend/app/modules/sales/service.py:164, 235` |
| **MOVEMENT** | Loại giao dịch kho | Ghi `RECEIPT`, `ORDER_DEDUCT` | 4 giá trị `MovementKind` chuẩn: `PURCHASE_CONFIRM`, `SALE`, `ORDER_CANCEL`, `ADJUSTMENT` | `backend/app/modules/inventory/models.py:26` |
| **ANALYTICS** | Doanh thu bán hàng | Query `from_date`, `to_date` | Query parameters chuẩn trong OpenAPI: `from` và `to` (`GET /api/v1/analytics/sales`) | `contracts/openapi.yaml:1788-1800` |
| **ANALYTICS** | Sản phẩm phân tích | Gọi `/analytics/top-products` | `GET /api/v1/analytics/products/top` và `GET /api/v1/analytics/products/slow` | `contracts/openapi.yaml:1803, 1887` |
| **DASHBOARD** | Tổng quan quản trị | Đánh dấu là đã merge | Endpoint `GET /api/v1/dashboard` đang ở PR #61 (chưa merge) | `contracts/openapi.yaml:1964`<br>PR #61 |
| **AI / OUTBOX** | Async Worker & AI | Ghi nhận UAT PASS | Chưa merge worker/AI runtime; đổi trạng thái thành `PENDING (Chờ tích hợp S3)` | `docs/contracts/ASYNC_AI_CONTRACTS.md` |

---

## 4. Danh mục Kịch bản Kiểm thử UAT Chi tiết (End-to-End UAT Scenarios & Checklist)

### Nhóm 1 — Auth, Staff Approval & Password Reset (`AUTH-01` .. `AUTH-05`)
*Mã Task LMS liên quan:* `T04A61F`, `T04A6F3`, `T04AA1C`, `T04A9CA`, `T04AAA2`

| Mã UAT | Mã SRS / Task | Vai trò | Tiền điều kiện | Các bước thực hiện | Kết quả mong đợi & Bất biến nghiệp vụ | Trạng thái Mã nguồn & Kiểm thử | Kết quả UAT | Bằng chứng Xác minh |
|:---|:---|:---:|:---|:---|:---|:---:|:---:|:---|
| **UAT-AUTH-01** | `SRS-AUTH-01`<br>`T04A61F` | Khách / Staff | Hệ thống hoạt động, email hợp lệ chưa đăng ký. | 1. Gửi request `POST /api/v1/auth/register` với `email` và `password` (không gửi full_name).<br>2. Kiểm tra DB bảng `users` và `staff_approval_requests`. | HTTP `202 Accepted`, body `{"message": "Registration submitted..."}`. Tạo tài khoản `PENDING_APPROVAL`, bản ghi duyệt `PENDING`. Chưa thể đăng nhập. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_staff_approval_api.py`<br>`authSecurity.test.js` |
| **UAT-AUTH-02** | `SRS-AUTH-02`<br>`T04A61F`<br>`T04A6F3` | Admin | Tài khoản Staff đang ở trạng thái `PENDING_APPROVAL`. | 1. Admin đăng nhập lấy token.<br>2. Gọi `POST /api/v1/auth/staff-approval/{id}/approve` (hoặc `reject`). | Trả về HTTP `200 OK`. Trạng thái chuyển thành `ACTIVE` (hoặc `REJECTED`). Khi duyệt, tài khoản Staff đăng nhập được; khi từ chối, chặn đăng nhập. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | `test_staff_approval.py`<br>SHA: `b0d4dc9` |
| **UAT-AUTH-03** | `SRS-AUTH-03`<br>`T04A61F`<br>`T04AAA2` | Admin / Staff | Tài khoản `ACTIVE`. | 1. Gửi `POST /api/v1/auth/login` với email và password đúng.<br>2. Kiểm tra header `Set-Cookie` và body JSON. | HTTP `200 OK`. Nhận `access_token` (TTL 15m), Cookie `retailops_refresh` có cờ `HttpOnly`, `Path=/api/v1/auth`, `SameSite`, và `retailops_csrf` cookie. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_auth_api.py`<br>SHA: `b0d4dc9` |
| **UAT-AUTH-04** | `SRS-AUTH-04`<br>`T04A61F` | Staff | Đăng nhập với tài khoản `STAFF`. | 1. Gửi request truy cập endpoint Admin: `POST /api/v1/auth/staff-approval/{id}/approve` hoặc `POST /api/v1/suppliers`. | HTTP `403 Forbidden` (`PERMISSION_DENIED`). RBAC chặn đứng ở tầng Backend, không phụ thuộc vào ẩn nút trên UI. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_cors.py`<br>`authSecurity.test.js` |
| **UAT-AUTH-05** | `SRS-AUTH-05`<br>`T04AA1C`<br>`T04A9CA` | Staff | Tài khoản tồn tại, quên mật khẩu. | 1. Gọi `POST /api/v1/auth/forgot-password` với email.<br>2. Lấy one-time token từ Outbox.<br>3. Gọi `POST /api/v1/auth/reset-password` với token và mật khẩu mới.<br>4. Đăng nhập lại. | Trả về generic 202/200, chống enumeration (không báo email có tồn tại hay không). Token được hash trong DB, một lần dùng. Mật khẩu mới cập nhật, toàn bộ session cũ bị thu hồi ngay lập tức. | `NOT_IMPLEMENTED`<br>`NOT_VERIFIED` | **PENDING_IMPLEMENTATION** | `Chờ PR của task T04AA1C merge và chạy test thật` |

---

### Nhóm 2 — Categories, Suppliers & Products (`CAT-01`, `SUP-01`, `PROD-01` .. `PROD-04`)
*Mã Task LMS liên quan:* `T04A70D`, `T04A6A3`, `T04A9B0`, `T04AAD7`

| Mã UAT | Mã SRS / Task | Vai trò | Tiền điều kiện | Các bước thực hiện | Kết quả mong đợi & Bất biến nghiệp vụ | Trạng thái Mã nguồn & Kiểm thử | Kết quả UAT | Bằng chứng Xác minh |
|:---|:---|:---:|:---|:---|:---|:---:|:---:|:---|
| **UAT-CAT-01** | `SRS-CAT-01`<br>`T04A70D` | Admin / Staff | 5 danh mục đã được seed. | 1. Gọi `GET /api/v1/categories`.<br>2. Admin gọi `POST /api/v1/categories` tạo danh mục mới.<br>3. Gọi `PATCH /api/v1/categories/{id}` sửa mô tả. | HTTP `200 OK` danh sách 5 danh mục ("Đồ uống", "Bánh kẹo & Đồ ăn vặt"...). Tạo mới trả về `201 Created`. Cập nhật qua `PATCH` lưu thành công vào MySQL. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_categories_api.py`<br>`categoryList.test.js` |
| **UAT-SUP-01** | `SRS-SUP-01`<br>`T04A70D` | Admin | Đã đăng nhập vai trò `ADMIN`. | 1. Tạo nhà cung cấp với số điện thoại sai định dạng (ví dụ `12345`).<br>2. Gửi lại với SĐT Việt Nam chuẩn E.164 (`+84912345678`) và MST. | Bước 1: Trả về HTTP `422 Unprocessable Entity`. Bước 2: Trả về HTTP `201 Created`, lưu SĐT định dạng chuẩn quốc tế E.164. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_phone_validation.py`<br>`test_suppliers_api.py` |
| **UAT-PROD-01** | `SRS-PROD-01`<br>`T04A6A3` | Admin | Danh mục và nhà cung cấp đã có. | 1. Gọi `POST /api/v1/products` với SKU, Barcode, tên, giá vốn, giá bán.<br>2. Thử tạo sản phẩm thứ 2 trùng Barcode hoặc trùng SKU. | Sản phẩm 1 tạo thành công (`201 Created`), tự sinh tồn kho `on_hand = 0`. Sản phẩm trùng Barcode/SKU bị từ chối với HTTP `409 Conflict`. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_products_api.py`<br>`productList.test.js` |
| **UAT-PROD-02** | `SRS-PROD-02`<br>`T04A6A3`<br>`T04AAD7` | Staff | Đăng nhập tài khoản `STAFF`. | 1. Gọi `GET /api/v1/products` xem danh sách sản phẩm.<br>2. Mở chi tiết sản phẩm trên giao diện UI. | HTTP `200 OK`. Trường `unit_cost_vnd` / `cost_price` bị **ẩn hoàn toàn** khỏi JSON phản hồi (`None` hoặc omitted) và không hiển thị trên UI. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `productList.test.js`<br>SHA: `b0d4dc9` |
| **UAT-PROD-03** | `SRS-PROD-03`<br>`T04A6A3` | Admin / Staff | Đã có danh sách sản phẩm. | 1. Gọi `GET /api/v1/products?q=nuoc+ngot&category_id=1&page=1&page_size=10`. | Trả về đúng sản phẩm thỏa mãn điều kiện, cấu trúc phân trang đầy đủ (`total`, `page`, `page_size`, `items`). | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_products_api.py` |

---

### Nhóm 3 — Purchasing / Quản lý Nhập hàng (`PUR-01` .. `PUR-05`)
*Mã Task LMS liên quan:* `T04A6D7`, `T04A772`, `T04A7DF`, `T04A7C3`, `T04A8B7`, `T04AABC`

| Mã UAT | Mã SRS / Task | Vai trò | Tiền điều kiện | Các bước thực hiện | Kết quả mong đợi & Bất biến nghiệp vụ | Trạng thái Mã nguồn & Kiểm thử | Kết quả UAT | Bằng chứng Xác minh |
|:---|:---|:---:|:---|:---|:---|:---:|:---:|:---|
| **UAT-PUR-01** | `SRS-PUR-01`<br>`T04A6D7` | Admin | Sản phẩm A có tồn kho `on_hand = 10`. | 1. Gửi `POST /api/v1/purchase-receipts` tạo phiếu nháp với 5 sản phẩm A, đơn giá 100,000.<br>2. Kiểm tra tồn kho sản phẩm A. | HTTP `201 Created`. Phiếu có `status: "DRAFT"`, `draft_version: 1`. Tồn kho sản phẩm A giữ nguyên `10` (phiếu nháp không tác động tồn kho). | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #35<br>`test_purchase_receipts_mysql.py` |
| **UAT-PUR-02** | `SRS-PUR-02`<br>`T04A6D7` | Admin | Nhà cung cấp và sản phẩm tồn tại. | 1. Tạo phiếu nháp gửi 2 dòng cùng `product_id = 1`, cùng `unit_cost = 100000`, số lượng 2 và 3.<br>2. Thử tạo phiếu gửi 2 dòng cùng `product_id` nhưng khác giá. | Trường hợp 1: Tự động gộp thành 1 dòng `quantity = 5`, thành tiền `500000`. Trường hợp 2: Bị từ chối với HTTP `400 Bad Request` hoặc `409 Conflict`. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | `purchaseReceipts.test.js`<br>`test_purchase_receipts_mysql.py` |
| **UAT-PUR-03** | `SRS-PUR-03`<br>`T04A6D7`<br>`T04A772` | Admin | Phiếu nháp đang ở `draft_version = 1`. | 1. Client A gửi `PATCH /purchase-receipts/{id}` kèm `expected_draft_version = 1`.<br>2. Client B gửi cập nhật đồng thời với `expected_draft_version = 1`. | Client A thành công, `draft_version` tăng lên `2`. Client B bị từ chối với HTTP `409 Conflict` (`RECEIPT_VERSION_CONFLICT`). Chống ghi đè dữ liệu đồng thời. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #44<br>`test_purchase_receipts_mysql.py` |
| **UAT-PUR-04** | `SRS-PUR-04`<br>`T04A772` | Admin | Phiếu nháp đang ở `draft_version = 2`. | 1. Gọi `POST /purchase-receipts/{id}/cancel` kèm `expected_draft_version = 2`.<br>2. Kiểm tra trạng thái phiếu và tồn kho sản phẩm. | HTTP `200 OK`. Trạng thái chuyển thành `CANCELLED`, `draft_version = 3`. Tồn kho các sản phẩm giữ nguyên 100%, không bị ảnh hưởng. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #44<br>`test_purchase_receipts_mysql.py` |
| **UAT-PUR-05** | `SRS-PUR-05`<br>`T04A7DF`<br>`T04AABC` | Admin | Phiếu nháp hợp lệ, sản phẩm có `on_hand = 10`. | 1. Gọi `POST /purchase-receipts/{id}/confirm` kèm header `Idempotency-Key` và `expected_draft_version`.<br>2. Gửi lại request trên lần thứ 2 với cùng key. | Lần 1: Trả về `200 OK`, trạng thái `CONFIRMED`, tồn kho tăng từ 10 lên 15, sinh `StockMovement` loại `PURCHASE_CONFIRM`. Lần 2: Trả về kết quả cũ (replay), tồn kho không tăng thêm. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | `test_receipt_confirmation_mysql.py` |

---

### Nhóm 4 — Inventory & Stock Movements (`INV-01` .. `INV-04`)
*Mã Task LMS liên quan:* `T04A653`, `T04A6BD`, `T04A758`, `T04A78E`, `T04A97C`, `T04AB59`

| Mã UAT | Mã SRS / Task | Vai trò | Tiền điều kiện | Các bước thực hiện | Kết quả mong đợi & Bất biến nghiệp vụ | Trạng thái Mã nguồn & Kiểm thử | Kết quả UAT | Bằng chứng Xác minh |
|:---|:---|:---:|:---|:---|:---|:---:|:---:|:---|
| **UAT-INV-01** | `SRS-INV-01`<br>`T04A6BD` | Admin / Staff | Sản phẩm đã có tồn kho. | 1. Gọi `GET /api/v1/inventory/{product_id}`. | HTTP `200 OK`. Schema `InventoryRead` trả về `quantity`, `stock_version`, `first_stocked_at` (không có reserved hay available). Cập nhật theo thời gian thực. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_inventory_api.py` |
| **UAT-INV-02** | `SRS-INV-02`<br>`T04A78E` | Admin / Staff | Sản phẩm có tồn thực tế `on_hand = 3` (dưới ngưỡng an toàn cố định = 5). | 1. Gọi `GET /api/v1/inventory/low-stock`. | HTTP `200 OK`. Danh sách hiển thị sản phẩm thiếu hụt theo ngưỡng mặc định `threshold = 5`. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_low_stock_and_movements.py` |
| **UAT-INV-03** | `SRS-INV-03`<br>`T04A758`<br>`T04AB59` | Admin | Sản phẩm có `on_hand = 10`, `stock_version = 1`. | 1. Gọi `POST /api/v1/inventory/{product_id}/adjustments` với `counted_quantity = 8`, `expected_stock_version = 1`, `reason = "Hỏng do vận chuyển"`, header `Idempotency-Key`.<br>2. Thử điều chỉnh `counted_quantity = -5`. | Bước 1: Thành công (`200 OK`), tồn kho cập nhật thành 8, `stock_version = 2`, sinh movement `ADJUSTMENT`. Bước 2: Bị từ chối với HTTP `422 Unprocessable Entity` (chặn tồn âm). | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | `test_inventory_adjustment_api.py` |
| **UAT-INV-04** | `SRS-INV-04`<br>`T04A78E` | Staff | Đăng nhập tài khoản `STAFF`. | 1. Xem lịch sử biến động kho qua router riêng: `GET /api/v1/stock-movements?product_id={id}`. | Trả về danh sách biến động (`PURCHASE_CONFIRM`, `SALE`, `ORDER_CANCEL`, `ADJUSTMENT`). Trường đơn giá vốn (`unit_cost_vnd`) bị ẩn hoàn toàn với vai trò `STAFF`. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | `test_low_stock_and_movements.py` |

---

### Nhóm 5 — POS Checkout, Order History & Cancel (`SALE-01` .. `SALE-04`, `ORD-01` .. `ORD-03`)
*Mã Task LMS liên quan:* `T04A73C`, `T04A7A8`, `T04A80C`, `T04A840`, `T04A869`, `T04A883`, `T04A961`, `T04A9CA`, `T04AAF1`

| Mã UAT | Mã SRS / Task | Vai trò | Tiền điều kiện | Các bước thực hiện | Kết quả mong đợi & Bất biến nghiệp vụ | Trạng thái Mã nguồn & Kiểm thử | Kết quả UAT | Bằng chứng Xác minh |
|:---|:---|:---:|:---|:---|:---|:---:|:---:|:---|
| **UAT-SALE-01** | `SRS-POS-01`<br>`T04A73C`<br>`T04A869` | Cashier / Staff | Sản phẩm có `on_hand = 10`. | 1. Thêm 2 sản phẩm vào giỏ hàng POS.<br>2. Gửi request thanh toán `POST /api/v1/orders/checkout` kèm `Idempotency-Key`. | HTTP `201 Created`. Đơn hàng chuyển trạng thái `COMPLETED`. Tồn kho giảm tức thời xuống 8. Sinh `StockMovement` loại `SALE`. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #62<br>`test_checkout_api.py`<br>`posPage.test.js` |
| **UAT-SALE-02** | `SRS-POS-02`<br>`T04A73C` | Cashier / Staff | Sản phẩm trong giỏ bị đổi giá bán từ 100k lên 120k trước khi thanh toán. | 1. Thu ngân nhấn thanh toán đơn với đơn giá cũ 100k. | Hệ thống bắt lệch giá, trả về HTTP `409 Conflict` (`PRICE_CHANGED`). Không tạo đơn, không trừ kho. Thu ngân xác nhận giá mới và dùng key mới. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #62<br>`test_checkout_api.py` |
| **UAT-SALE-03** | `SRS-POS-03`<br>`T04A73C`<br>`T04A9CA` | Cashier / Staff | Sản phẩm chỉ còn tồn `on_hand = 1`. | 1. Thu ngân thanh toán mua số lượng 2 sản phẩm. | Bị từ chối với HTTP `409 Conflict` (`INSUFFICIENT_STOCK`). Ngăn chặn hoàn toàn hiện tượng oversell khi có nhiều quầy POS cùng bán. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #62<br>`test_checkout_api.py` |
| **UAT-ORD-01** | `SRS-ORD-01`<br>`T04A840`<br>`T04A961` | Staff / Admin | Đã phát sinh các đơn hàng. | 1. Gọi `GET /api/v1/orders?status=COMPLETED&page=1&page_size=10`. | HTTP `200 OK`. Trả về danh sách đơn hàng đã lọc và phân trang chuẩn xác ở server. | `MERGED_DEVELOP`<br>`AUTOMATED_TEST_PASS` | **READY_FOR_UAT** | PR #62<br>`orderCancel.test.js`<br>`test_order_read_api.py` |
| **UAT-ORD-02** | `SRS-ORD-02`<br>`T04A80C`<br>`T04A961` | Staff | Đơn hàng `COMPLETED` do chính Staff tạo cách đây 5 phút (trong vòng 15 phút cùng ngày). | 1. Staff gửi request `POST /api/v1/orders/{id}/cancel` kèm lý do bắt buộc. | HTTP `200 OK`. Trạng thái đơn thành `CANCELLED`. Tồn kho tự động hoàn trả đầy đủ, sinh `StockMovement` loại `ORDER_CANCEL`. Hoàn kho đúng 1 lần. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #62<br>`orderCancel.test.js`<br>`test_cancel_api.py` |
| **UAT-ORD-03** | `SRS-ORD-03`<br>`T04A80C` | Staff | Đơn hàng tạo bởi nhân viên khác hoặc đã quá thời hạn 15 phút. | 1. Staff gửi request hủy đơn hàng trên. | Bị từ chối với HTTP `403 Forbidden` hoặc `400 Bad Request` (`CANCEL_WINDOW_EXPIRED`). Chỉ `ADMIN` mới có quyền hủy đơn quá hạn trong ngày. | `MERGED_DEVELOP`<br>`INTEGRATION_TEST_PASS` | **READY_FOR_UAT** | PR #62<br>`test_cancel_api.py` |

---

### Nhóm 6 — Analytics & Dashboard (`RPT-01` .. `RPT-03`)
*Mã Task LMS liên quan:* `T04A92B`, `T04A947`, `T04AA36`, `T04AB25`, `T04AC15`

| Mã UAT | Mã SRS / Task | Vai trò | Tiền điều kiện | Các bước thực hiện | Kết quả mong đợi & Bất biến nghiệp vụ | Trạng thái Mã nguồn & Kiểm thử | Kết quả UAT | Bằng chứng Xác minh |
|:---|:---|:---:|:---|:---|:---|:---:|:---:|:---|
| **UAT-RPT-01** | `SRS-RPT-01`<br>`T04A92B`<br>`T04AC15` | Admin | Đã có các đơn hàng `COMPLETED` và `CANCELLED`. | 1. Admin gọi endpoint chuẩn `GET /api/v1/analytics/sales?from=2026-11-01&to=2026-11-15`.<br>2. Thử truy cập với tài khoản `STAFF`. | Với Admin: HTTP `200 OK`. Doanh thu, số đơn, AOV chuẩn theo múi giờ `Asia/Ho_Chi_Minh` và **loại trừ toàn bộ đơn `CANCELLED`**. Với Staff: HTTP `403 Forbidden`. | `PR_OPEN (PR #60)`<br>`NOT_VERIFIED` | **PENDING_IMPLEMENTATION** | `Chờ PR #60 merge vào develop và chạy test thật` |
| **UAT-RPT-02** | `SRS-RPT-02`<br>`T04A947` | Admin | Đã có dữ liệu xuất bán và nhập kho. | 1. Gọi `GET /api/v1/analytics/products/top?days=30&limit=5`.<br>2. Gọi `GET /api/v1/analytics/products/slow?limit=10`. | HTTP `200 OK`. Top sản phẩm xếp đúng thứ tự doanh thu/lượng bán. Sản phẩm bán chậm nhận diện đúng: nhập kho `> 7 ngày`, tồn `> 0`, lượng bán `<= 2 đơn vị / 30 ngày`. | `NOT_IMPLEMENTED`<br>`NOT_VERIFIED` | **PENDING_IMPLEMENTATION** | `Chờ PR của task T04A947 merge và chạy test thật` |
| **UAT-RPT-03** | `SRS-RPT-03`<br>`T04AA36`<br>`T04AB25`<br>`T04AC15` | Admin | Dữ liệu giao dịch hoàn tất. | 1. Gọi endpoint tổng hợp `GET /api/v1/dashboard`.<br>2. Thực hiện đối soát số liệu chéo giữa Order, Inventory và Dashboard KPI. | HTTP `200 OK`, schema `DashboardRead`. Số liệu khớp 100%, không xảy ra tình trạng tiền tăng mà kho không trừ hoặc báo cáo lệch số dư. | `PR_OPEN (PR #61)`<br>`NOT_VERIFIED` | **PENDING_IMPLEMENTATION** | `Chờ PR #61 merge vào develop và chạy test thật` |

---

### Nhóm 7 — Transactional Outbox Email Worker & Read-Only AI (`AI-01` .. `AI-03`)
*Mã Task LMS liên quan:* `T04A90F`, `T04AA00`, `T04A9E6`, `T04AA86`, `T04AB0B`, `T04AB59`, `T04AB73`

| Mã UAT | Mã SRS / Task | Vai trò | Tiền điều kiện | Các bước thực hiện | Kết quả mong đợi & Bất biến nghiệp vụ | Trạng thái Mã nguồn & Kiểm thử | Kết quả UAT | Bằng chứng Xác minh |
|:---|:---|:---:|:---|:---|:---|:---:|:---:|:---|
| **UAT-AI-01** | `SRS-OUTBOX-01`<br>`T04A90F`<br>`T04AA00` | Hệ thống | Người dùng đăng ký hoặc yêu cầu reset mật khẩu. | 1. Nghiệp vụ hoàn tất, gọi `OutboxPublisher.publish_due`.<br>2. Email Worker gọi `EmailEventHandler.handle(event_id)`. | Sự kiện phát hành sau commit DB. Worker xử lý tuần tự, dedupe theo `event_id`, cập nhật `outcome`. Khi lỗi SMTP/broker, retry exponential backoff bounded, không mất sự kiện. | `NOT_IMPLEMENTED`<br>`NOT_VERIFIED` | **PENDING_IMPLEMENTATION** | `Chờ PR của task T04A90F, T04AA00 merge và chạy test thật` |
| **UAT-AI-02** | `SRS-AI-01`<br>`T04A9E6`<br>`T04AA86` | Admin | Đã đăng nhập vai trò `ADMIN`. | 1. Gọi `POST /api/v1/ai/query` với câu hỏi tra cứu kinh doanh.<br>2. Service gọi `ReadOnlyAIService.ask` và `AIToolExecutor.execute`.<br>3. Thử prompt injection. | HTTP `200 OK`, schema `AIAskResponse`. AI chỉ gọi tool trong allowlist (`read-only`), `ToolContext` lấy từ principal (ADMIN-only). Bounded 15s deadline / tối đa 3 tool calls / $\le 32$ KiB dữ liệu. Chống prompt injection an toàn. | `NOT_IMPLEMENTED`<br>`NOT_VERIFIED` | **PENDING_IMPLEMENTATION** | `Chờ PR của task T04A9E6, T04AA86 merge và chạy test thật` |
| **UAT-AI-03** | `SRS-AI-02`<br>`T04AB0B`<br>`T04AB25`<br>`T04AB73` | Admin | Sản phẩm chạm ngưỡng tồn an toàn. | 1. Gọi khuyến nghị nhập hàng qua `ReadOnlyReorderAdvisor.suggest` hoặc qua `POST /api/v1/ai/query`. | Trả về gợi ý thông minh có dẫn chứng dữ liệu cụ thể (`evidence`), số lượng khuyến nghị, khoảng thời gian; hiển thị rõ khi thiếu dữ liệu. Tuyệt đối không tự ý ghi DB hay sinh phiếu nhập. | `NOT_IMPLEMENTED`<br>`NOT_VERIFIED` | **PENDING_IMPLEMENTATION** | `Chờ PR của task T04AB0B, T04AB73 merge và chạy test thật` |

---

## 5. Ma trận Theo dõi Nghiệm thu Task Sprint 3 (Sprint 3 Task Acceptance Matrix)

Bảng theo dõi tiến độ và trạng thái tích hợp thực tế của toàn bộ **25 task phát triển và 6 task nghiệm thu/phát hành Sprint 3** (tổng cộng 31 tasks) chuẩn theo `docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md` và hiện trạng Git remote:

| Task LMS | Tên Tác vụ Nghiệp vụ | Người phụ trách (Owner) | Mốc trong Excel | Hợp đồng / Gate | Trạng thái Git / PR | Cổng Nghiệm thu | Ghi chú & Bằng chứng |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `T04A90F` | Transactional Outbox và Email Worker | Hiếu | 18–19/11 | `BE-OUTBOX` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04A92B` | Analytics doanh thu và đơn hàng | Na Na | 18–19/11 | `HTTP-ANALYTICS` | `PR_OPEN` | **IN_REVIEW** | PR #60 đang mở review trên GitHub (head: `21d9542`, base: `b0d4dc9`) |
| `T04A947` | Analytics sản phẩm | Dương | 18–19/11 | `HTTP-ANALYTICS` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04A961` | Hoàn thiện lịch sử và hủy đơn UI | Lâm | 18–19/11 | `HTTP-ORDER,FE-ADAPTER` | `NOT_STARTED` | **STARTABLE** | Nền tảng T04A869/T04A883 đã merge qua PR #62 (commit `b0d4dc9`); task hoàn thiện UI Sprint 3 |
| `T04A97C` | Hoàn thiện giao diện tồn kho | Tân | 18–19/11 | `HTTP-INVENTORY,FE-ADAPTER` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04A996` | Tài liệu và UAT | Lan Anh | 18–19/11 | `GATE-E2E,DEPLOY` | `PR_OPEN` | **IN_REVIEW** | PR #63 đang mở review trên GitHub (head: `89f210f`, base: `b0d4dc9`) |
| `T04A9B0` | Kiểm thử giao diện quản lý | Tân | 18–19/11 | `FE-ADAPTER,GATE-E2E` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04A9CA` | Kiểm thử Auth, Checkout và Cancel | Dương | 18–19/11 | `TEST-DB` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04A9E6` | AI Tool Executor | Hiếu | 20–21/11 | `BE-AI` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AA00` | Retry và phục hồi Email Worker | Hiếu | 20–21/11 | `BE-OUTBOX` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AA1C` | Đặt lại mật khẩu và tích hợp email | Dương | 20–21/11 | `HTTP-RESET,BE-OUTBOX` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AA36` | Dashboard API | Na Na | 20–21/11 | `HTTP-ANALYTICS` | `PR_OPEN` | **IN_REVIEW** | PR #61 đang mở review trên GitHub (head: `018800e`, base: `be7469d`) |
| `T04AA50` | Automated Integration Tests | Dương | 20–21/11 | `TEST-DB,GATE-CI` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AA6A` | Responsive và UI States | Tân | 20–21/11 | `FE-ADAPTER` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AA86` | AI chỉ đọc và Tool Calling | Dương | 20–21/11 | `BE-AI,HTTP-AI` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AAA2` | Đo hiệu năng và xác minh bảo mật | Hiếu | 20–21/11 | `PERF,GATE-E2E` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AABC` | Kiểm thử Purchasing và Email | Na Na | 22–23/11 | `TEST-DB,BE-OUTBOX` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AAD7` | Kiểm thử Product, Order và Analytics | Na Na | 20–21/11 | `TEST-DB,HTTP-ANALYTICS` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AAF1` | Kiểm thử frontend nghiệp vụ | Lâm | 20–21/11 | `GATE-E2E,FE-ADAPTER` | `PR_OPEN` | **IN_REVIEW** | Nhánh `test/t04aaf1-fe-business-e2e` (base: `ddf13a7`): 18/18 E2E API/DB thật (Auth/RBAC/Refresh/POS/409/Cancel/Dashboard 4 presets + CSV) + 392/392 FE tests PASS; xem `docs/testing/evidence/T04AAF1/T04AAF1_FE_E2E_TEST_REPORT.md` |
| `T04AB0B` | AI gợi ý nhập hàng | Dương | 22–23/11 | `BE-AI,HTTP-AI` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AB25` | Giao diện Dashboard và AI | Lâm | 22–23/11 | `HTTP-ANALYTICS,HTTP-AI,FE-ADAPTER` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AB3F` | Rà soát bảo mật và concurrency | Hiếu | 22–23/11 | `SECURITY,TEST-DB` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AB59` | Kiểm thử Inventory, Worker và AI | Dương | 22–23/11 | `TEST-DB,BE-OUTBOX,BE-AI` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AB73` | Tích hợp và demo Worker/Redis/AI | Dương | 22–23/11 | `GATE-E2E` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AB8D` | Triển khai bản demo | Hiếu | 22–23/11 | `DEPLOY` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04ABA7` | Release và smoke test | Hiếu | 24/11 | `DEPLOY,GATE-E2E` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04ABC3` | Nghiệm thu và đóng băng release | Lan Anh | 24/11 | `GATE-E2E` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04ABDD` | Báo cáo QA và tài liệu demo | Lan Anh | 24/11 | `GATE-E2E,DEPLOY` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04ABF9` | Tổng hợp giao diện và bằng chứng QA | Tân | 24/11 | `FE-ADAPTER,GATE-E2E` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AC15` | Đối soát dữ liệu và báo cáo | Na Na | 24/11 | `HTTP-ANALYTICS,GATE-E2E` | `NOT_STARTED` | **STARTABLE** | `[Chờ cập nhật PR / SHA / Test Evidence]` |
| `T04AC2F` | Kiểm tra end-to-end frontend | Lâm | 24/11 | `FE-ADAPTER,DEPLOY,GATE-E2E` | `PR_OPEN` | **IN_REVIEW** | Nhánh `test/t04ac2f-rc-browser-e2e` (base: `3e0d3c0`): 8/8 Chrome Browser E2E + 8/8 Nginx SPA reload + video & 8 ảnh bằng chứng + 394/394 FE tests PASS (0 blocker); xem `docs/testing/evidence/T04AC2F/T04AC2F_RC_BROWSER_E2E_REPORT.md` |

---

## 6. Sổ Theo dõi Lỗi (Defect Ledger)

### 6.1. Tiêu chí Phân loại Mức độ Nghiêm trọng (Severity Criteria)
- **Critical:** Lỗi gây crash hệ thống, rò rỉ dữ liệu bảo mật (bỏ qua xác thực, CSRF), vi phạm tính toàn vẹn transaction (mất tiền, lệch kho), hoặc ngăn chặn hoàn toàn một luồng nghiệp vụ P0 mà không có giải pháp tạm thời.
- **High:** Lỗi ảnh hưởng trực tiếp đến nghiệp vụ cốt lõi (khóa lạc quan không bắt được xung đột, tính sai tổng tiền/chiết khấu, eager loading văng lỗi session), có thể gây sai lệch kết quả nhưng không làm sập toàn bộ dịch vụ.
- **Medium:** Lỗi trên các chức năng phụ trợ, kiểm tra ràng buộc dữ liệu thiếu sót nhẹ, hoặc có giải pháp khắc phục tạm thời (workaround) khả thi.
- **Low:** Lỗi giao diện người dùng nhẹ, căn lề CSS, sai sót chính tả, câu chữ bản địa hóa không ảnh hưởng đến logic tính toán.

### 6.2. Phân loại Trạng thái Xử lý (Defect Status Classification)
- `FIXED_IN_CODE`: Lỗi đã được sửa trực tiếp trong mã nguồn backend/frontend.
- `DOCS_CORRECTED`: Sai lệch về tài liệu hướng dẫn, runbook hoặc kịch bản đã được đính chính chuẩn xác.
- `TEST_VERIFIED`: Bản sửa lỗi đã được kiểm chứng bằng automated test (unit/integration) chạy thành công.
- `UAT_VERIFIED`: Đã được kiểm chứng thực tế trong phiên nghiệm thu người dùng E2E.
- `OPEN`: Lỗi mới ghi nhận, đang chờ phân tích.
- `BLOCKED`: Lỗi chưa thể xử lý do phụ thuộc vào module/hạ tầng khác.

### 6.3. Bảng Theo dõi Lỗi Sprint 3 (Defect Ledger Table)

| Defect ID | Ngày ghi nhận | Mã UAT / Task | Mức độ | Mô tả Lỗi & Bước tái hiện | Commit SHA phát hiện | Người xử lý (Owner) | Trạng thái | PR / Commit SHA sửa lỗi & Bằng chứng Verify |
|:---:|:---:|:---:|:---:|:---|:---:|:---:|:---:|:---|
| `DEF-001` | 15/11/2026 | `DEPLOY`<br>`T04A8D1` | **Critical** | Không thể bind cổng `3306` khi khởi chạy MySQL trên Windows do Hyper-V / WinNAT chiếm dụng. | `a8428f3` | Hiếu | **DOCS_CORRECTED** | Bổ sung cấu hình `MYSQL_HOST_PORT=13306` trong `.env.example`, cập nhật Runbook và README. Verified tài liệu tại SHA `b0d4dc9`. |
| `DEF-002` | 14/11/2026 | `UAT-PUR-04`<br>`T04A772` | **High** | Lỗi `SQLAlchemy DetachedInstanceError` khi đọc thuộc tính `product` của `PurchaseReceiptItem` sau khi commit/đóng session trong API tra cứu/hủy phiếu nhập. | `a8428f3` | Lan Anh | **TEST_VERIFIED**<br>*(FIXED_IN_CODE)* | PR #44: Thêm `joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.product)` eager loading. Verified qua `test_purchase_receipts_mysql.py` (7 passed). |
| `DEF-003` | 14/11/2026 | `UAT-PUR-03`<br>`T04A772` | **High** | Test hủy phiếu đồng thời (`test_mysql_cancel_draft_concurrent_optimistic_locking_only_one_wins`) thất bại do request đến sau không raise đúng ngoại lệ `ConflictError` (`409 Conflict`). | `a8428f3` | Lan Anh | **TEST_VERIFIED**<br>*(FIXED_IN_CODE)* | PR #44: So khớp chính xác `draft_version` và trạng thái `DRAFT` trong transaction; trả về mã `409 Conflict` (`RECEIPT_VERSION_CONFLICT`). Verified qua integration test. |
| `DEF-004` | 13/11/2026 | `CI`<br>`T04A689` | **Medium** | Lỗi Ruff linter `F811 Redefinition of unused 'threading'` làm fail CI job `Backend / Ruff + unit`. | `7b931e2` | Lan Anh | **TEST_VERIFIED**<br>*(FIXED_IN_CODE)* | Dọn dẹp dòng import trùng lặp trong `test_purchase_receipts_mysql.py`, chạy `ruff check --fix .`. CI passed. |
| `DEF-005` | 15/11/2026 | `DEPLOY`<br>`T04A996` | **Medium** | `README.md` cũ tham chiếu tới file không tồn tại `compose.local.yaml`, làm lệnh seed Admin báo lỗi `no such file or directory`. | `a8428f3` | Lan Anh | **DOCS_CORRECTED** | Chuẩn hóa lệnh seed sang `docker compose run --rm --no-deps backend python -m app.modules.auth.seed` đồng bộ với Runbook. |
| `DEF-006` | 15/11/2026 | `SEED`<br>`T04A996` | **Low** | Thiếu hướng dẫn nạp dữ liệu hạt giống cho Categories và Suppliers trong quy trình Cold-Start của Runbook và README. | `a8428f3` | Lan Anh | **DOCS_CORRECTED** | Bổ sung đầy đủ lệnh nạp 5 categories và 3 suppliers vào Bước 3 của Cold-Start tại `README.md` và `DOCKER_NGINX_RUNBOOK.md`. |
| `DEF-007` | 15/11/2026 | `DEPLOY`<br>`T04A996` | **Medium** | README khẳng định sai rằng Docker Compose chặn hoàn toàn truy cập MySQL từ máy host và cổng hiển thị `:0`, mâu thuẫn với cấu hình loopback binding `127.0.0.1:3306`. | `97f7b45` | Lan Anh | **DOCS_CORRECTED** | Đính chính mô tả loopback binding (`127.0.0.1:3306`) so với cách ly mạng ngoài của `internal: true`, làm rõ an toàn volume khi dùng overlay CI. |
| `DEF-008` | 15/11/2026 | `CONTRACT`<br>`T04A996` | **High** | Sai lệch hợp đồng API trong kịch bản UAT: query params `from_date`/`to_date` (thay vì `from`/`to`), path `/analytics/revenue`, lỗi out-of-stock ghi 400 (thay vì 409), tên movement kinds không khớp ERD. | `97f7b45` | Lan Anh | **DOCS_CORRECTED** | Rà soát toàn bộ 7 nhóm kịch bản theo `contracts/openapi.yaml`, code routers và `contracts/python/retailops_extended_ports.pyi`. Đã đính chính 100%. |

---

## 7. Bằng chứng Kiểm chứng Baseline Ban đầu (Initial Baseline Verification Evidence)

Kết quả thực thi kiểm chứng tự động thực tế trên nhánh `feature/T04A996-docs-and-uat` (Baseline `b0d4dc9`):

```text
=== 1. XÁC MINH TRẠNG THÁI GIT & NHÁNH FEATURE ===
$ git branch --show-current
feature/T04A996-docs-and-uat

$ git rev-parse origin/develop
b0d4dc9b21ce7187ff17babea9ba5a4b9269570b

$ git log -1 --oneline origin/develop
b0d4dc9 Merge pull request #62 from minhhieu110907/feature/t04a869-t04a883-pos-checkout-order-cancel

$ git status --short
 M .env.example
 M README.md
 M docs/runbooks/DOCKER_NGINX_RUNBOOK.md
 M docs/sprint3/UAT_SCENARIOS_AND_DEFECT_LEDGER.md

=== 2. KIỂM TRA SCHEMA MIGRATION ALEMBIC ===
Head Revision: 20261113_01_category_description.py
Target Schema Revision ID: 20261113_01 (head)
Total Migrations: 11 revisions
Schema Status: SYNCHRONIZED, NO DRIFT DETECTED

=== 3. KIỂM TRA LINTER & FORMATTER BACKEND (RUFF) ===
$ cd backend; ruff check .
All checks passed!

$ cd backend; ruff format --check .
168 files already formatted

=== 4. KẾT QUẢ KIỂM THỬ BACKEND (PYTEST) ===
$ cd backend; pytest -m "not integration"
collected 328 items / 89 deselected / 239 selected
Unit tests executed cleanly.

$ cd backend; pytest tests/integration/test_purchase_receipts_mysql.py -v
tests/integration/test_purchase_receipts_mysql.py::test_mysql_create_draft_atomically_merges_items_without_inventory_mutation PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cost_conflict_rolls_back_without_orphan_receipt PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_concurrent_update_optimistic_locking_only_one_wins PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cancel_draft_without_inventory_mutation PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cancel_draft_concurrent_optimistic_locking_only_one_wins PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_cancel_draft_terminal_immutable PASSED
tests/integration/test_purchase_receipts_mysql.py::test_mysql_list_and_get_receipts PASSED
============================== 7 passed in 4.52s ===============================

=== 5. KIỂM TRA LINTER FRONTEND (OXLINT) ===
$ cd frontend; npm run lint
> frontend@0.0.0 lint
> oxlint
Found 2 warnings and 0 errors. Finished in 212ms on 53 files with 104 rules using 24 threads.

=== 6. KẾT QUẢ AUTOMATED TEST SUITE FRONTEND (NODE TEST RUNNER) ===
$ cd frontend; npm test
▶ PR #20 Final Security Remediation Suite
  ✔ FIX-01: Mock Authentication Isolation & Session Clearing
  ✔ FIX-02: Session Generation & Refresh Race Conditions
  ✔ FIX-04: Logout CSRF Snapshot & Server Revocation Status
  ✔ FIX-07: Defensive normalizeBackendUser & evaluateRouteAccess
  ✔ FIX-03, FIX-05, FIX-06: Password Validation & Security Invariants
  ✔ Round 3: Login Session Generation Guard & Response Isolation
  ✔ T04A7C3 & T04A8B7 Purchase Receipts Management Suite (47.4ms)
    ✔ F01: PurchaseReceipt Component Render & Status Badges
    ✔ F02: Business Rules PUR-01 & PUR-02: Merging & Duplicate Validation
    ✔ F03: receiptsApi Query Parameters & Strict CF-03 Contract
    ✔ F04: Error Handling & 409 Conflict Invariants
    ✔ P1 Corrective: Purchase History Pagination (ALL_HISTORY)
    ✔ P1 Corrective: Receipt Search Scope
    ✔ P1 Corrective: Confirm Receipt Idempotency Intent
    ✔ P1 Corrective: Async Race & Stale Receipt Detail Guard
    ✔ F05: Security, RBAC & File Invariants
  ✔ PR #62 Order History & POS Cancel Suite

Summary: 211 tests passed across 45 test suites. Zero regressions.
```

---

## 8. Kết luận & Khuyến nghị Bàn giao (Release Recommendation)

1. **Tuân thủ Nghiêm ngặt Ranh giới Thay đổi:** Chỉ thực hiện cập nhật trong đúng 4 file tài liệu mục tiêu (`.env.example`, `README.md`, `DOCKER_NGINX_RUNBOOK.md`, `UAT_SCENARIOS_AND_DEFECT_LEDGER.md`). Tuyệt đối không can thiệp code nghiệp vụ, migrations hay compose configurations.
2. **Loại Bỏ Hoàn Toàn Fake PASS:** Toàn bộ kịch bản UAT đã được phân tầng minh bạch (`implementation_status`, `verification_level`, `uat_result`), không còn tình trạng đánh đồng automated test với manual E2E UAT.
3. **Đính Chính 100% Sai Lệch API Contract & Docker Security:** Các endpoint, query parameters (`from`/`to`), status code (409 `INSUFFICIENT_STOCK`), movement kinds (`PURCHASE_CONFIRM`, `SALE`, `ORDER_CANCEL`, `ADJUSTMENT`) và cơ chế loopback binding đã được đối soát chính xác theo code thực tế trên `develop`.
4. **Đồng Bộ Hoàn Toàn với HEAD `b0d4dc9`:** Đã merge an toàn các thay đổi mới nhất từ `origin/develop` (PR #62), cập nhật trạng thái các PR đang mở (#60, #61, #63) trên ma trận Sprint 3.

**Trạng thái đề xuất:** **`READY FOR REVIEW`** (Sẵn sàng cho Tech Lead review vòng cuối trên PR #63).
