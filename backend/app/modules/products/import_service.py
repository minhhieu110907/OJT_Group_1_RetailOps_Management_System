"""CSV Product Import service with row-by-row validation & partial success (T3C9EFC)."""

from __future__ import annotations

import csv
import io
import re
from email import policy
from email.parser import BytesParser

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DomainValidationError,
    DuplicateSkuError,
    ResourceNotFoundError,
)
from app.modules.categories.models import Category, CategoryStatus
from app.modules.products.schemas import (
    ProductCreateRequest,
    ProductImportResponse,
    ProductImportRowError,
    normalize_product_name,
    normalize_sku,
)
from app.modules.products.service import ProductService

MAX_CSV_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB
MAX_IMPORT_ROWS = 5000
MAX_SQL_BIGINT = 9_223_372_036_854_775_807

_POSITIVE_INT_RE = re.compile(r"^[0-9]+$")

_HEADER_ALIASES: dict[str, str] = {
    "sku": "sku",
    "mã sku": "sku",
    "ma sku": "sku",
    "name": "name",
    "product_name": "name",
    "tên sản phẩm": "name",
    "ten san pham": "name",
    "category": "category",
    "category_name": "category",
    "danh mục": "category",
    "danh muc": "category",
    "category_id": "category_id",
    "mã danh mục": "category_id",
    "ma danh muc": "category_id",
    "price": "price",
    "sale_price_vnd": "price",
    "giá": "price",
    "gia": "price",
    "giá bán": "price",
    "gia ban": "price",
    "giá bán (vnđ)": "price",
    "image_url": "image_url",
}

_ALLOWED_RAW_CONTENT_TYPES = frozenset(
    {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "text/plain",
    }
)


def extract_csv_upload(
    raw_body: bytes, *, content_type: str | None
) -> tuple[bytes, str | None]:
    """Extract CSV bytes & optional filename from multipart/form-data or raw body."""
    ct = (content_type or "").strip()
    ct_lower = ct.lower()

    if ct_lower.startswith("multipart/form-data"):
        if "boundary=" not in ct_lower:
            raise DomainValidationError(
                "Header Content-Type multipart/form-data thiếu boundary."
            )
        mime_payload = (
            f"Content-Type: {ct}\r\nMIME-Version: 1.0\r\n\r\n".encode("latin-1")
            + raw_body
        )
        msg = BytesParser(policy=policy.default).parsebytes(mime_payload)
        if not msg.is_multipart():
            raise DomainValidationError("Nội dung tải lên multipart không hợp lệ.")
        for part in msg.iter_parts():
            disposition = part.get_content_disposition()
            param_name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            if disposition == "form-data" and (
                param_name == "file" or filename is not None
            ):
                payload = part.get_payload(decode=True)
                if not isinstance(payload, bytes):
                    raise DomainValidationError("Không thể đọc dữ liệu tệp CSV.")
                return payload, filename
        raise DomainValidationError("Không tìm thấy trường tệp 'file' trong yêu cầu.")

    media_type = ct_lower.split(";", 1)[0].strip()
    if media_type and media_type not in _ALLOWED_RAW_CONTENT_TYPES:
        raise DomainValidationError(
            "Định dạng tệp tải lên không hợp lệ. Chỉ chấp nhận tệp CSV."
        )
    return raw_body, None


class ProductImportService:
    """Parse CSV rows, validate independently, and reuse ProductService.create()."""

    def __init__(self, product_service: ProductService | None = None) -> None:
        self._product_service = product_service or ProductService()

    def import_csv(
        self,
        session: Session,
        raw_bytes: bytes,
        *,
        filename: str | None = None,
    ) -> ProductImportResponse:
        if filename is not None and not filename.strip().lower().endswith(".csv"):
            raise DomainValidationError(
                "Định dạng tệp không hợp lệ. Chỉ chấp nhận tệp có đuôi .csv."
            )
        if len(raw_bytes) > MAX_CSV_FILE_BYTES:
            raise DomainValidationError(
                "Kích thước tệp CSV vượt quá giới hạn tối đa 2MB."
            )
        if not raw_bytes or not raw_bytes.strip():
            raise DomainValidationError("Tệp CSV rỗng, không có dữ liệu để nhập.")
        if b"\x00" in raw_bytes:
            raise DomainValidationError(
                "Tệp tải lên không phải tệp văn bản CSV hợp lệ."
            )

        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise DomainValidationError(
                "Tệp CSV phải được mã hóa UTF-8 hợp lệ."
            ) from error

        try:
            all_rows = list(csv.reader(io.StringIO(text, newline="")))
        except csv.Error as error:
            raise DomainValidationError(
                f"Không thể đọc cấu trúc tệp CSV: {error}"
            ) from error

        if not all_rows or all(cell.strip() == "" for cell in all_rows[0]):
            raise DomainValidationError("Tệp CSV thiếu dòng tiêu đề (header).")

        col_map, expected_cols = self._parse_headers(all_rows[0])
        data_rows = all_rows[1:]
        non_empty_count = sum(
            1 for row in data_rows if any(cell.strip() != "" for cell in row)
        )
        if non_empty_count > MAX_IMPORT_ROWS:
            raise DomainValidationError(
                f"Số dòng dữ liệu ({non_empty_count}) vượt quá giới hạn tối đa "
                f"{MAX_IMPORT_ROWS} dòng mỗi lần nhập."
            )

        total_rows = 0
        imported_count = 0
        errors: list[ProductImportRowError] = []
        seen_skus: set[str] = set()

        for row_number, row in enumerate(data_rows, start=2):
            if not row or all(cell.strip() == "" for cell in row):
                continue
            total_rows += 1

            if len(row) != expected_cols:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=None,
                        reason=(
                            f"Số cột ({len(row)}) không khớp với tiêu đề "
                            f"({expected_cols} cột)."
                        ),
                    )
                )
                continue

            raw_sku = row[col_map["sku"]].strip()
            raw_name = row[col_map["name"]].strip()
            cat_col = "category_id" if "category_id" in col_map else "category"
            raw_category = row[col_map[cat_col]].strip()
            raw_price = row[col_map["price"]].strip()
            raw_image_url = (
                row[col_map["image_url"]].strip() if "image_url" in col_map else ""
            )

            row_sku_display = raw_sku or None

            # 1. Validate SKU & in-file duplicate
            try:
                sku = normalize_sku(raw_sku)
            except ValueError as error:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=row_sku_display,
                        reason=f"SKU không hợp lệ: {error}",
                    )
                )
                continue
            row_sku_display = sku

            if sku in seen_skus:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=sku,
                        reason="Mã SKU bị trùng lặp trong cùng tệp CSV.",
                    )
                )
                continue
            seen_skus.add(sku)

            # 2. Validate Name
            try:
                name = normalize_product_name(raw_name)
            except ValueError as error:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=sku,
                        reason=f"Tên sản phẩm không hợp lệ: {error}",
                    )
                )
                continue

            # 3. Validate Price (strict positive integer VND)
            price = self._parse_price_vnd(raw_price)
            if price is None:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=sku,
                        reason="Giá bán phải là số nguyên dương (VNĐ).",
                    )
                )
                continue

            # 4. Resolve & Validate Active Category
            category, cat_error = self._resolve_category(
                session, raw_category, strict_id_only=(cat_col == "category_id")
            )
            if cat_error is not None or category is None:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=sku,
                        reason=cat_error or "Danh mục không hợp lệ.",
                    )
                )
                continue

            # 5. Build canonical ProductCreateRequest (reuses all Pydantic validators)
            try:
                req = ProductCreateRequest(
                    sku=sku,
                    name=name,
                    category_id=category.id,
                    sale_price_vnd=price,
                    image_url=raw_image_url or None,
                )
            except ValidationError as error:
                first_msg = error.errors()[0].get("msg", "Dữ liệu dòng không hợp lệ.")
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=sku,
                        reason=str(first_msg),
                    )
                )
                continue

            # 6. Persist atomically per row via ProductService.create()
            try:
                self._product_service.create(session, req)
                imported_count += 1
            except DuplicateSkuError:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=sku,
                        reason="Mã SKU đã tồn tại trong hệ thống.",
                    )
                )
            except (ResourceNotFoundError, DomainValidationError) as error:
                errors.append(
                    ProductImportRowError(
                        row_number=row_number,
                        sku=sku,
                        reason=error.message,
                    )
                )

        return ProductImportResponse(
            total_rows=total_rows,
            imported_count=imported_count,
            skipped_count=len(errors),
            error_count=len(errors),
            errors=errors,
        )

    @staticmethod
    def _parse_headers(header_row: list[str]) -> tuple[dict[str, int], int]:
        col_map: dict[str, int] = {}
        for idx, raw_header in enumerate(header_row):
            normalized = raw_header.strip().lower()
            canonical = _HEADER_ALIASES.get(normalized)
            if canonical is None:
                continue
            if canonical in col_map or (
                canonical in ("category", "category_id")
                and ("category" in col_map or "category_id" in col_map)
            ):
                raise DomainValidationError(
                    f"Tiêu đề CSV bị trùng cột '{raw_header.strip()}'."
                )
            col_map[canonical] = idx

        missing: list[str] = []
        for req_col in ("sku", "name", "price"):
            if req_col not in col_map:
                missing.append(req_col)
        if "category" not in col_map and "category_id" not in col_map:
            missing.append("category")

        if missing:
            raise DomainValidationError(
                "Tệp CSV thiếu cột bắt buộc: " + ", ".join(missing) + "."
            )
        return col_map, len(header_row)

    @staticmethod
    def _parse_price_vnd(raw_price: str) -> int | None:
        if not raw_price or not _POSITIVE_INT_RE.fullmatch(raw_price):
            return None
        value = int(raw_price)
        if value <= 0 or value > MAX_SQL_BIGINT:
            return None
        return value

    def _resolve_category(
        self,
        session: Session,
        raw_category: str,
        *,
        strict_id_only: bool,
    ) -> tuple[Category | None, str | None]:
        if not raw_category:
            return None, "Danh mục không được để trống."

        repo = self._product_service.products
        if _POSITIVE_INT_RE.fullmatch(raw_category):
            cat_id = int(raw_category)
            if cat_id <= 0:
                return None, "Mã danh mục phải là số nguyên dương."
            cat = repo.get_category(session, cat_id)
            if cat is not None:
                if cat.status != CategoryStatus.ACTIVE.value:
                    return (
                        None,
                        "Danh mục đã ngừng hoạt động, không thể gán cho sản phẩm.",
                    )
                return cat, None
            if strict_id_only:
                return None, "Không tìm thấy danh mục."

        if strict_id_only:
            return None, "Mã danh mục phải là số nguyên dương."

        matches = repo.find_categories_by_name(session, raw_category)
        if not matches:
            return None, f"Không tìm thấy danh mục '{raw_category}'."

        active_matches = [c for c in matches if c.status == CategoryStatus.ACTIVE.value]
        if not active_matches:
            return None, "Danh mục đã ngừng hoạt động, không thể gán cho sản phẩm."
        if len(active_matches) > 1:
            return (
                None,
                f"Tên danh mục '{raw_category}' bị trùng, vui lòng dùng category_id.",
            )
        return active_matches[0], None
