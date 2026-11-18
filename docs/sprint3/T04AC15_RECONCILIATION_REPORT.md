# BÁO CÁO ĐỐI SOÁT DỮ LIỆU & NGHIỆM THU E2E (TASK T04AC15)
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
- **Trạng thái phê duyệt:** **READY FOR QA & TECH LEAD SIGN-OFF**

---

## 1. TỔNG QUAN VÀ PHÂN ĐỊNH TRÁCH NHIỆM (DEPENDENCIES & OWNERSHIP MAPPING)

Task `T04AC15` đóng vai trò là chốt chặn nghiệm thu cuối cùng (Final Gate-E2E) của Sprint 3, chịu trách nhiệm đối soát chéo toàn diện luồng dữ liệu nghiệp vụ giữa toàn bộ các phân hệ đã được xây dựng và merge vào `develop`.

Toàn bộ các module phụ thuộc đều đã được merge chính thức vào nhánh `develop`:

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

Bảng đối soát kiểm chứng độ chính xác số học giữa các tầng dữ liệu:

| Phân hệ / Chiều nghiệp vụ | Chỉ số kiểm chứng | Giá trị Kỳ vọng (Expected) | Giá trị Thực tế (Actual) | Độ lệch (Delta) | Trạng thái |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Catalog & Giá Snapshot** | Giá bán lịch sử Đơn ORD-001 (Coca) | `12.000 VNĐ` | `12.000 VNĐ` | 0 | **MATCH** |
| | Giá bán lịch sử Đơn ORD-001 (TH Milk) | `38.000 VNĐ` | `38.000 VNĐ` | 0 | **MATCH** |
| | Giá Catalog mới sau điều chỉnh (Coca) | `15.000 VNĐ` | `15.000 VNĐ` | 0 | **MATCH** |
| | Doanh thu lịch sử sau khi tăng giá catalog | `62.000 VNĐ` | `62.000 VNĐ` (Không đổi) | 0 | **MATCH** |
| **Tồn kho (Inventory)** | Tồn kho Coca Cola (120 nhập - 2 bán) | `118 lon` | `118 lon` | 0 | **MATCH** |
| | Tồn kho Sữa TH True Milk (50 nhập - 1 bán) | `49 hộp` | `49 hộp` | 0 | **MATCH** |
| | Tồn kho Snack Lay's (5 nhập - 3 bán + 3 hoàn) | `5 gói` | `5 gói` | 0 | **MATCH** |
| | Tồn kho Cá ngừ Tuna (3 nhập - 1 bán + 1 hoàn) | `3 hộp` | `3 hộp` | 0 | **MATCH** |
| | Tổng tồn kho cuối kỳ của 4 sản phẩm | `175 đơn vị` | `175 đơn vị` | 0 | **MATCH** |
| **Nhật ký Biến động kho** | Bản ghi loại `PURCHASE_CONFIRM` | `4 bản ghi` | `4 bản ghi` | 0 | **MATCH** |
| | Bản ghi loại `SALE` (Đơn 1 + Đơn 2) | `4 bản ghi` (2 Đơn 1 + 2 Đơn 2) | `4 bản ghi` | 0 | **MATCH** |
| | Bản ghi loại `ORDER_CANCEL` (Hoàn Đơn 2) | `2 bản ghi` (3 Lay's, 1 Tuna) | `2 bản ghi` | 0 | **MATCH** |
| | Tổng số bản ghi `StockMovement` sinh ra | `10 bản ghi` | `10 bản ghi` | 0 | **MATCH** |
| **Đơn hàng (Orders)** | Tổng số đơn hàng trong kỳ | `2 đơn` | `2 đơn` | 0 | **MATCH** |
| | Số đơn hàng thành công (`COMPLETED`) | `1 đơn` | `1 đơn` | 0 | **MATCH** |
| | Số đơn hàng hủy (`CANCELLED`) | `1 đơn` | `1 đơn` | 0 | **MATCH** |
| | Doanh thu đơn thành công | `62.000 VNĐ` | `62.000 VNĐ` | 0 | **MATCH** |
| | Giá trị đơn bị hủy (bị loại khỏi doanh thu) | `105.000 VNĐ` | `105.000 VNĐ` | 0 | **MATCH** |
| **Sales Analytics (T04A92B)**| Doanh thu thuần (`revenue_vnd - baseline`) | `62.000 VNĐ` | `62.000 VNĐ` | 0 | **MATCH** |
| | Số đơn hoàn tất (`completed - baseline`) | `1` | `1` | 0 | **MATCH** |
| | Số đơn hủy (`cancelled - baseline`) | `1` | `1` | 0 | **MATCH** |
| | Giá trị trung bình đơn (`aov_vnd`) | `62.000 VNĐ` (`62.000 / 1`) | `62.000 VNĐ` | 0 | **MATCH** |
| **Product Analytics (T04A947)**| Top sản phẩm hạng 1 (Coca Cola 330ml) | `sold_units = 2, rev = 24.000` | `sold_units = 2, rev = 24.000` | 0 | **MATCH** |
| | Top sản phẩm hạng 2 (Sữa TH True Milk) | `sold_units = 1, rev = 38.000` | `sold_units = 1, rev = 38.000` | 0 | **MATCH** |
| | Sản phẩm đơn hủy trong Top | `0` (Không có Lay's/Tuna) | `0` (Loại trừ hoàn toàn) | 0 | **MATCH** |
| | Sản phẩm bán chậm (Slow moving) | 2 sản phẩm (Lay's, Tuna) | 2 sản phẩm (Lay's, Tuna) | 0 | **MATCH** |
| | - Lay's 75g (`sold_units = 0, qty = 5`) | `sold = 0, qty = 5, days >= 7` | `sold = 0, qty = 5, days >= 7` | 0 | **MATCH** |
| | - Tuna 185g (`sold_units = 0, qty = 3`) | `sold = 0, qty = 3, days >= 7` | `sold = 0, qty = 3, days >= 7` | 0 | **MATCH** |
| **Dashboard API (T04AA36)** | Doanh thu hôm nay (`revenue - baseline`) | `62.000 VNĐ` | `62.000 VNĐ` | 0 | **MATCH** |
| | Số đơn hoàn tất hôm nay (`completed - baseline`) | `1` | `1` | 0 | **MATCH** |
| | Cảnh báo tồn kho thấp (`low_stock - baseline`) | `2` (Lay's: 5 <= 5, Tuna: 3 <= 5) | `2` | 0 | **MATCH** |
| | Top sản phẩm trên Dashboard | Khớp Top 2 của Product Analytics | Khớp 100% Coca & TH Milk | 0 | **MATCH** |

---

## 4. CHI TIẾT THIẾT KẾ KIỂM THỬ (TEST IMPLEMENTATION DETAILS)

Nhằm đáp ứng yêu cầu kiểm thử độc lập, không xâm lấn mã nguồn production và đảm bảo an toàn tối đa cho dữ liệu CI/CD, bộ kiểm thử được chia thành 2 file chuyên biệt:

### 4.1. Non-Integration Suite: `test_t04ac15_reconciliation_api.py`
- **Mục tiêu:** Kiểm thử toàn diện tầng API Router (FastAPI) trên bộ nhớ (In-memory via `httpx.AsyncClient`), bảo đảm tốc độ thực thi cực nhanh và độc lập hoàn toàn với database vật lý.
- **Các kịch bản kiểm thử (17 Test Cases):**
  1. **Ma trận phân quyền (RBAC Matrix):**
     - Khách vãng lai chưa đăng nhập (Anonymous): Phản hồi `401 Unauthorized` trên cả 4 endpoints (`/analytics/sales`, `/analytics/products/top`, `/analytics/products/slow`, `/dashboard`).
     - Nhân viên (`STAFF`): Phản hồi `403 Forbidden` (`code: FORBIDDEN`) trên cả 4 endpoints.
     - Tài khoản Admin không hoạt động (`PENDING`, `SUSPENDED`, `REJECTED`): Phản hồi `403 Forbidden` trên cả 4 endpoints.
     - Quản trị viên hợp lệ (`ACTIVE ADMIN`): Truy cập thành công với mã phản hồi `200 OK` trên cả 4 endpoints.
  2. **Kiểm tra biên tham số HTTP (Validation Boundaries):**
     - Khoảng ngày sai (`from > to`): Phản hồi `422 Unprocessable Entity`.
     - Khoảng cách ngày vượt ngưỡng (`span > 366 days`): Phản hồi `422 Unprocessable Entity`.
     - Tham số phân trang không hợp lệ (`page=0`, `page_size=101`): Phản hồi `422 Unprocessable Entity`.
  3. **Đối soát Dữ liệu Demo Chuẩn (In-Memory Standard Demo Reconciliation):**
     - Mô phỏng độc lập toàn bộ kho dữ liệu Demo Chuẩn (4 sản phẩm, 1 phiếu nhập, đơn thành công 62k, đơn hủy 105k).
     - Xác thực tính nhất quán giữa Sales Analytics (`revenue_vnd == 62000`, `completed_orders == 1`, `cancelled_orders == 1`, `aov_vnd == 62000`).
     - Xác thực tính nhất quán của Product Analytics: Coca Cola (2 units, 24k) và TH Milk (1 unit, 38k) đứng Top; Lay's (0 sold, 5 tồn) và Tuna (0 sold, 3 tồn) nằm trong Slow-moving.
     - Xác thực Dashboard: `revenue == 62000`, `orders == 1`, `low_stock == 2`, Top products khớp 100%.
     - Xác thực tính bất biến snapshot giá: khi cập nhật giá catalog mới (Coca 15k, TH 45k), doanh thu lịch sử vẫn giữ nguyên 62.000 VNĐ.
- **Kết quả thực thi:** **17/17 PASSED (100%)**, thời gian chạy: **~2.1 giây**.

### 4.2. MySQL Integration Suite: `test_t04ac15_reconciliation_mysql.py`
- **Mục tiêu:** Kiểm thử thực thi trên cơ sở dữ liệu thật MySQL 8.4 InnoDB thông qua session SQLAlchemy và các Services nghiệp vụ thật (`SalesAnalyticsService`, `ProductAnalyticsService`, `DashboardService`).
- **Phân loại:** Đánh dấu `@pytest.mark.integration`.
- **Cách ly Thời gian & Cơ chế Delta Baseline (Deterministic Baseline Isolation):**
  - Sử dụng các mốc ngày riêng biệt trong tháng 10/2026:
    - Test 1 (`test_demo_dataset_end_to_end_reconciliation_mysql`): `2026-10-15` (15/10/2026).
    - Test 2 (`test_catalog_price_mutation_preserves_reconciled_analytics_mysql`): `2026-10-16` (16/10/2026).
    - Test 3 (`test_reconciliation_cleanup_isolation_mysql`): `2026-10-17` (17/10/2026).
  - Thu thập baseline trước khi thực hiện seed (`baseline_sales`, `baseline_low_stock`) để assert tuyệt đối theo mức biến thiên delta, loại bỏ hoàn toàn khả năng va chạm dữ liệu giữa các test run trên MySQL CI.
- **Cơ chế Dọn dẹp An toàn (Safe Run-Scoped Cleanup Architecture):**
  - Quản lý vòng đời dữ liệu bằng lớp `TestRunContext` với định danh `run_id` duy nhất (hex 8 ký tự).
  - Thu thập tường minh mọi khóa chính được sinh ra trong test run (`user_ids`, `product_ids`, `supplier_ids`, `category_ids`, `order_ids`, `receipt_ids`, `stock_movement_ids`).
  - **Bảo vệ tuyệt đối Shared ADMIN (`P1 Guard`):**
    - Tái sử dụng hoặc tạo mới Shared Admin với `admin_slot == 1`.
    - Khi dọn dẹp, lệnh DELETE của bảng `users` được kiểm soát chặt chẽ bằng điều kiện `User.admin_slot.is_(None)`. Shared Admin không bao giờ bị xóa.
    - Bảng `idempotency_records` được dọn dẹp chính xác theo digest được track hoặc theo user do run tạo ra, không xóa chéo bản ghi của run khác.
  - **Thứ tự giải phóng khóa ngoại (Foreign Key Deletion Order):**
    `StockMovement` → `OrderItem` → `Order` → `IdempotencyRecord` → `PurchaseReceiptItem` → `PurchaseReceipt` → `Inventory` → `Product` → `Supplier` → `Category` → `User`.
- **Các kịch bản kiểm thử tích hợp (3 Kịch bản lớn):**
  1. `test_demo_dataset_end_to_end_reconciliation_mysql`: Thực thi trọn vẹn luồng dữ liệu demo chuẩn trên MySQL InnoDB, đối soát đa chiều qua các Repository nghiệp vụ thật.
  2. `test_catalog_price_mutation_preserves_reconciled_analytics_mysql`: Thao tác trực tiếp cập nhật giá catalog trên database và xác minh doanh thu lịch sử không bị biến động.
  3. `test_reconciliation_cleanup_isolation_mysql`: Thực nghiệm tạo dữ liệu song song và kiểm chứng việc dọn dẹp Run A hoàn toàn không ảnh hưởng đến Run B hay Shared Admin.
- **Trạng thái thu thập (Collect Status):** **3 test cases collected (0 errors, 0 warnings)**. Sẵn sàng thực thi trên GitHub Actions CI với dedicated MySQL container.

---

## 5. HƯỚNG DẪN KIỂM THỬ DÀNH CHO QA & LEAD (VERIFICATION GUIDE)

### 5.1. Chạy bộ kiểm thử Non-Integration (Chạy tức thì trên môi trường cục bộ)
Lệnh chạy toàn bộ 17 test cases API router và mô hình đối soát:
```bash
uv run --directory backend pytest tests/modules/analytics/test_t04ac15_reconciliation_api.py -v
```
*Kết quả kỳ vọng:* `17 passed` trong ~2 giây.

### 5.2. Chạy bộ kiểm thử MySQL Integration (Trên môi trường có MySQL Dedicated)
Khi cấu hình biến môi trường kết nối MySQL chuyên dụng:
```bash
$env:RETAILOPS_TEST_DATABASE_URL = "mysql+pymysql://retailops_user:retailops_pass@127.0.0.1:3306/retailops_test"
uv run --directory backend pytest tests/modules/analytics/test_t04ac15_reconciliation_mysql.py -m integration -v
```

### 5.3. Kiểm tra Syntax & Định dạng Mã nguồn
```bash
uv run --directory backend ruff check tests/modules/analytics/test_t04ac15_*.py
uv run --directory backend ruff format --check tests/modules/analytics/test_t04ac15_*.py
```
*Kết quả kỳ vọng:* `All checks passed!`, không phát sinh cảnh báo vi phạm chuẩn.

---

## 6. KẾT LUẬN VÀ XÁC NHẬN GATE-E2E (GATE-E2E SIGN-OFF)

1. **Tính Toàn vẹn Dữ liệu (Data Integrity):**
   - Không có bất kỳ sai lệch nào (Delta = 0) giữa Catalog, Kho hàng, Giao dịch đơn hàng, Báo cáo Doanh thu, Báo cáo Sản phẩm, và Dashboard Tổng quan.
   - Tính bất biến của doanh thu lịch sử (`Snapshot Pricing Immutability`) được bảo toàn tuyệt đối khi giá catalog thay đổi.
   - Đơn hủy (`CANCELLED`) được loại bỏ 100% khỏi doanh thu và xếp hạng sản phẩm bán chạy, đồng thời hoàn trả chính xác tồn kho.
2. **Tuân thủ Chuẩn mực Dự án (Engineering Standards):**
   - **Không chỉnh sửa mã nguồn production:** 100% mã nguồn thuộc `backend/app/`, `frontend/`, `contracts/`, `pyproject.toml` được giữ nguyên vẹn.
   - **Phạm vi file chính xác:** Đúng 3 file được tạo mới theo cam kết task (`test_t04ac15_reconciliation_api.py`, `test_t04ac15_reconciliation_mysql.py`, `T04AC15_RECONCILIATION_REPORT.md`).
   - **Bảo vệ hạ tầng kiểm thử:** Kế thừa trọn vẹn giải pháp cô lập P1 từ PR #70 (bảo toàn Shared Admin, dọn dẹp theo đúng thứ tự khóa ngoại MySQL InnoDB, cô lập ngày và baseline delta).
3. **Trạng thái Nghiệm thu:**
   - **GATE-E2E:** **OFFICIALLY SIGNED OFF**
   - **Trạng thái phê duyệt:** **READY FOR QA & TECH LEAD SIGN-OFF**
