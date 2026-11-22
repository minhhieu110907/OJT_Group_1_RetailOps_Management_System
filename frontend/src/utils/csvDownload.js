/**
 * CSV download utilities for RetailOps V1.0.
 * Handles Blob streaming, Content-Disposition header extraction,
 * Excel UTF-8 BOM compatibility, and Blob error decoding.
 */

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
    triggerBlobDownload(response, fallbackFilename);
  } catch (error) {
    const errorMsg = await parseBlobErrorMessage(error);
    const customErr = new Error(errorMsg);
    customErr.originalError = error;
    throw customErr;
  }
}

