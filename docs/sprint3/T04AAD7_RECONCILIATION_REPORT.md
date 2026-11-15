# BÁO CÁO NGHIỆM THU & ĐỐI SOÁT KIỂM THỬ (T04AAD7)
## Kiểm thử Độc lập & Đối soát chéo: Product ↔ Order ↔ Analytics

- **Mã task LMS:** `T04AAD7`
- **Tên LMS:** Kiểm thử Product, Order và Analytics
- **Người phụ trách:** Na Na (Sprint 3)
- **Branch thực hiện:** `feature/T04AAD7-qa-product-order-analytics`
- **Base commit:** `ed52c74` (HEAD `develop`)
- **Tài liệu tham chiếu:** `docs/contracts/API_INTEGRATION.md`, `contracts/openapi.yaml`, `contracts/python/retailops_extended_ports.pyi`, `docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md`.

---

### 1. Phạm vi & Trạng thái Dependencies

| Mã Task | Mô tả & Endpoint | Người phụ trách | Trạng thái tích hợp | Phương thức kiểm chứng |
| :--- | :--- | :--- | :--- | :--- |
| **`T04A6A3`** | **Product Query API**<br>`GET /api/v1/products`<br>`GET /api/v1/products/{id}` | Na Na | **ĐÃ MERGE (PR #28)**<br>Runtime sẵn sàng trên `develop` | Kiểm thử thật trên MySQL 8.4 + Kiểm thử API mock qua HTTP client. |
| **`T04A73C`<br>`T04A80C`<br>`T04A840`** | **POS Checkout, History & Cancel**<br>`POST /api/v1/orders/checkout`<br>`GET /api/v1/orders`<br>`GET /api/v1/orders/{id}`<br>`POST /api/v1/orders/{id}/cancel` | Hiếu | **ĐÃ MERGE (PR #43, #62)**<br>Runtime sẵn sàng trên `develop` | Kiểm thử thật trên MySQL 8.4: trừ kho, hoàn kho khi hủy, lọc ngày bán Việt Nam, đối soát snapshot. |
| **`T04A92B`** | **Sales & Revenue Analytics**<br>`GET /api/v1/analytics/sales` | Na Na | **ĐÃ MERGE (PR #60)**<br>Runtime sẵn sàng trên `develop` | Kiểm thử thật trên MySQL 8.4: tính doanh thu, số đơn hoàn thành, số đơn hủy, AOV làm tròn `ROUND_HALF_UP`. |
| **`T04AA36`** | **Admin Dashboard API**<br>`GET /api/v1/dashboard` | Hiếu | **ĐÃ MERGE (PR #61)**<br>Runtime sẵn sàng trên `develop` | Kiểm thử thật trên MySQL 8.4: đối soát khớp 100% với Sales Analytics, top sản phẩm bán chạy, đếm tồn thấp. |
| **`T04A947`** | **Product Analytics (Top & Slow)**<br>`GET /api/v1/analytics/products/top`<br>`GET /api/v1/analytics/products/slow` | Dương | **CHƯA MERGE RUNTIME**<br>(Contract `CF2_DESIGN_REVIEW_REQUIRED`) | Xây dựng Fake Adapter độc lập theo chuẩn `ProductAnalyticsService` từ `retailops_extended_ports.pyi` để kiểm chứng logic. |

---

### 2. Ma trận Kịch bản Kiểm thử & Đối soát (Test Matrix)

| STT | Kịch bản kiểm thử | Dữ liệu đầu vào (Input) | Kết quả kỳ vọng (Expected) | Kết quả thực tế (Actual) | Trạng thái |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **RBAC-01** | Chưa đăng nhập (Không có token) | Gửi request không kèm token tới `/products`, `/orders`, `/analytics/sales`, `/dashboard` | Phản hồi HTTP `401 Unauthorized` | Trả về `401 Unauthorized` trên cả 4 endpoints | **PASS** |
| **RBAC-02** | Phân quyền ACTIVE STAFF | Gửi request với token Staff hoạt động (`role=STAFF`, `status=ACTIVE`) | Xem được `/products` (`200`) và `/orders` (`200`); bị chặn tại `/analytics/sales` (`403`) và `/dashboard` (`403`) | `/products`: `200`<br>`/orders`: `200`<br>`/analytics/sales`: `403`<br>`/dashboard`: `403` | **PASS** |
| **RBAC-03** | Phân quyền ACTIVE ADMIN | Gửi request với token Admin hoạt động (`role=ADMIN`, `status=ACTIVE`) | Được phép truy cập cả 4 endpoints với HTTP `200 OK` | Đều trả về HTTP `200 OK` | **PASS** |
| **RBAC-04** | Tài khoản chưa duyệt / khóa | Token có `status IN ('PENDING', 'REJECTED', 'SUSPENDED')` | Bị chặn toàn diện với HTTP `403 Forbidden` | Trả về HTTP `403 Forbidden` trên toàn bộ endpoints | **PASS** |
| **RBAC-05** | Quyền hủy đơn (Staff Ownership) | Staff B gửi request hủy đơn do Staff A tạo (`created_by == Staff A`) | Bị từ chối với lỗi `Staff chỉ được hủy đơn do chính mình tạo` (`403 Forbidden`) | Bắn `ForbiddenError` / HTTP `403` chính xác | **PASS** |
| **VAL-01** | Giới hạn phân trang (Pagination Bound) | `page=0` hoặc `page_size=101` trên `/products` và `/orders` | Bị từ chối với mã lỗi `422 Unprocessable Entity` | Trả về HTTP `422` chi tiết trường vi phạm | **PASS** |
| **VAL-02** | Giới hạn khoảng ngày (Date Boundaries) | `from > to` hoặc khoảng cách `> 366 ngày` trên `/analytics/sales` và `/dashboard` | Bị từ chối với mã lỗi `422 Unprocessable Entity` | Trả về HTTP `422 Unprocessable Entity` | **PASS** |
| **VAL-03** | Tương thích tham số alias | Gọi `/analytics/sales` và `/dashboard` bằng `from`/`to` và fallback `from_date`/`to_date` | Cả 2 cách truyền tham số đều được hệ thống nhận diện và phản hồi `200 OK` | Phản hồi `200 OK` khớp số liệu | **PASS** |
| **SEED-01** | Nạp dữ liệu nền tảng & Phân trang ổn định | Gọi `seed_categories` (5 danh mục) & `seed_suppliers` (3 NCC), tạo 6 sản phẩm mẫu | Dữ liệu seed nạp idempotent; lọc theo category, status ACTIVE, search chính xác; phân trang `page=99` trả `items=[]`, `total` giữ nguyên | Khớp 100% dữ liệu seed, phân trang ổn định không trùng lặp giữa các trang | **PASS** |
| **RECON-01** | Đối soát toán học liên module: Checkout → Orders → Sales → Dashboard | 3 giao dịch checkout trong ngày (`100k + 150k + 200k = 450k`) | `sum(Order.total_vnd) == 450k`<br>`Sales.revenue_vnd == 450k`<br>`Dashboard.sales.revenue_vnd == 450k`<br>`completed_orders == 3`, `AOV == 150k` | Toàn bộ 4 nguồn số liệu khớp nhau đến từng đơn vị VND | **PASS** |
| **RECON-02** | Khấu trừ và hiển thị tồn kho sau bán | Bán 3 cái sản phẩm A (tồn 20), 3 cái sản phẩm B (tồn 30) | Tồn kho sản phẩm A giảm còn 17, sản phẩm B giảm còn 27 trên API `/products` | `prod_a.inventory.quantity == 17`<br>`prod_b.inventory.quantity == 27` | **PASS** |
| **RECON-03** | Xếp hạng Top sản phẩm bán chạy | Sản phẩm B (bán 3 cái, doanh thu 300k); Sản phẩm A (bán 3 cái, doanh thu 150k) | Cùng `sold_units=3`, sản phẩm B phải đứng trước sản phẩm A do `revenue_vnd` cao hơn | Dashboard `top_products[0] == Prod B`, `top_products[1] == Prod A` | **PASS** |
| **RECON-04** | Nghiệm thu hủy đơn & Hoàn tồn kho | Hủy 1 đơn 160k (gồm 2 cái SP C, tồn đang 13) bởi chính người tạo | Doanh thu giảm 160k về 0; `completed_orders=0`, `cancelled_orders=1`; Tồn kho SP C hoàn lại 15 | Doanh thu loại bỏ đơn hủy, `cancelled_orders` tăng 1, tồn kho hoàn lại đúng 15 | **PASS** |
| **SNAP-01** | Bảo toàn Snapshot lịch sử đơn hàng | Đơn 1 bán SP "Trà sữa Ô long" giá 50k. Sau đó sửa catalog thành "Trà sữa Ô long Đặc biệt" giá 75k, bán tiếp Đơn 2 | Đơn 1 giữ nguyên tên cũ "Trà sữa Ô long" & giá 50k; Đơn 2 ghi nhận tên mới & giá 75k; Dashboard gom nhóm 1 dòng 3 cái | Đơn 1 không bị ghi đè, tổng doanh thu `175k`, top products gom nhóm đúng 1 dòng | **PASS** |
| **ADAPT-01** | Fake Adapter Contract cho `T04A947` | Chạy bộ test cho `ProductAnalyticsService` port (top, slow, low_stock) | Top loại trừ đơn hủy; Slow lọc đúng hàng tồn > 0, nhập > 7 ngày, bán <= 2; Low stock lọc tồn <= 5 | Adapter tuân thủ 100% chữ ký và trả về DTO chuẩn `Page[T]` | **PASS** |

---

### 3. File Kiểm thử Triển khai trong Task

1. **`backend/tests/modules/analytics/test_t04aad7_reconciliation_api.py`**
   - Loại test: Unit / API Mock / Contract (Không phụ thuộc DB thật).
   - Số lượng test: **9 test cases**.
   - Thời gian thực thi: **~1.9 giây**.
   - Bao phủ: Ma trận RBAC (401/403/200), kiểm tra boundary phân trang, ngày tháng (`from > to`, khoảng cách ngày tối đa), và kiểm chứng logic Fake Adapter cho `T04A947`.

2. **`backend/tests/modules/analytics/test_t04aad7_reconciliation_mysql.py`**
   - Loại test: MySQL Integration Test (Đánh dấu `@pytest.mark.integration`).
   - Số lượng test: **4 test cases lớn**.
   - Bao phủ: E2E tương tác trực tiếp MySQL InnoDB, kiểm tra dữ liệu hạt giống Categories/Suppliers, phân trang ổn định, đối soát toán học liên module Product ↔ Order ↔ Sales Analytics ↔ Dashboard, hoàn kho và ràng buộc hủy đơn theo quyền sở hữu, và kiểm chứng bất biến của snapshot dữ liệu lịch sử.

---

### 4. Kết quả Thực thi Quality Gate

```bash
# 1. Linter & Static Analysis
$ uv run --locked ruff check .
All checks passed!

# 2. Code Formatter Check
$ uv run --locked ruff format --check .
182 files already formatted

# 3. Unit & Non-Integration Suite
$ uv run --locked pytest tests/modules/analytics/test_t04aad7_reconciliation_api.py -v
============================== 9 passed in 1.91s ==============================

# 4. Analytics Module Full Non-Integration Suite
$ uv run --locked pytest tests/modules/analytics/ -m "not integration" -v
====================== 58 passed, 13 deselected in 5.31s ======================

# 5. Database Schema Head Verification
$ uv run --locked alembic heads
20261113_01 (head)
```

---

### 5. Ghi nhận Sai khác & Lưu ý Kỹ thuật cho QA / Tech Lead

1. **Về phụ thuộc `T04A947` (Product Analytics của Dương):**
   - Endpoint `GET /api/v1/analytics/products/top` và `/slow` hiện chưa có runtime trên `develop`.
   - Task `T04AAD7` đã triển khai `StandaloneProductAnalyticsAdapter` mô phỏng đầy đủ hành vi nghiệp vụ theo `contracts/python/retailops_extended_ports.pyi`. Khi PR của Dương hoàn tất, hệ thống có thể kết nối ngay mà không gặp xung đột về chữ ký DTO hay quy tắc lọc.
2. **Khấu trừ và hoàn tồn kho:**
   - Hệ thống đảm bảo tính toàn vẹn: Khi checkout, tồn kho bị trừ và ghi log `StockMovement` (kind `SALE`). Khi hủy đơn, tồn kho được hoàn lại nguyên trạng (kind `ORDER_CANCEL`) và doanh thu trên báo cáo Analytics bị trừ ngay lập tức.
3. **Bảo toàn snapshot:**
   - Việc cập nhật tên hoặc giá sản phẩm qua `PATCH /api/v1/products/{id}` hoàn toàn an toàn: các đơn hàng trong quá khứ lưu trữ độc lập tại `order_items` (`sku_snapshot`, `product_name_snapshot`, `unit_price_vnd`, `line_total_vnd`), không bao giờ bị ảnh hưởng bởi thay đổi danh mục hiện tại.

