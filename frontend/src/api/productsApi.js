import axiosClient from './axiosClient.js';

/**
 * Whitelist các kiểu sắp xếp hợp lệ cho API Product (phối hợp với backend T3C9D97).
 */
export const ALLOWED_PRODUCT_SORTS = new Set([
  'name_asc',
  'name_desc',
  'sku_asc',
  'sku_desc',
  'created_desc',
]);

/**
 * Strict validation and parsing for Sale Price in VND (VND Positive Integer).
 *
 * Rules:
 * - Accepts only positive integers (> 0).
 * - Accepts clean plain digits (e.g. "28000").
 * - Accepts standard dot-thousands (e.g. "28.000", "1.000.000").
 * - Accepts standard comma-thousands (e.g. "28,000", "1,000,000").
 * - Rejects any decimal fractional amounts (e.g. "10,5", "1.2", "28.5").
 * - Rejects zero ("0") and negative amounts ("-1000").
 * - Rejects empty string, whitespace, non-numeric strings ("abc", "28k").
 * - Rejects values exceeding Number.MAX_SAFE_INTEGER or MySQL INT limit (2,147,483,647).
 * - Never converts an invalid fractional or malformed input into a distorted number.
 */
export function parseAndValidateSalePriceVnd(rawInput) {
  if (rawInput === null || rawInput === undefined) {
    return { isValid: false, value: null, error: 'Vui lòng nhập giá bán.' };
  }
  const str = String(rawInput).trim();
  if (!str) {
    return { isValid: false, value: null, error: 'Vui lòng nhập giá bán.' };
  }

  // Chặn số âm rõ ràng
  if (str.startsWith('-')) {
    return {
      isValid: false,
      value: null,
      error: 'Giá bán phải là số nguyên dương lớn hơn 0 VND.',
    };
  }

  // Định dạng hợp lệ:
  // 1. Số nguyên thuần không phân cách: vd "28000"
  const isPlainDigits = /^\d+$/.test(str);
  // 2. Phân cách hàng nghìn bằng dấu chấm: vd "28.000", "1.000.000"
  const isDotThousands = /^\d{1,3}(\.\d{3})+$/.test(str);
  // 3. Phân cách hàng nghìn bằng dấu phẩy: vd "28,000", "1,000,000"
  const isCommaThousands = /^\d{1,3}(,\d{3})+$/.test(str);

  if (!isPlainDigits && !isDotThousands && !isCommaThousands) {
    if (str.includes(',') || str.includes('.')) {
      return {
        isValid: false,
        value: null,
        error:
          'Giá bán phải là số nguyên VND, không được chứa số lẻ thập phân (ví dụ 10,5 hoặc 1.2) hoặc dấu phân cách sai quy cách.',
      };
    }
    return {
      isValid: false,
      value: null,
      error: 'Giá bán không hợp lệ. Vui lòng chỉ nhập số nguyên VND.',
    };
  }

  const cleanedStr = str.replace(/[.,]/g, '');
  const num = Number(cleanedStr);

  if (!Number.isFinite(num) || !Number.isSafeInteger(num) || num > 2147483647) {
    return {
      isValid: false,
      value: null,
      error: 'Giá bán vượt quá giới hạn số nguyên cho phép (tối đa 2.147.483.647 VND).',
    };
  }

  if (num <= 0) {
    return {
      isValid: false,
      value: null,
      error: 'Giá bán phải là số nguyên dương lớn hơn 0 VND.',
    };
  }

  return { isValid: true, value: num, error: null };
}

/**
 * Validate ProductRead contract.
 * Invariant: Never default missing quantity to zero stock.
 */
export function validateProductRead(item) {
  if (!item || typeof item !== 'object') {
    throw new Error('Product payload must be an object.');
  }
  if (typeof item.id !== 'number' || !Number.isInteger(item.id) || item.id <= 0) {
    throw new Error(`Product missing valid integer id: ${JSON.stringify(item)}`);
  }
  if (typeof item.sku !== 'string' || !item.sku.trim()) {
    throw new Error(`Product ${item.id} missing valid sku.`);
  }
  if (typeof item.name !== 'string' || !item.name.trim()) {
    throw new Error(`Product ${item.id} missing valid name.`);
  }
  if (typeof item.category_id !== 'number' || !Number.isInteger(item.category_id)) {
    throw new Error(`Product ${item.id} missing valid category_id.`);
  }
  if (typeof item.sale_price_vnd !== 'number' || item.sale_price_vnd <= 0) {
    throw new Error(`Product ${item.id} missing valid sale_price_vnd.`);
  }
  // CRITICAL REQUIREMENT: Do NOT default missing or undefined quantity to 0
  if (typeof item.quantity !== 'number' || !Number.isInteger(item.quantity) || item.quantity < 0) {
    throw new Error(
      `Schema violation: Product "${item.name}" (SKU: ${item.sku}) has invalid or missing quantity: ${item.quantity}.`
    );
  }
  return {
    id: item.id,
    category_id: item.category_id,
    sku: item.sku,
    name: item.name,
    status: item.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE',
    sale_price_vnd: item.sale_price_vnd,
    quantity: item.quantity,
    stock_version: Number(item.stock_version ?? 0),
    created_at: item.created_at || new Date().toISOString(),
    updated_at: item.updated_at || new Date().toISOString(),
  };
}

/**
 * Validate CategoryRead contract.
 */
export function validateCategoryRead(item) {
  if (!item || typeof item !== 'object') {
    throw new Error('Category payload must be an object.');
  }
  if (typeof item.id !== 'number' || item.id <= 0) {
    throw new Error(`Category missing valid id: ${JSON.stringify(item)}`);
  }
  if (typeof item.name !== 'string' || !item.name.trim()) {
    throw new Error(`Category ${item.id} missing valid name.`);
  }
  return {
    id: item.id,
    name: item.name,
    status: item.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE',
    created_at: item.created_at || new Date().toISOString(),
    updated_at: item.updated_at || new Date().toISOString(),
  };
}

/**
 * Unified Product API service connecting directly to FastAPI backend.
 */
export const productsApi = {
  /**
   * Fetch products with pagination, filters, and sorting.
   * Calls Real FastAPI backend GET /api/v1/products.
   */
  async getProducts({
    page = 1,
    pageSize = 20,
    keyword = '',
    categoryId = '',
    status = '',
    sort = '',
  } = {}) {
    const params = {
      page,
      page_size: pageSize,
    };
    if (keyword && String(keyword).trim()) params.search = String(keyword).trim();
    if (categoryId) params.category_id = Number(categoryId);
    if (status) params.status = status;
    if (sort && ALLOWED_PRODUCT_SORTS.has(sort)) params.sort = sort;

    const response = await axiosClient.get('/products', { params });
    const payload = response.data || {};
    const items = Array.isArray(payload.items) ? payload.items.map(validateProductRead) : [];

    return {
      items,
      total: Number(payload.total) || items.length,
      page: Number(payload.page) || page,
      page_size: Number(payload.page_size) || pageSize,
    };
  },

  /**
   * Create a new product (Admin only).
   * Initial quantity is always 0 on backend (PROD-01).
   */
  async createProduct(payloadOrWrapper) {
    const data = payloadOrWrapper?.data ?? payloadOrWrapper;
    const response = await axiosClient.post('/products', data);
    return validateProductRead(response.data);
  },

  /**
   * Update an existing product master fields (PROD-01).
   * Note: SKU is strictly immutable in edit mode.
   */
  async updateProduct({ id, data }) {
    // Defensive payload sanitization: Send only whitelisted ProductUpdateRequest fields (name, category_id, sale_price_vnd)
    // Never send 'sku', 'status', 'quantity', 'stock_version'
    const cleanPayload = {};
    if (data.name !== undefined) cleanPayload.name = String(data.name).trim();
    if (data.category_id !== undefined) cleanPayload.category_id = Number(data.category_id);
    if (data.sale_price_vnd !== undefined) cleanPayload.sale_price_vnd = Number(data.sale_price_vnd);

    const response = await axiosClient.patch(`/products/${id}`, cleanPayload);
    return validateProductRead(response.data);
  },

  /**
   * Toggle product active/inactive status (Admin only).
   */
  async updateProductStatus({ id, status }) {
    const response = await axiosClient.patch(`/products/${id}/status`, { status });
    return validateProductRead(response.data);
  },

  /**
   * Fetch categories list from FastAPI backend GET /api/v1/categories.
   */
  async getCategories({ page = 1, pageSize = 100 } = {}) {
    const response = await axiosClient.get('/categories', {
      params: { page, page_size: pageSize },
    });
    const payload = response.data || {};
    const items = Array.isArray(payload.items) ? payload.items.map(validateCategoryRead) : [];
    return {
      items,
      total: Number(payload.total) || items.length,
      page: Number(payload.page) || page,
      page_size: Number(payload.page_size) || pageSize,
    };
  },

  /**
   * Create a new category (Admin only - PROD-02).
   */
  async createCategory(payloadOrWrapper) {
    const name = typeof payloadOrWrapper === 'string' ? payloadOrWrapper : payloadOrWrapper?.name;
    const response = await axiosClient.post('/categories', { name });
    return validateCategoryRead(response.data);
  },

  /**
   * Update category name (Admin only - PROD-02).
   */
  async updateCategory({ id, name }) {
    const response = await axiosClient.patch(`/categories/${id}`, { name });
    return validateCategoryRead(response.data);
  },

  /**
   * Toggle category status ACTIVE / INACTIVE (Admin only - PROD-02).
   */
  async updateCategoryStatus({ id, status }) {
    const response = await axiosClient.patch(`/categories/${id}/status`, { status });
    return validateCategoryRead(response.data);
  },
};
