import axiosClient from './axiosClient.js';

export const VALID_RECEIPT_STATUSES = new Set(['DRAFT', 'CONFIRMED', 'CANCELLED']);

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

    const finalKey = idempotencyKey || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `receipt-confirm-${id}-${Date.now()}`);

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

