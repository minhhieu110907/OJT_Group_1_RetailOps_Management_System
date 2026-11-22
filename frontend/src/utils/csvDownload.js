/**
 * CSV download utilities for RetailOps V1.0.
 * Handles Blob streaming, Content-Disposition header extraction,
 * Excel UTF-8 BOM compatibility, Excel-friendly cell formatting, and Blob error decoding.
 */

const STATUS_LABELS_VN = {
  COMPLETED: 'Hoàn tất',
  CANCELLED: 'Đã hủy',
  ACTIVE: 'Đang bán',
  INACTIVE: 'Ngừng bán',
};

/**
 * Parse RFC-4180 CSV text (supporting quoted fields, escaped quotes, and BOM)
 * into an array of row arrays.
 * @param {string} rawText
 * @returns {string[][]}
 */
export function parseCsvRows(rawText) {
  if (!rawText || typeof rawText !== 'string') {
    return [];
  }
  const text = rawText.replace(/^\ufeff/, '');
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      row.push(cell);
      cell = '';
    } else if (ch === '\r' && next === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      i += 1;
    } else if (ch === '\n' || ch === '\r') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else {
      cell += ch;
    }
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  return rows;
}

/**
 * Serialize a 2D array of cells back into an Excel-compatible UTF-8 BOM CSV string.
 * @param {string[][]} rows
 * @returns {string}
 */
export function serializeCsvRows(rows) {
  const escapeCell = (val) => {
    const str = val === null || val === undefined ? '' : String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const body = rows.map((r) => r.map(escapeCell).join(',')).join('\r\n');
  return `\ufeff${body}\r\n`;
}

/**
 * Format an ISO date/datetime string (`YYYY-MM-DD` or `YYYY-MM-DD HH:mm:ss`)
 * into a clean Vietnamese display string (`DD/MM/YYYY` or `DD/MM/YYYY HH:mm:ss`)
 * using non-breaking space padding (`\u00A0`) so Excel treats it as a text label
 * and never collapses the date into `#######`.
 * @param {string} raw
 * @returns {string}
 */
function formatDateForExcel(raw) {
  const trimmed = (raw || '').trim();
  if (!trimmed) return '—';
  const dtMatch = /^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?$/.exec(trimmed);
  if (!dtMatch) return trimmed;
  const [, yyyy, mm, dd, timePart] = dtMatch;
  const nbsp = '\u00A0';
  return timePart
    ? `${nbsp}${dd}/${mm}/${yyyy} ${timePart}${nbsp}`
    : `${nbsp}${dd}/${mm}/${yyyy}${nbsp}`;
}

/**
 * Format an integer VND string with Vietnamese thousand separators (e.g. `100000` -> `100.000 ₫`).
 * @param {string} raw
 * @returns {string}
 */
function formatVndForExcel(raw) {
  const trimmed = (raw || '').trim();
  if (!trimmed) return '0 ₫';
  const num = Number(trimmed);
  if (!Number.isFinite(num)) return trimmed;
  return `${Math.round(num).toLocaleString('vi-VN')} ₫`;
}

/**
 * Transform raw backend CSV text into a human-friendly, spaciously formatted
 * CSV for Microsoft Excel:
 * - Translates status codes (`COMPLETED` -> `Hoàn tất`, `CANCELLED` -> `Đã hủy`,
 *   `ACTIVE` -> `Đang bán`, `INACTIVE` -> `Ngừng bán`).
 * - Formats VND currency columns with thousand separators (`100.000 ₫`).
 * - Formats Order IDs (`#HD-101`) and Product IDs (`#SP-1`).
 * - Formats dates as `DD/MM/YYYY HH:mm:ss` with breathing room so Excel
 *   widens the column automatically instead of collapsing into `#######`.
 * - Adds visual breathing room to column headers.
 * @param {string} rawCsvText
 * @returns {string}
 */
export function beautifyCsvForExcel(rawCsvText) {
  if (!rawCsvText || typeof rawCsvText !== 'string') {
    return rawCsvText;
  }

  const rows = parseCsvRows(rawCsvText);
  if (rows.length === 0) {
    return rawCsvText;
  }

  const rawHeaders = rows[0].map((h) => (h || '').trim());
  if (rawHeaders.length < 2) {
    return rawCsvText;
  }

  // Pad headers slightly so Excel's initial column width calculation is generous
  const formattedHeaders = rawHeaders.map((header) => `  ${header.toUpperCase()}  `);

  const formattedDataRows = rows.slice(1).map((row) =>
    rawHeaders.map((header, colIdx) => {
      const cell = row[colIdx] !== undefined ? String(row[colIdx]) : '';
      const trimmed = cell.trim();
      const headerLower = header.toLowerCase();

      // 1. Order ID column ("Mã đơn")
      if (headerLower === 'mã đơn' && /^\d+$/.test(trimmed)) {
        return `#HD-${trimmed}`;
      }

      // 2. Product ID column ("Mã SP")
      if (headerLower === 'mã sp' && /^\d+$/.test(trimmed)) {
        return `#SP-${trimmed}`;
      }

      // 3. Status column ("Trạng thái")
      if (headerLower === 'trạng thái') {
        return STATUS_LABELS_VN[trimmed.toUpperCase()] || trimmed;
      }

      // 4. Date / Datetime columns ("Ngày", "Ngày bán (VN)", "Ngày nhập đầu tiên (VN)")
      if (headerLower.startsWith('ngày')) {
        return formatDateForExcel(trimmed);
      }

      // 5. Currency columns ("...(VNĐ)")
      if (headerLower.includes('(vnđ)')) {
        return formatVndForExcel(trimmed);
      }

      // 6. Empty cancellation reason or optional fields
      if (headerLower === 'lý do hủy' && !trimmed) {
        return '—';
      }

      return cell;
    })
  );

  return serializeCsvRows([formattedHeaders, ...formattedDataRows]);
}

/**
 * Extract filename from Content-Disposition header or use fallback.
 * @param {string|null|undefined} contentDisposition
 * @param {string} fallback
 * @returns {string}
 */
export function extractFilenameFromHeader(contentDisposition, fallback = 'report.csv') {
  if (!contentDisposition || typeof contentDisposition !== 'string') {
    return fallback;
  }

  // Check for UTF-8 encoded filename: filename*=UTF-8''...
  const utf8Match = /filename\*=UTF-8''([^;\s]+)/i.exec(contentDisposition);
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1].replace(/["']/g, ''));
    } catch {
      return utf8Match[1].replace(/["']/g, '');
    }
  }

  // Standard filename="...":
  const standardMatch = /filename=["']?([^"';\n]+)["']?/i.exec(contentDisposition);
  if (standardMatch && standardMatch[1]) {
    return standardMatch[1].trim();
  }

  return fallback;
}

/**
 * Decode error message from an Axios error where error.response.data is a Blob.
 * @param {any} error
 * @returns {Promise<string>}
 */
export async function parseBlobErrorMessage(error) {
  if (error?.response?.data instanceof Blob) {
    try {
      const text = await error.response.data.text();
      const json = JSON.parse(text);
      if (typeof json.message === 'string' && json.message.trim()) {
        return json.message;
      }
      if (typeof json.detail === 'string' && json.detail.trim()) {
        return json.detail;
      }
    } catch {
      // Fallback below
    }
  }
  return (
    error?.response?.data?.message ||
    error?.response?.data?.detail ||
    error?.message ||
    'Không thể xuất báo cáo CSV. Vui lòng thử lại sau.'
  );
}

/**
 * Trigger browser file download from a Blob or an Axios response.
 * @param {Blob|{ data: Blob, headers?: any }} blobOrResponse
 * @param {string} fallbackFilename
 */
export function triggerBlobDownload(blobOrResponse, fallbackFilename = 'report.csv') {
  let blob;
  let filename = fallbackFilename;

  if (blobOrResponse instanceof Blob) {
    blob = blobOrResponse;
  } else if (blobOrResponse && blobOrResponse.data instanceof Blob) {
    blob = blobOrResponse.data;
    const disposition =
      blobOrResponse.headers?.['content-disposition'] ||
      (typeof blobOrResponse.headers?.get === 'function' &&
        blobOrResponse.headers.get('content-disposition'));
    filename = extractFilenameFromHeader(disposition, fallbackFilename);
  } else {
    throw new Error('Dữ liệu tải về không hợp lệ.');
  }

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

/**
 * Higher-level helper to execute an API call and download the resulting CSV.
 * @param {() => Promise<any>} fetchFn
 * @param {string} fallbackFilename
 * @returns {Promise<void>}
 */
export async function downloadCsvReport(fetchFn, fallbackFilename = 'report.csv') {
  try {
    const response = await fetchFn();
    let finalPayload = response;

    const rawBlob =
      response instanceof Blob
        ? response
        : response && response.data instanceof Blob
        ? response.data
        : null;

    if (rawBlob && typeof rawBlob.text === 'function') {
      try {
        const rawText = await rawBlob.text();
        const beautifiedText = beautifyCsvForExcel(rawText);
        const beautifiedBlob = new Blob([beautifiedText], {
          type: 'text/csv; charset=utf-8',
        });
        finalPayload =
          response instanceof Blob
            ? beautifiedBlob
            : { ...response, data: beautifiedBlob };
      } catch {
        // Fallback to raw response if Blob reading fails
      }
    }

    triggerBlobDownload(finalPayload, fallbackFilename);
  } catch (error) {
    const errorMsg = await parseBlobErrorMessage(error);
    const customErr = new Error(errorMsg);
    customErr.originalError = error;
    throw customErr;
  }
}

