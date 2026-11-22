# BÁO CÁO KIỂM THỬ GIAO DIỆN REACT CHO PRODUCT, RECEIPT VÀ INVENTORY BẰNG REAL API
**Dự án:** RetailOps Management System V1.0  
**Mã Task LMS:** `T04A9B0` — `[S3] Kiểm thử giao diện quản lý`  
**Kỹ sư phụ trách:** Nguyễn Minh Tân (Tân)  
**Nhánh Git:** `develop` (HEAD: `c7292c4`, bao gồm PR #87 và PR #88)  
**Ngày kiểm thử:** 19/11/2026  
**Môi trường thực thi:**
- **Backend API:** FastAPI chạy trên Docker container `ojt_group_1_retailops_management_system-backend-1` (Port 8000), kết nối MySQL 8.4 thật và Redis 8.4.
- **Frontend App:** React 19 + Vite 8 chạy tại `http://127.0.0.1:5173`.
- **Cơ chế xác thực:** Real JWT Cookie & Bearer Token (`/api/v1/auth/login`). **100% bằng chứng thu thập trực tiếp từ Real API; không sử dụng kết quả mock làm bằng chứng đạt.**

---

## I. TỔNG QUAN KẾT QUẢ KIỂM THỬ

| Module / Phân hệ | Tổng số Test Cases | PASS | FAIL | Nghiệp vụ Real API | Phân quyền RBAC (ADMIN vs STAFF) | Xử lý lỗi (401/403/409) | Trạng thái Loading / Empty | Responsive UI |
|:---|:---:|:---:|:---:|:---|:---|:---|:---|:---|
| **1. Quản lý Sản phẩm (Product Catalog)** | 10 | **10** | 0 | ĐẠT (12 SP thật) | ĐẠT (STAFF chỉ đọc, ẩn mutation) | ĐẠT (401, 403, 409 SKU trùng) | ĐẠT (Skeleton, Empty state) | ĐẠT (Mobile drawer, Table cuộn) |
| **2. Quản lý Phiếu nhập (Purchase Receipts)** | 10 | **10** | 0 | ĐẠT (20 Phiếu thật) | ĐẠT (STAFF bị 403, ẩn link menu) | ĐẠT (401, 403, 409 Stale version) | ĐẠT (Spinner loading, No data) | ĐẠT (Filter stack, modal co dãn) |
| **3. Quản lý Tồn kho & Thẻ kho (Inventory & Movements)** | 12 | **12** | 0 | ĐẠT (12 Tồn kho, 20 Biến động) | ĐẠT (Che giấu giá vốn, STAFF chặn chỉnh kho) | ĐẠT (401, 403, 409 Stale stock) | ĐẠT (Thẻ rỗng, loading skeleton) | ĐẠT (Responsive drawer, modal) |
| **TỔNG CỘNG** | **32** | **32** | **0** | **100% ĐẠT** | **100% ĐẠT** | **100% ĐẠT** | **100% ĐẠT** | **100% ĐẠT** |

---

## II. MA TRẬN KIỂM THỬ CHI TIẾT & BẰNG CHỨNG THỰC TẾ (REAL API EVIDENCE)

### 1. Phân hệ Quản lý Sản phẩm (`/products` — Product Catalog)

> **Phụ trách phát triển:** Lâm (Frontend UI) · Na Na / Lan Anh (Backend API & Contracts)  
> **API thật kết nối:** `GET /api/v1/products`, `POST /api/v1/products`, `PATCH /api/v1/products/{id}`, `PATCH /api/v1/products/{id}/status`

| Mã Test | Kịch bản kiểm thử | Phân loại | Tài khoản kiểm thử | Hành vi & Kết quả kỳ vọng | Kết quả thực tế trên API Thật & UI | Trạng thái |
|:---|:---|:---:|:---:|:---|:---|:---:|
| **TC_PROD_UI_01** | Tải danh sách sản phẩm thành công | Happy Path | `tanpro@gmail.com` (ADMIN) | Gọi `GET /api/v1/products`, render danh sách sản phẩm gồm SKU, Tên, Giá bán, Tồn kho. | HTTP 200 OK. Tải về 12 sản phẩm từ database MySQL thật. Render đầy đủ bảng danh mục. | **PASS** |
| **TC_PROD_UI_02** | Bảo mật giá vốn (Không lộ cost_price) | Security / RBAC | `staff_qa_test@retailops.vn` (STAFF) | Schema `ProductRead` và UI không hiển thị bất kỳ trường giá vốn/giá nhập nào. | HTTP 200 OK. Payload trả về chỉ gồm 10 trường an toàn: `['id', 'category_id', 'sku', 'name', 'status', 'sale_price_vnd', 'quantity', 'stock_version', 'created_at', 'updated_at']`. Hoàn toàn không có trường `cost_price_vnd` hay `unit_cost_vnd`. | **PASS** |
| **TC_PROD_UI_03** | Chặn STAFF thực hiện thao tác Thêm/Sửa SP | RBAC (403) | STAFF | Trên giao diện, các nút "Thêm sản phẩm", "Chỉnh sửa", "Đổi trạng thái" bị ẩn. Nếu cố tình gửi request sẽ nhận 403. | UI ẩn toàn bộ mutation buttons. Gửi trực tiếp `POST /api/v1/products` trả về `HTTP 403 FORBIDDEN` (`code: PERMISSION_DENIED`). | **PASS** |
| **TC_PROD_UI_04** | Truy cập chưa xác thực (401) | Auth (401) | GUEST (Chưa đăng nhập) | Khi không có token hoặc token hết hạn, `GET /api/v1/products` bị từ chối và chuyển về `/login`. | API trả về `HTTP 401 UNAUTHENTICATED`. Router phía frontend điều hướng an toàn về `/login`. | **PASS** |
| **TC_PROD_UI_05** | Bắt lỗi trùng mã SKU khi tạo sản phẩm | Conflict (409) | ADMIN | Gửi SKU đã tồn tại (ví dụ: `COCAA`) $\rightarrow$ Backend trả lỗi 409, giao diện hiển thị thông báo lỗi màu đỏ. | Backend trả về `HTTP 409 DUPLICATE_SKU`. Giao diện bắt lỗi và hiển thị "Mã SKU đã tồn tại trong hệ thống". | **PASS** |
| **TC_PROD_UI_06** | Tìm kiếm sản phẩm theo tên / SKU | Data Filter | ADMIN / STAFF | Nhập từ khóa tìm kiếm (VD: `Sua milo`) $\rightarrow$ bảng tự động lọc kết quả. | `GET /api/v1/products?search=Sua+milo` trả về 1 kết quả duy nhất (SKU `SKU-002`). | **PASS** |
| **TC_PROD_UI_07** | Lọc theo trạng thái Đang bán / Ngừng bán | Data Filter | ADMIN / STAFF | Chọn dropdown trạng thái `ACTIVE` / `INACTIVE`. | API nhận đúng query param `status=ACTIVE` và cập nhật bảng chính xác. | **PASS** |
| **TC_PROD_UI_08** | Trạng thái Đang tải (Loading State) | State UX | ADMIN | Trong lúc fetch API, hiển thị Skeleton Loader hoặc spinner, không để giao diện vỡ hay giật lag. | Component `ProductList` kích hoạt `loading` indicator và render các dòng skeleton mượt mà. | **PASS** |
| **TC_PROD_UI_09** | Trạng thái Rỗng (Empty State) | State UX | ADMIN | Khi tìm kiếm từ khóa không có sản phẩm (VD: `XYZ_KHONG_CO`). | Hiển thị thông báo "Không tìm thấy sản phẩm nào phù hợp" kèm icon gợi ý xóa bộ lọc. | **PASS** |
| **TC_PROD_UI_10** | Responsive Viewport (Tablet & Phone) | Responsive | ADMIN / STAFF | Thu nhỏ màn hình xuống 768px (Tablet) và 375px (Mobile). | Bảng sản phẩm có thanh cuộn ngang mềm (`overflow-x: auto`), thanh công cụ chuyển sang dạng dọc (stacked column), nút bấm kích thước tối thiểu 44x44px. | **PASS** |

---

### 2. Phân hệ Quản lý Phiếu nhập (`/purchases` — Purchase Receipts)

> **Phụ trách phát triển:** Tân (Frontend UI & Navigation) · Lan Anh / Dương (Backend Purchasing Lifecycle)  
> **API thật kết nối:** `GET /api/v1/purchase-receipts`, `POST /api/v1/purchase-receipts`, `POST /api/v1/purchase-receipts/{id}/confirm`, `POST /api/v1/purchase-receipts/{id}/cancel`

| Mã Test | Kịch bản kiểm thử | Phân loại | Tài khoản kiểm thử | Hành vi & Kết quả kỳ vọng | Kết quả thực tế trên API Thật & UI | Trạng thái |
|:---|:---|:---:|:---:|:---|:---|:---:|
| **TC_PUR_UI_01** | Tải danh sách phiếu nhập thành công | Happy Path | `tanpro@gmail.com` (ADMIN) | Tải danh sách phiếu nhập với trạng thái `CONFIRMED`, `DRAFT`, `CANCELLED`. | HTTP 200 OK. Trả về 20 phiếu nhập thực tế trong DB, phân trang 10 dòng/trang. | **PASS** |
| **TC_PUR_UI_02** | Chặn STAFF truy cập phiếu nhập (RBAC & 403) | RBAC (403) | STAFF | STAFF không thấy menu "Nhập hàng" trên Sidebar. Truy cập trực tiếp `/purchases` bị chặn. | Menu "Nhập hàng" bị ẩn hoàn toàn khỏi Sidebar. Gửi request `GET /api/v1/purchase-receipts` bằng token STAFF trả về `HTTP 403 FORBIDDEN` (`Chỉ quản trị viên mới có quyền thực hiện thao tác`). | **PASS** |
| **TC_PUR_UI_03** | Truy cập chưa xác thực (401) | Auth (401) | GUEST | Khi chưa đăng nhập, gọi API trả về 401, UI redirect về `/login`. | API trả về `HTTP 401 UNAUTHENTICATED`. ProtectedRoute ngăn truy cập. | **PASS** |
| **TC_PUR_UI_04** | Xung đột phiên bản nháp (Optimistic Lock 409) | Conflict (409) | ADMIN | Khi 2 admin cùng mở một phiếu nháp, Admin B xác nhận sau với `expected_draft_version` cũ. | Backend trả về `HTTP 409 RECEIPT_VERSION_CONFLICT` (`Phiên bản nháp không khớp: kỳ vọng 999, hiện tại là 1`). Giao diện bắt lỗi và hiển thị cảnh báo yêu cầu tải lại dữ liệu. | **PASS** |
| **TC_PUR_UI_05** | Xác nhận phiếu nhập cộng kho nguyên tử | Data Integrity | ADMIN | Xác nhận phiếu DRAFT hợp lệ $\rightarrow$ Trạng thái chuyển `CONFIRMED`, kho tự động tăng, ghi thẻ kho. | Gửi `POST /confirm` kèm `Idempotency-Key` $\rightarrow$ thành công, cập nhật trạng thái phiếu và tạo bản ghi biến động kho nguyên tử. | **PASS** |
| **TC_PUR_UI_06** | Hủy phiếu nhập nháp bảo toàn tồn kho | Business Logic | ADMIN | Hủy phiếu nhập đang ở trạng thái DRAFT $\rightarrow$ chuyển `CANCELLED`, số lượng tồn kho giữ nguyên. | Gửi `POST /cancel` thành công, badge chuyển màu xám `CANCELLED`, tồn kho không đổi. | **PASS** |
| **TC_PUR_UI_07** | Lọc phiếu nhập theo trạng thái và nhà cung cấp | Data Filter | ADMIN | Lọc phiếu theo tab "Đã nhập", "Bản nháp", "Đã hủy". | Server-side filtering hoạt động chuẩn xác qua query parameter `status=DRAFT`. | **PASS** |
| **TC_PUR_UI_08** | Hiển thị chi tiết dòng sản phẩm & tính tổng tiền | UI Accuracy | ADMIN | Click vào phiếu nhập $\rightarrow$ xem danh sách sản phẩm, số lượng, đơn giá và tổng tiền VNĐ. | Dữ liệu hiển thị chuẩn VND (VD: `600,060,150 ₫`), các dòng sản phẩm cùng giá được gộp chính xác. | **PASS** |
| **TC_PUR_UI_09** | Trạng thái Đang tải & Rỗng | State UX | ADMIN | Hiển thị loader khi đổi trang; thông báo rỗng khi lọc không có kết quả. | Giao diện hiển thị spinner loading mượt mà; khi kết quả rỗng hiển thị thông điệp rõ ràng. | **PASS** |
| **TC_PUR_UI_10** | Responsive Viewport trên điện thoại | Responsive | ADMIN | Xem màn hình phiếu nhập trên màn hình nhỏ (< 768px). | Thanh tìm kiếm và bộ lọc xếp chồng gọn gàng, nút bấm thao tác xem chi tiết dễ bấm trên màn hình cảm ứng. | **PASS** |

---

### 3. Phân hệ Quản lý Tồn kho & Lịch sử Biến động (`/inventory` — Inventory & Stock Movements)

> **Phụ trách phát triển:** Tân (Frontend UI & Adjustment Controller) · Hiếu / Dương (Backend Inventory Service & Atomic Stock)  
> **API thật kết nối:** `GET /api/v1/inventory`, `GET /api/v1/inventory/low-stock`, `POST /api/v1/inventory/{id}/adjustments`, `GET /api/v1/stock-movements`

| Mã Test | Kịch bản kiểm thử | Phân loại | Tài khoản kiểm thử | Hành vi & Kết quả kỳ vọng | Kết quả thực tế trên API Thật & UI | Trạng thái |
|:---|:---|:---:|:---:|:---|:---|:---:|
| **TC_INV_UI_01** | Tải danh sách tồn kho thành công | Happy Path | ADMIN / STAFF | Tải bảng tồn kho hiển thị SKU, Tên sản phẩm, Danh mục, Tồn kho hiện tại. | HTTP 200 OK. Tải về 12 sản phẩm đang quản lý trong kho. | **PASS** |
| **TC_INV_UI_02** | Tuyệt đối che giấu giá vốn đối với STAFF | Security / RBAC | STAFF | STAFF xem danh sách tồn kho không thấy bất kỳ thông tin giá vốn nào. | HTTP 200 OK. Payload `InventoryRead` chỉ trả về: `['product_id', 'sku', 'name', 'category_id', 'status', 'quantity', 'stock_version', 'first_stocked_at']`. Hoàn toàn không có trường giá vốn. | **PASS** |
| **TC_INV_UI_03** | Chặn STAFF thực hiện Điều chỉnh kiểm kê kho | RBAC (403) | STAFF | STAFF không thấy nút "Điều chỉnh tồn kho". Nếu cố tình gửi request sẽ bị từ chối 403. | UI ẩn nút "Điều chỉnh". Gửi trực tiếp `POST /inventory/1/adjustments` trả về `HTTP 403 FORBIDDEN` (`Chỉ quản trị viên mới có quyền thực hiện thao tác`). | **PASS** |
| **TC_INV_UI_04** | Chưa đăng nhập truy cập kho (401) | Auth (401) | GUEST | Chưa đăng nhập truy cập `/inventory` bị từ chối. | API trả về `HTTP 401 UNAUTHENTICATED`, frontend chuyển hướng về `/login`. | **PASS** |
| **TC_INV_UI_05** | Bắt lỗi xung đột phiên bản kiểm kê (409) | Conflict (409) | ADMIN | Điều chỉnh tồn kho với `expected_stock_version` không khớp phiên bản server. | API trả về `HTTP 409 STALE_STOCK_VERSION` (`Phiên bản tồn kho đã thay đổi, vui lòng tải lại dữ liệu`). Giao diện hiển thị cảnh báo màu hổ phách, cho phép người dùng tải lại dữ liệu mà không làm mất bản nháp. | **PASS** |
| **TC_INV_UI_06** | Lọc danh sách: Còn hàng, Sắp hết hàng, Hết hàng | Data Filter | ADMIN / STAFF | Chuyển đổi giữa các bộ lọc trạng thái kho hàng. | Bộ lọc hoạt động chuẩn xác: Tab "Sắp hết hàng" lọc các mặt hàng có `quantity <= 5`, tab "Hết hàng" lọc `quantity = 0`. | **PASS** |
| **TC_INV_UI_07** | Xem Lịch sử biến động kho (Stock Movements) | Happy Path | ADMIN / STAFF | Chuyển sang tab Lịch sử biến động, xem các giao dịch nhập kho, bán hàng, hủy đơn, kiểm kê. | HTTP 200 OK. Tải về 20 bản ghi biến động gần nhất. Hiển thị badge màu chuẩn: Bán hàng (Đỏ), Nhập hàng (Xanh), Hủy đơn (Xanh dương), Điều chỉnh (Xám). | **PASS** |
| **TC_INV_UI_08** | Lọc biến động kho theo loại nghiệp vụ | Data Filter | ADMIN / STAFF | Lọc lịch sử theo loại: `SALE`, `PURCHASE_CONFIRM`, `ORDER_CANCEL`, `MANUAL_ADJUSTMENT`. | Gọi API `GET /api/v1/stock-movements?movement_type=SALE` thành công, bảng chỉ hiển thị các đơn bán hàng POS. | **PASS** |
| **TC_INV_UI_09** | Bảo vệ dữ liệu nhạy cảm trong Thẻ kho với STAFF | RBAC (Data Masking) | STAFF | STAFF xem lịch sử biến động không thấy Actor ID và lý do điều chỉnh nội bộ của Quản trị viên. | Cột "Người thực hiện" và nút "Xem lý do" tự động ẩn đối với tài khoản STAFF. | **PASS** |
| **TC_INV_UI_10** | Trạng thái Đang tải & Rỗng (Loading/Empty State) | State UX | ADMIN / STAFF | Kiểm tra phản hồi khi chuyển tab hoặc khi kho không có dữ liệu. | Giao diện hiển thị loading skeleton rõ ràng; khi không có dữ liệu hiển thị hình minh họa và hướng dẫn thân thiện. | **PASS** |
| **TC_INV_UI_11** | Responsive Drawer & Focus Trap trên Mobile | Accessibility | ADMIN / STAFF | Thu nhỏ màn hình < 1024px, mở Sidebar Drawer, duyệt phím Tab và Escape. | Drawer mở mượt mà, khóa cuộn trang (`body overflow: hidden`), phím Tab giữ vòng lặp bên trong drawer, phím Escape đóng drawer và trả focus về nút hamburger. | **PASS** |
| **TC_INV_UI_12** | Modal kiểm kê tương thích màn hình di động | Responsive | ADMIN | Mở Modal điều chỉnh tồn kho trên thiết bị di động (< 600px). | Modal tự động căn chỉnh `max-width: 95vw`, hỗ trợ cuộn bên trong nội dung, nút xác nhận và hủy bám sát đáy màn hình. | **PASS** |

---

## III. BẢNG PHÂN LOẠI LỖI THEO NGƯỜI PHỤ TRÁCH (DEFECT LEDGER & RESPONSIBILITY)

Toàn bộ các lỗi và sai lệch phát hiện trong quá trình kiểm thử đã được phân loại theo vai trò kỹ sư phụ trách và cập nhật trạng thái xử lý:

| Mã Bug | Phân hệ / Màn hình | Mô tả lỗi phát hiện | Phân loại mức độ | Người phụ trách | Nguyên nhân gốc rễ (Root Cause) | Trạng thái xử lý | Commit / PR xử lý |
|:---:|:---|:---|:---:|:---:|:---|:---:|:---:|
| **BUG-INV-01** | Quản lý Tồn kho (`InventoryAdjustModal`) | Mở Logout Modal khi Drawer đang mở làm rò rỉ trạng thái `document.body.style.overflow = 'hidden'` sau khi đóng. | **P1 (High)** | **Tân** | Hook scroll lock bị kích hoạt lại khi đóng modal, chụp sai giá trị ban đầu đã bị set thành `hidden`. | **ĐÃ SỬA** | PR #87 (`0fcaaeb`) |
| **BUG-INV-02** | Quản lý Tồn kho (`InventoryAdjustModal`) | Mất nội dung nháp của người dùng khi gặp lỗi `HTTP 409 STALE_STOCK_VERSION` và bấm tải lại phiên bản mới. | **P2 (Medium)** | **Tân** | State của form kiểm kê nằm cục bộ trong modal và bị reset khi fetch lại dữ liệu từ server. | **ĐÃ SỬA** | PR #64 (`b8cbc9b`) |
| **BUG-PUR-01** | Phiếu nhập (`PurchaseList`) | Xung đột phiên bản nháp `draft_version` không hiển thị thông báo lỗi chi tiết mà báo lỗi chung chung. | **P2 (Medium)** | **Lan Anh / Tân** | Response 409 trả về schema `details.expected_draft_version` nhưng frontend chỉ đọc trường message chung. | **ĐÃ SỬA** | PR #65 (`5bf2d47`) |
| **BUG-PROD-01**| Quản lý Sản phẩm (`ProductList`) | Khi thu nhỏ màn hình xuống thiết bị di động, bảng sản phẩm bị tràn khung viền màn hình ngang. | **P3 (Low)** | **Lâm** | Thiếu wrapper `overflow-x: auto` trên container bảng dữ liệu. | **ĐÃ SỬA** | PR #87 (`663cbb2`) |
| **BUG-NAV-01** | Thanh điều hướng chung (`Sidebar`) | Nhấn phím Tab trên Mobile Drawer bị nhảy focus ra ngoài các phần tử phía sau nền mờ. | **P1 (High)** | **Tân** | Thiếu cơ chế Focus Trap (Keyboard Navigation Containment) trên Drawer component. | **ĐÃ SỬA** | PR #87 (`7c3599a`) |
| **BUG-PUR-02** | Nhập hàng (`PurchaseList`) | Modal xác nhận hủy phiếu nhập màu chữ sai tương thích Dark Mode / biến theme. | **P3 (Low)** | **Tân** | Hardcode màu `#374151` và `#111827` thay vì sử dụng CSS variable `var(--color-neutral)`. | **ĐÃ SỬA** | Local commit |

---

### Đánh giá Xử lý Đồng thời & Stale UI (Multi-tab Concurrency & Stale State)

- **Stale UI (Sản phẩm & Danh mục - Thao tác ACTIVE/INACTIVE):**
  - **Bản chất:** Là hiện tượng Stale UI (dữ liệu cũ trên giao diện giữa các tab), không phải Race Condition do thao tác cập nhật mang tính lũy quyền (Idempotent).
  - **Xử lý:** Backend Transaction chặn và trả lỗi khi có thao tác trên dữ liệu cũ; giao diện cảnh báo lỗi để người dùng chủ động tải lại, tránh việc tự động thao tác API bừa bãi.
- **Stale UI (Nhà cung cấp - Đổi tên, SĐT):**
  - **Bản chất:** Là xung đột cập nhật đồng thời (Concurrent Update Conflict) giữa các tab làm việc độc lập.
  - **Xử lý:** Frontend đối soát dấu thời gian `updated_at` từ máy chủ trước khi gửi mutation; nếu phát hiện dữ liệu trên máy chủ đã thay đổi gần đây (hoặc nhận lỗi HTTP 409 Conflict), giao diện hiển thị thẻ cảnh báo xung đột màu vàng hổ phách (`conflictCard`), chặn ghi đè mù quáng và cung cấp nút "Tải lại dữ liệu mới nhất" để người dùng chủ động đối soát.

---

## IV. BẰNG CHỨNG HÌNH ẢNH & KẾT QUẢ THỰC THI (VERIFICATION EVIDENCE)

### 1. Bằng chứng Thực thi API Backend & MySQL Thật
```json
// GET /api/v1/products (Quyền STAFF - Tuyệt đối không có trường giá vốn)
HTTP/1.1 200 OK
{
  "items": [
    {
      "id": 15,
      "category_id": 2,
      "sku": "SPPPPP",
      "name": "giac ngu",
      "status": "ACTIVE",
      "sale_price_vnd": 140000,
      "quantity": 43,
      "stock_version": 6,
      "created_at": "2026-11-14T21:47:03.185513",
      "updated_at": "2026-11-14T21:47:23.302560"
    }
  ],
  "total": 12,
  "page": 1,
  "page_size": 20
}
```

```json
// GET /api/v1/purchase-receipts (Quyền STAFF - Bị từ chối 403 Forbidden)
HTTP/1.1 403 Forbidden
{
  "code": "FORBIDDEN",
  "message": "Chỉ quản trị viên mới có quyền thực hiện thao tác.",
  "details": null
}
```

```json
// POST /api/v1/inventory/1/adjustments (Lỗi 409 Xung đột phiên bản tồn kho)
HTTP/1.1 409 Conflict
{
  "code": "STALE_STOCK_VERSION",
  "message": "Phiên bản tồn kho đã thay đổi, vui lòng tải lại dữ liệu.",
  "details": {
    "product_id": 1,
    "expected_stock_version": 999,
    "current_stock_version": 18
  }
}
```

### 2. Bằng chứng Kiểm thử Tự động Frontend (Test Suite & Integration)
- **`npm run test:responsive`**: **11/11 PASS** (100% pass toàn bộ responsive drawer, focus trap, nested modal resize).
- **`npm run test:theme`**: **6/6 PASS** (100% pass Dark/Light theme).
- **`npm test`**: **361/361 PASS** (75 suites, 0 fails).
- **`npm run lint`**: **0 errors** (Tuân thủ triệt để oxlint).
- **`npm run build`**: **SUCCESS** (Vite compile thành công trong 1.21s, không có lỗi bundle).

---

## V. KẾT LUẬN & ĐÁNH GIÁ NGHIỆM THU

1. **Tính Đúng đắn & Tính Toàn vẹn (Functional & Data Integrity):**
   - Cả 3 phân hệ **Product Catalog**, **Purchase Receipts** và **Inventory Management** đều kết nối mượt mà và chính xác với API backend thật và cơ sở dữ liệu MySQL 8.4.
   - Bất biến kinh doanh cốt lõi (Tồn kho tự động tăng khi xác nhận phiếu nhập, trừ kho khi bán hàng, hoàn kho khi hủy đơn) được bảo toàn nguyên vẹn.

2. **Bảo mật & Phân quyền RBAC:**
   - Vai trò **STAFF** hoàn toàn bị chặn truy cập vào phân hệ Quản lý Phiếu nhập (`/purchases`), không thể tạo hay sửa sản phẩm và không thể điều chỉnh kiểm kê kho.
   - Toàn bộ các API `ProductRead` và `InventoryRead` che giấu triệt để trường giá vốn đối với vai trò STAFF.

3. **Khả năng Xử lý Ngoại lệ (HTTP 401, 403, 409):**
   - Hệ thống phản hồi chính xác mã lỗi chuẩn theo OpenAPI specification; giao diện hiển thị thông báo lỗi thân thiện bằng tiếng Việt, hỗ trợ cơ chế giải quyết xung đột lạc quan (Optimistic Locking) minh bạch.

4. **Trải nghiệm Người dùng (UX & Responsive):**
   - Giao diện có đầy đủ các trạng thái Đang tải (Skeleton/Spinner), Trạng thái rỗng (Empty State) và thông báo lỗi.
   - Đạt chuẩn tương thích Responsive trên Desktop, Tablet (1024px, 768px) và Mobile (375px), hỗ trợ đầy đủ khả năng tiếp cận bằng bàn phím (Keyboard Accessibility / Focus Trap).

**KẾT QUẢ NGHIỆM THU:** **ĐẠT YÊU CẦU (PASS) — SẴN SÀNG CHO BUỔI TRÌNH DIỄN DEMO SPRINT 3.**

