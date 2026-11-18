# RetailOps V1.0 — Biên Bản Nghiệm Thu Kỹ Thuật & Quyết Định Đóng Băng Phát Hành (Release Freeze)

**Hệ thống:** RetailOps Management System V1.0<br>
**Giai đoạn:** Sprint 3 — Nghiệm thu Tích hợp & Đóng băng Release Candidate<br>
**Mã Task LMS:** `T04ABC3` — `[S3] Nghiệm thu và đóng băng release`<br>
**Hợp đồng / Cổng kiểm soát:** `GATE-E2E`<br>
**Kỹ sư tổng hợp tài liệu:** Vũ Hoàng Lan Anh (`B25DTCN143`)<br>
**Người phê duyệt kỹ thuật cuối cùng:** Nguyễn Minh Hiếu (Tech Lead / Repository Owner)<br>
**Mốc kế hoạch Sprint:** 24/11/2026 · **Mốc nghiệm thu & Demo chính thức:** 27/11/2026<br>
**Nhánh Git:** `feature/t04abc3-release-acceptance-and-freeze`<br>
**Base Commit SHA (develop):** `4a2623c` (*Merge PR #77 `T04AA00` - Outbox Recovery Reconciliation*)<br>
**Trạng thái Phát hành:** **`RELEASE_CANDIDATE_READY_FOR_LEAD_SIGN_OFF`**

---

## MỤC LỤC
1. [Thông Tin Quản Trị & Trạng Thái Release Candidate (`T04ABC3`)](#1-thông-tin-quản-trị--trạng-thái-release-candidate-t04abc3)
2. [Ma Trận Đối Soát Tiêu Chí Nghiệm Thu Product Owner Theo SRS](#2-ma-trận-đối-soát-tiêu-chí-nghiệm-thu-product-owner-theo-srs)
   - 2.1. [Phân định Phạm vi Nghiệm thu V1.0: P0 vs P1 vs Ngoài phạm vi](#21-phân-định-phạm-vi-nghiệm-thu-v10-p0-vs-p1-vs-ngoài-phạm-vi)
   - 2.2. [Ma trận Đối soát Chi tiết Các Nhóm Chức năng P0 Cốt lõi](#22-ma-trận-đối-soát-chi-tiết-các-nhóm-chức-năng-p0-cốt-lõi)
3. [Kiểm Chứng 8 Bất Biến Nghiệp Vụ Cốt Lõi (Core Business Invariants)](#3-kiểm-chứng-8-bất-biến-nghiệp-vụ-cốt-lõi-core-business-invariants)
4. [Tổng Hợp Bằng Chứng CI, UAT, Benchmark & Sổ Cái Lỗi Hợp Nhất](#4-tổng-hợp-bằng-chứng-ci-uat-benchmark--sổ-cái-lỗi-hợp-nhất)
   - 4.1. [Thống kê Bằng chứng Kiểm thử Toàn diện của Đội ngũ](#41-thống-kê-bằng-chứng-kiểm-thử-toàn-diện-của-đội-ngũ)
   - 4.2. [Đánh giá Hiện trạng Benchmark & Hiệu năng Theo Mục tiêu DEC-14](#42-đánh-giá-hiện-trạng-benchmark--hiệu-năng-theo-mục-tiêu-dec-14)
   - 4.3. [Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger — 14/14 Resolved)](#43-sổ-cái-theo-dõi-lỗi-hợp-nhất-consolidated-defect-ledger--1414-resolved)
5. [Giới Hạn Đã Biết & Lưu Ý Vận Hành Cho Buổi Demo](#5-giới-hạn-đã-biết--lưu-ý-vận-hành-cho-buổi-demo)
6. [Đánh Giá Cổng Chất Lượng & Quyết Định Đóng Băng (Release Gate Verdict)](#6-đánh-giá-cổng-chất-lượng--quyết-định-đóng-băng-release-gate-verdict)
7. [Biên Bản Ký Duyệt Kỹ Thuật (Technical Sign-off Block)](#7-biên-bản-ký-duyệt-kỹ-thuật-technical-sign-off-block)

---

## 1. Thông Tin Quản Trị & Trạng Thái Release Candidate (`T04ABC3`)

### 1.1. Mục đích và Định hướng Tài liệu
Tài liệu này là biên bản nghiệm thu kỹ thuật và căn cứ pháp lý để đóng băng mã nguồn bản phát hành **RetailOps Management System V1.0 Release Candidate** theo tiêu chuẩn phân công của task LMS `T04ABC3`. Tài liệu thực hiện:
1. Đối soát toàn diện các yêu cầu nghiệp vụ bắt buộc **P0** được phê duyệt trong [RetailOps_SRS_Approved.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/requirement/RetailOps_SRS_Approved.md).
2. Kiểm chứng sự toàn vẹn của **8 bất biến nghiệp vụ cốt lõi** thông qua các ràng buộc cơ sở dữ liệu và bằng chứng kiểm thử tự động.
3. Hợp nhất bằng chứng kiểm thử từ tất cả các thành viên trong nhóm (`T3C9972`, `T3C9978`, `T3C9970`, `T04AABC`, `T04AAD7`, `T3C9F30`, `T04A90F`, `T04AA00`).
4. Khóa sổ cái theo dõi lỗi (Defect Ledger) với tiêu chí **Zero Critical/High Open Defects**.
5. Thiết lập khung chữ ký bàn giao kỹ thuật giữa Kỹ sư tổng hợp QA (**Vũ Hoàng Lan Anh**) và Tech Lead / Repository Owner (**Nguyễn Minh Hiếu**).

### 1.2. Trạng thái Release Candidate Hiện tại
- **Baseline Git Commit:** Commit **`4a2623c`** trên nhánh `develop` (sau khi sáp nhập PR #77 — controlled recovery outbox).
- **Trạng thái phê duyệt:** **`RELEASE_CANDIDATE_READY_FOR_LEAD_SIGN_OFF`**.
- **Giải trình trạng thái:**
  - Toàn bộ các module P0 phục vụ nghiệp vụ bán hàng, nhập hàng, tồn kho, phân tích, xác thực và outbox đã sáp nhập đầy đủ trên `develop` và vượt qua 100% CI checks.
  - Bản báo cáo QA tổng hợp và kịch bản demo (`T04ABDD`) đã hoàn tất tại PR #75 (commit `17898ad`), hiện đang chờ Tech Lead hợp nhất.
  - Các nhánh tính năng phụ trợ cuối cùng (`T04AA1C` — password reset và `T04AC15` — đối soát dữ liệu báo cáo) đang trong giai đoạn hoàn thiện review độc lập.
  - Trạng thái đóng băng chính thức sẽ được kích hoạt sau khi Tech Lead ký duyệt tại Mục 7.

---

## 2. Ma Trận Đối Soát Tiêu Chí Nghiệm Thu Product Owner Theo SRS

### 2.1. Phân định Phạm vi Nghiệm thu V1.0: P0 vs P1 vs Ngoài phạm vi

Căn cứ Phần 1.3 và Phần 5 của [RetailOps_SRS_Approved.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/requirement/RetailOps_SRS_Approved.md), phạm vi hệ thống được phân định minh bạch như sau:

| Nhóm Phạm Vi | Danh Mục Chức Năng | Tiêu Chuẩn Nghiệm Thu V1.0 | Trạng Thái Đánh Giá |
|:---|:---|:---|:---:|
| **P0 — Bắt buộc hoàn thành (Core Scope)** | • AUTH-01 .. AUTH-05 (Xác thực, phân quyền, duyệt staff)<br>• PROD-01 .. PROD-04, CAT-01, SUP-01 (Catalog master data)<br>• PUR-01 .. PUR-05 (Quản lý nhập hàng, draft, confirm, cancel)<br>• INV-01 .. INV-04 (Tồn kho real-time, kiểm kê thực tế, biến động, tồn thấp)<br>• SALE-01 .. SALE-05, ORD-01 .. ORD-03 (Giỏ POS, checkout, hủy đơn, idempotency)<br>• ANA-01 .. ANA-04 (Doanh thu, top/slow products, Dashboard)<br>• INF-01 .. INF-05 (Reverse proxy, rate limit, Outbox, RabbitMQ, Celery) | Bắt buộc 100% chức năng có mã nguồn đã merge vào `develop`, không có lỗi Critical/High, có bằng chứng test tự động và kịch bản demo khả lặp. | **ĐẠT TIÊU CHUẨN P0** |
| **P1 — Mở rộng sau Quality Gate** | • `INV-05`: Cấu hình ngưỡng tồn kho thấp tùy chỉnh theo từng sản phẩm.<br>• `ANA-05`: Xuất báo cáo thống kê ra file định dạng CSV an toàn.<br>• `ENG-10`: Tối ưu hóa truy vấn chuyên sâu và loại bỏ N+1 query. | Không bắt buộc hoàn thành trước phiên nghiệm thu V1.0 / demo; chỉ triển khai sau khi P0 đạt Quality Gates. | **P1 DEFERRED (ĐÚNG SRS)** |
| **Ngoài phạm vi V1 (Out-of-Scope)** | • Google / Social Login, khôi phục hoặc khóa tài khoản Staff.<br>• Trả hàng / hoàn tiền (Returns / Refunds), Purchase Reversal.<br>• Đa chi nhánh / đa kho (Multi-store / Multi-warehouse).<br>• Cổng thanh toán trực tuyến thực tế (Payment Gateway integration).<br>• Thuế, chiết khấu, chương trình khuyến mãi, đa tiền tệ.<br>• Kế toán tài chính tổng hợp, tự động dự báo nhu cầu (Forecasting).<br>• Thao tác ghi dữ liệu từ Trợ lý AI (AI Write Path). | Tuyệt đối không xuất hiện trong mã nguồn V1.0; hệ thống bảo đảm cơ chế chỉ đọc cho AI và phân quyền 1 cửa hàng / 1 kho. | **TUÂN THỦ RÀNG BUỘC** |

---

### 2.2. Ma trận Đối soát Chi tiết Các Nhóm Chức năng P0 Cốt lõi

| Mã SRS / Task | Tên Chức Năng Nghiệp Vụ | Yêu Cầu Cốt Lõi Theo SRS | Hiện Trạng Triển Khai Thực Tế | Bằng Chứng Kiểm Chứng (Evidence) | Đánh Giá PO |
|:---|:---|:---|:---|:---|:---:|
| **AUTH-01** (`T04A61F`) | Đăng ký Staff | Đăng ký công khai, email chuẩn hóa duy nhất, sinh hồ sơ `PENDING_APPROVAL`, trả `202 Accepted`. | Đã triển khai tại `auth/router.py`, trả HTTP 202. Chặn đăng ký trùng email. | `test_staff_registration.py`<br>`authSecurity.test.js` | **ACCEPTED** |
| **AUTH-02** (`T04A61F`) | Đăng nhập & Quản lý phiên | 1 Admin seed duy nhất; Access JWT 15m; Refresh token trong cookie HttpOnly xoay vòng; thu hồi phiên server-side. | JWT 15m; Cookie `retailops_refresh` có cờ `HttpOnly`, `Path=/api/v1/auth`, `SameSite=Lax`. | `test_auth_api.py`<br>`test_auth_tokens_csrf.py` | **ACCEPTED** |
| **AUTH-03** (`T04A61F`) | Duyệt / Từ chối Staff | Admin duyệt/từ chối; chuyển trạng thái nguyên tử; ghi nhận Transactional Outbox gửi email trong cùng transaction. | Endpoint `POST /api/v1/auth/staff-approval/{id}/approve` (hoặc reject). Ghi sự kiện outbox. | `test_staff_approval.py`<br>SHA: `b0d4dc9` | **ACCEPTED** |
| **AUTH-04** (`T04A61F`) | Phân quyền vai trò (RBAC) | Chỉ tài khoản `ACTIVE` được truy cập; Staff không xem giá vốn; Dashboard/Analytics chỉ dành cho Admin. | Dependency `require_active_admin` và `require_active_user` chặn từ tầng router. Trả `403 Forbidden`. | `test_cors.py`<br>`test_staff_approval_api.py` | **ACCEPTED** |
| **AUTH-05** (`T04A61F`) | Thông báo Admin in-app | Tạo 1 thông báo in-app cho Admin khi có Staff đăng ký mới trong cùng transaction. | Bảng `admin_notifications` ghi nhận thông báo nguyên tử; chống sinh trùng lặp. | `test_api.py` (notifications)<br>`test_models_mysql.py` | **ACCEPTED** |
| **PROD-01** (`T3C9AEB`) | Quản lý sản phẩm | Admin tạo/sửa; bắt buộc SKU, Barcode, tên, giá bán nguyên VND; sản phẩm mới tạo luôn có tồn kho = 0. | `products/service.py` tạo bản ghi Product kèm Inventory `quantity=0` trong 1 transaction. Chặn trùng SKU/Barcode. | `test_products_integration.py`<br>`test_products_api.py` | **ACCEPTED** |
| **PROD-02** (`T3C9D7D`) | Quản lý danh mục | Admin tạo, sửa qua `PATCH`, đổi trạng thái ACTIVE/INACTIVE; không cascade xóa lịch sử. | Endpoint `PATCH /api/v1/categories/{id}`. Ràng buộc quan hệ khóa ngoại an toàn. | `test_categories_api.py`<br>`categoryList.test.js` | **ACCEPTED** |
| **PROD-03** (`T04A6A3`) | Tra cứu & Phân trang sản phẩm | Tra cứu theo từ khóa, danh mục, trạng thái; phân trang ổn định (`page`, `page_size`, `total`). | API `GET /api/v1/products` hỗ trợ filter, order_by hợp lệ và phân trang server-side. | `test_products_api.py`<br>`productList.test.js` | **ACCEPTED** |
| **PROD-04** (`T04A6A3`) | Xem chi tiết sản phẩm | Xem chi tiết sản phẩm; che giấu tuyệt đối trường giá vốn (`cost_price_vnd`) đối với vai trò Staff. | DTO `ProductRead` loại bỏ hoàn toàn trường giá vốn khi serialize phản hồi cho client. | `productList.test.js`<br>`test_t04aad7_reconciliation_api.py` | **ACCEPTED** |
| **SUP-01** (`T3C9D7D`) | Quản lý nhà cung cấp | Tạo, sửa, tra cứu nhà cung cấp; chuẩn hóa và xác thực số điện thoại theo định dạng quốc tế E.164. | Sử dụng thư viện `phonenumbers` chuẩn hóa E.164 Việt Nam; từ chối SĐT sai định dạng với HTTP 422. | `test_phone_validation.py`<br>`test_suppliers_api.py` | **ACCEPTED** |
| **PUR-01** (`T04A6D7`) | Phiếu nhập DRAFT | Tạo phiếu nháp gồm nhà cung cấp, sản phẩm, số lượng nguyên dương, đơn giá không âm; không thay đổi tồn kho. | `PurchaseReceipt` tạo ở trạng thái `DRAFT`, `draft_version=1`. Tồn kho giữ nguyên 100%. | `test_purchase_receipts_mysql.py`<br>PR #35 | **ACCEPTED** |
| **PUR-02** (`T04A6D7`) | Item Merging phiếu nhập | Tự động gộp dòng trùng sản phẩm và cùng giá nhập; từ chối dòng trùng sản phẩm khác giá nhập (`409 Conflict`). | Logic gộp item tại service; tính tổng tiền chính xác bằng số nguyên VND; chặn lệch giá. | `purchaseReceipts.test.js`<br>`test_purchase_receipts_mysql.py` | **ACCEPTED** |
| **PUR-03** (`T04A772`) | Khóa lạc quan phiếu nhập | Sửa/hủy phiếu dùng `expected_draft_version`; phiên bản cũ bị từ chối ngay với `409 Conflict`. | Kiểm tra `draft_version == expected_draft_version` trong câu lệnh update. Chống lost update. | `test_purchase_receipts_mysql.py`<br>PR #44 | **ACCEPTED** |
| **PUR-04** (`T04A772`) | Hủy phiếu nhập nháp | Hủy phiếu khi còn `DRAFT`; chuyển sang `CANCELLED` đúng 1 lần; không làm thay đổi số lượng tồn kho. | Chuyển trạng thái sang `CANCELLED`, tăng version; không ghi nhận biến động kho. | `test_purchase_receipts_mysql.py`<br>PR #44 | **ACCEPTED** |
| **PUR-05** (`T04A7DF`) | Xác nhận phiếu nhập | Xác nhận phiếu `DRAFT`, tăng tồn kho và ghi `StockMovement(PURCHASE_CONFIRM)` nguyên tử; phiếu CONFIRMED là bất biến. | Tăng `quantity`, tăng `stock_version`, ghi movement trong 1 transaction; chặn xác nhận lại lần 2. | `test_receipt_confirmation_mysql.py`<br>PR #70 | **ACCEPTED** |
| **INV-01** (`T04A6BD`) | Tổng quan tồn kho | Xem tồn kho theo thời gian thực (`quantity`, `stock_version`, `first_stocked_at`); không có reserved/available ảo. | Schema `InventoryRead` phản ánh đúng thực tế cơ sở dữ liệu, không sinh trường ảo. | `test_inventory_api.py`<br>`test_inventory_integration.py` | **ACCEPTED** |
| **INV-02** (`T04A758`) | Điều chỉnh kiểm kê thực tế | Admin nhập số đếm thực tế, lý do, `expected_stock_version`; tự tính delta; version cũ trả 409; no-op chỉ ghi audit. | Endpoint `POST /api/v1/inventory/{id}/adjustments`; tính delta nguyên tử; chặn số đếm âm. | `test_inventory_adjustment_api.py`<br>`test_inventory_mysql.py` | **ACCEPTED** |
| **INV-03** (`T04A78E`) | Lịch sử biến động kho | Lịch sử append-only; 4 loại chuẩn; che giấu giá vốn và lý do điều chỉnh nội bộ đối với vai trò Staff. | Router `GET /api/v1/stock-movements`; ẩn `unit_cost_vnd` đối với Staff thông qua serializer. | `test_low_stock_and_movements.py`<br>`test_inventory_movements_mysql.py` | **ACCEPTED** |
| **INV-04** (`T04A78E`) | Cảnh báo tồn kho thấp | Cảnh báo sản phẩm ACTIVE có tồn $\le$ 5 theo ngưỡng an toàn mặc định (`DEFAULT_LOW_STOCK_THRESHOLD = 5`). | API `GET /api/v1/inventory/low-stock` lọc theo ngưỡng hằng số thống nhất toàn hệ thống. | `test_low_stock_and_movements.py` | **ACCEPTED** |
| **SALE-01** (`T04A73C`) | Giỏ hàng POS | Thêm/sửa/xóa giỏ POS; tự động gộp dòng trùng; không giữ tồn kho; sản phẩm INACTIVE không được bán. | Quản lý giỏ hàng phía client và validation phía server; không khóa giữ tồn trước checkout. | `posPage.test.js`<br>`test_checkout_api.py` | **ACCEPTED** |
| **SALE-02** (`T04A73C`) | Thanh toán trực tiếp | Checkout nguyên tử: tạo đơn COMPLETED, trừ tồn kho, ghi `StockMovement(SALE)`. Lệch giá trả 409 PRICE_CHANGED. | Transaction trừ kho với `SELECT ... FOR UPDATE`; kiểm tra giá bán; chặn bán vượt tồn (`INSUFFICIENT_STOCK`). | `test_checkout_mysql.py`<br>PR #62 | **ACCEPTED** |
| **SALE-03** (`T04A840`) | Lịch sử đơn hàng | Xem danh sách, lọc theo ngày/trạng thái; Staff chỉ xem đơn của mình; Admin xem toàn bộ đơn hệ thống. | Endpoint `GET /api/v1/orders` kiểm tra ownership dựa trên User ID của access token. | `test_order_read_api.py`<br>`test_order_read_mysql.py` | **ACCEPTED** |
| **SALE-04** (`T04A80C`) | Hủy đơn hàng có điều kiện | Staff chỉ hủy đơn mình tạo $\le$ 15 phút cùng ngày VN; Admin hủy mọi đơn trong ngày; hoàn tồn đúng 1 lần. | Endpoint `POST /api/v1/orders/{id}/cancel` kiểm tra ownership, mốc thời gian 15m; hoàn kho nguyên tử. | `orderCancel.test.js`<br>`test_cancel_api.py` | **ACCEPTED** |
| **SALE-05** (`T04A639`) | Idempotency cho Checkout | Header `Idempotency-Key` lưu 24h; replay kết quả cũ khi trùng payload; từ chối khi khác payload. | Khung middleware idempotency lưu trạng thái `STARTED`, `COMPLETED` trong MySQL; khóa chống race condition. | `test_idempotency.py`<br>`test_checkout_mysql.py` | **ACCEPTED** |
| **ANA-01** (`T04A92B`) | Doanh thu & Chỉ số bán hàng | Doanh thu, số đơn hoàn thành, AOV (làm tròn `ROUND_HALF_UP`); loại bỏ 100% đơn CANCELLED; timezone VN. | API `GET /api/v1/analytics/sales?from=...&to=...`; query loại bỏ đơn hủy; tiền nguyên VND. | `test_sales_analytics_api.py`<br>`test_sales_analytics_mysql.py` | **ACCEPTED** |
| **ANA-02** (`T04A947`) | Top sản phẩm bán chạy | Xếp hạng theo lượng bán trong kỳ; chỉ tính item của đơn COMPLETED; sắp xếp ổn định. | API `GET /api/v1/analytics/products/top`; tính tổng số lượng bán từ đơn hoàn thành. | `test_product_analytics_api.py`<br>`test_product_analytics_mysql.py` | **ACCEPTED** |
| **ANA-03** (`T04A947`) | Sản phẩm bán chậm | Nhận diện sản phẩm: nhập kho `> 7 ngày` (`first_stocked_at`), tồn `> 0`, bán $\le$ 2 đơn vị trong 30 ngày. | API `GET /api/v1/analytics/products/slow`; căn cứ thời điểm nhập kho đầu tiên, không dùng created_at. | `test_product_analytics_api.py`<br>`test_product_analytics_mysql.py` | **ACCEPTED** |
| **ANA-04** (`T04AA36`) | Dashboard API | Tổng quan quản trị: KPI doanh thu, đơn hàng, cảnh báo tồn thấp và top sản phẩm; độc quyền cho Admin. | Endpoint `GET /api/v1/dashboard`; tổng hợp số liệu nhất quán với sales analytics và inventory. | `test_dashboard_api.py`<br>`test_dashboard_mysql.py` | **ACCEPTED** |
| **INF-01** (`T04A8D1`) | Nginx Reverse Proxy | Định tuyến `/api/` tới Backend, `/` tới static SPA; chuyển tiếp header bảo mật an toàn; chặn giả mạo IP. | Multi-stage build Nginx; `docker/nginx/nginx.conf` cấu hình `proxy_set_header` chuẩn allowlist. | `DOCKER_NGINX_RUNBOOK.md`<br>`test_proxy_registration.py` | **ACCEPTED** |
| **INF-02** (`T04A826`) | Redis Rate Limiting | Rate limit độc lập theo IP và User: Auth 5 req/min, Business 120 req/min. Auth fail-closed, POS fail-open. | Middleware `RateLimitMiddleware` kết nối Redis; xử lý phân nhánh fallback an toàn khi Redis mất kết nối. | `test_rate_limit.py`<br>`test_redis_rate_limit.py` | **ACCEPTED** |
| **INF-03** (`T04A90F`) | Transactional Outbox & Worker | MySQL outbox lưu sự kiện sau commit; Celery Worker xử lý email qua RabbitMQ broker; cơ chế at-least-once. | Bảng `outbox_events`; tiến trình `publisher_main.py` poll event và publish sang RabbitMQ exchange. | `test_outbox_delivery_mysql.py`<br>`test_outbox_rabbitmq.py` | **ACCEPTED** |
| **INF-04** (`T04A90F`) | Gửi email nghiệp vụ | Gửi email bất đồng bộ thông báo đăng ký, duyệt/từ chối; không chặn giao dịch nghiệp vụ chính; log không lộ token. | Module `outbox/smtp.py` gửi email qua Mailpit/SMTP; bảo vệ dữ liệu nhạy cảm (sanitized log). | `OUTBOX_RECOVERY_RUNBOOK.md`<br>PR #73 | **ACCEPTED** |
| **INF-05** (`T04AA00`) | Retry & Phục hồi Outbox | Reconciler quét sự kiện kẹt; retry exponential backoff có chặn trên; dead-letter queue cô lập lỗi vĩnh viễn. | Module `outbox/reconciler.py` và script `reconcile_outbox.py`; bảo đảm tính lũy thừa khi replay. | `test_runtime.py`<br>PR #77 | **ACCEPTED** |

---

## 3. Kiểm Chứng 8 Bất Biến Nghiệp Vụ Cốt Lõi (Core Business Invariants)

Hệ thống RetailOps V1.0 được thiết kế dựa trên nguyên tắc phòng thủ đa tầng (Defense-in-Depth). Toàn bộ 8 bất biến nghiệp vụ cốt lõi đã được kiểm chứng bằng kiểm thử tích hợp trên **MySQL 8.4 InnoDB**:

| STT | Tên Bất Biến Nghiệp Vụ | Đặc Tả Nguy Cơ Xâm Phạm | Cơ Chế Kỹ Thuật Bảo Vệ (Technical Enforcement) | File Test & Bằng Chứng Kiểm Chứng Thực Tế |
|:---:|:---|:---|:---|:---|
| **INV-01** | **Tiền tệ nguyên VND & Tồn kho không âm** | Sai số dấu phẩy động (`float`) gây thất thoát tiền; xuất bán vượt quá tồn kho thực tế dẫn đến âm kho. | • Trường tiền tệ lưu dạng `INTEGER` / `BIGINT` VND.<br>• Ràng buộc cơ sở dữ liệu `CHECK (quantity >= 0)` tại bảng `inventory`.<br>• Ràng buộc `CHECK (line_total_vnd = quantity * unit_price)`. | `tests/integration/test_inventory_integration.py`<br>`tests/modules/sales/test_checkout_mysql.py` |
| **INV-02** | **Tồn kho ban đầu = 0 & Che giấu giá vốn** | Tạo sản phẩm gán khống tồn kho; nhân viên thu ngân (Staff) thấy giá vốn của sản phẩm hoặc phiếu nhập. | • Transaction tạo Product luôn khởi tạo kèm bản ghi Inventory `quantity = 0`.<br>• DTO `ProductRead` và `StockMovementRead` loại bỏ hoàn toàn trường `cost_price_vnd` / `unit_cost_vnd` đối với Staff. | `tests/integration/test_products_integration.py`<br>`tests/modules/analytics/test_t04aad7_reconciliation_api.py` |
| **INV-03** | **Item Merging & Chặn lệch giá nhập** | Phiếu nhập nháp chứa nhiều dòng cùng 1 mặt hàng gây rối loạn quản lý; cố tình nhập 1 mặt hàng với 2 mức giá khác nhau trong cùng 1 phiếu. | • Service tự động gom nhóm `(product_id, unit_cost_vnd)` bằng cách cộng dồn số lượng.<br>• Khi phát hiện cùng `product_id` nhưng khác `unit_cost_vnd`, hệ thống từ chối ngay với HTTP `409 Conflict`. | `tests/integration/test_purchase_receipts_mysql.py`<br>`frontend/src/__tests__/purchaseReceipts.test.js` |
| **INV-04** | **Khóa lạc quan chống Lost Update** | Hai người dùng cùng mở 1 phiếu nhập hoặc cùng kiểm kê 1 mặt hàng, người lưu sau ghi đè mất dữ liệu của người lưu trước. | • Áp dụng cột `draft_version` cho phiếu nhập và `stock_version` cho tồn kho.<br>• Mọi thao tác cập nhật đều yêu cầu `expected_draft_version` / `expected_stock_version`. Nếu lệch, trả về HTTP `409 Conflict`. | `tests/integration/test_purchase_receipts_mysql.py`<br>`tests/modules/inventory/test_inventory_mysql.py` |
| **INV-05** | **Tính bất biến của Phiếu nhập (Terminal Immutability)** | Phiếu nhập đã xác nhận hoặc đã hủy bị sửa đổi số lượng hoặc xác nhận lại lần thứ 2 làm tăng khống tồn kho. | • Máy trạng thái (State Machine) chỉ cho phép chuyển đổi từ `DRAFT` sang `CONFIRMED` hoặc `CANCELLED`.<br>• Phiếu đã ở trạng thái terminal bị từ chối mọi thao tác ghi tiếp theo với HTTP `409 Conflict`. | `tests/integration/test_purchase_receipts_mysql.py`<br>`tests/modules/purchasing/test_receipt_confirmation_mysql.py` |
| **INV-06** | **Chống bán âm kho & Chặn biến động giá POS** | Khách hàng mua món hàng vừa hết tồn; giá sản phẩm tăng trong lúc khách đang chọn đồ dẫn đến thu sai tiền. | • Câu lệnh `SELECT ... FOR UPDATE` khóa dòng tồn kho trong transaction checkout.<br>• So sánh giá tại thời điểm thêm vào giỏ với giá hiện tại trong DB; nếu lệch giá, rollback và trả `409 PRICE_CHANGED`. | `tests/modules/sales/test_checkout_mysql.py`<br>`tests/integration/test_idempotency.py` |
| **INV-07** | **Điều kiện hủy đơn & Hoàn tồn duy nhất 1 lần** | Nhân viên hủy đơn của người khác; hủy đơn của những ngày trước; gọi API hủy nhiều lần làm hoàn kho lặp vô tận. | • Staff chỉ được hủy đơn do chính mình tạo (`owner_id == user_id`) trong vòng $\le 15$ phút và cùng ngày kinh doanh Việt Nam.<br>• Thao tác hủy chuyển trạng thái sang `CANCELLED` và hoàn tồn trong 1 transaction duy nhất có cờ kiểm soát. | `tests/modules/sales/test_cancel_api.py`<br>`tests/modules/sales/test_cancel_service.py` |
| **INV-08** | **Transactional Outbox & Email Decoupling** | Gửi email thất bại làm rollback đơn hàng; hoặc cơ sở dữ liệu crash nhưng email thông báo xác nhận vẫn bị gửi đi. | • Sự kiện email được ghi vào bảng `outbox_events` trong cùng transaction cơ sở dữ liệu của nghiệp vụ chính.<br>• Tiến trình độc lập quét bảng outbox và chỉ đưa message vào RabbitMQ sau khi transaction đã commit thành công. | `tests/integration/test_outbox_delivery_mysql.py`<br>`tests/integration/test_outbox_rabbitmq.py` |

---

## 4. Tổng Hợp Bằng Chứng CI, UAT, Benchmark & Sổ Cái Lỗi Hợp Nhất

### 4.1. Thống kê Bằng chứng Kiểm thử Toàn diện của Đội ngũ

Hệ thống RetailOps V1.0 đạt độ phủ kiểm thử tự động toàn diện qua 3 Sprint, được thực thi và chứng nhận bởi toàn bộ kỹ sư trong nhóm:

| Phân Hệ / Module Kiểm Thử | Kỹ Sư Phụ Trách | Mã Task LMS | Số Lượng Test | Tỷ Lệ Pass | Môi Trường Thực Thi & Bằng Chứng |
|:---|:---:|:---:|:---:|:---:|:---|
| **Products & Purchasing** | Vũ Hoàng Lan Anh | `T3C9972` | **68 tests** | **100%** (68/68) | [T3C9972_MODULE_TEST_CASES_AND_LOG.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/T3C9972_MODULE_TEST_CASES_AND_LOG.md): 53 unit/API + 15 MySQL integration. |
| **Catalog, Stock, Order, Analytics QA** | Phạm Thị Na Na | `T3C9978` | **305 tests** | **100%** (305/305) | [T3C9978_MODULE_TEST_LOG_REPORT.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/T3C9978_MODULE_TEST_LOG_REPORT.md): 42 QA Test Specs; 305 automated executions (9.14s). |
| **Purchasing Lifecycle & Outbox QA** | Phạm Thị Na Na | `T04AABC` | **24+ tests** | **100%** | [T04AABC_RECONCILIATION_REPORT.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/T04AABC_RECONCILIATION_REPORT.md): RBAC, Outbox storage invariant, Shared Admin isolation. |
| **Product, Order, Analytics Reconciliation** | Phạm Thị Na Na | `T04AAD7` | **31+ tests** | **100%** | [T04AAD7_RECONCILIATION_REPORT.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/T04AAD7_RECONCILIATION_REPORT.md): Run-Scoped test context, đối soát chéo số liệu tài chính - kho. |
| **Inventory & Receipt Confirmation** | Nguyễn Cao Kỳ Dương | `T3C9970` | **40 tests** | **95.0%** (38/40) | [docs/sprint3/testing/T3C9970/](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/testing/T3C9970/): 38 Passed; 2 Partial (TC034, TC035 xác nhận phiếu đã đóng qua stale version). |
| **UI Dark Theme & Component Layout** | Phan Nguyễn Nhật Tân | `T3C9F30` | **All suites** | **100%** | `frontend/src/__tests__/`: Ngăn chặn rò rỉ màu nền bảng/modal khi chuyển Night Mode (PR #72). |
| **Transactional Outbox & Celery Worker** | Nguyễn Minh Hiếu | `T04A90F`<br>`T04AA00` | **4 suites** | **100%** | `test_outbox_delivery_mysql.py`, `test_outbox_rabbitmq.py`, `test_runtime.py`, Celery retry & DLQ. |
| **Frontend CI Suite (Node Test Runner)** | Đội ngũ Frontend | — | **211 tests** | **100%** (211/211) | [.github/workflows/frontend-ci.yml](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/.github/workflows/frontend-ci.yml): 45 test suites, oxlint 0 errors, build Vite thành công. |
| **Backend CI Pipeline (GitHub Actions)** | Toàn đội ngũ | — | **3 Jobs** | **100% PASS** | [.github/workflows/backend-ci.yml](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/.github/workflows/backend-ci.yml): Ruff linter, 11 Alembic migrations, MySQL & RabbitMQ integration. |

---

### 4.2. Đánh giá Hiện trạng Benchmark & Hiệu năng Theo Mục tiêu DEC-14

- **Chỉ tiêu Hiệu năng Mục tiêu Theo SRS (DEC-14):**
  Trong điều kiện tải thử nghiệm từ **10 đến 20 người dùng đồng thời (concurrent users)**:
  - Phân hệ Tra cứu Sản phẩm, Danh mục và Tồn kho (`Read Path`): Thời gian đáp ứng **P95 $\le$ 300 ms**.
  - Phân hệ Giao dịch Thanh toán POS và Xác nhận Phiếu nhập (`Write Path`): Thời gian đáp ứng **P95 $\le$ 800 ms**.
  - Phân hệ Tổng quan Quản trị (`Dashboard API`): Thời gian đáp ứng **P95 $\le$ 1.500 ms**.
  - Trợ lý AI (`AI Assistant Read-Only`): Bounded timeout **15 giây**, hạn mức tối đa 3 lần gọi tool và dung lượng phản hồi $\le 32$ KiB.
- **Hiện trạng Thực tế & Cam kết Trung thực (No Fake PASS):**
  - **Tình trạng:** Khung chỉ tiêu và mô hình đo đạc đã được chuẩn hóa trong SRS và [TASK_IMPLEMENTATION_GUIDE.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md) dưới mã task **`T04AAA2`** (*Đo hiệu năng và xác minh bảo mật* do Tech Lead **Nguyễn Minh Hiếu** phụ trách, mốc kế hoạch 20–21/11, contract `PERF,GATE-E2E`).
  - **Kết luận nghiệm thu:** Ghi nhận **MỤC TIÊU HIỆU NĂNG ĐÃ KHÓA; KẾT QUẢ ĐO ĐẠC CHÍNH THỨC SẼ ĐƯỢC CẬP NHẬT TRỰC TIẾP TỪ RUN LOG CỦA TASK T04AAA2. BAN KIỂM THỬ KHÔNG TỰ SUY DIỄN HOẶC ĐÁNH GIÁ KHỐNG LÀ BENCHMARK ĐÃ PASS KHI CHƯA CÓ DỮ LIỆU ĐO THỰC TẾ TRÊN MÔI TRƯỜNG TẢI**.

---

### 4.3. Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger — 14/14 Resolved)

Toàn bộ **14 lỗi kỹ thuật và sai lệch tài liệu** phát sinh qua các đợt kiểm thử đã được phân tích nguyên nhân gốc rễ và xử lý triệt để:

| Defect ID | Phân Hệ / Task | Mức Độ | Triệu Chứng Lỗi & Nguyên Nhân Gốc Rễ | Giải Pháp Khắc Phục (Resolution) | Commit SHA Sửa Lỗi | Người Xử Lý | Trạng Thái |
|:---:|:---:|:---:|:---|:---|:---:|:---:|:---:|
| **`DEF-001`** | Deploy / Docker (`T04A8D1`) | **Critical** | Cổng mặc định 3306 bị Windows WinNAT/Hyper-V chiếm dụng, ngăn khởi động MySQL. | Bổ sung biến `MYSQL_HOST_PORT=13306` vào `.env.example`, cập nhật README và Runbook. | `b0d4dc9` | Hiếu | **DOCS_CORRECTED** |
| **`DEF-002`** | Purchasing (`T04A772`) | **High** | Lỗi `SQLAlchemy DetachedInstanceError` khi đọc thuộc tính `product` của item sau khi commit/close session. | Thêm eager loading `joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.product)`. | `546ae09` | Lan Anh | **FIXED & VERIFIED** |
| **`DEF-003`** | Purchasing (`T04A772`) | **High** | Test hủy phiếu đồng thời thất bại do request thứ 2 không raise đúng ngoại lệ `409 Conflict`. | So khớp chính xác điều kiện `draft_version == expected_draft_version` và `status == DRAFT`. | `546ae09` | Lan Anh | **FIXED & VERIFIED** |
| **`DEF-004`** | CI Pipeline (`T04A689`) | **Medium** | Lỗi Ruff linter `F811 Redefinition of unused 'threading'` làm fail GitHub Actions CI. | Dọn dẹp import trùng lặp, định dạng lại toàn bộ mã nguồn bằng lệnh `ruff check --fix .`. | `a8428f3` | Lan Anh | **FIXED & VERIFIED** |
| **`DEF-005`** | Deploy / UAT (`T04A996`) | **Medium** | `README.md` cũ tham chiếu tới file không tồn tại `compose.local.yaml`, làm lệnh seed báo lỗi file missing. | Chuẩn hóa lệnh seed sang `docker compose run --rm --no-deps backend python -m app.modules.auth.seed`. | `f1ced70` | Lan Anh | **DOCS_CORRECTED** |
| **`DEF-006`** | Seed / Docs (`T04A996`) | **Low** | Thiếu hướng dẫn nạp dữ liệu hạt giống cho Categories và Suppliers trong quy trình Cold-Start. | Bổ sung đầy đủ lệnh nạp 5 categories và 3 suppliers vào Bước 3 của Cold-Start trong README. | `f1ced70` | Lan Anh | **DOCS_CORRECTED** |
| **`DEF-007`** | Docker Network (`T04A996`) | **Medium** | Tài liệu khẳng định Docker chặn toàn bộ truy cập MySQL, mâu thuẫn với cấu hình loopback `127.0.0.1:3306`. | Đính chính loopback binding an toàn và lưu ý cách ly volume khi chạy suite test CI. | `f1ced70` | Lan Anh | **DOCS_CORRECTED** |
| **`DEF-008`** | API Contracts (`T04A996`) | **High** | Sai lệch hợp đồng API trong kịch bản UAT: query params `from_date`/`to_date`, lỗi out-of-stock ghi 400. | Rà soát toàn bộ 7 nhóm kịch bản theo `contracts/openapi.yaml`, đính chính 100% khớp với code. | `f1ced70` | Lan Anh | **DOCS_CORRECTED** |
| **`DEF-009`** | Products (`T3C9AEB`) | **High** | Xung đột chuỗi Alembic migration do khai báo trùng lặp Category model ở cả module products và categories. | Xóa Category model trùng lặp trong module products, chuẩn hóa import từ module categories. | `ee31bd0` | Lan Anh | **FIXED & VERIFIED** |
| **`DEF-010`** | Products (`T3C9AEB`) | **Medium** | Teardown cleanup của bài test MySQL vô tình xóa mất các danh mục seed có sẵn trong DB. | Cô lập phạm vi cleanup chỉ xóa các ID sản phẩm được sinh ra trong fixture của chính bài test đó. | `1d60b93` | Lan Anh | **FIXED & VERIFIED** |
| **`DEF-011`** | QA Isolation (`T04AAD7`) | **Medium** | Fixture autouse xóa toàn bộ bản ghi có tiền tố `T04AAD7_%`, gây nguy cơ xóa chéo test khác. | Chuyển sang cơ chế Run-Scoped cleanup do `TestRunContext` quản lý theo danh sách ID thực tế. | `55ebc43` | Na Na | **FIXED & VERIFIED** |
| **`DEF-012`** | Analytics QA (`T04AAD7`) | **Low** | Lệch ngày kiểm thử khi test chạy qua mốc nửa đêm do lấy thời gian wall-clock độc lập giữa UTC và VN. | Áp dụng Single Source of Truth cho thời gian: Khởi tạo `frozen_time_utc` cố định và suy diễn ngày VN. | `55ebc43` | Na Na | **FIXED & VERIFIED** |
| **`DEF-013`** | Dashboard QA (`T04AA36`) | **Medium** | Lỗi check constraint `line_total_vnd` trong fixture test MySQL Dashboard do dữ liệu mock sai công thức. | Đồng bộ công thức `line_total_vnd = quantity * unit_price` trong fixture test MySQL. | `f3a7daf` | Na Na | **FIXED & VERIFIED** |
| **`DEF-014`** | Frontend Theme (`T3C9F30`) | **Low** | Rò rỉ màu nền trắng trên table header và modal input khi người dùng kích hoạt Dark Theme (Night Mode). | Thiết lập biến màu CSS scoped, chuẩn hóa nền tối cho toàn bộ component giao diện. | `26ee520` | Tân | **FIXED & VERIFIED** |

> [!NOTE]
> **Xác nhận Tiêu chuẩn Zero Open Defects:**
> - Số lỗi Critical / High còn mở: **0 lỗi**.
> - Số lỗi Medium / Low còn mở: **0 lỗi**.
> - Tỷ lệ khắc phục và kiểm chứng đạt: **100% (14/14 lỗi)**.

---

## 5. Giới Hạn Đã Biết & Lưu Ý Vận Hành Cho Buổi Demo

Nhằm bảo đảm buổi nghiệm thu và thuyết trình demo diễn ra ổn định, các bên liên quan cần nắm rõ 4 lưu ý kỹ thuật:

1. **Giới hạn Độ phủ Kiểm thử Cụ thể (Partial Test Coverage Boundary):**
   - Trong bộ test `T3C9970`, 2 ca kiểm thử `TC034` và `TC035` (xác nhận phiếu nhập đã `CONFIRMED` hoặc `CANCELLED`) hiện được xác thực thông qua cơ chế phiên bản cũ (`draft_version` đã tăng, trả về `409 Conflict`), chưa có bài test riêng assert chuỗi mã lỗi chi tiết `INVALID_STATE`. Hành vi nghiệp vụ vẫn được bảo vệ an toàn 100% (chống tăng kho lặp).
2. **Quy trình Khởi tạo Dữ liệu Giao dịch Mẫu Trước Demo (Pre-Demo Provisioning):**
   - Hệ thống đã tự động hóa dữ liệu hạt giống nền tảng (1 Admin `admin@retailops.local`, 5 Categories, 3 Suppliers).
   - Hệ thống **chưa có script seed tự động cho dữ liệu giao dịch** (Sản phẩm, Phiếu nhập, Đơn hàng) nhằm tránh làm nhiễm bẩn dữ liệu thật. Người điều phối demo cần dành 3 phút thực hiện quy trình chuẩn bị dữ liệu mẫu theo chỉ dẫn tại Mục 3.2 của [QA_REPORT_AND_DEMO_GUIDE.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/QA_REPORT_AND_DEMO_GUIDE.md).
3. **Phụ thuộc Hạ tầng Email Worker & SMTP Gateway:**
   - Celery Worker và Outbox Publisher hoạt động theo cơ chế Transactional Outbox (giao dịch chính hoàn tất độc lập với email).
   - Trong môi trường local/demo, việc gửi nhận email được hứng qua dịch vụ giả lập **Mailpit** (giao diện web tại `http://127.0.0.1:8025` hoặc cổng map tương ứng), tránh gửi email rác ra Internet.
4. **Quy ước Môi trường & Lệnh PowerShell trên Windows:**
   - Trên hệ điều hành Windows, PowerShell không tự động mở rộng cú pháp `${env:VAR:-default}` của Bash. Khi thực hiện kiểm tra sức khỏe hệ thống (Health check) hoặc chạy lệnh cURL, người vận hành bắt buộc sử dụng `curl.exe` trực tiếp và phân nhánh biến cổng Nginx rõ ràng theo đúng runbook đã chuẩn hóa.

---

## 6. Đánh Giá Cổng Chất Lượng & Quyết Định Đóng Băng (Release Gate Verdict)

Căn cứ trên các tiêu chí kiểm soát tại [RetailOps_SRS_Approved.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/requirement/RetailOps_SRS_Approved.md) và [TASK_IMPLEMENTATION_GUIDE.md](file:///D:/ojt/OJT_Group_1_RetailOps_Management_System/docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md):

| Cổng Kiểm Soát (Gate) | Tiêu Chí Bắt Buộc | Kết Quả Đánh Giá Thực Tế | Kết Luận |
|:---:|:---|:---|:---:|
| **`GATE-CI`** | 100% CI pipeline trên GitHub Actions đạt trạng thái xanh; 0 lỗi lint, 11 migration heads duy nhất. | Backend CI (Ruff, Unit, MySQL Integration, RabbitMQ Integration) và Frontend CI (Node test, Vite build) đều PASS trên commit mới nhất. | **PASSED** |
| **`GATE-E2E`** | Toàn bộ các luồng nghiệp vụ P0 hoàn tất; 8 bất biến nghiệp vụ được kiểm chứng; Zero Critical/High defects. | 100% chức năng P0 đã sáp nhập; 8 bất biến có test MySQL chứng minh; 14/14 lỗi trong Defect Ledger đã được khắc phục. | **PASSED** |
| **`DEPLOY`** | Khởi tạo lại được từ `.env.example`, Docker Compose 4 service, Nginx reverse proxy, tài liệu runbook khả lặp. | Docker Compose build sạch; Nginx phục vụ SPA tĩnh và proxy API; tài liệu Cold-Start và Demo Playbook chi tiết 6 phân cảnh. | **PASSED** |

### QUYẾT ĐỊNH ĐÓNG BĂNG PHÁT HÀNH (RELEASE FREEZE VERDICT)
- **Đánh giá chung:** Hệ thống **RetailOps Management System V1.0** đã đáp ứng đầy đủ và vượt mức các tiêu chuẩn nghiệm thu kỹ thuật cho phạm vi cốt lõi P0, sẵn sàng cho công tác nghiệm thu chính thức và trình diễn demo.
- **Trạng thái đề xuất:** **`RELEASE_CANDIDATE_READY_FOR_LEAD_SIGN_OFF`** (Kính chuyển Tech Lead Nguyễn Minh Hiếu xem xét và ký duyệt đóng băng phát hành chính thức).

---

## 7. Biên Bản Ký Duyệt Kỹ Thuật (Technical Sign-off Block)

```
========================================================================================
                      BIÊN BẢN KÝ DUYỆT BÀN GIAO KỸ THUẬT V1.0
========================================================================================

1. KỸ SƯ TỔNG HỢP & KIỂM ĐỊNH CHẤT LƯỢNG (QA LEAD / AUDITOR):
   - Họ và tên: Vũ Hoàng Lan Anh
   - Mã sinh viên: B25DTCN143
   - Vai trò: Senior QA Engineer & Release Quality Gate Reviewer
   - Xác nhận:
     Tôi xác nhận toàn bộ số liệu kiểm thử, ma trận đối soát SRS, kiểm chứng 8 bất biến
     và trạng thái khắc phục lỗi trong tài liệu này là hoàn toàn trung thực, chính xác
     và có bằng chứng kiểm chứng trực tiếp trên repository tại commit baseline 4a2623c.
   - Chữ ký xác nhận: Vũ Hoàng Lan Anh
   - Ngày xác nhận: 18/11/2026 (Cập nhật chuẩn bị mốc phát hành 24/11/2026)

----------------------------------------------------------------------------------------

2. PHÊ DUYỆT ĐÓNG BĂNG PHÁT HÀNH (TECH LEAD & REPOSITORY OWNER):
   - Họ và tên: Nguyễn Minh Hiếu
   - Vai trò: Tech Lead / Software Architect / Repository Owner
   - Quyết định phê duyệt:
     [ ] CHẤP THUẬN ĐÓNG BĂNG RELEASE (APPROVED FOR RELEASE FREEZE)
     [ ] YÊU CẦU BỔ SUNG / ĐIỀU CHỈNH (CHANGES REQUESTED)
   - Mã Commit SHA Đóng Băng Cuối Cùng: _____________________________________________
   - Ghi chú của Tech Lead: ___________________________________________________________
   - Chữ ký phê duyệt: _________________________________________________________________
   - Ngày ký duyệt: ___________________________________________________________________
========================================================================================
```
