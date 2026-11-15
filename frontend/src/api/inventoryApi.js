import axiosClient from './axiosClient.js';

export const STOCK_STATUS_TABS = {
  ALL: 'ALL',
  IN_STOCK: 'IN_STOCK',
  LOW_STOCK: 'LOW_STOCK',
  OUT_OF_STOCK: 'OUT_OF_STOCK',
};

export const DEFAULT_LOW_STOCK_THRESHOLD = 5;

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
 * Định dạng mã chứng từ theo loại biến động và ID
 * @param {string} kind
 * @param {number} referenceId
 * @param {string} dateStr (YYYY-MM-DD)
 */
export function formatReferenceCode(kind, referenceId, dateStr = '') {
  if (!referenceId) return '-';
  const paddedId = String(referenceId).padStart(3, '0');
  const dateFormatted = dateStr ? dateStr.replace(/[^0-9]/g, '').slice(0, 8) : '20261104';

  switch (kind) {
    case 'SALE':
    case 'ORDER_CANCEL':
      return `HĐ-${dateFormatted}-${paddedId}`;
    case 'PURCHASE_CONFIRM':
      return `PN-${dateFormatted}-${paddedId}`;
    case 'ADJUSTMENT':
      return `KK-${dateFormatted}-${paddedId}`;
    default:
      return `#${referenceId}`;
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
  async getLowStock({ page = 1, pageSize = 20 } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 20,
    };
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
    if (!Number.isInteger(counted) || counted < 0) {
      throw new Error('Số lượng kiểm kê thực tế phải là số nguyên không âm (≥ 0).');
    }
    if (typeof expectedStockVersion !== 'number' || expectedStockVersion < 0) {
      throw new Error('Phiên bản tồn kho không hợp lệ.');
    }
    const trimmedReason = (reason || '').trim();
    if (!trimmedReason) {
      throw new Error('Lý do điều chỉnh không được để trống.');
    }

    const key = idempotencyKey || (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `adj-${Date.now()}-${Math.random().toString(36).substring(2, 10)}`);

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
};

