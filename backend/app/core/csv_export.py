"""CSV export utilities, security sanitization (CWE-1236), and response generation."""

import csv
import io
from collections.abc import Sequence
from typing import Any

from fastapi import Response

from app.core.exceptions import DomainValidationError

# Formula injection trigger characters (CWE-1236)
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
MAX_EXPORT_ROWS = 5000


def sanitize_csv_cell(val: Any) -> Any:
    """Sanitize a cell value to prevent CSV Formula Injection (CWE-1236).

    If a text value starts with '=', '+', '-', '@', tab, or carriage return,
    it is prepended with a single quote (') so spreadsheet engines treat it
    strictly as plain text rather than executing it as an expression.
    """
    if val is None:
        return ""
    if isinstance(val, str):
        if val.startswith(FORMULA_PREFIXES):
            return f"'{val}"
        stripped = val.lstrip()
        if stripped and stripped[0] in FORMULA_PREFIXES:
            return f"'{val}"
        return val
    return val


def check_export_limit(count: int, max_rows: int = MAX_EXPORT_ROWS) -> None:
    """Validate that the query result does not exceed the allowed export limit."""
    if count > max_rows:
        raise DomainValidationError(
            f"Số lượng bản ghi ({count}) vượt quá giới hạn xuất tối đa {max_rows}. "
            "Vui lòng thu hẹp bộ lọc."
        )


def generate_csv_response(
    headers: list[str],
    rows: Sequence[Sequence[Any]],
    filename: str,
) -> Response:
    """Generate a streaming-compatible HTTP Response with UTF-8 BOM and CRLF.

    - Prepends UTF-8 BOM (\\ufeff) for seamless Microsoft Excel Vietnamese support.
    - Uses CRLF (\\r\\n) row terminators per RFC 4180.
    - Sanitizes every cell against CSV Formula Injection.
    - Sets appropriate Content-Disposition and Cache-Control headers.
    """
    buffer = io.StringIO()
    # Write UTF-8 BOM for Excel compatibility
    buffer.write("\ufeff")

    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)

    for row in rows:
        writer.writerow([sanitize_csv_cell(cell) for cell in row])

    content_bytes = buffer.getvalue().encode("utf-8")

    return Response(
        content=content_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
