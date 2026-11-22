import axiosClient from './axiosClient.js';

export const STOCK_STATUS_TABS = {
  ALL: 'ALL',
  IN_STOCK: 'IN_STOCK',
  LOW_STOCK: 'LOW_STOCK',
  OUT_OF_STOCK: 'OUT_OF_STOCK',
};

export const DEFAULT_LOW_STOCK_THRESHOLD = 5;

export const MAX_STOCK_QUANTITY = 2147483647;

/**
 * Format UTC ISO string sang ngày giờ Việt Nam cố định múi giờ Asia/Ho_Chi_Minh
 * Không phụ thuộc vào timezone của máy trạm người dùng.
 * @param {string} isoString
 */
export function formatVietnamDateTime(isoString) {
  if (!isoString) return '-';
  try {
    const raw = String(isoString).trim();
    const utcStr = raw.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(raw)
      ? raw
      : `${raw.replace(' ', 'T')}Z`;
    const d = new Date(utcStr);
    if (Number.isNaN(d.getTime())) return String(isoString);

    const parts = new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).formatToParts(d);

    const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
    return `${map.day}/${map.month}/${map.year} ${map.hour}:${map.minute}:${map.second}`;
  } catch {
    return String(isoString);
  }
}

/**
 * Generate a cryptographically secure UUID v4 for Idempotency-Key.
 * Never falls back to Math.random() or timestamps.
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
  throw new Error('Môi trường không hỗ trợ crypto an toàn để sinh Idempotency-Key.');
}

/**
 * Phân loại tình trạng tồn kho theo chuẩn INV-04:
 * Chỉ áp dụng cảnh báo Tồn thấp (<=5) và Hết hàng (=0) cho sản phẩm Đang bán (ACTIVE).
 * @param {number} quantity - Số lượng tồn kho
 * @param {string} status - Trạng thái kinh doanh ('ACTIVE' | 'INACTIVE')
 * @param {number} threshold - Ngưỡng tồn thấp P0 (mặc định 5)
 * @returns {{ code: 'NORMAL' | 'LOW' | 'OUT_OF_STOCK' | 'INACTIVE', label: string, badgeClass: string }}
 */
export function classifyStockLevel(quantity, status = 'ACTIVE', threshold = DEFAULT_LOW_STOCK_THRESHOLD) {
  const qty = Math.max(0, Number(quantity) || 0);
  const isActive = status === 'ACTIVE';

  if (!isActive) {
    return {
      code: 'INACTIVE',
      label: 'Ngừng bán',
      badgeClass: 'badgeInactive',
    };
  }

  if (qty === 0) {
    return {
      code: 'OUT_OF_STOCK',
      label: 'Hết hàng',
      badgeClass: 'badgeOutOfStock',
    };
  }

  if (qty <= threshold) {
    return {
      code: 'LOW',
      label: `Tồn thấp`,
      badgeClass: 'badgeLowStock',
    };
  }

  return {
    code: 'NORMAL',
    label: 'Bình thường',
    badgeClass: 'badgeNormal',
  };
}

export const MOVEMENT_KIND_LABELS = {
  SALE: {
    label: 'Bán hàng POS',
    badgeClass: 'badgeMovementSale',
    icon: 'pos',
    prefix: '-',
  },
  PURCHASE_CONFIRM: {
    label: 'Nhập hàng',
    badgeClass: 'badgeMovementPurchase',
    icon: 'purchase',
    prefix: '+',
  },
  ORDER_CANCEL: {
    label: 'Hoàn trả hủy đơn',
    badgeClass: 'badgeMovementCancel',
    icon: 'cancel',
    prefix: '+',
  },
  ADJUSTMENT: {
    label: 'Điều chỉnh kho',
    badgeClass: 'badgeMovementAdjustment',
    icon: 'adjust',
    prefix: '',
  },
};

/**
 * Định dạng mã chứng từ theo loại biến động và reference_id thật từ database.
 * Không tự suy đoán ngày tháng hoặc tạo mã chứng từ giả dạng ISO date khi backend chỉ trả ID.
 * @param {string} kind
 * @param {number|string} referenceId
 */
export function formatReferenceCode(kind, referenceId) {
  if (!referenceId && referenceId !== 0) return '-';
  const idStr = String(referenceId);

  switch (kind) {
    case 'SALE':
      return `HĐ-${idStr}`;
    case 'ORDER_CANCEL':
      return `HỦY-HĐ-${idStr}`;
    case 'PURCHASE_CONFIRM':
      return `PN-${idStr}`;
    case 'ADJUSTMENT':
      return `KK-${idStr}`;
    default:
      return `#${idStr}`;
  }
}

export const inventoryApi = {
  /**
   * Lấy danh sách tồn kho phân trang theo chuẩn INV-01
   * @param {Object} params
   * @param {number} params.page
   * @param {number} params.pageSize
   * @param {number|null} params.categoryId
   * @param {'ACTIVE'|'INACTIVE'|null} params.status
   * @param {boolean|null} params.inStock
   */
  async getInventory({ page = 1, pageSize = 10, categoryId = null, status = null, inStock = null } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 10,
    };
    if (categoryId) {
      params.category_id = Number(categoryId);
    }
    if (status && (status === 'ACTIVE' || status === 'INACTIVE')) {
      params.status = status;
    }
    if (typeof inStock === 'boolean') {
      params.in_stock = inStock;
    }

    const response = await axiosClient.get('/inventory', { params });
    const data = response.data || {};
    const items = Array.isArray(data.items) ? data.items : [];
    const total = Number(data.total) || 0;
    const pageNum = Number(data.page) || 1;
    const size = Number(data.page_size) || pageSize;

    return {
      items,
      total,
      page: pageNum,
      pageSize: size,
      totalPages: Math.max(1, Math.ceil(total / size)),
    };
  },

  /**
   * Lấy danh sách tồn kho thấp theo chuẩn INV-04
   * @param {Object} params
   * @param {number} params.page
   * @param {number} params.pageSize
   */
  async getLowStock({
    page = 1,
    pageSize = 20,
    categoryId = null,
    excludeOutOfStock = false,
  } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 20,
    };
    if (categoryId !== null && categoryId !== undefined && Number(categoryId) > 0) {
      params.category_id = Number(categoryId);
    }
    if (excludeOutOfStock) {
      params.exclude_out_of_stock = true;
    }
    const response = await axiosClient.get('/inventory/low-stock', { params });
    const data = response.data || {};
    return {
      items: Array.isArray(data.items) ? data.items : [],
      total: Number(data.total) || 0,
      page: Number(data.page) || 1,
      pageSize: Number(data.page_size) || pageSize,
      totalPages: Math.max(1, Math.ceil((Number(data.total) || 0) / (Number(data.page_size) || pageSize))),
    };
  },

  /**
   * Lấy chi tiết tồn kho 1 sản phẩm
   * @param {number} productId
   */
  async getProductInventory(productId) {
    if (!productId || Number(productId) <= 0) {
      throw new Error('Mã sản phẩm không hợp lệ.');
    }
    const response = await axiosClient.get(`/inventory/${productId}`);
    return response.data;
  },

  /**
   * Lịch sử biến động kho theo chuẩn INV-03
   * @param {Object} params
   */
  async getStockMovements({ page = 1, pageSize = 20, productId = null, kind = null } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 20,
    };
    if (productId) {
      params.product_id = Number(productId);
    }
    if (kind) {
      params.kind = kind;
    }
    const response = await axiosClient.get('/stock-movements', { params });
    const data = response.data || {};
    return {
      items: Array.isArray(data.items) ? data.items : [],
      total: Number(data.total) || 0,
      page: Number(data.page) || 1,
      pageSize: Number(data.page_size) || pageSize,
      totalPages: Math.max(1, Math.ceil((Number(data.total) || 0) / (Number(data.page_size) || pageSize))),
    };
  },

  /**
   * Điều chỉnh tồn kho thực tế theo chuẩn INV-02 (Admin only)
   * @param {Object} params
   * @param {number} params.productId
   * @param {number} params.countedQuantity
   * @param {number} params.expectedStockVersion
   * @param {string} params.reason
   * @param {string} [params.idempotencyKey]
   */
  async adjustInventory({
    productId,
    countedQuantity,
    expectedStockVersion,
    reason,
    idempotencyKey,
  }) {
    const pid = Number(productId);
    if (!pid || pid <= 0) {
      throw new Error('Mã sản phẩm không hợp lệ.');
    }
    const counted = Number(countedQuantity);
    if (!Number.isInteger(counted) || counted < 0 || counted > MAX_STOCK_QUANTITY) {
      throw new Error(`Số lượng kiểm kê thực tế phải là số nguyên từ 0 đến ${MAX_STOCK_QUANTITY.toLocaleString('vi-VN')}.`);
    }
    if (typeof expectedStockVersion !== 'number' || !Number.isInteger(expectedStockVersion) || expectedStockVersion < 0) {
      throw new Error('Phiên bản tồn kho không hợp lệ.');
    }
    const trimmedReason = (reason || '').trim();
    if (!trimmedReason) {
      throw new Error('Lý do điều chỉnh không được để trống.');
    }
    if (trimmedReason.length > 500) {
      throw new Error('Lý do điều chỉnh không được vượt quá 500 ký tự.');
    }

    const key = idempotencyKey || generateSecureIdempotencyKey();

    const response = await axiosClient.post(
      `/inventory/${pid}/adjustments`,
      {
        counted_quantity: counted,
        expected_stock_version: expectedStockVersion,
        reason: trimmedReason,
      },
      {
        headers: {
          'Idempotency-Key': key,
        },
      }
    );

    return response.data;
  },

  /**
   * Xuất danh sách tồn kho dạng CSV (Admin only)
   */
  async exportInventoryCsv({ categoryId = null, status = null, inStock = null, lowStockOnly = false } = {}) {
    const params = {};
    if (categoryId) {
      params.category_id = Number(categoryId);
    }
    if (status && (status === 'ACTIVE' || status === 'INACTIVE')) {
      params.status = status;
    }
    if (typeof inStock === 'boolean') {
      params.in_stock = inStock;
    }
    if (lowStockOnly) {
      params.low_stock_only = true;
    }

    return axiosClient.get('/inventory/export/csv', {
      params: Object.keys(params).length > 0 ? params : undefined,
      responseType: 'blob',
    });
  },
};

