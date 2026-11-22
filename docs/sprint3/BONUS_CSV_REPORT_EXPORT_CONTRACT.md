# Contract: Bonus CSV Report Export (Task T3C9F4A)

## 1. Overview
This contract specifies the CSV export capabilities for RetailOps V1.0 (Task `T3C9F4A` / `ANA-05`).
All export endpoints are strictly **read-only**, available exclusively to authenticated users possessing the **`ADMIN`** role, and safeguarded against CSV Formula Injection (CWE-1236) and large data overflows.

---

## 2. Global Security & Formatting Rules

### 2.1 Authorization & Authentication (RBAC)
- All CSV export endpoints require active authentication and administrative privileges (`Depends(require_active_admin)`).
- **401 Unauthorized (`UNAUTHENTICATED`)**: Caller does not provide a valid Bearer token or session.
- **403 Forbidden (`FORBIDDEN`)**: Caller possesses `STAFF` role or account status is not `ACTIVE`.

### 2.2 Character Encoding & Microsoft Excel Compatibility
- **UTF-8 with BOM**: The response byte stream MUST begin with the UTF-8 Byte Order Mark (`\ufeff` / `b"\xef\xbb\xbf"`). This prevents Mojibake / garbled text when opening Vietnamese text files in Microsoft Excel on Windows/macOS.
- **Line Terminators**: Rows are terminated with standard CRLF (`\r\n`).
- **Response Headers**:
  - `Content-Type: text/csv; charset=utf-8`
  - `Content-Disposition: attachment; filename="<filename>.csv"`
  - `Cache-Control: no-store`

### 2.3 CSV Formula Injection Prevention (CWE-1236)
Any cell value that begins with formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`), either directly or after leading whitespace, MUST be prepended with a single quote character (`'`).
This forces spreadsheet software (e.g. Microsoft Excel, LibreOffice Calc, Google Sheets) to treat the cell contents strictly as plain text rather than executable formulas or DDE commands.

### 2.4 Max Export Row Limitation
- **Maximum Limit**: `MAX_EXPORT_ROWS = 5000` records.
- If the number of matching records to be exported exceeds 5,000, the system must NOT truncate silently; instead, it raises a `DomainValidationError` (HTTP status 422):
  ```json
  {
    "code": "VALIDATION_ERROR",
    "message": "Số lượng bản ghi ({count}) vượt quá giới hạn xuất tối đa 5000. Vui lòng thu hẹp bộ lọc.",
    "details": null
  }
  ```

---

## 3. Endpoints Specification

### 3.1 Orders CSV Export (`GET /api/v1/orders/export/csv`)

- **Path**: `GET /api/v1/orders/export/csv`
- **Role**: `ADMIN` only
- **Query Parameters**:
  - `status`: Optional order status filter (`COMPLETED` | `CANCELLED`).
  - `from_date`: Optional start date (`YYYY-MM-DD`, inclusive) in Vietnam business date (`Asia/Ho_Chi_Minh`).
  - `to_date`: Optional end date (`YYYY-MM-DD`, inclusive) in Vietnam business date (`Asia/Ho_Chi_Minh`).
  - `search`: Optional search query (matches exact numeric Order ID or partial SKU snapshot).
- **Structure**: Flattened line-item representation (one row per order item).
- **Columns (Header)**:
  1. `Mã đơn` (Order ID integer)
  2. `Ngày bán (VN)` (`YYYY-MM-DD HH:mm:ss` in `Asia/Ho_Chi_Minh`)
  3. `Trạng thái` (`COMPLETED` | `CANCELLED`)
  4. `SKU` (Snapshot SKU)
  5. `Tên sản phẩm` (Snapshot product name)
  6. `Số lượng` (Item quantity integer)
  7. `Đơn giá (VNĐ)` (Unit price integer VND)
  8. `Thành tiền (VNĐ)` (Line total integer VND)
  9. `Tổng đơn (VNĐ)` (Order total integer VND)
  10. `Người tạo` (Creator full name or identifier)
  11. `Lý do hủy` (Cancellation reason or empty string if not cancelled)
- **Default Filename**: `orders_export_<timestamp>.csv`

---

### 3.2 Daily Sales Analytics CSV Export (`GET /api/v1/analytics/sales/daily/export/csv`)

- **Path**: `GET /api/v1/analytics/sales/daily/export/csv`
- **Role**: `ADMIN` only
- **Query Parameters**:
  - `from` / `from_date`: Optional start date (`YYYY-MM-DD`). Defaults to 30 days ago in Vietnam business time if omitted.
  - `to` / `to_date`: Optional end date (`YYYY-MM-DD`). Defaults to current date in Vietnam business time if omitted.
- **Business Logic**:
  - Aggregated daily by Vietnam business date (`Asia/Ho_Chi_Minh`).
  - `CANCELLED` orders are strictly excluded from net revenue (`revenue_vnd`) and AOV (`aov_vnd`), counting only towards `cancelled_orders`.
  - Average Order Value (AOV) is computed as `ROUND_HALF_UP(revenue_vnd / completed_orders)` when `completed_orders > 0`, else `0`.
- **Columns (Header)**:
  1. `Ngày` (`YYYY-MM-DD`)
  2. `Doanh thu thuần (VNĐ)` (Net revenue integer VND)
  3. `Số đơn hoàn tất` (Count of completed orders)
  4. `Số đơn hủy` (Count of cancelled orders)
  5. `Giá trị trung bình đơn (VNĐ)` (AOV integer VND)
- **Default Filename**: `daily_sales_export_<from>_<to>.csv`

---

### 3.3 Inventory CSV Export (`GET /api/v1/inventory/export/csv`)

- **Path**: `GET /api/v1/inventory/export/csv`
- **Role**: `ADMIN` only
- **Query Parameters**:
  - `category_id`: Optional category ID integer.
  - `status`: Optional catalog status (`ACTIVE` | `INACTIVE`).
  - `in_stock`: Optional boolean (`true` for quantity > 0, `false` for quantity == 0).
  - `low_stock_only`: Optional boolean (if `true`, filters items with current stock `<= 5`).
- **Security & Privacy Invariant**:
  - `unit_cost_vnd` (cost price) MUST NEVER be exported. Only the public selling list price (`sale_price_vnd`) is exported.
- **Columns (Header)**:
  1. `Mã SP` (Product ID integer)
  2. `SKU` (Product SKU)
  3. `Tên sản phẩm` (Product Name)
  4. `Danh mục` (Category Name resolved via join)
  5. `Trạng thái` (`ACTIVE` | `INACTIVE`)
  6. `Tồn kho hiện tại` (Current quantity integer)
  7. `Giá bán niêm yết (VNĐ)` (`sale_price_vnd` integer VND)
  8. `Ngày nhập đầu tiên (VN)` (`YYYY-MM-DD HH:mm:ss` in `Asia/Ho_Chi_Minh` or empty if null)
- **Default Filename**: `inventory_export_<timestamp>.csv`

---

## 4. Frontend Integration Contract
- Role Guard: Buttons are displayed only when `user?.role === 'ADMIN'`.
- Safe Blob Download: Handles `responseType: 'blob'`, reads `content-disposition` header for filename, and inspects Blob for JSON error envelopes (mapping to user-friendly toast alerts).
- Non-blocking: Download requests run with loading states on the respective button without freezing tables or navigating away.

