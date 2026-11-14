import axiosClient from './axiosClient.js';

export const VALID_RECEIPT_STATUSES = new Set(['DRAFT', 'CONFIRMED', 'CANCELLED']);

export const MAX_HISTORY_MERGE_WINDOW = 500;

/**
 * Validate ISO-8601 timestamp string according to OpenAPI/Pydantic/MySQL contract.
 */
export function isValidIsoTimestamp(val) {
  if (typeof val !== 'string' || !val.trim()) return false;
  const trimmed = val.trim();
  const match = trimmed.match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(?:Z|([+-]\d{2}:?\d{2}))?$/
  );
  if (!match) return false;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);

  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;
  if (hour < 0 || hour > 23) return false;
  if (minute < 0 || minute > 59) return false;
  if (second < 0 || second > 59) return false;

  const isLeapYear = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const daysInMonths = [31, isLeapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (day > daysInMonths[month - 1]) return false;

  const parsed = new Date(trimmed);
  return !Number.isNaN(parsed.getTime());
}

/**
 * Normalize an ISO timestamp string (with or without explicit 'Z' offset) to UTC epoch ms.
 */
export function parseUtcTimestampMs(isoString) {
  if (!isoString || typeof isoString !== 'string') return 0;
  const raw = isoString.trim();
  if (!raw) return 0;
  const utcStr =
    raw.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(raw)
      ? raw
      : `${raw.replace(' ', 'T')}Z`;
  const ms = Date.parse(utcStr);
  return Number.isFinite(ms) ? ms : 0;
}

/**
 * Extract Vietnam business date (YYYY-MM-DD in Asia/Ho_Chi_Minh) from a receipt timestamp.
 */
export function toVietnamBusinessDate(isoString) {
  const ms = parseUtcTimestampMs(isoString);
  if (!ms) return '';
  return new Date(ms).toLocaleDateString('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
  });
}

/**
 * Deterministic comparator matching backend SQL ORDER BY:
 * PurchaseReceipt.created_at DESC, PurchaseReceipt.id DESC
 */
export function compareReceiptsByCreatedAtDesc(a, b) {
  const timeA = parseUtcTimestampMs(a?.created_at);
  const timeB = parseUtcTimestampMs(b?.created_at);
  if (timeA !== timeB) {
    return timeB - timeA;
  }
  const idA = Number(a?.id) || 0;
  const idB = Number(b?.id) || 0;
  return idB - idA;
}

/**
 * Generate a cryptographically random UUID v4 for Idempotency-Key.
 * Never falls back to predictable Date.now() timestamps.
 */
export function generateSecureIdempotencyKey() {
  if (typeof globalThis !== 'undefined' && globalThis.crypto) {
    if (typeof globalThis.crypto.randomUUID === 'function') {
      return globalThis.crypto.randomUUID();
    }
    if (typeof globalThis.crypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(16);
      globalThis.crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
    }
  }
  throw new Error('Trình duyệt hoặc môi trường runtime không hỗ trợ tạo khóa bảo mật (Web Crypto API).');
}

/**
 * Validate ReceiptLineRead schema from backend response.
 */
export function validateReceiptLineRead(item) {
  if (!item || typeof item !== 'object') {
    throw new Error('Receipt item must be a non-null object.');
  }

  const productId = Number(item.product_id);
  if (!Number.isInteger(productId) || productId <= 0) {
    throw new Error(`Receipt item product_id must be a positive integer, got: ${item.product_id}`);
  }

  if (typeof item.sku_snapshot !== 'string' || !item.sku_snapshot.trim()) {
    throw new Error('Receipt item sku_snapshot is required and must be non-empty.');
  }

  if (typeof item.product_name_snapshot !== 'string' || !item.product_name_snapshot.trim()) {
    throw new Error('Receipt item product_name_snapshot is required and must be non-empty.');
  }

  const quantity = Number(item.quantity);
  if (!Number.isInteger(quantity) || quantity <= 0) {
    throw new Error(`Receipt item quantity must be a positive integer (>0), got: ${item.quantity}`);
  }

  const unitCostVnd = Number(item.unit_cost_vnd);
  if (!Number.isInteger(unitCostVnd) || unitCostVnd < 0) {
    throw new Error(`Receipt item unit_cost_vnd must be a non-negative integer (>=0), got: ${item.unit_cost_vnd}`);
  }

  const lineTotalVnd = Number(item.line_total_vnd);
  if (!Number.isInteger(lineTotalVnd) || lineTotalVnd < 0) {
    throw new Error(`Receipt item line_total_vnd must be a non-negative integer (>=0), got: ${item.line_total_vnd}`);
  }

  return {
    product_id: productId,
    sku_snapshot: item.sku_snapshot.trim(),
    product_name_snapshot: item.product_name_snapshot.trim(),
    quantity,
    unit_cost_vnd: unitCostVnd,
    line_total_vnd: lineTotalVnd,
  };
}

/**
 * Validate ReceiptRead response envelope.
 */
export function validateReceiptRead(data) {
  if (!data || typeof data !== 'object') {
    throw new Error('Receipt payload must be a non-null object.');
  }

  const id = Number(data.id);
  if (!Number.isInteger(id) || id <= 0) {
    throw new Error(`Invalid receipt ID: ${data.id}`);
  }

  const supplierId = Number(data.supplier_id);
  if (!Number.isInteger(supplierId) || supplierId <= 0) {
    throw new Error(`Invalid supplier_id: ${data.supplier_id}`);
  }

  if (!VALID_RECEIPT_STATUSES.has(data.status)) {
    throw new Error(`Invalid receipt status: "${data.status}". Must be one of: DRAFT, CONFIRMED, CANCELLED`);
  }

  const draftVersion = Number(data.draft_version);
  if (!Number.isInteger(draftVersion) || draftVersion <= 0) {
    throw new Error(`Invalid draft_version: ${data.draft_version}`);
  }

  const totalVnd = Number(data.total_vnd);
  if (!Number.isInteger(totalVnd) || totalVnd < 0) {
    throw new Error(`Invalid total_vnd: ${data.total_vnd}`);
  }

  const createdBy = Number(data.created_by);
  if (!Number.isInteger(createdBy) || createdBy <= 0) {
    throw new Error(`Invalid created_by: ${data.created_by}`);
  }

  let closedBy = null;
  if (data.closed_by !== undefined && data.closed_by !== null) {
    closedBy = Number(data.closed_by);
    if (!Number.isInteger(closedBy) || closedBy <= 0) {
      throw new Error(`Invalid closed_by: ${data.closed_by}`);
    }
  }

  if (!isValidIsoTimestamp(data.created_at)) {
    throw new Error(`Invalid created_at timestamp: "${data.created_at}"`);
  }

  if (!isValidIsoTimestamp(data.updated_at)) {
    throw new Error(`Invalid updated_at timestamp: "${data.updated_at}"`);
  }

  let closedAt = null;
  if (data.closed_at !== undefined && data.closed_at !== null) {
    if (!isValidIsoTimestamp(data.closed_at)) {
      throw new Error(`Invalid closed_at timestamp: "${data.closed_at}"`);
    }
    closedAt = data.closed_at;
  }

  if (!Array.isArray(data.items)) {
    throw new Error('Receipt items must be an array.');
  }

  const validatedItems = data.items.map(validateReceiptLineRead);

  return {
    id,
    supplier_id: supplierId,
    supplier_name_snapshot: data.supplier_name_snapshot ? String(data.supplier_name_snapshot).trim() : null,
    status: data.status,
    draft_version: draftVersion,
    total_vnd: totalVnd,
    created_by: createdBy,
    closed_by: closedBy,
    created_at: data.created_at,
    updated_at: data.updated_at,
    closed_at: closedAt,
    items: validatedItems,
  };
}

/**
 * Validate ReceiptPage response structure.
 */
export function validateReceiptPage(res) {
  if (!res || typeof res !== 'object') {
    throw new Error('ReceiptPage response must be a non-null object.');
  }

  if (!Array.isArray(res.items)) {
    throw new Error('ReceiptPage items must be an array.');
  }

  const total = Number(res.total);
  if (!Number.isInteger(total) || total < 0) {
    throw new Error(`Invalid ReceiptPage total: ${res.total}`);
  }

  const page = Number(res.page);
  if (!Number.isInteger(page) || page < 1) {
    throw new Error(`Invalid ReceiptPage page: ${res.page}`);
  }

  const pageSize = Number(res.page_size);
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
    throw new Error(`Invalid ReceiptPage page_size: ${res.page_size}`);
  }

  const validatedItems = res.items.map(validateReceiptRead);

  return {
    items: validatedItems,
    total,
    page,
    page_size: pageSize,
    total_pages: Math.max(1, Math.ceil(total / pageSize)),
  };
}

/**
 * Validate & normalize receipt lines for creation/update payload.
 * Enforces PUR-01 / PUR-02 rules:
 * - Duplicate product with same unit_cost_vnd => auto-merged (quantities summed).
 * - Duplicate product with different unit_cost_vnd => throws 422 Client Validation Error.
 */
export function normalizeAndValidateReceiptLines(rawItems) {
  if (!Array.isArray(rawItems) || rawItems.length === 0) {
    throw new Error('Danh sách sản phẩm nhập không được để trống.');
  }

  const productCostMap = new Map(); // product_id -> unit_cost_vnd
  const productQuantityMap = new Map(); // product_id -> sum_quantity

  for (let idx = 0; idx < rawItems.length; idx++) {
    const item = rawItems[idx];
    if (!item || typeof item !== 'object') {
      throw new Error(`Dòng sản phẩm thứ ${idx + 1} không hợp lệ.`);
    }

    const productId = Number(item.product_id);
    if (!Number.isInteger(productId) || productId <= 0) {
      throw new Error(`Dòng thứ ${idx + 1}: Vui lòng chọn sản phẩm hợp lệ.`);
    }

    const quantity = Number(item.quantity);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      throw new Error(`Dòng thứ ${idx + 1}: Số lượng nhập phải là số nguyên dương lớn hơn 0.`);
    }

    const unitCostVnd = Number(item.unit_cost_vnd);
    if (!Number.isInteger(unitCostVnd) || unitCostVnd < 0) {
      throw new Error(`Dòng thứ ${idx + 1}: Đơn giá nhập phải là số nguyên không âm (>= 0 đ).`);
    }

    if (productCostMap.has(productId)) {
      const existingCost = productCostMap.get(productId);
      if (existingCost !== unitCostVnd) {
        throw new Error(
          `Sản phẩm ID ${productId} xuất hiện nhiều dòng với đơn giá nhập khác nhau (${existingCost} đ và ${unitCostVnd} đ). Vui lòng thống nhất đơn giá hoặc tách thành phiếu nhập khác.`
        );
      }
      productQuantityMap.set(productId, productQuantityMap.get(productId) + quantity);
    } else {
      productCostMap.set(productId, unitCostVnd);
      productQuantityMap.set(productId, quantity);
    }
  }

  const mergedItems = [];
  for (const [productId, unitCostVnd] of productCostMap.entries()) {
    mergedItems.push({
      product_id: productId,
      quantity: productQuantityMap.get(productId),
      unit_cost_vnd: unitCostVnd,
    });
  }

  return mergedItems;
}

/**
 * Parse user input in Receipt Search box.
 * Backend contract only supports exact receipt_id lookup via GET /purchase-receipts/{id}
 * and supplier_id filter via GET /purchase-receipts?supplier_id=...
 */
export function parseReceiptSearchInput(rawQuery) {
  if (rawQuery === null || rawQuery === undefined) {
    return { mode: 'NONE', receiptId: null, error: null };
  }
  const trimmed = String(rawQuery).trim();
  if (!trimmed) {
    return { mode: 'NONE', receiptId: null, error: null };
  }

  const exactIdMatch = trimmed.match(/^#?([1-9]\d*)$/);
  if (exactIdMatch) {
    const parsedId = Number(exactIdMatch[1]);
    if (Number.isSafeInteger(parsedId) && parsedId > 0 && parsedId <= 2147483647) {
      return { mode: 'EXACT_ID', receiptId: parsedId, error: null };
    }
    return {
      mode: 'INVALID_ID',
      receiptId: null,
      error: 'Mã phiếu nhập vượt quá giới hạn hợp lệ.',
    };
  }

  return {
    mode: 'UNSUPPORTED_QUERY',
    receiptId: null,
    error:
      'API hiện tại chỉ hỗ trợ tra cứu toàn cục theo Mã phiếu chính xác (VD: 12 hoặc #12). Để lọc theo Nhà cung cấp, vui lòng chọn tại ô "Nhà cung cấp".',
  };
}

/**
 * Check whether a single ReceiptRead matches active status, supplier, and Vietnam date filters.
 */
export function doesReceiptMatchActiveFilters(
  receipt,
  { topTab = 'RECEIPTS', activeTab = 'DRAFT', supplierId = null, fromDate = '', toDate = '' } = {}
) {
  if (!receipt || typeof receipt !== 'object') return false;

  if (topTab === 'HISTORY') {
    if (activeTab === 'ALL_HISTORY') {
      if (receipt.status !== 'CONFIRMED' && receipt.status !== 'CANCELLED') {
        return false;
      }
    } else if (VALID_RECEIPT_STATUSES.has(activeTab)) {
      if (receipt.status !== activeTab) return false;
    }
  } else if (VALID_RECEIPT_STATUSES.has(activeTab)) {
    if (receipt.status !== activeTab) return false;
  }

  if (supplierId && Number(supplierId) > 0) {
    if (Number(receipt.supplier_id) !== Number(supplierId)) {
      return false;
    }
  }

  const receiptVnDate = toVietnamBusinessDate(receipt.created_at);
  if (fromDate && typeof fromDate === 'string' && fromDate.trim()) {
    if (!receiptVnDate || receiptVnDate < fromDate.trim()) {
      return false;
    }
  }
  if (toDate && typeof toDate === 'string' && toDate.trim()) {
    if (!receiptVnDate || receiptVnDate > toDate.trim()) {
      return false;
    }
  }

  return true;
}

/**
 * Intent-level Idempotency tracker for POST /purchase-receipts/{id}/confirm.
 * Guarantees:
 * - One cryptographically random UUID key per (receiptId, expectedDraftVersion) intent.
 * - Synchronous in-flight guard against double-click / concurrent submission.
 * - Retrying the same (receiptId, expectedDraftVersion) after timeout/network failure reuses the exact same key and payload.
 * - Changing receiptId or expectedDraftVersion generates a new key.
 * - Receiving 409 stale/terminal state reconciles authoritative ReceiptRead via GET /purchase-receipts/{id} without infinite retry.
 */
export function createConfirmIntentTracker(keyGenerator = generateSecureIdempotencyKey) {
  let currentIntent = null; // { receiptId, expectedDraftVersion, idempotencyKey }
  let inFlight = false;

  return {
    isInFlight() {
      return inFlight;
    },

    getCurrentIntent() {
      return currentIntent ? { ...currentIntent } : null;
    },

    getOrCreateKey(receiptId, expectedDraftVersion) {
      const id = Number(receiptId);
      const version = Number(expectedDraftVersion);
      if (!Number.isInteger(id) || id <= 0) {
        throw new Error('ID phiếu nhập không hợp lệ.');
      }
      if (!Number.isInteger(version) || version <= 0) {
        throw new Error('Phiên bản nháp (expected_draft_version) không hợp lệ.');
      }

      if (
        currentIntent &&
        currentIntent.receiptId === id &&
        currentIntent.expectedDraftVersion === version &&
        typeof currentIntent.idempotencyKey === 'string' &&
        currentIntent.idempotencyKey.length >= 16
      ) {
        return currentIntent.idempotencyKey;
      }

      const newKey = keyGenerator();
      currentIntent = {
        receiptId: id,
        expectedDraftVersion: version,
        idempotencyKey: newKey,
      };
      return newKey;
    },

    clearIntent(receiptId = null) {
      if (receiptId === null || (currentIntent && currentIntent.receiptId === Number(receiptId))) {
        currentIntent = null;
      }
    },

    async executeConfirm(
      receiptId,
      expectedDraftVersion,
      {
        confirmFn = (id, opts) => receiptsApi.confirm(id, opts),
        getFn = (id) => receiptsApi.get(id),
      } = {}
    ) {
      if (inFlight) {
        return {
          outcome: 'IGNORED_IN_FLIGHT',
          receipt: null,
          idempotencyKey: currentIntent?.idempotencyKey || null,
        };
      }

      const id = Number(receiptId);
      const version = Number(expectedDraftVersion);
      const idempotencyKey = this.getOrCreateKey(id, version);
      inFlight = true;

      try {
        const confirmed = await confirmFn(id, {
          expected_draft_version: version,
          idempotencyKey,
        });
        this.clearIntent(id);
        return {
          outcome: 'CONFIRMED',
          receipt: confirmed,
          idempotencyKey,
        };
      } catch (err) {
        const status = err?.response?.status;
        const errorCode = err?.response?.data?.code;

        // If duplicate request is still in progress on backend, keep the same key for retry
        if (status === 409 && errorCode === 'REQUEST_IN_PROGRESS') {
          throw err;
        }

        // For 409 version/state conflict (or if a prior timeout committed under a different state),
        // fetch authoritative receipt state from backend and clear stale intent.
        if (status === 409) {
          this.clearIntent(id);
          let authoritativeReceipt = null;
          try {
            authoritativeReceipt = await getFn(id);
          } catch {
            authoritativeReceipt = null;
          }

          if (authoritativeReceipt && authoritativeReceipt.status === 'CONFIRMED') {
            return {
              outcome: 'RECONCILED_CONFIRMED',
              receipt: authoritativeReceipt,
              error: err,
              idempotencyKey,
            };
          }

          return {
            outcome: 'CONFLICT_STALE',
            receipt: authoritativeReceipt,
            error: err,
            idempotencyKey,
          };
        }

        // For 400/401/403/404/422 client/domain errors, clear intent;
        // For network timeouts / 5xx / 429, preserve currentIntent so retry uses the exact same key!
        if (status && status >= 400 && status < 500 && status !== 429) {
          this.clearIntent(id);
        }
        throw err;
      } finally {
        inFlight = false;
      }
    },
  };
}

/**
 * Request generation guard for receipt detail modal to prevent async race conditions
 * (e.g. open Receipt A -> close/switch to Receipt B before A resolves/rejects).
 */
export function createDetailRequestGuard() {
  let currentRequestId = 0;
  let activeReceiptId = null;
  let modalOpen = false;

  return {
    begin(receiptId) {
      const id = Number(receiptId);
      currentRequestId += 1;
      activeReceiptId = Number.isInteger(id) && id > 0 ? id : null;
      modalOpen = Boolean(activeReceiptId);
      return currentRequestId;
    },

    invalidate() {
      currentRequestId += 1;
      activeReceiptId = null;
      modalOpen = false;
      return currentRequestId;
    },

    isCurrent(requestId, receiptId) {
      return (
        modalOpen &&
        requestId === currentRequestId &&
        activeReceiptId !== null &&
        activeReceiptId === Number(receiptId)
      );
    },

    getActiveReceiptId() {
      return modalOpen ? activeReceiptId : null;
    },
  };
}

/**
 * Standard Receipts API client conforming strictly to contract CF-03 (HTTP-RECEIPT).
 */
export const receiptsApi = {
  /**
   * GET /purchase-receipts
   */
  async list({ page = 1, pageSize = 10, status = '', supplierId = null, fromDate = '', toDate = '' } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 10,
    };

    if (status && VALID_RECEIPT_STATUSES.has(status)) {
      params.status = status;
    }

    if (supplierId && Number(supplierId) > 0) {
      params.supplier_id = Number(supplierId);
    }

    if (fromDate && typeof fromDate === 'string' && fromDate.trim()) {
      params.from_date = fromDate.trim();
    }

    if (toDate && typeof toDate === 'string' && toDate.trim()) {
      params.to_date = toDate.trim();
    }

    const response = await axiosClient.get('/purchase-receipts', { params });
    return validateReceiptPage(response.data);
  },

  /**
   * Paginated history merge for ALL_HISTORY (CONFIRMED + CANCELLED) under current single-status backend contract.
   * - Fetches bounded sorted prefixes from CONFIRMED and CANCELLED without swallowing errors.
   * - Merges deterministically by (created_at DESC, id DESC) and slices exact pageSize items.
   * - Rejects with ERR_HISTORY_WINDOW_EXCEEDED if page * pageSize exceeds maxMergedItems (default 500)
   *   so frontend never fetches unbounded pages.
   */
  async listHistory({
    page = 1,
    pageSize = 10,
    supplierId = null,
    fromDate = '',
    toDate = '',
    maxMergedItems = MAX_HISTORY_MERGE_WINDOW,
  } = {}) {
    const safePage = Math.max(1, Number(page) || 1);
    const safePageSize = Math.min(100, Math.max(1, Number(pageSize) || 10));
    const requiredWindow = safePage * safePageSize;

    if (requiredWindow > maxMergedItems) {
      const err = new Error(
        `Chế độ "Tất cả lịch sử" chỉ hỗ trợ phân trang tối đa ${maxMergedItems} phiếu gần nhất do API Backend hiện chỉ lọc từng trạng thái đơn lẻ. Vui lòng lọc theo trạng thái "Đã nhập" / "Đã hủy" hoặc thu hẹp khoảng thời gian.`
      );
      err.code = 'ERR_HISTORY_WINDOW_EXCEEDED';
      throw err;
    }

    const fetchSortedStatusPrefix = async (statusValue) => {
      const firstBatchSize = Math.min(100, requiredWindow);
      const firstPage = await this.list({
        page: 1,
        pageSize: firstBatchSize,
        status: statusValue,
        supplierId,
        fromDate,
        toDate,
      });

      const items = [...firstPage.items];
      const totalForStatus = firstPage.total;
      const targetCount = Math.min(requiredWindow, totalForStatus);

      let nextPage = 2;
      while (items.length < targetCount) {
        const res = await this.list({
          page: nextPage,
          pageSize: firstBatchSize,
          status: statusValue,
          supplierId,
          fromDate,
          toDate,
        });
        if (!res.items.length) break;
        items.push(...res.items);
        nextPage += 1;
      }

      return {
        items: items.slice(0, targetCount),
        total: totalForStatus,
      };
    };

    // Fail-closed: if either CONFIRMED or CANCELLED fails, Promise.all rejects immediately
    const [confirmedRes, cancelledRes] = await Promise.all([
      fetchSortedStatusPrefix('CONFIRMED'),
      fetchSortedStatusPrefix('CANCELLED'),
    ]);

    const dedupMap = new Map();
    for (const item of [...confirmedRes.items, ...cancelledRes.items]) {
      dedupMap.set(item.id, item);
    }

    const sortedCombined = Array.from(dedupMap.values()).sort(compareReceiptsByCreatedAtDesc);
    const combinedTotal = confirmedRes.total + cancelledRes.total;
    const isWindowCapped = combinedTotal > maxMergedItems;
    const effectiveTotal = Math.min(combinedTotal, maxMergedItems);
    const totalPages = Math.max(1, Math.ceil(effectiveTotal / safePageSize));
    const startIndex = (safePage - 1) * safePageSize;
    const pageItems = sortedCombined.slice(startIndex, startIndex + safePageSize);

    return {
      items: pageItems,
      total: combinedTotal,
      effective_total: effectiveTotal,
      page: safePage,
      page_size: safePageSize,
      total_pages: totalPages,
      is_window_capped: isWindowCapped,
    };
  },

  /**
   * Exact ID lookup via GET /purchase-receipts/:id for global Receipt ID search across pages.
   * Only treats 404 RESOURCE_NOT_FOUND on this single-item endpoint as "no matching receipt".
   * Any other error (401/403/429/5xx/network) is rethrown fail-closed.
   */
  async findByExactId(
    receiptId,
    {
      pageSize = 10,
      topTab = 'RECEIPTS',
      activeTab = 'DRAFT',
      supplierId = null,
      fromDate = '',
      toDate = '',
    } = {}
  ) {
    const safePageSize = Math.min(100, Math.max(1, Number(pageSize) || 10));
    try {
      const receipt = await this.get(receiptId);
      const matches = doesReceiptMatchActiveFilters(receipt, {
        topTab,
        activeTab,
        supplierId,
        fromDate,
        toDate,
      });

      if (!matches) {
        return {
          items: [],
          total: 0,
          page: 1,
          page_size: safePageSize,
          total_pages: 1,
        };
      }

      return {
        items: [receipt],
        total: 1,
        page: 1,
        page_size: safePageSize,
        total_pages: 1,
      };
    } catch (err) {
      if (err?.response?.status === 404) {
        return {
          items: [],
          total: 0,
          page: 1,
          page_size: safePageSize,
          total_pages: 1,
        };
      }
      throw err;
    }
  },

  /**
   * GET /purchase-receipts/:id
   */
  async get(receiptId) {
    const id = Number(receiptId);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('ID phiếu nhập không hợp lệ.');
    }

    const response = await axiosClient.get(`/purchase-receipts/${id}`);
    return validateReceiptRead(response.data);
  },

  /**
   * POST /purchase-receipts
   * Create DRAFT receipt.
   */
  async createDraft({ supplier_id, items }) {
    const supplierId = Number(supplier_id);
    if (!Number.isInteger(supplierId) || supplierId <= 0) {
      throw new Error('Vui lòng chọn nhà cung cấp hợp lệ.');
    }

    const validatedLines = normalizeAndValidateReceiptLines(items);

    const payload = {
      supplier_id: supplierId,
      items: validatedLines,
    };

    const response = await axiosClient.post('/purchase-receipts', payload);
    return validateReceiptRead(response.data);
  },

  /**
   * PATCH /purchase-receipts/:id
   * Update DRAFT receipt.
   */
  async updateDraft(receiptId, { expected_draft_version, supplier_id, items }) {
    const id = Number(receiptId);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('ID phiếu nhập không hợp lệ.');
    }

    const expVersion = Number(expected_draft_version);
    if (!Number.isInteger(expVersion) || expVersion <= 0) {
      throw new Error('Phiên bản nháp (expected_draft_version) không hợp lệ.');
    }

    const payload = {
      expected_draft_version: expVersion,
    };

    if (supplier_id !== undefined) {
      const sId = Number(supplier_id);
      if (!Number.isInteger(sId) || sId <= 0) {
        throw new Error('Vui lòng chọn nhà cung cấp hợp lệ.');
      }
      payload.supplier_id = sId;
    }

    if (items !== undefined) {
      payload.items = normalizeAndValidateReceiptLines(items);
    }

    const response = await axiosClient.patch(`/purchase-receipts/${id}`, payload);
    return validateReceiptRead(response.data);
  },

  /**
   * POST /purchase-receipts/:id/confirm
   * Confirm DRAFT receipt and mutate stock with Idempotency-Key.
   */
  async confirm(receiptId, { expected_draft_version, idempotencyKey = null }) {
    const id = Number(receiptId);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('ID phiếu nhập không hợp lệ.');
    }

    const expVersion = Number(expected_draft_version);
    if (!Number.isInteger(expVersion) || expVersion <= 0) {
      throw new Error('Phiên bản nháp (expected_draft_version) không hợp lệ.');
    }

    const finalKey =
      typeof idempotencyKey === 'string' && idempotencyKey.trim()
        ? idempotencyKey.trim()
        : generateSecureIdempotencyKey();

    if (!/^[A-Za-z0-9._:-]{16,128}$/.test(finalKey)) {
      throw new Error('Idempotency-Key không đúng định dạng bảo mật (16-128 ký tự).');
    }

    const response = await axiosClient.post(
      `/purchase-receipts/${id}/confirm`,
      { expected_draft_version: expVersion },
      {
        headers: {
          'Idempotency-Key': finalKey,
        },
      }
    );
    return validateReceiptRead(response.data);
  },

  /**
   * POST /purchase-receipts/:id/cancel
   * Cancel DRAFT receipt.
   */
  async cancel(receiptId, { expected_draft_version }) {
    const id = Number(receiptId);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error('ID phiếu nhập không hợp lệ.');
    }

    const expVersion = Number(expected_draft_version);
    if (!Number.isInteger(expVersion) || expVersion <= 0) {
      throw new Error('Phiên bản nháp (expected_draft_version) không hợp lệ.');
    }

    const response = await axiosClient.post(`/purchase-receipts/${id}/cancel`, {
      expected_draft_version: expVersion,
    });
    return validateReceiptRead(response.data);
  },
};
