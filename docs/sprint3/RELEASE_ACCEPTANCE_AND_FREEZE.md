# RetailOps V1.0 — Biên Bản Nghiệm Thu Kỹ Thuật & Đóng Băng Phát Hành (Release Candidate)

**Hệ thống:** RetailOps Management System V1.0<br>
**Giai đoạn:** Sprint 3 — Nghiệm thu Tích hợp & Chuẩn bị Đóng băng Release Candidate<br>
**Mã Task LMS:** `T04ABC3` — `[S3] Nghiệm thu và đóng băng release`<br>
**Hợp đồng / Cổng kiểm soát:** `GATE-E2E`<br>
**Kỹ sư tổng hợp tài liệu:** Vũ Hoàng Lan Anh (`B25DTCN143`)<br>
**Người phê duyệt kỹ thuật cuối cùng:** Nguyễn Minh Hiếu (Tech Lead / Repository Owner)<br>
**Mốc kế hoạch Sprint:** 24/11/2026 · **Mốc nghiệm thu & Demo dự kiến:** 27/11/2026<br>
**Nhánh Git:** `feature/t04abc3-release-acceptance-and-freeze`<br>
**Baseline Snapshot (`develop` tại thời điểm tách nhánh):** `4a2623c` (*Merge PR #77 `T04AA00` — lưu ý: đây là baseline snapshot, chưa phải Final Release SHA*)<br>
**Trạng thái Hồ sơ:** **`READY_FOR_LEAD_REVIEW — PENDING_FINAL_GATES_AND_SIGN_OFF`**

---

## MỤC LỤC
1. [Thông Tin Quản Trị & Trạng Thái Release Candidate (`T04ABC3`)](#1-thông-tin-quản-trị--trạng-thái-release-candidate-t04abc3)
2. [Ma Trận Đối Soát Tiêu Chí Nghiệm Thu Product Owner Theo SRS](#2-ma-trận-đối-soát-tiêu-chí-nghiệm-thu-product-owner-theo-srs)
   - 2.1. [Phân định Phạm vi Nghiệm thu V1.0: P0 vs P1 vs Ngoài phạm vi](#21-phân-định-phạm-vi-nghiệm-thu-v10-p0-vs-p1-vs-ngoài-phạm-vi)
   - 2.2. [Ma trận Đối soát Chi tiết Các Nhóm Chức năng P0 Cốt lõi](#22-ma-trận-đối-soát-chi-tiết-các-nhóm-chức-năng-p0-cốt-lõi)
3. [Kiểm Chứng 8 Bất Biến Nghiệp Vụ Cốt Lõi (Core Business Invariants)](#3-kiểm-chứng-8-bất-biến-nghiệp-vụ-cốt-lõi-core-business-invariants)
4. [Tổng Hợp Bằng Chứng CI, UAT, Benchmark & Sổ Cái Lỗi Hợp Nhất](#4-tổng-hợp-bằng-chứng-ci-uat-benchmark--sổ-cái-lỗi-hợp-nhất)
   - 4.1. [Thống kê Bằng chứng Kiểm thử Tự động & Đặc tả QA](#41-thống-kê-bằng-chứng-kiểm-thử-tự-động--đặc-tả-qa)
   - 4.2. [Thông tin Alembic Migrations & Độ Sạch Schema](#42-thông-tin-alembic-migrations--độ-sạch-schema)
   - 4.3. [Đánh giá Hiện trạng Benchmark & Hiệu năng Theo Mục tiêu DEC-14](#43-đánh-giá-hiện-trạng-benchmark--hiệu-năng-theo-mục-tiêu-dec-14)
   - 4.4. [Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger)](#44-sổ-cái-theo-dõi-lỗi-hợp-nhất-consolidated-defect-ledger)
5. [Giới Hạn Đã Biết & Lưu Ý Vận Hành Cho Buổi Demo](#5-giới-hạn-đã-biết--lưu-ý-vận-hành-cho-buổi-demo)
6. [Đánh Giá Cổng Chất Lượng & Điều Kiện Đóng Băng (Release Gate Verdict)](#6-đánh-giá-cổng-chất-lượng--điều-kiện-đóng-băng-release-gate-verdict)
7. [Biên Bản Ký Duyệt Kỹ Thuật (Technical Sign-off Block)](#7-biên-bản-ký-duyệt-kỹ-thuật-technical-sign-off-block)

---

## 1. Thông Tin Quản Trị & Trạng Thái Release Candidate (`T04ABC3`)

### 1.1. Mục đích và Định hướng Tài liệu
Tài liệu này là hồ sơ tổng hợp bằng chứng nghiệm thu kỹ thuật chuẩn bị cho quyết định đóng băng bản phát hành **RetailOps Management System V1.0 Release Candidate** theo phân công của task LMS `T04ABC3`. Tài liệu thực hiện:
1. Đối soát các yêu cầu nghiệp vụ bắt buộc **P0** được mô tả trong [RetailOps_SRS_Approved.md](../requirement/RetailOps_SRS_Approved.md).
2. Tổng hợp bằng chứng kiểm chứng **8 bất biến nghiệp vụ cốt lõi** ở mức độ Unit/API và MySQL Integration tests.
3. Tổng hợp kết quả kiểm thử đã có từ các thành viên (`T3C9972`, `T3C9978`, `T3C9970`, `T04AABC`, `T04AAD7`, `T3C9F30`, `T04A90F`, `T04AA00`).
4. Ghi nhận trung thực các hạng mục còn đang chờ (`PENDING`) như Benchmark (`T04AAA2`), đối soát báo cáo PR #78 (`T04AC15`), Browser E2E (`T04AC2F`) và Cold-start demo deployment (`T04AB8D`, `T04ABA7`).
5. Thiết lập khung chữ ký bàn giao kỹ thuật để Tech Lead / Repository Owner (**Nguyễn Minh Hiếu**) xem xét và quyết định Final Release SHA.

### 1.2. Trạng thái Baseline Snapshot & Các PR Liên Quan
- **Baseline Snapshot tại thời điểm lập báo cáo:** Commit **`4a2623c`** trên nhánh `develop` (sau khi sáp nhập PR #77 — Outbox Recovery & Reconciliation).
- **Lưu ý về Final Release SHA:** `4a2623c` **không phải là Final Release SHA**. Sau thời điểm tách nhánh này, `origin/develop` đã tiếp tục tiếp nhận các PR mới (như PR #75 `a060507` — `T04ABDD`, PR #80 `5541c8e` — `T04A9E6`), và vẫn còn các PR/nhánh đang trong quá trình hoàn thiện/review (như PR #78 `T04AC15`, `T04AA1C`, `T04AC2F`, `T04AAA2`). Tech Lead sẽ chốt **Final Release SHA** tại Mục 7 sau khi toàn bộ các gates đạt điều kiện.
- **Trạng thái hiện tại:** **`READY_FOR_LEAD_REVIEW — PENDING_FINAL_GATES_AND_SIGN_OFF`**.

---

## 2. Ma Trận Đối Soát Tiêu Chí Nghiệm Thu Product Owner Theo SRS

### 2.1. Phân định Phạm vi Nghiệm thu V1.0: P0 vs P1 vs Ngoài phạm vi

Căn cứ Phần 1.3 và Phần 5 của [RetailOps_SRS_Approved.md](../requirement/RetailOps_SRS_Approved.md), phạm vi hệ thống được phân định minh bạch như sau:

| Nhóm Phạm Vi | Danh Mục Chức Năng | Tiêu Chuẩn Nghiệm Thu V1.0 | Trạng Thái Hiện Tại |
|:---|:---|:---|:---:|
| **P0 — Bắt buộc hoàn thành (Core Scope)** | • `AUTH-01 .. AUTH-05` (Xác thực, phân quyền, duyệt staff)<br>• `PROD-01 .. PROD-04`, `CAT-01`, `SUP-01` (Catalog master data)<br>• `PUR-01 .. PUR-05` (Quản lý nhập hàng, draft, confirm, cancel)<br>• `INV-01 .. INV-04` (Tồn kho real-time, kiểm kê thực tế, biến động, tồn thấp)<br>• `SALE-01 .. SALE-05`, `ORD-01 .. ORD-03` (Giỏ POS, checkout, hủy đơn, idempotency)<br>• `ANA-01 .. ANA-04` (Doanh thu, top/slow products, Dashboard)<br>• `INF-01 .. INF-05` (Reverse proxy, rate limit, Outbox, RabbitMQ, Celery) | Bắt buộc mã nguồn đã merge vào `develop`, không còn lỗi Critical/High mở, có đầy đủ bằng chứng Unit/Integration, Benchmark (`T04AAA2`), E2E/UAT và Deployment verification. | **CORE_IMPLEMENTED**<br>*(Chờ hoàn tất `GATE-E2E`, `DEPLOY` & Lead Sign-off)* |
| **P1 — Mở rộng sau Quality Gate** | • `INV-05`: Cấu hình ngưỡng tồn kho thấp tùy chỉnh theo từng sản phẩm.<br>• `ANA-05`: Xuất báo cáo thống kê ra file định dạng CSV an toàn.<br>• `ENG-10`: Tối ưu hóa truy vấn chuyên sâu và loại bỏ N+1 query. | Không bắt buộc hoàn thành trước phiên nghiệm thu V1.0 / demo; chỉ triển khai sau khi P0 đạt Quality Gates. | **P1 DEFERRED (ĐÚNG SRS)** |
| **Ngoài phạm vi V1 (Out-of-Scope)** | • Google / Social Login, khôi phục hoặc khóa tài khoản Staff.<br>• Trả hàng / hoàn tiền (Returns / Refunds), Purchase Reversal.<br>• Đa chi nhánh / đa kho (Multi-store / Multi-warehouse).<br>• Cổng thanh toán trực tuyến thực tế (Payment Gateway integration).<br>• Thuế, chiết khấu, chương trình khuyến mãi, đa tiền tệ.<br>• Kế toán tài chính tổng hợp, tự động dự báo nhu cầu (Forecasting).<br>• Thao tác ghi dữ liệu từ Trợ lý AI (AI Write Path). | Không đưa vào phạm vi V1.0; giữ trợ lý AI ở chế độ chỉ đọc và mô hình 1 cửa hàng / 1 kho. | **TUÂN THỦ PHẠM VI** |

---

### 2.2. Ma trận Đối soát Chi tiết Các Nhóm Chức năng P0 Cốt lõi

*Lưu ý cấp độ kiểm chứng: Bảng dưới đây phản ánh trạng thái triển khai mã nguồn và bằng chứng kiểm thử tự động (Unit/API/MySQL Integration) tính đến baseline `4a2623c`, không thay thế cho biên bản Manual UAT hay Final PO Sign-off.*

| Mã SRS / Task | Tên Chức Năng Nghiệp Vụ | Yêu Cầu Cốt Lõi Theo SRS | Hiện Trạng Triển Khai Thực Tế | Bằng Chứng Kiểm Chứng (Automated / Module Tests) | Trạng Thái Sơ Bộ (Chờ E2E & Sign-off) |
|:---|:---|:---|:---|:---|:---:|
| **AUTH-01** (`T04A61F`) | Đăng ký Staff | Đăng ký công khai, email chuẩn hóa duy nhất, sinh hồ sơ `PENDING_APPROVAL`, trả `202 Accepted`. | Đã triển khai tại `auth/router.py`, trả HTTP 202. Chặn đăng ký trùng email. | `test_staff_registration.py`<br>`authSecurity.test.js` | **MODULE_VERIFIED** |
| **AUTH-02** (`T04A61F`) | Đăng nhập & Quản lý phiên | 1 Admin seed duy nhất; Access JWT 15m; Refresh token trong cookie HttpOnly xoay vòng; thu hồi phiên server-side. | JWT 15m; Cookie `retailops_refresh` có cờ `HttpOnly`, `Path=/api/v1/auth`, `SameSite=Lax`. | `test_auth_api.py`<br>`test_auth_tokens_csrf.py` | **MODULE_VERIFIED** |
| **AUTH-03** (`T04A61F`) | Duyệt / Từ chối Staff | Admin duyệt/từ chối; chuyển trạng thái nguyên tử; ghi nhận Transactional Outbox gửi email trong cùng transaction. | Endpoint `POST /api/v1/auth/staff-approval/{id}/approve` (hoặc reject). Ghi sự kiện outbox. | `test_staff_approval.py`<br>SHA: `b0d4dc9` | **MODULE_VERIFIED** |
| **AUTH-04** (`T04A61F`) | Phân quyền vai trò (RBAC) | Chỉ tài khoản `ACTIVE` được truy cập; Staff không xem giá vốn; Dashboard/Analytics chỉ dành cho Admin. | Dependency `require_active_admin` và `require_active_user` chặn từ tầng router. Trả `403 Forbidden`. | `test_cors.py`<br>`test_staff_approval_api.py` | **MODULE_VERIFIED** |
| **AUTH-05** (`T04A61F`) | Thông báo Admin in-app | Tạo 1 thông báo in-app cho Admin khi có Staff đăng ký mới trong cùng transaction. | Bảng `admin_notifications` ghi nhận thông báo nguyên tử; chống sinh trùng lặp. | `test_api.py` (notifications)<br>`test_models_mysql.py` | **MODULE_VERIFIED** |
| **PROD-01** (`T3C9AEB`) | Quản lý sản phẩm | Admin tạo/sửa; bắt buộc SKU, Barcode, tên, giá bán nguyên VND; sản phẩm mới tạo luôn có tồn kho = 0. | `products/service.py` tạo bản ghi Product kèm Inventory `quantity=0` trong 1 transaction. Chặn trùng SKU/Barcode. | `test_products_integration.py`<br>`test_products_api.py` | **MODULE_VERIFIED** |
| **PROD-02** (`T3C9D7D`) | Quản lý danh mục | Admin tạo, sửa qua `PATCH`, đổi trạng thái ACTIVE/INACTIVE; không cascade xóa lịch sử. | Endpoint `PATCH /api/v1/categories/{id}`. Ràng buộc quan hệ khóa ngoại an toàn. | `test_categories_api.py`<br>`categoryList.test.js` | **MODULE_VERIFIED** |
| **PROD-03** (`T04A6A3`) | Tra cứu & Phân trang sản phẩm | Tra cứu theo từ khóa, danh mục, trạng thái; phân trang ổn định (`page`, `page_size`, `total`). | API `GET /api/v1/products` hỗ trợ filter, order_by hợp lệ và phân trang server-side. | `test_products_api.py`<br>`productList.test.js` | **MODULE_VERIFIED** |
| **PROD-04** (`T04A6A3`) | Xem chi tiết sản phẩm | Xem chi tiết sản phẩm; che giấu tuyệt đối trường giá vốn (`cost_price_vnd`) đối với vai trò Staff. | DTO `ProductRead` loại bỏ hoàn toàn trường giá vốn khi serialize phản hồi cho client. | `productList.test.js`<br>`test_t04aad7_reconciliation_api.py` | **MODULE_VERIFIED** |
| **SUP-01** (`T3C9D7D`) | Quản lý nhà cung cấp | Tạo, sửa, tra cứu nhà cung cấp; chuẩn hóa và xác thực số điện thoại theo định dạng quốc tế E.164. | Sử dụng thư viện `phonenumbers` chuẩn hóa E.164 Việt Nam; từ chối SĐT sai định dạng với HTTP 422. | `test_phone_validation.py`<br>`test_suppliers_api.py` | **MODULE_VERIFIED** |
| **PUR-01** (`T04A6D7`) | Phiếu nhập DRAFT | Tạo phiếu nháp gồm nhà cung cấp, sản phẩm, số lượng nguyên dương, đơn giá không âm; không thay đổi tồn kho. | `PurchaseReceipt` tạo ở trạng thái `DRAFT`, `draft_version=1`. Tồn kho giữ nguyên không đổi. | `test_purchase_receipts_mysql.py`<br>PR #35 | **MODULE_VERIFIED** |
| **PUR-02** (`T04A6D7`) | Item Merging phiếu nhập | Tự động gộp dòng trùng sản phẩm và cùng giá nhập; từ chối dòng trùng sản phẩm khác giá nhập (`409 Conflict`). | Logic gộp item tại service; tính tổng tiền chính xác bằng số nguyên VND; chặn lệch giá. | `purchaseReceipts.test.js`<br>`test_purchase_receipts_mysql.py` | **MODULE_VERIFIED** |
| **PUR-03** (`T04A772`) | Khóa lạc quan phiếu nhập | Sửa/hủy phiếu dùng `expected_draft_version`; phiên bản cũ bị từ chối ngay với `409 Conflict`. | Kiểm tra `draft_version == expected_draft_version` trong câu lệnh update. Chống lost update. | `test_purchase_receipts_mysql.py`<br>PR #44 | **MODULE_VERIFIED** |
| **PUR-04** (`T04A772`) | Hủy phiếu nhập nháp | Hủy phiếu khi còn `DRAFT`; chuyển sang `CANCELLED` đúng 1 lần; không làm thay đổi số lượng tồn kho. | Chuyển trạng thái sang `CANCELLED`, tăng version; không ghi nhận biến động kho. | `test_purchase_receipts_mysql.py`<br>PR #44 | **MODULE_VERIFIED** |
| **PUR-05** (`T04A7DF`) | Xác nhận phiếu nhập | Xác nhận phiếu `DRAFT`, tăng tồn kho và ghi `StockMovement(PURCHASE_CONFIRM)` nguyên tử; phiếu CONFIRMED là bất biến. | Tăng `quantity`, tăng `stock_version`, ghi movement trong 1 transaction; chặn xác nhận lại lần 2. | `test_receipt_confirmation_mysql.py`<br>PR #70 | **MODULE_VERIFIED** |
| **INV-01** (`T04A6BD`) | Tổng quan tồn kho | Xem tồn kho theo thời gian thực (`quantity`, `stock_version`, `first_stocked_at`); không có reserved/available ảo. | Schema `InventoryRead` phản ánh đúng thực tế cơ sở dữ liệu, không sinh trường ảo. | `test_inventory_api.py`<br>`test_inventory_integration.py` | **MODULE_VERIFIED** |
| **INV-02** (`T04A758`) | Điều chỉnh kiểm kê thực tế | Admin nhập số đếm thực tế, lý do, `expected_stock_version`; tự tính delta; version cũ trả 409; no-op chỉ ghi audit. | Endpoint `POST /api/v1/inventory/{id}/adjustments`; tính delta nguyên tử; chặn số đếm âm. | `test_inventory_adjustment_api.py`<br>`test_inventory_mysql.py` | **MODULE_VERIFIED** |
| **INV-03** (`T04A78E`) | Lịch sử biến động kho | Lịch sử append-only; 4 loại chuẩn; che giấu giá vốn và lý do điều chỉnh nội bộ đối với vai trò Staff. | Router `GET /api/v1/stock-movements`; ẩn `unit_cost_vnd` đối với Staff thông qua serializer. | `test_low_stock_and_movements.py`<br>`test_inventory_movements_mysql.py` | **MODULE_VERIFIED** |
| **INV-04** (`T04A78E`) | Cảnh báo tồn kho thấp | Cảnh báo sản phẩm ACTIVE có tồn $\le$ 5 theo ngưỡng an toàn mặc định (`DEFAULT_LOW_STOCK_THRESHOLD = 5`). | API `GET /api/v1/inventory/low-stock` lọc theo ngưỡng hằng số thống nhất toàn hệ thống. | `test_low_stock_and_movements.py` | **MODULE_VERIFIED** |
| **SALE-01** (`T04A73C`) | Giỏ hàng POS | Thêm/sửa/xóa giỏ POS; tự động gộp dòng trùng; không giữ tồn kho; sản phẩm INACTIVE không được bán. | Quản lý giỏ hàng phía client và validation phía server; không khóa giữ tồn trước checkout. | `posPage.test.js`<br>`test_checkout_api.py` | **MODULE_VERIFIED** |
| **SALE-02** (`T04A73C`) | Thanh toán trực tiếp | Checkout nguyên tử: tạo đơn COMPLETED, trừ tồn kho, ghi `StockMovement(SALE)`. Lệch giá trả 409 PRICE_CHANGED. | Transaction trừ kho với `SELECT ... FOR UPDATE`; kiểm tra giá bán; chặn bán vượt tồn (`INSUFFICIENT_STOCK`). | `test_checkout_mysql.py`<br>PR #62 | **MODULE_VERIFIED** |
| **SALE-03** (`T04A840`) | Lịch sử đơn hàng | Xem danh sách, lọc theo ngày/trạng thái; Staff chỉ xem đơn của mình; Admin xem toàn bộ đơn hệ thống. | Endpoint `GET /api/v1/orders` kiểm tra ownership dựa trên User ID của access token. | `test_order_read_api.py`<br>`test_order_read_mysql.py` | **MODULE_VERIFIED** |
| **SALE-04** (`T04A80C`) | Hủy đơn hàng có điều kiện | Staff chỉ hủy đơn mình tạo $\le$ 15 phút cùng ngày VN; Admin hủy mọi đơn trong ngày; hoàn tồn đúng 1 lần. | Endpoint `POST /api/v1/orders/{id}/cancel` kiểm tra ownership, mốc thời gian 15m; hoàn kho nguyên tử. | `orderCancel.test.js`<br>`test_cancel_api.py` | **MODULE_VERIFIED** |
| **SALE-05** (`T04A639`) | Idempotency cho Checkout | Header `Idempotency-Key` lưu 24h; replay kết quả cũ khi trùng payload; từ chối khi khác payload. | Khung middleware idempotency lưu trạng thái `STARTED`, `COMPLETED` trong MySQL; khóa chống race condition. | `test_idempotency.py`<br>`test_checkout_mysql.py` | **MODULE_VERIFIED** |
| **ANA-01** (`T04A92B`) | Doanh thu & Chỉ số bán hàng | Doanh thu, số đơn hoàn thành, AOV (làm tròn `ROUND_HALF_UP`); loại bỏ 100% đơn CANCELLED; timezone VN. | API `GET /api/v1/analytics/sales?from=...&to=...`; query loại bỏ đơn hủy; tiền nguyên VND. | `test_sales_analytics_api.py`<br>`test_sales_analytics_mysql.py` | **MODULE_VERIFIED** |
| **ANA-02** (`T04A947`) | Top sản phẩm bán chạy | Xếp hạng theo lượng bán trong kỳ; chỉ tính item của đơn COMPLETED; sắp xếp ổn định. | API `GET /api/v1/analytics/products/top`; tính tổng số lượng bán từ đơn hoàn thành. | `test_product_analytics_api.py`<br>`test_product_analytics_mysql.py` | **MODULE_VERIFIED** |
| **ANA-03** (`T04A947`) | Sản phẩm bán chậm | Nhận diện sản phẩm: nhập kho `> 7 ngày` (`first_stocked_at`), tồn `> 0`, bán $\le$ 2 đơn vị trong 30 ngày. | API `GET /api/v1/analytics/products/slow`; căn cứ thời điểm nhập kho đầu tiên, không dùng created_at. | `test_product_analytics_api.py`<br>`test_product_analytics_mysql.py` | **MODULE_VERIFIED** |
| **ANA-04** (`T04AA36`) | Dashboard API | Tổng quan quản trị: KPI doanh thu, đơn hàng, cảnh báo tồn thấp và top sản phẩm; độc quyền cho Admin. | Endpoint `GET /api/v1/dashboard`; tổng hợp số liệu nhất quán với sales analytics và inventory. | `test_dashboard_api.py`<br>`test_dashboard_mysql.py` | **MODULE_VERIFIED** |
| **INF-01** (`T04A8D1`) | Nginx Reverse Proxy | Định tuyến `/api/` tới Backend, `/` tới static SPA; chuyển tiếp header bảo mật an toàn; chặn giả mạo IP. | Multi-stage build Nginx; `docker/nginx/nginx.conf` cấu hình `proxy_set_header` chuẩn allowlist. | [DOCKER_NGINX_RUNBOOK.md](../runbooks/DOCKER_NGINX_RUNBOOK.md)<br>`test_proxy_registration.py` | **MODULE_VERIFIED** |
| **INF-02** (`T04A826`) | Redis Rate Limiting | Rate limit độc lập theo IP và User: Auth 5 req/min, Business 120 req/min. Auth fail-closed, POS fail-open. | Middleware `RateLimitMiddleware` kết nối Redis; xử lý phân nhánh fallback an toàn khi Redis mất kết nối. | `test_rate_limit.py`<br>`test_redis_rate_limit.py` | **MODULE_VERIFIED** |
| **INF-03** (`T04A90F`) | Transactional Outbox & Worker | MySQL outbox lưu sự kiện sau commit; Celery Worker xử lý email qua RabbitMQ broker; cơ chế at-least-once. | Bảng `outbox_events`; tiến trình `publisher_main.py` poll event và publish sang RabbitMQ exchange. | `test_outbox_delivery_mysql.py`<br>`test_outbox_rabbitmq.py` | **MODULE_VERIFIED** |
| **INF-04** (`T04A90F`) | Gửi email nghiệp vụ | Gửi email bất đồng bộ thông báo đăng ký, duyệt/từ chối; không chặn giao dịch nghiệp vụ chính; log không lộ token. | Module `outbox/smtp.py` gửi email theo cơ chế at-least-once và retry hữu hạn; bảo vệ dữ liệu nhạy cảm (sanitized log). | [OUTBOX_RECOVERY_RUNBOOK.md](../runbooks/OUTBOX_RECOVERY_RUNBOOK.md)<br>PR #73 | **MODULE_VERIFIED**<br>*(SMTP thật cần cấu hình env)* |
| **INF-05** (`T04AA00`) | Retry & Phục hồi Outbox | Reconciler quét sự kiện kẹt; retry exponential backoff có chặn trên; dead-letter queue cô lập lỗi vĩnh viễn. | Module `outbox/reconciler.py` và script `reconcile_outbox.py`; bảo đảm tính an toàn khi replay. | `test_runtime.py`<br>PR #77 | **MODULE_VERIFIED** |

---

## 3. Kiểm Chứng 8 Bất Biến Nghiệp Vụ Cốt Lõi (Core Business Invariants)

Các bất biến nghiệp vụ cốt lõi dưới đây đã có lớp bảo vệ ở tầng cơ sở dữ liệu/service và được kiểm chứng thông qua các test tự động trên **MySQL 8.4 InnoDB** (trong phạm vi các kịch bản integration đã thực thi):

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

### 4.1. Thống kê Bằng chứng Kiểm thử Tự động & Đặc tả QA

*Lưu ý phân định: Số lượng **QA Test Specifications** (ca kiểm thử đặc tả nghiệp vụ) khác với số lượng **Automated Pytest Executions** (hàm test và assertions tự động). Các báo cáo dưới đây phản ánh kết quả tại thời điểm từng module hoàn thành và không đồng nghĩa với 100% độ phủ mọi yêu cầu SRS hoặc full E2E:*

| Phân Hệ / Module Kiểm Thử | Kỹ Sư Phụ Trách | Mã Task LMS | Số Lượng Specs / Executions | Kết Quả Ghi Nhận | Tài Liệu Nguồn & Bằng Chứng |
|:---|:---:|:---:|:---|:---|:---|
| **Products & Purchasing** | Vũ Hoàng Lan Anh | `T3C9972` | **36 QA Specs** / **68 pytest executions** | 68/68 automated passed (53 unit/API + 15 MySQL integration) | [T3C9972_MODULE_TEST_CASES_AND_LOG.md](./T3C9972_MODULE_TEST_CASES_AND_LOG.md) |
| **Catalog, Stock, Order, Analytics QA** | Phạm Thị Na Na | `T3C9978` | **42 QA Specs** / **305 pytest executions** | 38 specs directly verified, 3 partial, 1 not verified; 305/305 pytest passed (9.14s unified run) | [T3C9978_MODULE_TEST_LOG_REPORT.md](./T3C9978_MODULE_TEST_LOG_REPORT.md) |
| **Purchasing Lifecycle & Outbox QA** | Phạm Thị Na Na | `T04AABC` | **24+ tests** | Passed (RBAC, Outbox storage invariant, Shared Admin isolation) | [T04AABC_RECONCILIATION_REPORT.md](./T04AABC_RECONCILIATION_REPORT.md) |
| **Product, Order, Analytics Reconciliation** | Phạm Thị Na Na | `T04AAD7` | **31+ tests** | Passed (Run-Scoped test context, đối soát chéo số liệu) | [T04AAD7_RECONCILIATION_REPORT.md](./T04AAD7_RECONCILIATION_REPORT.md) |
| **Inventory & Receipt Confirmation** | Nguyễn Cao Kỳ Dương | `T3C9970` | **40 QA Specs** | 38 Passed, 2 Partial (95.0% — TC034, TC035 qua stale version) | [testing/T3C9970/README.md](./testing/T3C9970/README.md) |
| **UI Dark Theme & Component Layout** | Phan Nguyễn Nhật Tân | `T3C9F30` | **Frontend theme tests** | Passed trong PR #72 (cô lập CSS Dark Theme) | PR #72 (`26ee520`) |
| **Transactional Outbox & Celery Worker** | Nguyễn Minh Hiếu | `T04A90F`<br>`T04AA00` | **4 test suites** | Passed trong PR #73 & PR #77 (`test_outbox_delivery_mysql.py`, `test_outbox_rabbitmq.py`, `test_runtime.py`) | PR #73 (`00b6c56`), PR #77 (`4a2623c`) |
| **Frontend CI Suite (Node Test Runner)** | Đội ngũ Frontend | — | **211 tests** (45 suites) | Passed trong workflow cấu hình tại CI (oxlint, tsc, Vite build, node test) | [frontend-ci.yml](../../.github/workflows/frontend-ci.yml) |
| **Backend CI Pipeline (GitHub Actions)** | Toàn đội ngũ | — | **3 Jobs** (`lint-and-unit`, `mysql-integration`, `rabbitmq-integration`) | Passed trên các commit đã merge vào `develop` tính đến `4a2623c`; cần run mới cho Final Release SHA | [backend-ci.yml](../../.github/workflows/backend-ci.yml) |
| **Reconciliation & Reporting (PR #78)** | Phạm Thị Na Na | `T04AC15` | **PENDING MERGE** | PR #78 đang trong quá trình hoàn thiện, chưa merge vào `develop` tại baseline `4a2623c`. | `origin/feature/T04AC15-reconciliation-and-reporting` |

---

### 4.2. Thông tin Alembic Migrations & Độ Sạch Schema

Thông tin xác minh trực tiếp từ thư mục `backend/migrations/versions/` và workflow [backend-ci.yml](../../.github/workflows/backend-ci.yml):
- **Số migration revisions trong mã nguồn:** **12 revisions** (chuỗi tuyến tính từ `20261105_01_initial_baseline.py` đến `20261116_01_profile_product_enrichment.py`).
- **Số Alembic heads:** **1 head duy nhất** (được kiểm tra tự động qua step `Check single Alembic head` trong CI: `alembic heads | grep -c " (head)"` == 1).
- **Code migration head:** **`20261116_01`** (`20261116_01_profile_product_enrichment.py`).
- **Database revision hiện tại:** Phụ thuộc từng môi trường thực thi; trong CI, job `Backend / MySQL integration` kiểm chứng nâng cấp từ trống lên `head` thông qua `tests/integration/test_migrations.py`. Trên môi trường demo/staging thực tế, cần chạy `alembic current` sau cold-start để xác nhận database đạt `20261116_01 (head)`.

---

### 4.3. Đánh giá Hiện trạng Benchmark & Hiệu năng Theo Mục tiêu DEC-14

- **Chỉ tiêu Hiệu năng Mục tiêu Theo SRS (DEC-14):**
  Trong điều kiện tải thử nghiệm từ **10 đến 20 người dùng đồng thời (concurrent users)**:
  - Phân hệ Tra cứu Sản phẩm, Danh mục và Tồn kho (`Read Path`): Thời gian đáp ứng **P95 $\le$ 300 ms**.
  - Phân hệ Giao dịch Thanh toán POS và Xác nhận Phiếu nhập (`Write Path`): Thời gian đáp ứng **P95 $\le$ 800 ms**.
  - Phân hệ Tổng quan Quản trị (`Dashboard API`): Thời gian đáp ứng **P95 $\le$ 1.500 ms**.
  - Trợ lý AI (`AI Assistant Read-Only`): Bounded timeout **15 giây**, hạn mức tối đa 3 lần gọi tool và dung lượng phản hồi $\le 32$ KiB.
- **Hiện trạng Thực tế:** **`PENDING` (CHƯA CÓ BẰNG CHỨNG ĐO THỰC TẾ)**
  - Khung chỉ tiêu và yêu cầu đo đạc thuộc về task **`T04AAA2`** (*Đo hiệu năng và xác minh bảo mật* do Tech Lead **Nguyễn Minh Hiếu** phụ trách, contract `PERF,GATE-E2E` trong [TASK_IMPLEMENTATION_GUIDE.md](./TASK_IMPLEMENTATION_GUIDE.md)).
  - Hiện tại repository chưa có kịch bản tải và run log đo P95 thực tế. Ban QA giữ trạng thái **`PENDING`** cho đến khi nhận được benchmark logs hợp lệ từ `T04AAA2` (không tự ước lượng hoặc đánh dấu PASS).

---

### 4.4. Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger)

Tổng hợp **14 lỗi kỹ thuật và sai lệch tài liệu** đã ghi nhận trong quá trình phát triển và kiểm thử Sprint 1–3:

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
> **Phạm vi Đánh giá Sổ cái Lỗi:**
> - Trong phạm vi **14 lỗi đã ghi nhận tại bảng trên**, tất cả **14/14** đều đã ở trạng thái `FIXED & VERIFIED` (9 lỗi code/test) hoặc `DOCS_CORRECTED` (5 lỗi tài liệu); không còn lỗi Critical hoặc High đang mở trong ledger này.
> - **Lưu ý trung thực:** Kết luận trên áp dụng cho 14 lỗi đã theo dõi tại ledger; không suy diễn thành toàn bộ repository không còn vấn đề, vì các PR đang mở (như PR #78 `T04AC15`, PR #79 `T04ABC3`, `T04AA1C`) vẫn đang trong quá trình review/hoàn thiện findings.

---

## 5. Giới Hạn Đã Biết & Lưu Ý Vận Hành Cho Buổi Demo

Nhằm bảo đảm buổi nghiệm thu và thuyết trình demo diễn ra chính xác, các bên liên quan cần nắm rõ 4 lưu ý kỹ thuật:

1. **Giới hạn Độ phủ Kiểm thử Cụ thể (Partial Test Coverage Boundary):**
   - Trong bộ test `T3C9970`, 2 ca kiểm thử `TC034` và `TC035` (xác nhận phiếu nhập đã `CONFIRMED` hoặc `CANCELLED`) hiện được xác thực thông qua cơ chế phiên bản cũ (`draft_version` đã tăng, trả về `409 Conflict`), chưa có bài test riêng assert chuỗi mã lỗi chi tiết `INVALID_STATE`.
   - Trong bộ test `T3C9978`, 3 specs ở mức `PARTIALLY VERIFIED` và 1 spec ở mức `NOT VERIFIED` (`TC_SP1_03` từ chối danh mục trùng tên do kiến trúc V1 Category cho phép trùng tên theo thiết kế schema).
2. **Quy trình Khởi tạo Dữ liệu Giao dịch Mẫu Trước Demo (Pre-Demo Provisioning):**
   - Hệ thống đã tự động hóa dữ liệu hạt giống nền tảng (1 Admin từ `RETAILOPS_ADMIN_SEED_EMAIL`, 5 Categories, 3 Suppliers).
   - Hệ thống **chưa có script seed tự động cho dữ liệu giao dịch** (Sản phẩm, Phiếu nhập, Đơn hàng). Người điều phối demo cần thực hiện tạo dữ liệu mẫu trước buổi trình diễn theo hướng dẫn trong tài liệu `docs/sprint3/QA_REPORT_AND_DEMO_GUIDE.md` (đã merge vào `develop` tại PR #75 / `a060507`).
3. **Cấu hình Mailpit & Ngữ nghĩa Giao nhận Email (`at-least-once`):**
   - Trong `compose.yaml`, dịch vụ `mailpit` thuộc **`profiles: ["email-local"]`** và **không mở cổng ra host mặc định** (chỉ gắn vào mạng nội bộ `application`). Do đó, lệnh `docker compose up -d` mặc định không khởi chạy Mailpit và cổng `8025` không mặc định khả dụng trên host.
   - Khi kiểm thử hoặc trình diễn giao nhận email cục bộ với Mailpit, cần khởi chạy kèm profile `email-local` và overlay `compose.ci.yaml` (hoặc cấu hình biến `MAILPIT_HTTP_HOST_PORT`, mặc định map `127.0.0.1:18025 -> 8025`), hoặc cấu hình một SMTP server độc lập qua các biến `RETAILOPS_SMTP_*`.
   - **Ngữ nghĩa kiểm chứng:** Kiểm thử CI hiện chứng minh Outbox storage trong MySQL, RabbitMQ protocol/ACL, Celery worker retry policy (exponential backoff + dead-letter/parking) và kết nối Mailpit trong CI overlay. Chưa khẳng định SMTP delivery tới mail server bên ngoài đã PASS; hệ thống giữ đúng semantics **at-least-once** của Email Worker.
4. **Quy ước Môi trường & Lệnh PowerShell trên Windows:**
   - Trên hệ điều hành Windows, PowerShell không tự động mở rộng cú pháp `${env:VAR:-default}` của Bash. Khi thực hiện health check hoặc chạy lệnh HTTP probe, cần dùng `curl.exe` trực tiếp và xác định biến cổng Nginx rõ ràng theo [DOCKER_NGINX_RUNBOOK.md](../runbooks/DOCKER_NGINX_RUNBOOK.md).

---

## 6. Đánh Giá Cổng Chất Lượng & Điều Kiện Đóng Băng (Release Gate Verdict)

Căn cứ trên các tiêu chí kiểm soát tại [RetailOps_SRS_Approved.md](../requirement/RetailOps_SRS_Approved.md) và [TASK_IMPLEMENTATION_GUIDE.md](./TASK_IMPLEMENTATION_GUIDE.md):

| Cổng Kiểm Soát (Gate) | Trạng Thái Hiện Tại | Bằng Chứng Đã Có | Điều Kiện Còn Thiếu Để Chốt `PASSED` | Người Chịu Trách Nhiệm Sign-off |
|:---:|:---:|:---|:---|:---|
| **`GATE-CI`** | **PASSED ON BASELINE**<br>*(Pending Final Release SHA CI)* | Backend CI (`lint-and-unit`, `mysql-integration`, `rabbitmq-integration`) và Frontend CI (`Lint + Build`, 211 tests) đã pass trên `develop` tại các commit đã merge tính đến baseline `4a2623c`. | Cần chạy và xác nhận GitHub Actions CI PASS trực tiếp trên **Final Release SHA** sau khi toàn bộ PR Sprint 3 còn lại được merge (không dùng CI của feature PR làm bằng chứng cho SHA khác). | **Nguyễn Minh Hiếu**<br>*(Tech Lead)* |
| **`GATE-E2E`** | **PARTIALLY VERIFIED / PENDING FINAL ACCEPTANCE** | Đã có Unit/API tests và MySQL/RabbitMQ integration tests cho các module P0 (`T3C9972`, `T3C9978`, `T3C9970`, `T04AABC`, `T04AAD7`, PR #73, PR #77). | 1. Kết quả đối soát dữ liệu & báo cáo của PR #78 (`T04AC15` — đang hoàn thiện).<br>2. Bằng chứng Browser E2E (`T04AC2F`).<br>3. Biên bản Manual UAT sign-off.<br>4. Kết quả Benchmark & Security Audit (`T04AAA2`). | **Vũ Hoàng Lan Anh** *(QA)*<br>**Nguyễn Minh Hiếu** *(Tech Lead / PO)* |
| **`DEPLOY`** | **PARTIALLY VERIFIED** | Đã xác minh tĩnh cấu hình `compose.yaml`, `compose.ci.yaml`, Nginx reverse proxy và tài liệu runbooks (`DOCKER_NGINX_RUNBOOK.md`, `OUTBOX_RECOVERY_RUNBOOK.md`). | Chưa có run log cold-start đầy đủ (4 container healthy, `alembic current` tại `20261116_01 (head)`, seed 3 modules, `/api/v1/health` 200 OK) trên môi trường demo/staging thực tế (`T04AB8D`, `T04ABA7`). | **Nguyễn Minh Hiếu**<br>*(Tech Lead / Release Owner)* |
| **`PERF (DEC-14)`** | **PENDING** | Đã khóa chỉ tiêu mục tiêu trong SRS (`DEC-14`: Read $\le$ 300ms, Write $\le$ 800ms, Dashboard $\le$ 1500ms với 10–20 concurrent users). | Chưa có kịch bản tải và benchmark logs thực tế từ task `T04AAA2`. | **Nguyễn Minh Hiếu**<br>*(Tech Lead)* |

### KẾT LUẬN TRẠNG THÁI RELEASE CANDIDATE
- **Đánh giá hiện tại:** Hồ sơ kỹ thuật đã tổng hợp đầy đủ hiện trạng thực tế, đối soát trung thực phần đã kiểm chứng và phần còn `PENDING`. Tài liệu **chưa tự tuyên bố đóng băng chính thức** khi các điều kiện ở `GATE-E2E`, `DEPLOY` và `PERF (DEC-14)` chưa hoàn tất.
- **Trạng thái đề xuất:** **`READY_FOR_LEAD_REVIEW`** (Kính chuyển Tech Lead Nguyễn Minh Hiếu rà soát, theo dõi hoàn tất các cổng còn thiếu và ký duyệt Final Release SHA tại Mục 7).

---

## 7. Biên Bản Ký Duyệt Kỹ Thuật (Technical Sign-off Block)

```text
========================================================================================
                      BIÊN BẢN KÝ DUYỆT BÀN GIAO KỸ THUẬT V1.0
========================================================================================

1. KỸ SƯ TỔNG HỢP & KIỂM ĐỊNH CHẤT LƯỢNG (QA LEAD / AUDITOR):
   - Họ và tên: Vũ Hoàng Lan Anh
   - Mã sinh viên: B25DTCN143
   - Vai trò: Senior QA Engineer & Release Quality Gate Reviewer
   - Xác nhận:
     Tôi xác nhận toàn bộ số liệu kiểm thử, đối soát SRS, kiểm chứng bất biến,
     hiện trạng Defect Ledger và các hạng mục còn PENDING trong tài liệu này được
     tổng hợp trung thực dựa trên bằng chứng thực tế trên repository tính đến
     baseline snapshot 4a2623c.
   - Chữ ký xác nhận: Vũ Hoàng Lan Anh
   - Ngày lập hồ sơ: 18/11/2026 (Phục vụ mốc Sprint 24/11/2026)

----------------------------------------------------------------------------------------

2. PHÊ DUYỆT ĐÓNG BĂNG PHÁT HÀNH (TECH LEAD & REPOSITORY OWNER):
   - Họ và tên: Nguyễn Minh Hiếu
   - Vai trò: Tech Lead / Software Architect / Repository Owner
   - Quyết định phê duyệt (chỉ đánh dấu sau khi toàn bộ Gates đạt PASSED):
     [ ] CHẤP THUẬN ĐÓNG BĂNG RELEASE (APPROVED FOR RELEASE FREEZE)
     [ ] YÊU CẦU BỔ SUNG / ĐIỀU CHỈNH (CHANGES REQUESTED)
   - Final Release Commit SHA: _________________________________________________________
   - CI Run URL trên Final Release SHA: _________________________________________________
   - Ghi chú của Tech Lead: ___________________________________________________________
   - Chữ ký phê duyệt: _________________________________________________________________
   - Ngày ký duyệt: ___________________________________________________________________
========================================================================================
```
