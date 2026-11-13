# RETAILOPS V1.0 — TỪ ĐIỂN DATABASE DỄ HIỂU

**Nguồn duy nhất cho phần cấu trúc:** `RetailOps_ERD_V1.0_Chot_Thiet_Ke.dbml` (baseline thiết kế đã thống nhất; **chưa** xác nhận migration MySQL thực tế).

**Phạm vi:** 18 bảng · 139 trường · 27 khai báo quan hệ · 8 nhóm nghiệp vụ.

**Cách dùng:** Đọc mục 1–3 để hiểu ý nghĩa các bảng; tra cứu mục 4 để biết từng trường; xem mục 5–7 để hình dung luồng dữ liệu, ràng buộc và rủi ro.

> **Lưu ý phân biệt:** Phần "Có trong DBML" phản ánh khai báo thực tế. Những giải thích về transaction, bảo mật, các ví dụ hoặc hành vi service được đánh dấu là *quy tắc triển khai/diễn giải*, không phải DB tự thực thi.

## 1. Tư duy đọc ERD — 5 phút

- **Bảng (Table):** nơi chứa một loại đối tượng. `orders` chứa đơn hàng; `order_items` chứa từng sản phẩm của đơn.
- **Trường/cột (Column):** một thông tin cụ thể trong bảng, chẳng hạn `quantity`, `status`, `sold_at`.
- **PK (Primary Key):** mã nhận diện duy nhất một dòng. Có thể gồm một cột hoặc nhiều cột.
- **FK (Foreign Key):** cột tham chiếu PK/UNIQUE của bảng khác, giúp bảo đảm đối tượng được tham chiếu tồn tại.
- **UNIQUE:** không cho hai dòng có cùng giá trị khóa (cần chú ý cách MySQL xử lý NULL và collation).
- **CHECK:** điều kiện được viết trong schema; phải xác minh có thật trong SQL sau khi xuất/migration.
- **Index:** cấu trúc hỗ trợ tìm kiếm/lọc/join; đổi lại có chi phí khi ghi dữ liệu.
- **Snapshot:** bản sao tên/mã/giá tại thời điểm giao dịch, tránh lịch sử đổi theo thông tin hiện tại.
- **UTC:** các thời điểm nghiệp vụ lưu theo UTC; quy tắc ngày bán tại Việt Nam cần chuyển về `Asia/Ho_Chi_Minh` trong service/query.
- **NULL:** chưa có giá trị; không có nghĩa là 0 hoặc chuỗi rỗng.

### Kiểu dữ liệu thường gặp

| Kiểu | Hiểu đơn giản | Ví dụ |
|---|---|---|
| `bigint`, `int`, `smallint`, `tinyint` | Các kiểu số nguyên, khác nhau ở dung lượng | ID, số lượng, version, HTTP status |
| `varchar(n)` | Chuỗi tối đa n ký tự (ràng buộc chi tiết theo MySQL) | tên, SKU, trạng thái |
| `datetime(6)` | Ngày giờ, lưu đến microsecond | `sold_at` |
| `binary(16)` | 16 byte cố định | session/event ID |
| `binary(32)` | 32 byte cố định | digest SHA-256 |
| `varbinary(2048)` | Dữ liệu byte, kích thước tối đa 2048 | ciphertext của email token |
| `json` | Dữ liệu có cấu trúc kiểu JSON | payload, response |

## 2. Bản đồ 8 nhóm nghiệp vụ

| Nhóm | Bảng | Vai trò |
|---|---|---|
| Authentication | `users`, `staff_approval_requests`, `auth_sessions`, `refresh_tokens`, `account_action_tokens` | Quản lý tài khoản Staff/Admin, xét duyệt, đăng nhập, refresh và token qua email. |
| Master Data | `categories`, `suppliers`, `products` | Lưu danh mục, nhà cung cấp và thông tin sản phẩm hiện tại. |
| Purchasing | `purchase_receipts`, `purchase_receipt_items` | Ghi phiếu nhập đang soạn, đã xác nhận hoặc hủy nháp. |
| Inventory | `inventory`, `inventory_adjustments`, `stock_movements` | Lưu số tồn hiện tại, lịch sử kiểm kê và mọi biến động kho. |
| Sales | `orders`, `order_items` | Lưu đơn bán và từng sản phẩm đã bán theo giá tại thời điểm checkout. |
| Idempotency | `idempotency_records` | Ngăn retry request làm lặp tác động nghiệp vụ. |
| Outbox | `outbox_events` | Giữ ý định email bền vững và trạng thái xử lý bất đồng bộ. |
| Notifications | `admin_notifications` | Thông báo in-app cho Admin về yêu cầu xét duyệt Staff. |

## 3. Quan hệ cốt lõi và cách nhớ

```text
users ──< staff_approval_requests ──< admin_notifications
   ├──< auth_sessions ──< refresh_tokens
   ├──< account_action_tokens
   ├──< orders ──< order_items >── products >── categories
   └──< purchase_receipts ──< purchase_receipt_items >── products
suppliers ──< purchase_receipts
products ── inventory ──< stock_movements
inventory ──< inventory_adjustments
stock_movements ──> chứng từ nguồn đúng (receipt item / order item / adjustment)
idempotency_records ──> users
outbox_events ──> users
```

Dấu `──<` ở đây chỉ nghĩa "một tới nhiều" ở mức minh họa; quan hệ 1–1 của Product/Inventory được trình bày riêng. Sơ đồ chữ không thay thế FK trong DBML.

## 4. Giải thích đầy đủ từng bảng và từng trường

### 4.1. Nhóm Authentication

Quản lý tài khoản Staff/Admin, xét duyệt, đăng nhập, refresh và token qua email.

#### `users` — 9 trường

Đây là **tài khoản**, không đồng nghĩa với **một lần đăng ký Staff**. Ví dụ một `users.id = 10` có thể có 2 lần xin xét duyệt nhưng vẫn chỉ là 1 tài khoản. `admin_slot` bảo vệ **tối đa** một Admin; việc thực sự tồn tại một Admin phụ thuộc seed/kiểm tra vận hành.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | Mã định danh duy nhất của tài khoản; dùng liên kết với phiên, đơn hàng và lịch sử xét duyệt. |
| `email_normalized` | `varchar(254)` — **UNIQUE, NOT NULL** | Email đã chuẩn hóa để tìm kiếm và chống đăng ký trùng; phải thống nhất cách chuẩn hóa và collation khi migration. |
| `password_hash` | `varchar(255)` — **NOT NULL** | Chuỗi băm mật khẩu; tuyệt đối không lưu mật khẩu gốc. |
| `role` | `varchar(5)` — **NOT NULL** | Vai trò của tài khoản: ADMIN hoặc STAFF. |
| `status` | `varchar(16)` — **NOT NULL** | Trạng thái tài khoản: ADMIN luôn ACTIVE; STAFF có thể PENDING_APPROVAL, ACTIVE hoặc REJECTED. |
| `admin_slot` | `tinyint` — **UNIQUE** | Ô đánh dấu dành riêng cho ADMIN: giá trị 1 cho ADMIN, NULL cho STAFF; UNIQUE giới hạn tối đa một ADMIN. |
| `last_reapplied_at` | `datetime(6)` | Lần gần nhất yêu cầu xét duyệt lại được xác minh và chấp nhận; phục vụ giới hạn 24 giờ. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm tạo tài khoản (UTC). |
| `updated_at` | `datetime(6)` — **NOT NULL** | Thời điểm cập nhật gần nhất (UTC). |

**CHECK được khai báo trong DBML (diễn giải):**
- `(role = 'ADMIN' AND admin_slot IS NOT NULL AND admin_slot = 1 AND status = 'ACTIVE') OR (role = 'STAFF' AND admin_slot IS NULL AND status IN ('PENDING_APPROVAL','ACTIVE','REJECTED'))`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `staff_approval_requests` — 8 trường

Một user có thể có nhiều lần xin xét duyệt. `attempt_no` phải duy nhất theo từng user. Không được duyệt đồng thời hai lần: service kiểm tra trạng thái dưới transaction.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | Mã của một lần yêu cầu xét duyệt Staff. |
| `user_id` | `bigint` — **NOT NULL** | Tài khoản Staff gửi yêu cầu; giữ nguyên khi đăng ký lại. |
| `attempt_no` | `int` — **NOT NULL** | Số thứ tự lần xin xét duyệt của cùng tài khoản: 1, 2, 3… |
| `status` | `varchar(10)` — **NOT NULL** | Trạng thái riêng của lần xét duyệt: PENDING, APPROVED hoặc REJECTED. |
| `requested_at` | `datetime(6)` — **NOT NULL** | Thời điểm gửi yêu cầu (UTC). |
| `decided_by` | `bigint` | ID Admin đã duyệt/từ chối; chưa xét thì để NULL. |
| `decided_at` | `datetime(6)` | Thời điểm Admin đưa ra quyết định; chưa xét thì NULL. |
| `decision_reason` | `varchar(500)` | Lý do/ghi chú quyết định (tùy chọn); không sửa sau khi đã chốt. |

**Khóa / index khai báo trong DBML:**
- `(user_id, attempt_no) [unique]`
- `(status, requested_at, id)`

**CHECK được khai báo trong DBML (diễn giải):**
- `attempt_no > 0`
- `(status = 'PENDING' AND decided_by IS NULL AND decided_at IS NULL) OR (status IN ('APPROVED','REJECTED') AND decided_by IS NOT NULL AND decided_at IS NOT NULL AND decided_at >= requested_at)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `auth_sessions` — 5 trường

Access JWT ngắn hạn không thay thế kiểm tra phiên: API được bảo vệ phải kiểm tra `auth_sessions` còn hiệu lực và user ACTIVE trên MySQL.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `binary(16)` — **PK** | ID phiên đăng nhập dạng 16 byte (thường dùng UUID lưu nhị phân). |
| `user_id` | `bigint` — **NOT NULL** | Tài khoản sở hữu phiên đăng nhập. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm bắt đầu phiên. |
| `expires_at` | `datetime(6)` — **NOT NULL** | Hạn cuối của phiên; tối đa 8 giờ tính từ created_at. |
| `revoked_at` | `datetime(6)` | Thời điểm thu hồi phiên; NULL nghĩa là chưa bị thu hồi, vẫn phải kiểm tra expires_at. |

**Khóa / index khai báo trong DBML:**
- `(user_id, revoked_at)`
- `expires_at`

**CHECK được khai báo trong DBML (diễn giải):**
- `expires_at > created_at AND expires_at <= DATE_ADD(created_at, INTERVAL 8 HOUR)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `refresh_tokens` — 5 trường

`generation = 1 → 2 → 3` minh họa refresh rotation. Digest cũ được giữ cùng `consumed_at` để phát hiện token cũ bị dùng lại; chỉ lưu hash không thể khôi phục token gốc.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `token_digest` | `binary(32)` — **PK** | SHA-256 digest của refresh token; khóa chính, không lưu secret gốc. |
| `session_id` | `binary(16)` — **NOT NULL** | Phiên đăng nhập phát hành token này. |
| `generation` | `int` — **NOT NULL** | Số thế hệ refresh token trong cùng phiên; tăng mỗi lần rotation. |
| `issued_at` | `datetime(6)` — **NOT NULL** | Thời điểm phát hành token. |
| `consumed_at` | `datetime(6)` | Thời điểm token đã dùng để rotation; NULL nếu chưa consume. |

**Khóa / index khai báo trong DBML:**
- `(session_id, generation) [unique]`

**CHECK được khai báo trong DBML (diễn giải):**
- `generation >= 0 AND (consumed_at IS NULL OR consumed_at >= issued_at)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `account_action_tokens` — 6 trường

TD-01 dùng `STAFF_REAPPLY` để chứng minh quyền kiểm soát email sau khi REJECTED. `PASSWORD_RESET` có chung bảng nhưng là mục đích khác. Link nên mở trang xác nhận, sau đó POST mới consume token.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `token_digest` | `binary(32)` — **PK** | Digest của one-time token gửi qua email; không lưu token gốc. |
| `user_id` | `bigint` — **NOT NULL** | Tài khoản sẽ thực hiện hành động bảo vệ bằng token. |
| `purpose` | `varchar(14)` — **NOT NULL** | Mục đích: PASSWORD_RESET hoặc STAFF_REAPPLY; token hai mục đích không được dùng thay nhau. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm sinh token. |
| `expires_at` | `datetime(6)` — **NOT NULL** | Thời điểm hết hạn; STAFF_REAPPLY đúng 15 phút sau created_at trong DBML. |
| `consumed_at` | `datetime(6)` | Thời điểm token đã sử dụng; giúp ngăn xác minh/reset lặp. |

**Khóa / index khai báo trong DBML:**
- `(user_id, purpose, consumed_at)`
- `expires_at`

**CHECK được khai báo trong DBML (diễn giải):**
- `purpose IN ('PASSWORD_RESET','STAFF_REAPPLY') AND expires_at > created_at`
- `(purpose <> 'STAFF_REAPPLY' OR expires_at = DATE_ADD(created_at, INTERVAL 15 MINUTE))`
- `(consumed_at IS NULL OR consumed_at >= created_at)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

### 4.2. Nhóm Master Data

Lưu danh mục, nhà cung cấp và thông tin sản phẩm hiện tại.

#### `categories` — 6 trường

DBML hiện **không** đặt UNIQUE tên danh mục; không tự suy ra hai danh mục cùng tên bị DB chặn. Trạng thái INACTIVE được backend dùng để chặn gán mới.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | Mã danh mục sản phẩm. |
| `name` | `varchar(120)` — **NOT NULL** | Tên danh mục, ví dụ “Đồ uống”. |
| `description` | `text` — **NULL** | Mô tả tùy chọn của danh mục; API giới hạn tối đa 2.000 ký tự. |
| `status` | `varchar(8)` — **NOT NULL, mặc định 'ACTIVE'** | ACTIVE hoặc INACTIVE; ngừng sử dụng mà vẫn giữ lịch sử. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm tạo danh mục. |
| `updated_at` | `datetime(6)` — **NOT NULL** | Thời điểm sửa gần nhất. |

**CHECK được khai báo trong DBML (diễn giải):**
- `status IN ('ACTIVE','INACTIVE')`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `suppliers` — 7 trường

Một Supplier có nhiều Purchase Receipt; khi Supplier INACTIVE, dữ liệu chứng từ cũ vẫn được giữ qua ID và snapshot.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | Mã nhà cung cấp. |
| `name` | `varchar(160)` — **NOT NULL** | Tên nhà cung cấp. |
| `contact_email` | `varchar(254)` | Email liên hệ (có thể không có). |
| `contact_phone` | `varchar(32)` | Số điện thoại liên hệ (có thể không có). |
| `status` | `varchar(8)` — **NOT NULL, mặc định 'ACTIVE'** | ACTIVE hoặc INACTIVE; không xóa dữ liệu phiếu nhập cũ. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm tạo nhà cung cấp. |
| `updated_at` | `datetime(6)` — **NOT NULL** | Thời điểm sửa gần nhất. |

**CHECK được khai báo trong DBML (diễn giải):**
- `status IN ('ACTIVE','INACTIVE')`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `products` — 8 trường

Một Product thuộc một Category, có giá bán hiện tại và 1 dòng Inventory. **Giá nhập không nằm ở products** mà nằm ở từng dòng phiếu nhập; giá bán lịch sử nằm ở `order_items`.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | ID nội bộ của sản phẩm; khóa liên kết trong kho, chứng từ và báo cáo. |
| `category_id` | `bigint` — **NOT NULL** | Danh mục mà sản phẩm đang thuộc về. |
| `sku` | `varchar(64)` — **UNIQUE, NOT NULL** | Mã sản phẩm duy nhất dùng tra cứu; ví dụ NUOC-001. |
| `name` | `varchar(160)` — **NOT NULL** | Tên sản phẩm đang hiển thị; có thể đổi về sau. |
| `status` | `varchar(8)` — **NOT NULL, mặc định 'ACTIVE'** | ACTIVE hoặc INACTIVE; sản phẩm INACTIVE bị chặn POS/nhập mới theo quy tắc service. |
| `sale_price_vnd` | `bigint` — **NOT NULL** | Đơn giá bán hiện tại, số nguyên VND và lớn hơn 0. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm tạo sản phẩm. |
| `updated_at` | `datetime(6)` — **NOT NULL** | Thời điểm cập nhật sản phẩm/giá gần nhất. |

**Khóa / index khai báo trong DBML:**
- `(category_id, status, id)`
- `(status, id)`
- `(name, id)`

**CHECK được khai báo trong DBML (diễn giải):**
- `status IN ('ACTIVE','INACTIVE') AND sale_price_vnd > 0`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

### 4.3. Nhóm Purchasing

Ghi phiếu nhập đang soạn, đã xác nhận hoặc hủy nháp.

#### `purchase_receipts` — 11 trường

Đây là **đầu phiếu**: ai tạo, nhà cung cấp, trạng thái và tổng tiền. Một phiếu DRAFT không làm tăng kho; CONFIRMED mới cập nhật kho, CANCELLED chỉ hủy DRAFT.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | ID phiếu nhập (header); một phiếu có nhiều dòng sản phẩm. |
| `supplier_id` | `bigint` — **NOT NULL** | Nhà cung cấp của phiếu. |
| `supplier_name_snapshot` | `varchar(160)` | Tên nhà cung cấp chụp tại lúc CONFIRM; lúc CANCEL giữ tên lúc hủy để xem lịch sử. |
| `status` | `varchar(9)` — **NOT NULL, mặc định 'DRAFT'** | DRAFT (đang soạn), CONFIRMED (đã nhập kho), CANCELLED (hủy nháp). |
| `draft_version` | `bigint` — **NOT NULL, mặc định 1** | Phiên bản DRAFT; tăng theo chỉnh sửa và dùng chống ghi đè dữ liệu cũ. |
| `total_vnd` | `bigint` — **NOT NULL, mặc định 0** | Tổng tiền phiếu do backend tính từ các dòng, đơn vị VND. |
| `created_by` | `bigint` — **NOT NULL** | ID Admin tạo phiếu nhập. |
| `closed_by` | `bigint` | ID Admin xác nhận hoặc hủy phiếu; NULL nếu còn DRAFT. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm tạo phiếu. |
| `updated_at` | `datetime(6)` — **NOT NULL** | Thời điểm cập nhật phiếu gần nhất. |
| `closed_at` | `datetime(6)` | Thời điểm xác nhận/hủy; NULL nếu còn DRAFT. |

**Khóa / index khai báo trong DBML:**
- `(created_at, id)`
- `(status, created_at, id)`
- `(supplier_id, created_at, id)`

**CHECK được khai báo trong DBML (diễn giải):**
- `draft_version >= 1 AND total_vnd >= 0`
- `(status = 'DRAFT' AND closed_by IS NULL AND closed_at IS NULL) OR (status IN ('CONFIRMED','CANCELLED') AND closed_by IS NOT NULL AND closed_at IS NOT NULL AND supplier_name_snapshot IS NOT NULL)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `purchase_receipt_items` — 7 trường

Đây là **dòng hàng của phiếu**. Khóa chính `(receipt_id, product_id)` bảo vệ tối đa một dòng cho một Product trong một phiếu. Service phải gộp cùng giá, từ chối khác giá theo PUR-02.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `receipt_id` | `bigint` — **NOT NULL** | ID phiếu nhập chứa dòng hàng. |
| `product_id` | `bigint` — **NOT NULL** | ID sản phẩm được nhập. |
| `sku_snapshot` | `varchar(64)` — **NOT NULL** | SKU được chụp vào dòng; làm mới/chốt khi CONFIRM, hoặc giữ lúc CANCEL. |
| `product_name_snapshot` | `varchar(160)` — **NOT NULL** | Tên sản phẩm được chụp để lịch sử không đổi theo tên sản phẩm hiện tại. |
| `quantity` | `int` — **NOT NULL** | Số lượng nhập, số nguyên dương. |
| `unit_cost_vnd` | `bigint` — **NOT NULL** | Giá nhập của một đơn vị sản phẩm, số nguyên VND không âm. |
| `line_total_vnd` | `bigint` — **NOT NULL** | Thành tiền của dòng = quantity × unit_cost_vnd. |

**Khóa / index khai báo trong DBML:**
- `(receipt_id, product_id) [pk]`

**CHECK được khai báo trong DBML (diễn giải):**
- `quantity > 0 AND unit_cost_vnd >= 0 AND line_total_vnd = CAST(quantity AS DECIMAL(30,0)) * unit_cost_vnd`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

### 4.4. Nhóm Inventory

Lưu số tồn hiện tại, lịch sử kiểm kê và mọi biến động kho.

#### `inventory` — 5 trường

Đây là **tồn kho hiện tại**, không phải lịch sử. Khi thêm Product mới, service phải tạo dòng inventory với `quantity = 0`; FK không tự tạo dòng đó.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `product_id` | `bigint` — **PK** | ID sản phẩm; đồng thời là PK, mỗi sản phẩm có tối đa một dòng tồn kho. |
| `quantity` | `int` — **NOT NULL, mặc định 0** | Số đơn vị hiện có trong kho; không âm. |
| `stock_version` | `bigint` — **NOT NULL, mặc định 0** | Số phiên bản tồn kho; tăng mỗi lần lượng tồn thay đổi, trừ no-op. |
| `first_stocked_at` | `datetime(6)` | Lần đầu tồn từ 0 chuyển sang dương do nhập hoặc điều chỉnh; dùng phân tích slow-moving. |
| `updated_at` | `datetime(6)` — **NOT NULL** | Lần cập nhật tồn kho gần nhất. |

**Khóa / index khai báo trong DBML:**
- `(quantity, product_id)`

**CHECK được khai báo trong DBML (diễn giải):**
- `quantity >= 0 AND stock_version >= 0 AND (quantity = 0 OR first_stocked_at IS NOT NULL)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `inventory_adjustments` — 8 trường

Admin nhập `counted_quantity` (số đếm thực tế), **không nhập delta**. Nếu số đếm bằng tồn và version hợp lệ: ghi audit nhưng không tạo stock movement.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | ID của một lần kiểm kê/điều chỉnh. |
| `product_id` | `bigint` — **NOT NULL** | Sản phẩm được kiểm kê. |
| `actor_id` | `bigint` — **NOT NULL** | Admin thực hiện điều chỉnh. |
| `reason` | `varchar(500)` — **NOT NULL** | Lý do kiểm kê/điều chỉnh, bắt buộc có nội dung. |
| `quantity_before` | `int` — **NOT NULL** | Số tồn được backend đọc trước khi đối chiếu. |
| `counted_quantity` | `int` — **NOT NULL** | Số lượng thực tế Admin nhập vào khi kiểm kê. |
| `version_before` | `bigint` — **NOT NULL** | stock_version hợp lệ tại thời điểm thực hiện adjustment. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm ghi nhận kiểm kê. |

**Khóa / index khai báo trong DBML:**
- `(id, product_id) [unique]`
- `(product_id, created_at, id)`

**CHECK được khai báo trong DBML (diễn giải):**
- `quantity_before >= 0 AND counted_quantity >= 0 AND version_before >= 0 AND CHAR_LENGTH(TRIM(reason)) > 0`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `stock_movements` — 12 trường

Đây là **sổ cái biến động kho** (ledger). Mỗi lần tăng/giảm kho khác 0 có một dòng movement tương ứng; khóa ngoại ghép kiểm tra sản phẩm đúng dòng chứng từ. Bảng không tự chứng minh `quantity_after` khớp inventory nếu có writer bỏ qua service.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | ID duy nhất của một biến động kho. |
| `product_id` | `bigint` — **NOT NULL** | Sản phẩm có tồn kho thay đổi. |
| `actor_id` | `bigint` — **NOT NULL** | Tài khoản thực hiện nghiệp vụ gây biến động. |
| `kind` | `varchar(16)` — **NOT NULL** | Loại biến động: PURCHASE_CONFIRM, SALE, ORDER_CANCEL hoặc ADJUSTMENT. |
| `receipt_id` | `bigint` | Phiếu nhập nguồn nếu kind = PURCHASE_CONFIRM; ngoài ra NULL. |
| `order_id` | `bigint` | Đơn bán nguồn nếu kind = SALE hoặc ORDER_CANCEL; ngoài ra NULL. |
| `adjustment_id` | `bigint` | Lần kiểm kê nguồn nếu kind = ADJUSTMENT; ngoài ra NULL. |
| `sku_snapshot` | `varchar(64)` — **NOT NULL** | SKU tại thời điểm phát sinh movement để giữ ngữ cảnh lịch sử. |
| `quantity_before` | `int` — **NOT NULL** | Tồn kho ngay trước biến động. |
| `quantity_after` | `int` — **NOT NULL** | Tồn kho ngay sau biến động; chênh lệch là lượng nhập/xuất. |
| `stock_version_after` | `bigint` — **NOT NULL** | Phiên bản tồn kho sau thay đổi, giúp truy vết thứ tự trên từng sản phẩm. |
| `occurred_at` | `datetime(6)` — **NOT NULL** | Thời điểm biến động được ghi nhận. |

**Khóa / index khai báo trong DBML:**
- `(product_id, stock_version_after) [unique]`
- `(receipt_id, product_id) [unique]`
- `(order_id, product_id, kind) [unique]`
- `(adjustment_id, product_id) [unique]`
- `(product_id, occurred_at, id)`
- `(occurred_at, id)`

**CHECK được khai báo trong DBML (diễn giải):**
- `quantity_before >= 0 AND quantity_after >= 0 AND quantity_before <> quantity_after AND stock_version_after > 0`
- `(kind = 'PURCHASE_CONFIRM' AND receipt_id IS NOT NULL AND order_id IS NULL AND adjustment_id IS NULL AND quantity_after > quantity_before) OR (kind IN ('SALE','ORDER_CANCEL') AND order_id IS NOT NULL AND receipt_id IS NULL AND adjustment_id IS NULL AND ((kind = 'SALE' AND quantity_after < quantity_before) OR (kind = 'ORDER_CANCEL' AND quantity_after > quantity_before))) OR (kind = 'ADJUSTMENT' AND adjustment_id IS NOT NULL AND receipt_id IS NULL AND order_id IS NULL)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

### 4.5. Nhóm Sales

Lưu đơn bán và từng sản phẩm đã bán theo giá tại thời điểm checkout.

#### `orders` — 8 trường

Đây là **đầu đơn bán**. Staff chỉ được hủy đơn mình tạo trong 15 phút và cùng ngày kinh doanh Việt Nam; Admin có thể hủy mọi đơn trong cùng ngày. Quy tắc quyền và thời gian là logic service.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | ID đơn bán tại quầy. |
| `status` | `varchar(9)` — **NOT NULL, mặc định 'COMPLETED'** | COMPLETED ngay khi checkout thành công; CANCELLED nếu hủy hợp lệ. |
| `total_vnd` | `bigint` — **NOT NULL** | Tổng giá trị đơn đã chốt theo giá bán lúc checkout. |
| `created_by` | `bigint` — **NOT NULL** | ID Admin/Staff tạo đơn. |
| `sold_at` | `datetime(6)` — **NOT NULL** | Thời điểm bán gốc (UTC); dùng tính ngày kinh doanh VN, kể cả khi đơn bị hủy. |
| `cancelled_by` | `bigint` | ID người hủy; NULL khi đơn chưa hủy. |
| `cancelled_at` | `datetime(6)` | Thời điểm hủy (UTC); NULL khi đơn chưa hủy. |
| `cancel_reason` | `varchar(500)` | Lý do hủy bắt buộc nếu trạng thái CANCELLED. |

**Khóa / index khai báo trong DBML:**
- `(sold_at, id)`
- `(status, sold_at, id)`

**CHECK được khai báo trong DBML (diễn giải):**
- `total_vnd > 0`
- `(status = 'COMPLETED' AND cancelled_by IS NULL AND cancelled_at IS NULL AND cancel_reason IS NULL) OR (status = 'CANCELLED' AND cancelled_by IS NOT NULL AND cancelled_at IS NOT NULL AND cancelled_at >= sold_at AND cancel_reason IS NOT NULL AND CHAR_LENGTH(TRIM(cancel_reason)) > 0)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

#### `order_items` — 7 trường

Đây là **dòng hàng bán**. Snapshot giúp đơn cũ hiển thị đúng tên/giá bán ngay cả khi sau này Product đổi tên hoặc giá.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `order_id` | `bigint` — **NOT NULL** | Đơn bán chứa dòng hàng. |
| `product_id` | `bigint` — **NOT NULL** | Sản phẩm được bán. |
| `sku_snapshot` | `varchar(64)` — **NOT NULL** | SKU tại thời điểm checkout. |
| `product_name_snapshot` | `varchar(160)` — **NOT NULL** | Tên sản phẩm tại thời điểm checkout. |
| `quantity` | `int` — **NOT NULL** | Số lượng bán của sản phẩm trong đơn. |
| `unit_price_vnd` | `bigint` — **NOT NULL** | Đơn giá bán chụp tại checkout, không thay đổi khi bảng products đổi giá. |
| `line_total_vnd` | `bigint` — **NOT NULL** | Thành tiền dòng bán = quantity × unit_price_vnd. |

**Khóa / index khai báo trong DBML:**
- `(order_id, product_id) [pk]`

**CHECK được khai báo trong DBML (diễn giải):**
- `quantity > 0 AND unit_price_vnd > 0 AND line_total_vnd = CAST(quantity AS DECIMAL(30,0)) * unit_price_vnd`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

### 4.6. Nhóm Idempotency

Ngăn retry request làm lặp tác động nghiệp vụ.

#### `idempotency_records` — 9 trường

TD-04C phương án A: INSERT claim, thực hiện nghiệp vụ, lưu response hoàn tất trong **cùng một transaction**. Nếu rollback, claim cũng mất; không cần lease `locked_until` cho command đồng bộ.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `user_id` | `bigint` — **NOT NULL** | Người gửi business command; một phần namespace của idempotency key. |
| `operation` | `varchar(20)` — **NOT NULL** | Loại lệnh: CHECKOUT, CONFIRM_RECEIPT, CANCEL_ORDER, INVENTORY_ADJUSTMENT. |
| `key_digest` | `binary(32)` — **NOT NULL** | Digest của Idempotency-Key do client cung cấp; không phải request digest. |
| `request_digest` | `binary(32)` — **NOT NULL** | Fingerprint của payload đã chuẩn hóa để phát hiện cùng key nhưng khác nội dung. |
| `response_status` | `smallint` | HTTP status đã hoàn tất để phát lại; NULL khi còn trong transaction chưa xong. |
| `response_body` | `json` | Nội dung response đã hoàn tất, để retry trả đúng kết quả cũ. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm bắt đầu thao tác/idempotency record. |
| `completed_at` | `datetime(6)` | Thời điểm xử lý được đánh dấu hoàn tất. |
| `expires_at` | `datetime(6)` | Thời điểm hết hạn lưu kết quả hoàn tất: completed_at + 24 giờ. |

**Khóa / index khai báo trong DBML:**
- `(user_id, operation, key_digest) [pk, note: 'TD-04C: INSERT claim, execute command, and store completed response before a single COMMIT; never commit IN_PROGRESS alone']`
- `expires_at`

**CHECK được khai báo trong DBML (diễn giải):**
- `operation IN ('CHECKOUT','CONFIRM_RECEIPT','CANCEL_ORDER','INVENTORY_ADJUSTMENT')`
- `(response_status IS NULL AND response_body IS NULL AND completed_at IS NULL AND expires_at IS NULL) OR (response_status IS NOT NULL AND response_status BETWEEN 200 AND 499 AND response_body IS NOT NULL AND completed_at IS NOT NULL AND expires_at IS NOT NULL AND expires_at = DATE_ADD(completed_at, INTERVAL 24 HOUR))`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

### 4.7. Nhóm Outbox

Giữ ý định email bền vững và trạng thái xử lý bất đồng bộ.

#### `outbox_events` — 14 trường

Đây là **ý định gửi email bền vững**. Business transaction lưu event; publisher gửi RabbitMQ sau commit; worker thực hiện SMTP. `SENT` không đồng nghĩa chắc chắn email ngoài Internet được gửi đúng một lần.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `binary(16)` — **PK** | Event ID cố định dạng 16 byte, đi theo message để publisher/worker nhận biết cùng sự kiện. |
| `subject_user_id` | `bigint` — **NOT NULL** | Tài khoản liên quan trực tiếp tới email/sự kiện. |
| `event_type` | `varchar(32)` — **NOT NULL** | Loại event: STAFF_REGISTERED, STAFF_APPROVED, STAFF_REJECTED, PASSWORD_RESET, STAFF_REAPPLY_PROOF. |
| `payload` | `json` — **NOT NULL** | Dữ liệu event dạng JSON đã version hóa; không chứa token plaintext hoặc thông tin nhạy cảm không cần thiết. |
| `secret_expires_at` | `datetime(6)` | Thời điểm hết hạn secret đính kèm (nếu có). |
| `secret_ciphertext` | `varbinary(2048)` | Bản mã của secret dùng tạo link email một lần, không phải plaintext; cần scrub khi kết thúc/hết hạn. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm event được tạo cùng transaction nghiệp vụ. |
| `available_at` | `datetime(6)` — **NOT NULL** | Thời điểm sớm nhất event được phép đưa vào xử lý. |
| `published_at` | `datetime(6)` | Thời điểm publisher đã nhận broker confirm từ RabbitMQ; NULL là chưa được xác nhận publish. |
| `publish_attempts` | `int` — **NOT NULL, mặc định 0** | Số lần publisher thử publish. |
| `delivery_attempts` | `int` — **NOT NULL, mặc định 0** | Số lần worker thử gửi email. |
| `outcome` | `varchar(9)` | Kết quả cuối: SENT, FAILED hoặc SKIPPED; NULL khi chưa kết thúc. |
| `finished_at` | `datetime(6)` | Thời điểm ghi nhận kết quả cuối. |
| `last_error_code` | `varchar(64)` | Mã lỗi gần nhất phục vụ xử lý và theo dõi, không chứa secret. |

**Khóa / index khai báo trong DBML:**
- `(published_at, available_at, id) [note: 'Single publisher polls unpublished due events']`
- `(outcome, finished_at, id) [note: 'Retention and terminal status query']`

**CHECK được khai báo trong DBML (diễn giải):**
- `event_type IN ('STAFF_REGISTERED','STAFF_APPROVED','STAFF_REJECTED','PASSWORD_RESET','STAFF_REAPPLY_PROOF')`
- `(outcome IS NULL AND finished_at IS NULL) OR (outcome IN ('SENT','FAILED','SKIPPED') AND finished_at IS NOT NULL)`
- `publish_attempts >= 0 AND delivery_attempts >= 0`
- `secret_ciphertext IS NULL OR secret_expires_at IS NOT NULL`
- `available_at >= created_at`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

### 4.8. Nhóm Notifications

Thông báo in-app cho Admin về yêu cầu xét duyệt Staff.

#### `admin_notifications` — 5 trường

Đây là thông báo **trong ứng dụng**, khác email. Unique `approval_request_id` tránh tạo trùng thông báo cho cùng một lượt đăng ký.

| Trường | Kiểu DBML | Ý nghĩa dễ hiểu |
|---|---|---|
| `id` | `bigint` — **PK** | ID thông báo trong ứng dụng của Admin. |
| `admin_user_id` | `bigint` — **NOT NULL** | Admin nhận thông báo (RetailOps V1 có một Admin). |
| `approval_request_id` | `bigint` — **UNIQUE, NOT NULL** | Yêu cầu Staff làm phát sinh thông báo; unique tránh lặp cho cùng request. |
| `created_at` | `datetime(6)` — **NOT NULL** | Thời điểm tạo thông báo. |
| `read_at` | `datetime(6)` | Thời điểm Admin đã đọc; NULL nghĩa là chưa đọc. |

**Khóa / index khai báo trong DBML:**
- `(admin_user_id, read_at, created_at, id)`

**Lưu ý:** Nếu một trường là FK, quan hệ thật được khai báo ở cuối file DBML; xem thêm mục 6.

## 5. Năm luồng nghiệp vụ minh họa

### 5.1 Đăng ký Staff và xét duyệt

1. Tạo `users` với `role=STAFF`, `status=PENDING_APPROVAL` và một dòng `staff_approval_requests` lần 1 ở trạng thái `PENDING`.
2. Tạo `admin_notifications` gắn với approval request, ghi event `STAFF_REGISTERED` trong `outbox_events` cùng transaction.
3. Admin duyệt hoặc từ chối: cập nhật attempt, đổi trạng thái user, ghi event email sau commit.
4. Nếu REJECTED muốn đăng ký lại: phát `account_action_tokens` purpose `STAFF_REAPPLY`; sau xác minh token, tạo attempt tiếp theo trên **cùng** user ID.

### 5.2 Nhập 2 sản phẩm

1. Tạo `purchase_receipts` trạng thái `DRAFT` với hai dòng `purchase_receipt_items`.
2. Giả sử Product A số lượng 3, unit_cost 10.000 VND: line_total = 30.000 VND; Product B số lượng 2, unit_cost 20.000 VND: line_total = 40.000 VND; total = 70.000 VND.
3. Khi Admin Confirm: khóa phiếu và các sản phẩm/tồn kho theo quy ước; lưu snapshot; tăng `inventory.quantity`; ghi một `stock_movements` cho mỗi Product; chuyển receipt sang `CONFIRMED` trong cùng transaction.
4. Nếu gửi lại confirm cùng Idempotency-Key, trả kết quả cũ thay vì cộng kho lần nữa.

### 5.3 Checkout POS

1. Staff bán 2 đơn vị Product A, giá hiện tại 15.000 VND: tạo `orders` COMPLETED và `order_items` với giá snapshot 15.000.
2. Trừ `inventory.quantity` đi 2, tăng `stock_version`, ghi `stock_movements` kind SALE với quantity_before/after.
3. Ghi `idempotency_records` completion cùng transaction. Nếu giá đã đổi, trả 409 PRICE_CHANGED, không tạo đơn hay biến động.

### 5.4 Hủy đơn

1. Khóa `orders` và kiểm tra quyền: Staff chỉ hủy đơn mình tạo trong 15 phút và cùng ngày VN; Admin hủy mọi đơn trong ngày VN.
2. Nếu hợp lệ: đổi `orders.status=CANCELLED`, lưu actor/thời điểm/lý do; tăng tồn lại đúng lượng theo item gốc; ghi `stock_movements` kind ORDER_CANCEL.
3. Tất cả commit cùng nhau; retry hoặc request hủy thứ hai không được hoàn kho lại.

### 5.5 Điều chỉnh kho và gửi email

1. Điều chỉnh kho: Admin đếm thực tế (`counted_quantity`), backend kiểm tra `stock_version` rồi ghi `inventory_adjustments`.
2. Nếu số đếm giống số tồn và version hợp lệ: chỉ ghi adjustment audit, **không** sinh stock movement.
3. Gửi email: business transaction ghi `outbox_events`; publisher gửi RabbitMQ sau commit; Celery Worker gửi Mailpit hoặc SMTP thật; event lưu thời điểm publish, số lần thử và kết quả cuối; V1 chỉ một publisher và worker tuần tự.

## 6. Danh sách 27 quan hệ FK đúng như DBML

| # | Khóa ngoại (bảng con) | Tham chiếu tới | Ý nghĩa |
|---:|---|---|---|
| 1 | `staff_approval_requests.user_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 2 | `staff_approval_requests.decided_by` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 3 | `auth_sessions.user_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 4 | `refresh_tokens.session_id` | `auth_sessions.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 5 | `account_action_tokens.user_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 6 | `products.category_id` | `categories.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 7 | `purchase_receipts.supplier_id` | `suppliers.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 8 | `purchase_receipts.created_by` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 9 | `purchase_receipts.closed_by` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 10 | `purchase_receipt_items.receipt_id` | `purchase_receipts.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 11 | `purchase_receipt_items.product_id` | `products.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 12 | `inventory.product_id` | `products.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 13 | `inventory_adjustments.product_id` | `inventory.product_id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 14 | `inventory_adjustments.actor_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 15 | `orders.created_by` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 16 | `orders.cancelled_by` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 17 | `order_items.order_id` | `orders.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 18 | `order_items.product_id` | `products.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 19 | `stock_movements.product_id` | `inventory.product_id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 20 | `stock_movements.actor_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 21 | `stock_movements.(receipt_id, product_id)` | `purchase_receipt_items.(receipt_id, product_id)` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 22 | `stock_movements.(order_id, product_id)` | `order_items.(order_id, product_id)` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 23 | `stock_movements.(adjustment_id, product_id)` | `inventory_adjustments.(id, product_id)` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 24 | `idempotency_records.user_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 25 | `outbox_events.subject_user_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 26 | `admin_notifications.admin_user_id` | `users.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |
| 27 | `admin_notifications.approval_request_id` | `staff_approval_requests.id` | Cột ở bên trái phải tham chiếu dòng hợp lệ ở bên phải; quan hệ có thể dùng nhiều cột. |

**Đáng nhớ:** Ba FK ghép của `stock_movements` bảo đảm Movement cho Product X chỉ tham chiếu đúng Product X trong receipt/order/adjustment tương ứng. Tuy vậy FK không tự kiểm tra số lượng thay đổi có bằng số lượng chứng từ hay không.

## 7. Điều Database bảo vệ và điều Service phải bảo vệ

| Quy tắc | DBML hỗ trợ | Phần còn cần ở Backend / Tests |
|---|---|---|
| Email và SKU duy nhất | UNIQUE trên cột canonical | Chuẩn hóa email/SKU và xác minh collation nhị phân trong migration. |
| Tối đa một Admin | CHECK + UNIQUE admin_slot | Seed đúng một Admin và chặn role injection; UNIQUE không bảo đảm tự có Admin. |
| Product có dòng inventory 0 khi tạo | FK inventory → products, default quantity 0 | Product creation transaction phải tạo dòng inventory; FK không tạo tự động. |
| PUR-02 gộp dòng theo Product + Unit Cost | PK(receipt_id,product_id) | Service gộp cùng giá; từ chối khác giá; kiểm tổng, version và trạng thái DRAFT. |
| Tồn kho không âm | CHECK quantity>=0 | Lock/atomic guarded update, rollback, ledger và transaction. |
| No-op adjustment | Bảng adjustment không bắt buộc movement | Check version trước; ghi audit nhưng không ghi movement và không tăng stock_version. |
| Không checkout/hủy lặp | UNIQUE movement, idempotency composite PK | State guard, row locks, payload digest và cùng một commit. |
| Session 8 giờ, refresh rotation | CHECK expires_at<=created_at+8h, generation unique | Revoke/session validation mỗi request; rotation lock và replay detection. |
| Email không mất intent | Outbox row trong MySQL | Business + outbox cùng transaction; một publisher polling, broker confirm, một email worker tuần tự, worker retry/crash test. |
| Email gửi đúng một lần | Không bảo đảm bởi schema | SMTP bên ngoài có thể gửi trùng khi crash sau provider accept; không cam kết exactly-once. |
| Ngày kinh doanh Việt Nam | Lưu sold_at UTC | Service/query tính khoảng [00:00, 00:00 hôm sau) theo Asia/Ho_Chi_Minh. |
| AI read-only | Bảng Order/Inventory/Products đủ cho phân tích | Tool allowlist, Admin RBAC, bounded read APIs; không có bảng conversation. |

## 8. Outbox Lite và AI read-only trong phiên bản chốt

### 8.1 Outbox Lite: vừa đủ để học và triển khai

- **Chỉ một publisher:** quét `outbox_events` có `published_at IS NULL` và `available_at <= now`, publish RabbitMQ persistent message, chờ broker confirm rồi ghi `published_at`.
- **Một email worker xử lý tuần tự:** nhận event ID, nạp dữ liệu từ MySQL; gửi qua Mailpit khi test local, qua SMTP provider khi test Gmail thật.
- **Trạng thái:** `publish_attempts` cho publisher, `delivery_attempts` cho worker, `outcome` (`SENT`, `FAILED`, `SKIPPED`) và `finished_at` cho kết quả cuối.
- **Failure mode cần chấp nhận:** publisher crash sau broker confirm nhưng trước update MySQL sẽ publish lại; worker crash sau SMTP accept cũng có thể gửi trùng email. Không cam kết external exactly-once.
- **Giới hạn scale:** không chạy đồng thời nhiều publisher hoặc nhiều consumer email cho đến khi có claim/lease và fencing protocol mới; chỉ một worker không tự động khiến duplicate do broker/retry biến mất.
- **Bảo mật:** link reset/reapply chỉ lưu digest trong `account_action_tokens`. Nếu cần worker gửi link sau commit, secret mã hóa bằng AEAD trong `secret_ciphertext`, khóa ở ngoài DB, scrub ngay khi đã xử lý hoặc hết hạn; tuyệt đối không log plaintext token.

### 8.2 AI 3A+ sử dụng chính database này

| AI tool read-only | Đọc dữ liệu qua service | Quy tắc cần thống nhất |
|---|---|---|
| `get_sales_summary` | `orders` | Chỉ đơn hiện COMPLETED tính doanh thu/AOV; số đơn CANCELLED tính theo kỳ bán gốc |
| `get_top_selling_products` | `orders`, `order_items`, `products` | Chỉ tổng số lượng của đơn còn COMPLETED |
| `get_low_stock_products` | `products`, `inventory` | Product ACTIVE, stock ≤5 theo P0 |
| `get_slow_moving_products` | `products`, `inventory`, `orders`, `order_items` | ACTIVE, còn stock, first_stocked_at >7 ngày trước và lượng bán 30 ngày ≤2 |

Admin → FastAPI JWT/session/RBAC → AI Service → LLM tool proposal → Tool Executor (allowlist/Pydantic/timeout) → Analytics/Inventory Services → MySQL. LLM không được gửi SQL tự do hoặc thao tác ghi. Không cần bảng AI conversation/embedding và Outbox không tham gia luồng chat.

### 8.3 Điểm chưa được database tự bảo đảm

- API/Service phải enforce transitions DRAFT/CONFIRMED/CANCELLED và immutable snapshot; các FK/CHECK một dòng không tự bảo đảm bất biến qua nhiều bảng.
- `outbox_events` không tự ngăn việc xử lý bởi hai publisher/worker nếu vô tình cấu hình nhiều instance; đây là giả định vận hành V1 và phải có deployment guard/checklist.
- Các giá trị đầu vào ở upper-bound (quantity, total VND, item count) phải được giới hạn và kiểm thử; CHECK không thay thế validation.
- Kiểm tra DBML parser và MySQL 8 migrations thực trước khi tuyên bố Migration-Ready; không suy từ sơ đồ render thành công.

## 9. Các điểm cần nhớ khi dùng tài liệu này

1. Đây là tài liệu **giải thích schema hiện có**, không thay thế bản DBML và không phải bằng chứng migration đã chạy thành công.
2. Các `checks {}` trong DBML cần được xuất và thử trên MySQL 8 thật; mô tả ở đây không chứng minh engine đã thực thi.
3. `UNIQUE`/FK không tự đảm bảo transaction atomic, không oversell, không gửi email trùng hoặc audit append-only. Đây là trách nhiệm của protocol và test.
4. Những dữ liệu như tên Staff, `business_date_vn`, mã phiếu dễ đọc, ngưỡng riêng P1 **không có trong DBML này**; không được tự hiểu là đang được lưu ở một cột ẩn.
5. `created_at`, `sold_at`, `occurred_at` chỉ rõ ý nghĩa thời điểm khác nhau. Đừng dùng `created_at` của Product thay cho `first_stocked_at`.
6. Các ví dụ nghiệp vụ mô tả hành vi hệ thống kỳ vọng theo quyết định đã thống nhất, không phải SQL trigger hay tự động hóa từ khóa ngoại.

---
**Nguồn:** `RetailOps_ERD_V1.0_Chot_Thiet_Ke.dbml`. **Tình trạng:** tài liệu học tập/tra cứu đi kèm baseline thiết kế; chưa phải Migration-Validated Database Design.
