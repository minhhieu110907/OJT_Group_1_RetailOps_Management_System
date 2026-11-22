# Contract: Bonus CSV Product Import (Task T3C9EFC)

## 1. Overview
This contract specifies the Admin CSV Product Import feature for RetailOps V1.0 (`T3C9EFC`).
The endpoint allows an authenticated **`ADMIN`** to upload a CSV file of products (`sku`, `name`, `category`/`category_id`, `price`/`sale_price_vnd`, optional `image_url`), validates every row independently against existing Product & Category business rules, imports all valid rows with initial zero-stock `Inventory`, skips invalid rows without rolling back valid rows (**partial success**), and returns a detailed row-level error report.

No database migration or breaking changes to `contracts/openapi.yaml` are required.

---

## 2. Endpoint Specification

- **Path**: `POST /api/v1/products/import/csv`
- **Authorization**: `ADMIN` only (`Depends(require_active_admin)`)
  - `401 UNAUTHENTICATED`: Missing, invalid, expired, or revoked Bearer token/session.
  - `403 FORBIDDEN`: `STAFF` or non-`ACTIVE` account.
- **Supported Content-Types** (zero extra runtime dependencies):
  - `multipart/form-data` with file field `file` (`.csv`)
  - Raw `text/csv`, `application/csv`, `application/vnd.ms-excel`, or `text/plain`
- **Limits & Encoding**:
  - Max file size: `2 MiB` (`2,097,152` bytes) -> `422 VALIDATION_ERROR`
  - Max data rows: `5,000` non-empty data rows (aligned with `T3C9F4A`) -> `422 VALIDATION_ERROR`
  - Encoding: `UTF-8` or `UTF-8 with BOM (\ufeff)` (Excel-compatible); non-UTF-8 or binary/null-byte files -> `422 VALIDATION_ERROR`

---

## 3. CSV Columns & Validation Rules

### Required Columns (case-insensitive, trimmed header)
1. **SKU**: `sku` (aliases: `mã sku`, `ma sku`) — ASCII printable, no whitespace, `1..64` chars (`normalize_sku`), unique within file and DB (`uq_products_sku`, `ascii_bin`).
2. **Product Name**: `name` (aliases: `product_name`, `tên sản phẩm`, `ten san pham`) — non-empty after trim, `1..160` chars (`normalize_product_name`).
3. **Category**: `category` / `category_name` / `danh mục` (accepts positive integer ID or case-insensitive category name) OR `category_id` / `mã danh mục` (strict positive integer ID). Must resolve unambiguously to an `ACTIVE` category.
4. **Price**: `price` / `sale_price_vnd` / `giá` / `giá bán` / `giá bán (vnđ)` — strict positive integer VND (`> 0`, no decimals/negatives/text).
5. **Optional**: `image_url` — if non-empty, must be an absolute `https://` URL (`<= 500` chars).

### File-Level vs Row-Level Errors
- **File-level (`422 VALIDATION_ERROR`)**: non-`.csv` filename, unsupported `Content-Type`, empty file, file > 2 MiB, binary/null-byte or non-UTF-8 content, malformed CSV syntax, missing/duplicate required headers, > 5,000 data rows.
- **Row-level (`200 OK` with partial success report)**: column count mismatch, missing/invalid SKU, duplicate SKU in file or DB, invalid name, invalid price, missing/inactive/ambiguous category, invalid `image_url`.

---

## 4. Response Schema (`200 OK`)

```json
{
  "total_rows": 4,
  "imported_count": 2,
  "skipped_count": 2,
  "error_count": 2,
  "errors": [
    {
      "row_number": 3,
      "sku": "SKU-DUP",
      "reason": "Mã SKU bị trùng lặp trong cùng tệp CSV."
    },
    {
      "row_number": 5,
      "sku": "SKU-BAD",
      "reason": "Giá bán phải là số nguyên dương (VNĐ)."
    }
  ]
}
```

- `row_number` is 1-based matching spreadsheet line numbers (header = row `1`, first data row = row `2`).
- Every imported product is created atomically via `ProductService.create()` with `status = ACTIVE` and `Inventory(quantity=0, stock_version=0, first_stocked_at=None)`.
