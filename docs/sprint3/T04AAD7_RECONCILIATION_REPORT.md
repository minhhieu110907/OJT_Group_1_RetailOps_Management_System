# BÁO CÁO NGHIỆM THU & ĐỐI SOÁT KIỂM THỬ (T04AAD7)
## Kiểm thử Độc lập & Đối soát chéo: Product ↔ Order ↔ Analytics

- **Mã task LMS:** `T04AAD7`
- **Tên LMS:** Kiểm thử Product, Order và Analytics
- **Người phụ trách:** Na Na (Sprint 3)
- **Branch thực hiện:** `feature/T04AAD7-qa-product-order-analytics`
- **Base commit:** `ed52c74` (HEAD `develop`)
- **Tài liệu tham chiếu:** `docs/contracts/API_INTEGRATION.md`, `contracts/openapi.yaml`, `contracts/python/retailops_extended_ports.pyi`, `docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md`.
- **Trạng thái phê duyệt:** **READY FOR REVIEW**

---

### 1. Phân định Trách nhiệm & Trạng thái Dependencies (Ownership Mapping)

Bảng đối soát nguồn gốc mã nguồn và trách nhiệm kỹ thuật theo chuẩn cấu trúc nhóm:

| Mã Task | Mô tả & Endpoint | Người phụ trách | PR & Trạng thái Git | Trạng thái tích hợp | Phương thức kiểm chứng trong T04AAD7 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`T04A6A3`** | **Product Query API**<br>`GET /api/v1/products`<br>`GET /api/v1/products/{id}` | Na Na | **PR #28**<br>(Merged to `develop`) | **RUNTIME SẴN SÀNG** | Kiểm thử MySQL 8.4: Danh mục nền tảng, phân trang ổn định, bảo toàn snapshot giá & tên khi cập nhật catalog. |
| **`T04A73C`** | **POS Checkout API**<br>`POST /api/v1/orders/checkout` | Hiếu | **PR #43**<br>(Merged to `develop`) | **RUNTIME SẴN SÀNG** | Option A: Tích hợp trực tiếp `CheckoutService(InventoryService(), clock=...)` trên MySQL 8.4, trừ tồn kho thật, tăng `stock_version`, ghi nhận `StockMovement` (kind `SALE`). |
| **`T04A80C`** | **Order Cancellation API**<br>`POST /api/v1/orders/{id}/cancel` | Hiếu | **PR #52**<br>(Merged to `develop`) | **RUNTIME SẴN SÀNG** | Tích hợp trực tiếp `OrderService.cancel` trên MySQL 8.4: Kiểm tra RBAC ownership (Staff B bị 403 khi hủy đơn Staff A), hoàn tồn kho thật, ghi `StockMovement` (kind `ORDER_CANCEL`). |
| **`T04A840`** | **Order History & Detail API**<br>`GET /api/v1/orders`<br>`GET /api/v1/orders/{id}` | Hiếu | **PR #56**<br>(Merged to `develop`) | **RUNTIME SẴN SÀNG** | Kiểm thử lọc đơn theo ngày VN (`from_date`, `to_date`), tính tổng doanh thu đơn hoàn thành, loại trừ đơn hủy. |
| *Lưu ý: PR #62* | *POS Frontend / Orders UI* | *Phú / Hiếu* | *PR #62*<br>*(Merged)* | *FRONTEND UI ONLY* | *Không dùng PR #62 làm bằng chứng kiểm thử backend (đây là giao diện người dùng).* |
| **`T04A92B`** | **Sales & Revenue Analytics**<br>`GET /api/v1/analytics/sales` | Na Na | **PR #60**<br>(Merged to `develop`) | **RUNTIME SẴN SÀNG** | Kiểm thử MySQL 8.4: Tổng hợp doanh thu VND, số đơn `completed`, số đơn `cancelled`, AOV làm tròn `ROUND_HALF_UP`, múi giờ `Asia/Ho_Chi_Minh`. |
| **`T04AA36`** | **Admin Dashboard API**<br>`GET /api/v1/dashboard` | Na Na | **PR #61**<br>(Merged to `develop`) | **RUNTIME SẴN SÀNG** | Kiểm thử MySQL 8.4: Khớp 100% chỉ số Sales Analytics, tổng hợp `top_products` gom nhóm theo `product_id` (kể cả khi đổi tên catalog), đếm `low_stock_products_count`. |
| **`T04A947`** | **Product Analytics (Top & Slow)**<br>`GET /api/v1/analytics/products/top`<br>`GET /api/v1/analytics/products/slow` | Dương | **Chưa có PR/Branch**<br>(Contract `CF2_DESIGN_REVIEW_REQUIRED`) | **CHƯA CÓ RUNTIME TRÊN DEVELOP** | **Contract Reference Model: REFERENCE_MODEL_PASS**<br>Triển khai `StandaloneProductAnalyticsReferenceModel` tuân thủ 100% `retailops_extended_ports.pyi`.<br>**Runtime Integration: NOT_RUNTIME_VERIFIED** (Deferred Gate). |

---

### 2. Thuật ngữ & Phân định Cấp độ Kiểm thử (Test Terminology)

Để bảo đảm tính rõ ràng và truy xuất nguồn gốc chất lượng:
1. **Unit / Contract Tests (`test_t04aad7_reconciliation_api.py`)**:
   - Chạy hoàn toàn trên bộ nhớ (In-memory), không phụ thuộc vào cơ sở dữ liệu thật.
   - Xác thực các ràng buộc biên tham số HTTP (phân trang `page=0`, `page_size=101`, khoảng ngày `from > to`, `span > 366d`, tính tương thích giữa `from`/`to` và `from_date`/`to_date`).
   - Xác thực chữ ký DTO và logic tham chiếu cho các port mở rộng (`T04A947`).
2. **API Route Authorization Tests (`CurrentPrincipal` Injected Fixtures)**:
   - Sử dụng cơ chế ghi đè dependency FastAPI (`app.dependency_overrides[get_current_principal]`) để xác thực bảng ma trận phân quyền (RBAC) trên các tuyến API `/products`, `/orders`, `/analytics/sales`, `/dashboard`.
   - *Lưu ý quan trọng:* Bộ test này xác thực quyền hạn của route đối với từng Role và Status (401/403/200), **không thay thế** các bộ test E2E kiểm tra chữ ký mật mã JWT, vòng đời access/refresh token, CSRF, blacklist session đã có trong `test_auth_api.py`, `test_auth_flows.py`, và `test_auth_tokens_csrf.py`.
3. **Real-Service MySQL Integration Tests (`test_t04aad7_reconciliation_mysql.py` - Option A)**:
   - Chạy trực tiếp trên cơ sở dữ liệu MySQL 8.4 InnoDB thông qua fixture `migrated_integration_engine`.
   - Sử dụng trực tiếp service nghiệp vụ thật: `CheckoutService(InventoryService(), clock=...)` và `OrderService(InventoryService(), clock=...)`.
   - Kiểm chứng giao dịch thật: trừ tồn kho, cập nhật `stock_version`, ghi nhận log `StockMovement` (kind `SALE` và `ORDER_CANCEL`), hoàn trả tồn kho khi hủy đơn, và đối soát số học với Sales Analytics và Dashboard.
4. **Contract Reference Model vs. Runtime NOT_VERIFIED (`T04A947`)**:
   - `REFERENCE_MODEL_PASS`: Xác thực mô hình thuật toán tham chiếu độc lập tuân thủ giao ước `ProductAnalyticsService` (`top`, `slow`, `low_stock`).
   - `NOT_RUNTIME_VERIFIED`: Do chưa có runtime thực tế trên `develop`, các cổng tích hợp runtime (truy vấn aggregation trên MySQL, lọc snapshot, phân trang DB thật) được đánh dấu là **Deferred Integration Gates** và sẽ kích hoạt ngay khi task `T04A947` được merge.

---

### 3. Chiến lược Cô lập Dữ liệu MySQL (Hardened Isolation)

Để ngăn chặn triệt để lỗi xung đột khóa ngoại (`IntegrityError 1451`) và ô nhiễm dữ liệu giữa các lần chạy test:
1. **Tiền tố độc nhất (Run Prefix)**:
   - Mỗi test run khởi tạo một đối tượng `TestRunContext` với tiền tố riêng biệt: `T04AAD7_{test_name}_{run_id}_`.
   - Áp dụng tiền tố cho mọi dữ liệu tạo mới: SKU, username, category name, idempotency key.
2. **Theo dõi danh sách định danh (Tracked ID Context)**:
   - Thu thập chính xác danh sách các ID được sinh ra trong phiên test: `user_ids`, `product_ids`, `category_ids`, `order_ids`.
3. **Dọn dẹp phụ thuộc khóa ngoại có thứ tự (Dependency-Aware Teardown)**:
   - Khối `finally:` của mỗi test case gọi `ctx.cleanup()` thực thi xóa bảng theo đúng thứ tự ràng buộc khóa ngoại MySQL:
     1. `StockMovement` (tham chiếu `order_items`, `inventory`, `orders`, `users`)
     2. `OrderItem` (tham chiếu `orders`, `products`)
     3. `Order` (tham chiếu `users`)
     4. `IdempotencyRecord` (tham chiếu `users`)
     5. `Inventory` (tham chiếu `products`)
     6. `Product` (tham chiếu `categories`)
     7. `Category` (chỉ xóa category phát sinh trong test, bảo toàn category seed)
     8. `User` (chỉ xóa user phát sinh trong test)
4. **Bảo tồn Dữ liệu Nền tảng (Seed Data Preservation)**:
   - Trong `test_seed_data_and_deterministic_pagination`, các bản ghi seed gốc (Categories và Suppliers nền tảng) được giữ nguyên vẹn cho các suite test khác, chỉ dọn dẹp các sản phẩm và tồn kho do test tạo thêm.

---

### 4. Ma trận Kịch bản Kiểm thử & Đối soát (Test Matrix)

| STT | Kịch bản kiểm thử | Cấp độ test | Dữ liệu đầu vào (Input) | Kết quả kỳ vọng (Expected) | Kết quả thực tế (Actual) | Trạng thái |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **RBAC-01** | Chưa đăng nhập (Anonymous) | API Mock | Gửi request không kèm token tới `/products`, `/orders`, `/analytics/sales`, `/dashboard` | Phản hồi HTTP `401 Unauthorized` | Trả về `401 Unauthorized` trên cả 4 endpoints | **PASS** |
| **RBAC-02** | Phân quyền ACTIVE STAFF | API Mock | Token Staff hoạt động (`role=STAFF`, `status=ACTIVE`) | Xem được `/products` (`200`) và `/orders` (`200`); bị chặn tại `/analytics/sales` (`403`) và `/dashboard` (`403`) | `/products`: `200`<br>`/orders`: `200`<br>`/analytics/sales`: `403`<br>`/dashboard`: `403` | **PASS** |
| **RBAC-03** | Phân quyền ACTIVE ADMIN | API Mock | Token Admin hoạt động (`role=ADMIN`, `status=ACTIVE`) | Được phép truy cập cả 4 endpoints với HTTP `200 OK` | Đều trả về HTTP `200 OK` | **PASS** |
| **RBAC-04** | Tài khoản chưa duyệt / khóa | API Mock | Token có `status IN ('PENDING', 'REJECTED', 'SUSPENDED')` | Bị chặn toàn diện với HTTP `403 Forbidden` | Trả về HTTP `403 Forbidden` trên toàn bộ endpoints | **PASS** |
| **RBAC-05** | Quyền hủy đơn (Staff Ownership) | Real MySQL | Staff B gửi yêu cầu hủy đơn do Staff A tạo (`created_by == Staff A`) | Bị từ chối với lỗi `Staff chỉ được hủy đơn do chính mình tạo` (`403 Forbidden`) | Bắn `ForbiddenError` / HTTP `403` chính xác | **PASS** |
| **VAL-01** | Giới hạn phân trang (Pagination Bound) | API Mock | `page=0` hoặc `page_size=101` trên `/products` và `/orders` | Bị từ chối với mã lỗi `422 Unprocessable Entity` | Trả về HTTP `422` chi tiết trường vi phạm | **PASS** |
| **VAL-02** | Giới hạn khoảng ngày (Date Boundaries) | API Mock | `from > to` hoặc khoảng cách `> 366 ngày` trên `/analytics/sales` và `/dashboard` | Bị từ chối với mã lỗi `422 Unprocessable Entity` | Trả về HTTP `422 Unprocessable Entity` | **PASS** |
| **VAL-03** | Tương thích tham số alias & Múi giờ | API Mock | Gọi `/analytics/sales` và `/dashboard` bằng `from`/`to` và fallback `from_date`/`to_date` | Cả 2 cách truyền tham số đều cho kết quả trùng khớp, chuyển đổi chính xác múi giờ `Asia/Ho_Chi_Minh` sang UTC | `period_start` và `period_end_exclusive` khớp chuẩn UTC ISO | **PASS** |
| **SEED-01** | Nạp dữ liệu nền tảng & Phân trang ổn định | Real MySQL | Gọi `seed_categories` (5 danh mục) & `seed_suppliers` (3 NCC), tạo 6 sản phẩm mẫu | Dữ liệu seed nạp idempotent; lọc theo category, status ACTIVE; phân trang `page=99` trả `items=[]`, `total` giữ nguyên | Khớp 100% dữ liệu seed, phân trang ổn định không trùng lặp giữa các trang | **PASS** |
| **RECON-01** | Đối soát toán học liên module: Checkout → Orders → Sales → Dashboard | Real MySQL<br>(Option A) | 3 giao dịch checkout thật (`100k + 150k + 200k = 450k`) qua `CheckoutService` | `sum(Order.total_vnd) == 450k`<br>`Sales.revenue_vnd == 450k`<br>`Dashboard.sales.revenue_vnd == 450k`<br>`completed_orders == 3`, `AOV == 150k` | Toàn bộ 4 nguồn số liệu khớp nhau đến từng đơn vị VND | **PASS** |
| **RECON-02** | Khấu trừ tồn kho & Log biến động (StockMovement) | Real MySQL<br>(Option A) | Bán 3 cái sản phẩm A (tồn 20), 3 cái sản phẩm B (tồn 30) qua `CheckoutService` | Tồn kho SP A giảm còn 17, SP B giảm còn 27; `stock_version` tăng; log `StockMovement` (kind `SALE`) được tạo | `prod_a.quantity == 17`<br>`prod_b.quantity == 27`<br>`stock_version` tăng, 2 bản ghi `SALE` hợp lệ | **PASS** |
| **RECON-03** | Xếp hạng Top sản phẩm bán chạy | Real MySQL | Sản phẩm B (bán 3 cái, doanh thu 300k); Sản phẩm A (bán 3 cái, doanh thu 150k) | Cùng `sold_units=3`, sản phẩm B phải đứng trước sản phẩm A do `revenue_vnd` cao hơn | Dashboard `top_products[0] == Prod B`, `top_products[1] == Prod A` | **PASS** |
| **RECON-04** | Nghiệm thu hủy đơn, Hoàn tồn kho & Đối soát Analytics | Real MySQL<br>(Option A) | Checkout đơn 160k (2 cái SP C, tồn đang 15 giảm còn 13). Hủy đơn qua `OrderService.cancel` bởi chính người tạo | Doanh thu giảm 160k về 0; `completed_orders=0`, `cancelled_orders=1`; Tồn kho SP C hoàn lại 15; log `ORDER_CANCEL` | Doanh thu loại bỏ đơn hủy, `cancelled_orders` tăng 1, tồn kho hoàn lại 15, log `ORDER_CANCEL` chính xác | **PASS** |
| **SNAP-01** | Bảo toàn Snapshot lịch sử đơn hàng qua các bản cập nhật Catalog | Real MySQL<br>(Option A) | Đơn 1 bán SP giá 50k. Cập nhật catalog giá 75k và đổi tên. Bán tiếp Đơn 2 giá 75k qua `CheckoutService` | Đơn 1 giữ nguyên tên cũ & giá 50k; Đơn 2 ghi nhận tên mới & giá 75k; Sales Analytics tính đúng `175k`; Dashboard gom nhóm 1 dòng | Đơn 1 không bị ghi đè, tổng doanh thu `175k`, top products gom nhóm đúng 1 dòng | **PASS** |
| **ADAPT-01** | Contract Reference Model cho `T04A947` | Reference Model | Chạy bộ test cho `ProductAnalyticsService` port (top, slow, low_stock) trên mô hình tham chiếu | Top loại trừ đơn hủy; Slow lọc đúng hàng tồn > 0, nhập > 7 ngày, bán <= 2; Low stock lọc tồn <= 5 | Reference model tuân thủ 100% chữ ký và trả về DTO chuẩn `Page[T]` | **REFERENCE_MODEL_PASS** |

---

### 5. File Kiểm thử Triển khai trong Task

1. **`backend/tests/modules/analytics/test_t04aad7_reconciliation_api.py`**
   - Loại test: Unit / API Mock / Contract Reference Model (In-memory via httpx AsyncClient).
   - Số lượng test: **9 test cases**.
   - Thời gian thực thi: **~1.9 giây**.
   - Phạm vi: Ma trận RBAC route-level (401/403/200), validation boundaries (phân trang, ngày tháng, múi giờ VN), và mô hình tham chiếu giao ước cổng cho `T04A947`.

2. **`backend/tests/modules/analytics/test_t04aad7_reconciliation_mysql.py`**
   - Loại test: Real-Service MySQL Integration Test (`@pytest.mark.integration`).
   - Số lượng test: **4 test cases lớn**.
   - Thời gian thực thi: Chạy độc lập trên MySQL InnoDB test database.
   - Phạm vi: Thực thi nghiệp vụ thật qua `CheckoutService`, `OrderService`, `ProductService`, xác thực tính toàn vẹn giao dịch, trừ và hoàn tồn kho, snapshot lịch sử, phân quyền hủy đơn, và đối soát toán học 4 chiều.

---

### 6. Cổng Tích hợp Hoãn lại (Deferred Integration Gates for T04A947)

Do task `T04A947` (Dương phụ trách) chưa hoàn thành việc chuyển đổi từ trạng thái `CF2_DESIGN_REVIEW_REQUIRED` sang mã nguồn thực thi trên `develop`:
- Các bài kiểm thử tích hợp trực tiếp trên MySQL đối với 2 endpoint `GET /api/v1/analytics/products/top` và `GET /api/v1/analytics/products/slow` được tạm thời hoãn lại.
- **Kế hoạch kích hoạt khi T04A947 merge**:
  1. Kiểm tra câu lệnh truy vấn tổng hợp SQL aggregation trên MySQL 8.4 InnoDB.
  2. Kiểm tra bộ lọc cửa sổ 30 ngày và điều kiện `first_stocked_at > 7 ngày` đối với sản phẩm bán chậm.
  3. Kiểm tra loại trừ đơn `CANCELLED` trong các chỉ số sản phẩm.
  4. Kiểm tra phân trang tất định (`order_by(sold_units.desc(), revenue_vnd.desc(), product_id.asc())`).

---

### 7. Kết luận & Trạng thái Phê duyệt

- Toàn bộ các yêu cầu hiệu chỉnh của Backend Lead đã được đáp ứng đầy đủ và triệt để:
  1. Phân định rõ ràng quyền sở hữu từng module/PR, ghi nhận đúng PR #62 là frontend.
  2. Chuẩn hóa thuật ngữ phân cấp kiểm thử và lưu ý phạm vi RBAC route-level.
  3. Nâng cấp bộ test MySQL sang **Option A (Real Checkout Service)**, xác thực giao dịch và biến động kho thật.
  4. Gia cố cơ chế cô lập MySQL với tiền tố độc nhất và dọn dẹp theo thứ tự khóa ngoại.
  5. Đánh dấu chính xác trạng thái của `T04A947` là `REFERENCE_MODEL_PASS` và `NOT_RUNTIME_VERIFIED`.
- Task `T04AAD7` đã sẵn sàng cho Lead review lần cuối.
- **Trạng thái:** **READY FOR REVIEW**
