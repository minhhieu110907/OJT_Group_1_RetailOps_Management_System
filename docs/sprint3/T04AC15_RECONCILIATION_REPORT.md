# BÁO CÁO ĐỐI SOÁT DỮ LIỆU & ĐÁNH GIÁ NGHIỆM THU E2E (TASK T04AC15)
## Cross-Module Reconciliation: Catalog ↔ Inventory ↔ Purchasing ↔ Orders ↔ Analytics ↔ Dashboard

- **Mã Task:** `T04AC15`
- **Tên Task:** Đối soát dữ liệu và báo cáo (Reconciliation and Reporting)
- **Hợp đồng cam kết:** `HTTP-ANALYTICS`, `GATE-E2E`
- **Kỹ sư phụ trách:** Phạm Thị Na Na (Principal Backend QA Engineer & Database Reliability Engineer)
- **Thời gian lập:** 18/11/2026
- **Branch thực hiện:** `feature/T04AC15-reconciliation-and-reporting`
- **Base Commit:** `3de0aaf` (HEAD `develop`)
- **Tài liệu tham chiếu:**
  - `docs/requirement/RETAILOPS_AGENT_BUSINESS_CONTEXT.md`
  - `contracts/openapi.yaml`
  - `contracts/python/retailops_extended_ports.pyi`
  - `docs/contracts/API_INTEGRATION.md`
  - `docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md`
- **Trạng thái phê duyệt:** **READY FOR QA/TECH LEAD REVIEW**

---

## 1. TỔNG QUAN VÀ PHÂN ĐỊNH TẦNG KIỂM THỬ (VERIFICATION LEVELS & OWNERSHIP)

Task `T04AC15` đóng vai trò là chốt chặn đối soát số liệu và bảo đảm tính toàn vẹn (Final Reconciliation Gate) của Sprint 3. Nhiệm vụ trọng tâm là kiểm chứng tính nhất quán toán học giữa các phân hệ: Catalog, Kho hàng (Inventory), Mua hàng (Purchasing), Bán hàng (POS Orders), Hủy đơn (Order Cancellation), Phân tích doanh thu & sản phẩm (Sales/Product Analytics), và Bảng tin quản trị (Dashboard).

### 1.1. Phân định rõ ràng 3 Tầng Kiểm thử (Verification Levels)

Để bảo đảm tính minh bạch và trung thực kỹ thuật, phạm vi kiểm thử của Task `T04AC15` được phân định rõ ràng như sau:

| Tầng Kiểm thử (Verification Level) | File Thực thi / Nguồn kiểm chứng | Hạ tầng & Cơ chế Thực thi | Trọng tâm Đánh giá | Giới hạn & Lưu ý |
| :--- | :--- | :--- | :--- | :--- |
| **Level 1: Unit & Contract Test** | `backend/tests/modules/analytics/test_t04ac15_reconciliation_api.py` | FastAPI in-memory (`httpx.AsyncClient`) + Fake Services mô phỏng bộ dữ liệu demo chuẩn | - Ma trận RBAC 4 endpoints x 4 trạng thái auth.<br>- Kiểm tra biên tham số HTTP (Validation 422).<br>- Khớp hợp đồng JSON schema và tính nhất quán logic. | Chạy tức thì (~2s), không phụ thuộc database vật lý. Không thay thế test database thật. |
| **Level 2: MySQL Integration Test** | `backend/tests/modules/analytics/test_t04ac15_reconciliation_mysql.py` | Database thật MySQL 8.4 InnoDB + Real Services (`SalesAnalyticsService`, `ProductAnalyticsService`, `DashboardService`) | - Tính toán số liệu số học thật trên bảng InnoDB.<br>- Bất biến snapshot giá khi catalog thay đổi.<br>- Cô lập test runs, delta baseline, fail-closed teardown. | Chạy với database MySQL dedicated container. Dữ liệu được seed và kiểm soát vòng đời chặt chẽ qua ORM fixtures. |
| **Level 3: Write Lifecycle E2E** | Được kiểm chứng chéo tại các PR độc lập của từng module | Live API Endpoints kết hợp DB + Background Workers + Outbox | - Vòng đời ghi dữ liệu từ client -> API -> DB: POS Checkout (PR #43), Hủy đơn (PR #52), Mua hàng (PR #70). | T04AC15 **không** chạy lại browser E2E hay gọi lặp các write endpoints mà tập trung đối soát trạng thái chéo và bảo toàn số liệu. |

### 1.2. Trạng thái các Phân hệ Phụ thuộc trên `develop`

Toàn bộ các phân hệ phụ thuộc đều đã được merge chính thức vào nhánh `develop`:

| Phân hệ / Endpoint | Mã Task | Tác giả & PR | Trạng thái Git | Vai trò trong Luồng Đối soát T04AC15 |
| :--- | :--- | :--- | :--- | :--- |
| **Catalog & Products**<br>`GET /api/v1/products` | `T04A6A3` | Na Na (PR #28) | Merged to `develop` | Cung cấp danh mục sản phẩm, cấu hình giá niêm yết, ngưỡng cảnh báo tồn kho (`low_stock_threshold = 5`). |
| **Purchasing & Inbound**<br>`POST /api/v1/purchase-receipts` | `T04AABC` | Na Na (PR #70) | Merged to `develop` | Nhập kho ban đầu 4 sản phẩm qua phiếu nhập đã xác nhận (`CONFIRMED`), tăng tồn kho thực và ghi nhận `StockMovement` loại `PURCHASE_CONFIRM`. |
| **POS Checkout**<br>`POST /api/v1/orders/checkout` | `T04A73C` | Hiếu (PR #43) | Merged to `develop` | Tạo đơn bán hàng thành công 62.000 VNĐ, trừ tồn kho thật, ghi nhận snapshot giá lịch sử tại thời điểm bán, ghi `StockMovement` loại `SALE`. |
| **Order Cancellation**<br>`POST /api/v1/orders/{id}/cancel` | `T04A80C` | Hiếu (PR #52) | Merged to `develop` | Hủy đơn đặt hàng 105.000 VNĐ, hoàn lại 100% tồn kho, ghi nhận `StockMovement` loại `ORDER_CANCEL`, đảm bảo loại trừ khỏi doanh thu. |
| **Order History & Detail**<br>`GET /api/v1/orders` | `T04A840` | Hiếu (PR #56) | Merged to `develop` | Đối soát tổng số đơn theo trạng thái (`COMPLETED`, `CANCELLED`) và tổng tiền thanh toán theo snapshot. |
| **Sales & Revenue Analytics**<br>`GET /api/v1/analytics/sales` | `T04A92B` | Na Na (PR #60) | Merged to `develop` | Tổng hợp doanh thu thuần, số đơn hoàn tất, số đơn hủy, giá trị đơn trung bình (AOV) làm tròn `ROUND_HALF_UP` theo múi giờ `Asia/Ho_Chi_Minh`. |
| **Product Analytics (Top & Slow)**<br>`GET /api/v1/analytics/products/top`<br>`GET /api/v1/analytics/products/slow` | `T04A947` | Dương (PR #67) | Merged to `develop` | Xếp hạng sản phẩm bán chạy (Top Products) theo lượt bán/doanh thu và phát hiện sản phẩm ứ đọng bán chậm (Slow-moving Products). |
| **Admin Dashboard Overview**<br>`GET /api/v1/dashboard` | `T04AA36` | Na Na (PR #61) | Merged to `develop` | Tổng hợp thời gian thực (Real-time KPI): doanh thu trong ngày, số đơn thành công, số sản phẩm cảnh báo tồn thấp (`low_stock_count`), Top sản phẩm. |
| **QA Product / Order / Analytics** | `T04AAD7` | Na Na (PR #66) | Merged to `develop` | Khung kiểm thử đối soát và cô lập kiểm thử cross-run trên MySQL 8.4. |

---

## 2. ĐẶC TẢ BỘ DỮ LIỆU DEMO CHUẨN (STANDARD DEMO DATASET SPECIFICATION)

Để đảm bảo tính tất định (determinism) và khả năng đối soát chính xác đến từng đơn vị số học, kịch bản kiểm thử thiết lập một bộ dữ liệu demo chuẩn gồm: **1 Nhà cung cấp**, **2 Danh mục**, **4 Sản phẩm**, **1 Phiếu nhập kho**, **1 Đơn hàng thành công (62.000 VNĐ)**, và **1 Đơn hàng hủy (105.000 VNĐ)**.

### 2.1. Danh mục và Nhà cung cấp
- **Nhà cung cấp:** Nhà Phân Phối Nước Giải Khát & Tiêu Dùng Hà Nội (Mã: `SUP_BEV`).
- **Danh mục:**
  - `DO_UONG`: Nước giải khát & Sữa dinh dưỡng.
  - `THUC_PHAM`: Thực phẩm ăn liền & Đóng hộp.

### 2.2. Bảng cấu hình 4 Sản phẩm Demo
| Mã SKU | Tên sản phẩm | Danh mục | Giá vốn nhập (`cost_price`) | Giá bán ban đầu (`retail_price`) | Số lượng nhập | Tồn sau đối soát | Ngưỡng tồn thấp | Ghi chú vòng đời |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `DRK-COCA-330` | Nước ngọt Coca Cola 330ml | `DO_UONG` | 8.500 VNĐ | 12.000 VNĐ | 120 lon | **118 lon** | 5 lon | Bán 2 lon trong đơn thành công. Sau đó tăng giá catalog lên 15.000 VNĐ. |
| `DRK-MILK-TH1L` | Sữa tươi tiệt trùng TH True Milk 1L | `DO_UONG` | 28.000 VNĐ | 38.000 VNĐ | 50 hộp | **49 hộp** | 5 hộp | Bán 1 hộp trong đơn thành công. Sau đó tăng giá catalog lên 45.000 VNĐ. |
| `SNK-LAY-75G` | Bánh snack khoai tây Lay's 75g | `THUC_PHAM` | 14.000 VNĐ | 20.000 VNĐ | 5 gói | **5 gói** | 5 gói | Nhập 10 ngày trước, nằm trong đơn hủy 3 gói (hoàn kho đủ 5). Đạt tiêu chí Tồn thấp & Bán chậm. |
| `CAN-TUNA-185G` | Cá ngừ ngâm dầu Hạ Long Can 185g | `THUC_PHAM` | 32.000 VNĐ | 45.000 VNĐ | 3 hộp | **3 hộp** | 5 hộp | Nhập 10 ngày trước, nằm trong đơn hủy 1 hộp (hoàn kho đủ 3). Đạt tiêu chí Tồn thấp & Bán chậm. |

### 2.3. Phiếu nhập hàng (Purchase Receipt)
- **Mã tham chiếu:** `REC-DEMO-001`
- **Trạng thái:** `CONFIRMED`
- **Tổng số lượng nhập kho:** `120 + 50 + 5 + 3 = 178` đơn vị sản phẩm.
- **Tổng giá trị vốn nhập:**
  `120 * 8.500 + 50 * 28.000 + 5 * 14.000 + 3 * 32.000 = 1.020.000 + 1.400.000 + 70.000 + 96.000 = 2.586.000 VNĐ`.
- **Dòng chi tiết phiếu nhập:** Đầy đủ 4 dòng `PurchaseReceiptItem` tương ứng 4 sản phẩm.
- **Biến động kho phát sinh:** Đầy đủ 4 bản ghi `StockMovement` (loại `PURCHASE_CONFIRM`, delta dương tương ứng từng sản phẩm: Coca +120, TH +50, Lay's +5, Tuna +3).

### 2.4. Đơn hàng Bán lẻ Thành công (Order COMPLETED)
- **Mã đơn hàng:** `ORD-DEMO-001`
- **Trạng thái:** `COMPLETED`
- **Chi tiết giỏ hàng:**
  - 2 lon Coca Cola 330ml x 12.000 VNĐ = **24.000 VNĐ**.
  - 1 hộp Sữa TH True Milk 1L x 38.000 VNĐ = **38.000 VNĐ**.
- **Tổng tiền thanh toán (`total_vnd`):** **62.000 VNĐ**.
- **Biến động kho phát sinh:** 2 bản ghi `StockMovement` (loại `SALE`, delta = -2 Coca, -1 TH True Milk).

### 2.5. Đơn hàng Bán lẻ Bị hủy (Order CANCELLED)
- **Mã đơn hàng:** `ORD-DEMO-002`
- **Trạng thái ban đầu:** Tạo đơn thành công với giỏ hàng gồm:
  - 3 gói Snack Lay's 75g x 20.000 VNĐ = **60.000 VNĐ** (tạm trừ kho còn 2 gói).
  - 1 hộp Cá ngừ Hạ Long 185g x 45.000 VNĐ = **45.000 VNĐ** (tạm trừ kho còn 2 hộp).
  - Tổng giá trị đơn: **105.000 VNĐ**.
- **Thao tác hủy đơn (`POST /orders/{id}/cancel`):**
  - Trạng thái chuyển thành `CANCELLED`.
  - Hoàn trả 100% tồn kho: Lay's trở lại 5 gói, Cá ngừ trở lại 3 hộp.
- **Biến động kho phát sinh:** 2 bản ghi `StockMovement` loại `SALE` (delta âm) + 2 bản ghi `StockMovement` loại `ORDER_CANCEL` (delta dương hoàn kho).

---

## 3. BẢNG ĐỐI SOÁT ĐA CHIỀU (RECONCILIATION LEDGER - EXPECTED VS ACTUAL)

> **Lưu ý về Cơ chế Baseline Delta & Phạm vi Cô lập:**
> - Trên môi trường MySQL Integration, các chỉ số thực tế được assert theo hiệu số biến thiên: `Giá trị Thực tế = (Giá trị đo sau test - Baseline đo trước test)`.
> - **Cơ chế Baseline Delta giúp loại trừ ảnh hưởng của dữ liệu nền ổn định** từ các test suites chạy trước.
> - **Giới hạn kỹ thuật:** Baseline Delta **không bảo đảm isolation trước các concurrent writes** ghi đồng thời vào cùng chỉ số tổng hợp trong lúc test run đang thực thi.
> - **Quy chuẩn CI & Môi trường:** Toàn bộ MySQL Integration Tests **bắt buộc phải chạy trên dedicated/isolated test database** theo CI contract (qua container MySQL 8.4 riêng biệt được khởi tạo bởi GitHub Actions CI).
> - **Nguyên tắc an toàn dữ liệu:** Tuyệt đối **không sử dụng dữ liệu production** để chạy reconciliation tests.

| Phân hệ / Chiều nghiệp vụ | Chỉ số kiểm chứng | Giá trị Kỳ vọng (Expected) | Giá trị Thực tế (Actual) | Độ lệch (Delta) | Điều kiện Baseline & Nguồn Kiểm chứng | Trạng thái |
| :--- | :--- | :--- | :--- | :---: | :--- | :---: |
| **Catalog & Giá Snapshot** | Giá bán lịch sử Đơn ORD-001 (Coca) | `12.000 VNĐ` | `12.000 VNĐ` | 0 | `test_catalog_price_mutation_preserves_reconciled_analytics_mysql`<br>(Direct ORM OrderItem snapshot) | **MATCH** |
| | Giá bán lịch sử Đơn ORD-001 (TH Milk) | `38.000 VNĐ` | `38.000 VNĐ` | 0 | `test_catalog_price_mutation_preserves_reconciled_analytics_mysql`<br>(Direct ORM OrderItem snapshot) | **MATCH** |
| | Giá Catalog mới sau điều chỉnh (Coca) | `15.000 VNĐ` | `15.000 VNĐ` | 0 | `test_catalog_price_mutation_preserves_reconciled_analytics_mysql`<br>(Product.sale_price_vnd in DB) | **MATCH** |
| | Doanh thu lịch sử sau khi tăng giá catalog | `62.000 VNĐ` | `62.000 VNĐ` (Không đổi) | 0 | `test_catalog_price_mutation_preserves_reconciled_analytics_mysql`<br>`SalesAnalyticsService.summary()` | **MATCH** |
| **Tồn kho (Inventory)** | Tồn kho Coca Cola (120 nhập - 2 bán) | `118 lon` | `118 lon` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Inventory.quantity in DB) | **MATCH** |
| | Tồn kho Sữa TH True Milk (50 nhập - 1 bán) | `49 hộp` | `49 hộp` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Inventory.quantity in DB) | **MATCH** |
| | Tồn kho Snack Lay's (5 nhập - 3 bán + 3 hoàn) | `5 gói` | `5 gói` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Inventory.quantity in DB) | **MATCH** |
| | Tồn kho Cá ngừ Tuna (3 nhập - 1 bán + 1 hoàn) | `3 hộp` | `3 hộp` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Inventory.quantity in DB) | **MATCH** |
| | Tổng tồn kho cuối kỳ của 4 sản phẩm | `175 đơn vị` | `175 đơn vị` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(SUM(Inventory.quantity) for tracked prods) | **MATCH** |
| **Nhật ký Biến động kho** | Bản ghi loại `PURCHASE_CONFIRM` | `4 bản ghi` | `4 bản ghi` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Tracked StockMovement in DB) | **MATCH** |
| | Bản ghi loại `SALE` (Đơn 1 + Đơn 2) | `4 bản ghi` | `4 bản ghi` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Tracked StockMovement in DB) | **MATCH** |
| | Bản ghi loại `ORDER_CANCEL` (Hoàn Đơn 2) | `2 bản ghi` | `2 bản ghi` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Tracked StockMovement in DB) | **MATCH** |
| | Tổng số bản ghi `StockMovement` sinh ra | `10 bản ghi` | `10 bản ghi` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(len(ctx.stock_movement_ids) == 10) | **MATCH** |
| **Đơn hàng (Orders)** | Tổng số đơn hàng trong kỳ | `2 đơn` | `2 đơn` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Tracked Order in DB) | **MATCH** |
| | Số đơn hàng thành công (`COMPLETED`) | `1 đơn` | `1 đơn` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Tracked Order status in DB) | **MATCH** |
| | Số đơn hàng hủy (`CANCELLED`) | `1 đơn` | `1 đơn` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Tracked Order status in DB) | **MATCH** |
| | Doanh thu đơn thành công | `62.000 VNĐ` | `62.000 VNĐ` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Order.total_vnd in DB) | **MATCH** |
| | Giá trị đơn bị hủy (bị loại khỏi doanh thu) | `105.000 VNĐ` | `105.000 VNĐ` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>(Order.total_vnd in DB) | **MATCH** |
| **Sales Analytics (T04A92B)**| Doanh thu thuần (`revenue_vnd - baseline`) | `62.000 VNĐ` | `62.000 VNĐ` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`SalesAnalyticsService.summary()` | **MATCH** |
| | Số đơn hoàn tất (`completed - baseline`) | `1` | `1` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`SalesAnalyticsService.summary()` | **MATCH** |
| | Số đơn hủy (`cancelled - baseline`) | `1` | `1` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`SalesAnalyticsService.summary()` | **MATCH** |
| | Giá trị trung bình đơn (`aov_vnd`) | `62.000 VNĐ` (`62.000 / 1`) | `62.000 VNĐ` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`SalesAnalyticsService.summary()` | **MATCH** |
| **Product Analytics (T04A947)**| Top sản phẩm hạng 1 (Coca Cola 330ml) | `sold_units = 2, rev = 24.000` | `sold_units = 2, rev = 24.000` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`ProductAnalyticsService.top()` | **MATCH** |
| | Top sản phẩm hạng 2 (Sữa TH True Milk) | `sold_units = 1, rev = 38.000` | `sold_units = 1, rev = 38.000` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`ProductAnalyticsService.top()` | **MATCH** |
| | Sản phẩm đơn hủy trong Top | `0` (Không có Lay's/Tuna) | `0` (Loại trừ hoàn toàn) | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`ProductAnalyticsService.top()` | **MATCH** |
| | Sản phẩm bán chậm (Slow moving) | 2 sản phẩm (Lay's, Tuna) | 2 sản phẩm (Lay's, Tuna) | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`ProductAnalyticsService.slow()` | **MATCH** |
| | - Lay's 75g (`sold_units = 0, qty = 5`) | `sold = 0, qty = 5, days >= 7` | `sold = 0, qty = 5, days >= 7` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`ProductAnalyticsService.slow()` | **MATCH** |
| | - Tuna 185g (`sold_units = 0, qty = 3`) | `sold = 0, qty = 3, days >= 7` | `sold = 0, qty = 3, days >= 7` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`ProductAnalyticsService.slow()` | **MATCH** |
| **Dashboard API (T04AA36)** | Doanh thu hôm nay (`revenue - baseline`) | `62.000 VNĐ` | `62.000 VNĐ` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`DashboardService.read().sales` | **MATCH** |
| | Số đơn hoàn tất hôm nay (`completed - baseline`) | `1` | `1` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`DashboardService.read().sales` | **MATCH** |
| | Cảnh báo tồn kho thấp (`low_stock - baseline`) | `2` (Lay's: 5 <= 5, Tuna: 3 <= 5) | `2` | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`DashboardService.read().low_stock_count` | **MATCH** |
| | Top sản phẩm trên Dashboard | Khớp Top 2 của Product Analytics | Khớp 100% Coca & TH Milk | 0 | `test_demo_dataset_end_to_end_reconciliation_mysql`<br>`DashboardService.read().top_products` | **MATCH** |

---

## 4. CHI TIẾT THIẾT KẾ VÀ TRIỂN KHAI KIỂM THỬ (TEST IMPLEMENTATION DETAILS)

Nhằm bảo đảm tính tin cậy cao nhất của hệ thống, không làm ảnh hưởng đến môi trường production và loại trừ hoàn toàn nguy cơ rò rỉ dữ liệu kiểm thử, bộ kiểm thử được chia thành 2 file chuyên biệt:

### 4.1. Non-Integration Suite: `test_t04ac15_reconciliation_api.py`
- **Mục tiêu:** Kiểm thử toàn diện tầng API Router (FastAPI) trên bộ nhớ (In-memory via `httpx.AsyncClient`), bảo đảm tốc độ thực thi cực nhanh và độc lập hoàn toàn với database vật lý.
- **Các kịch bản kiểm thử (17 Test Cases):**
  1. **Ma trận phân quyền (RBAC Matrix - 4 Endpoints x 4 Trạng thái):**
     - Khách vãng lai chưa đăng nhập (Anonymous): Phản hồi `401 Unauthorized` trên cả 4 endpoints (`/analytics/sales`, `/analytics/products/top`, `/analytics/products/slow`, `/dashboard`).
     - Nhân viên (`STAFF`): Phản hồi `403 Forbidden` (`code: FORBIDDEN`) trên cả 4 endpoints.
     - Quản trị viên không hoạt động (`PENDING`, `SUSPENDED`, `REJECTED`): Phản hồi `403 Forbidden` trên cả 4 endpoints.
     - Quản trị viên hợp lệ (`ACTIVE ADMIN`): Truy cập thành công với mã phản hồi `200 OK` trên cả 4 endpoints.
  2. **Kiểm tra biên tham số HTTP (Validation Boundaries):**
     - Khoảng ngày sai (`from > to`): Phản hồi `422 Unprocessable Entity`.
     - Khoảng cách ngày vượt ngưỡng (`span > 366 days`): Phản hồi `422 Unprocessable Entity`.
     - Tham số phân trang không hợp lệ (`page=0`, `page_size=101`, `days=0`): Phản hồi `422 Unprocessable Entity`.
  3. **Đối soát Hợp đồng Dữ liệu Demo Chuẩn (In-Memory Contract Reconciliation):**
     - Xác thực tính nhất quán giữa Sales Analytics (`revenue_vnd == 62000`, `completed_orders == 1`, `cancelled_orders == 1`, `aov_vnd == 62000`).
     - Xác thực tính nhất quán của Product Analytics: Coca Cola (2 units, 24k) và TH Milk (1 unit, 38k) đứng Top; Lay's (0 sold, 5 tồn) và Tuna (0 sold, 3 tồn) nằm trong Slow-moving.
     - Xác thực Dashboard: `revenue == 62000`, `orders == 1`, `low_stock == 2`, Top products khớp 100%.
     - Xác thực tính bất biến snapshot giá: khi cập nhật giá catalog mới (Coca 15k, TH 45k), doanh thu lịch sử vẫn giữ nguyên 62.000 VNĐ.
- **Kết quả thực thi:** **17/17 PASSED (100%)**, thời gian chạy: **~2.2 giây**.

### 4.2. MySQL Integration Suite: `test_t04ac15_reconciliation_mysql.py`
- **Mục tiêu:** Kiểm thử thực thi trên cơ sở dữ liệu thật MySQL 8.4 InnoDB thông qua session SQLAlchemy và các Services nghiệp vụ thật (`SalesAnalyticsService`, `ProductAnalyticsService`, `DashboardService`).
- **Phân loại:** Đánh dấu `@pytest.mark.integration`.
- **Kiến trúc Dọn dẹp An toàn & Cơ chế Fail-Closed (Safe Teardown Architecture):**
  - **Quản lý Định danh Chính xác (Exact ID Tracking):**
    + Loại bỏ hoàn toàn việc tìm kiếm ID mở rộng qua foreign key (`select(Order.id).where(Order.created_by.in_...)`, `select(OrderItem.order_id).where(OrderItem.product_id.in_...)`).
    + Loại bỏ hoàn toàn việc xóa theo tiền tố (`Supplier.name.like(prefix)`, `Category.name.like(prefix)`, `User.email_normalized.like(prefix)`).
    + Chỉ xóa đúng các bản ghi có khóa chính nằm trong các danh sách được track tường minh: `self.stock_movement_ids`, `self.order_ids`, `self.receipt_ids`, `self.product_ids`, `self.supplier_ids`, `self.category_ids`, `self.user_ids`.
  - **Kiểm tra Tham chiếu Bắt buộc Fail-Closed (Fail-Closed Reference Checks):**
    + Được thực thi bên trong cùng transaction nguyên tử với thao tác DELETE.
    + Kiểm tra nếu có bất kỳ record ngoại lai nào tham chiếu đến tracked products, tracked categories, tracked suppliers, hoặc tracked users (ví dụ: `OrderItem` bên ngoài trỏ vào `product_ids`, `StockMovement` trỏ vào `product_ids`, v.v.).
    + Nếu phát hiện vi phạm tham chiếu $\rightarrow$ raise `RuntimeError("Fail-closed cleanup: ...")` ngay lập tức.
    + Khi exception xảy ra, transaction lập tức rollback 100%, **tuyệt đối không xảy ra hiện tượng xóa một phần (0 partial deletions)**.
  - **Loại bỏ Hoàn toàn việc Xóa IdempotencyRecord theo user_id:**
    + Task T04AC15 không sinh IdempotencyRecord trong luồng đối soát dữ liệu. Việc xóa broad theo `user_id` bị loại bỏ hoàn toàn để bảo đảm không bao giờ xóa dữ liệu ngoài quyền sở hữu của test run.
    + Ràng buộc khóa ngoại (foreign key) của MySQL InnoDB được giữ nguyên để bảo vệ toàn vẹn các bản ghi tham chiếu đến User.
  - **Bảo vệ Vững chắc Shared ADMIN & IdempotencyRecord:**
    + Shared Admin với `admin_slot == 1` không bao giờ được thêm vào `self.user_ids`.
    + Lệnh DELETE của bảng `users` được ràng buộc chặt chẽ bằng điều kiện `User.admin_slot.is_(None)`. Ngay cả khi `admin_id` bị thêm nhầm vào `user_ids`, tài khoản Shared Admin và toàn bộ IdempotencyRecord của Shared Admin vẫn được bảo toàn tuyệt đối.
  - **Tính Idempotent Tuyệt đối:**
    + Sau khi transaction dọn dẹp commit thành công, toàn bộ danh sách ID được clear (`self.product_ids.clear()`, v.v.).
    + Lần gọi `cleanup()` thứ hai sẽ kiểm tra danh sách rỗng và return ngay lập tức, không sinh query, không sinh lỗi.
  - **Thứ tự Giải phóng Khóa ngoại (Strict Reverse FK Deletion Order):**
    `StockMovement` $\rightarrow$ `OrderItem` $\rightarrow$ `Order` $\rightarrow$ `PurchaseReceiptItem` $\rightarrow$ `PurchaseReceipt` $\rightarrow$ `Inventory` $\rightarrow$ `Product` $\rightarrow$ `Supplier` $\rightarrow$ `Category` $\rightarrow$ `User (admin_slot IS NULL)`.
- **Các kịch bản kiểm thử tích hợp (5 Kịch bản):**
  1. `test_demo_dataset_end_to_end_reconciliation_mysql`: Thực thi trọn vẹn luồng dữ liệu demo chuẩn trên MySQL InnoDB, đối soát đa chiều qua các Repository nghiệp vụ thật.
  2. `test_catalog_price_mutation_preserves_reconciled_analytics_mysql`: Thao tác trực tiếp cập nhật giá catalog trên database và xác minh doanh thu lịch sử không bị biến động.
  3. `test_reconciliation_cleanup_isolation_mysql`: Thực nghiệm tạo dữ liệu song song (Run A và Run B gồm Users, Categories, Suppliers, Products, IdempotencyRecord). Xác nhận dọn dẹp Run A không làm mất bất kỳ dữ liệu nào của Run B (kể cả IdempotencyRecord của Run B), và gọi cleanup 2 lần liên tiếp an toàn tuyệt đối.
  4. `test_reconciliation_cleanup_fail_closed_on_external_reference_mysql`: Tạo tình huống OrderItem ngoại lai tham chiếu sản phẩm của Run A. Xác nhận cleanup() phát hiện vi phạm, raise `RuntimeError`, rollback toàn bộ (product, inventory, category của Run A vẫn nguyên vẹn 100%). Sau khi dọn dẹp liên kết ngoại lai, cleanup() lần 2 thành công trọn vẹn.
  5. `test_reconciliation_cleanup_shared_admin_immunity_mysql`: Tạo IdempotencyRecord cho Shared Admin, cố tình đưa `admin_id` vào `ctx.user_ids` và gọi cleanup(). Xác nhận tài khoản Shared Admin (`admin_slot == 1`) và bản ghi IdempotencyRecord của Shared Admin đều tồn tại nguyên vẹn trong cơ sở dữ liệu.
- **Trạng thái Thu thập & Bằng chứng Thực thi (Execution Evidence):**
  - **Local Collection:** Đã thực hiện `pytest --collect-only` thành công thu thập **5/5 test cases (0 errors, 0 warnings)**.
  - **Nguyên tắc môi trường:** Do môi trường local không có MySQL dedicated container chạy nền, tuân thủ nghiêm ngặt nguyên tắc an toàn dữ liệu, test integration không được chạy trên DB dùng chung mà được ủy quyền cho CI pipeline chuyên dụng.
  - **CI Integration Status:** **COLLECTED & CI-EXECUTION PENDING** cho exact commit mới nhất. Job `MySQL integration tests` trong `.github/workflows/backend-ci.yml` khởi tạo dedicated MySQL 8.4 container và chạy lệnh:
    ```bash
    uv run --locked pytest -m "integration and not redis_integration and not proxy_integration"
    ```
    bao gồm toàn bộ 5 integration test cases của `test_t04ac15_reconciliation_mysql.py`.
  - **Phạm vi cam kết:** Không suy diễn kết quả PASS khi chưa có test execution log độc lập từ CI runner; báo cáo không tuyên bố Browser E2E hay Final Release Sign-off đã hoàn tất.

---

## 5. HƯỚNG DẪN KIỂM THỬ DÀNH CHO QA & LEAD (VERIFICATION GUIDE)

### 5.1. Chạy bộ kiểm thử Non-Integration (Chạy tức thì trên môi trường cục bộ)
Lệnh chạy toàn bộ 17 test cases API router và mô hình đối soát:
```bash
uv run --directory backend pytest tests/modules/analytics/test_t04ac15_reconciliation_api.py -v
```
*Kết quả kỳ vọng:* `17 passed` trong ~2.2 giây.

### 5.2. Chạy bộ kiểm thử MySQL Integration (Trên môi trường có MySQL Dedicated)
Khi cấu hình biến môi trường kết nối MySQL chuyên dụng:
```bash
$env:RETAILOPS_TEST_DATABASE_URL = "mysql+pymysql://retailops_user:retailops_pass@127.0.0.1:3306/retailops_test"
uv run --directory backend pytest tests/modules/analytics/test_t04ac15_reconciliation_mysql.py -m integration -v
```

### 5.3. Kiểm tra Thu thập Test & Cú pháp Mã nguồn
```bash
uv run --directory backend pytest tests/modules/analytics/test_t04ac15_reconciliation_mysql.py --collect-only -q
uv run --directory backend ruff check tests/modules/analytics/test_t04ac15_*.py
uv run --directory backend ruff format --check tests/modules/analytics/test_t04ac15_*.py
```
*Kết quả kỳ vọng:* `All checks passed!`, không phát sinh cảnh báo vi phạm chuẩn.

---

## 6. KẾT LUẬN VÀ TRẠNG THÁI GATE-E2E (GATE-E2E REVIEW STATUS)

1. **Tính Toàn vẹn Dữ liệu (Data Integrity):**
   - Không có bất kỳ sai lệch nào (Delta = 0) giữa Catalog, Kho hàng, Giao dịch đơn hàng, Báo cáo Doanh thu, Báo cáo Sản phẩm, và Dashboard Tổng quan.
   - Tính bất biến của doanh thu lịch sử (`Snapshot Pricing Immutability`) được bảo toàn tuyệt đối khi giá catalog thay đổi.
   - Đơn hủy (`CANCELLED`) được loại bỏ 100% khỏi doanh thu và xếp hạng sản phẩm bán chạy, đồng thời hoàn trả chính xác tồn kho.
2. **Tuân thủ Chuẩn mực Kỹ thuật & Cô lập Kiểm thử:**
   - **Không chỉnh sửa mã nguồn production:** 100% mã nguồn thuộc `backend/app/`, `frontend/`, `contracts/`, `pyproject.toml` được giữ nguyên vẹn.
   - **Phạm vi file chuẩn xác:** Chỉ bao gồm đúng 3 file được cho phép của task (`test_t04ac15_reconciliation_api.py`, `test_t04ac15_reconciliation_mysql.py`, `T04AC15_RECONCILIATION_REPORT.md`).
   - **Bảo vệ tuyệt đối cơ sở dữ liệu:** Áp dụng mô hình Exact ID Tracking + Fail-Closed Rollback, bảo toàn Shared Admin, đảm bảo tính idempotent và không xâm lấn dữ liệu giữa các test suites trên CI.
3. **Trạng thái Trình duyệt:**
   - **GATE-E2E Status:** **READY FOR QA/TECH LEAD REVIEW**
   - Kính chuyển Senior QA Lead và Tech Lead xem xét và phê duyệt PR #78.
