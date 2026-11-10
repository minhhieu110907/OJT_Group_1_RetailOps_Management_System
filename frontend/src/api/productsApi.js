import axiosClient, {
  getClientToken,
  getUseMock,
  isMockAllowed,
} from './axiosClient.js';

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
 * Whitelist trạng thái sản phẩm và danh mục hợp lệ theo CatalogStatus enum.
 */
export const VALID_CATALOG_STATUSES = new Set(['ACTIVE', 'INACTIVE']);

/**
 * Validate ISO timestamp string according to backend datetime contract.
 * Rejects missing, null, undefined, invalid date strings, or NaN timestamps.
 */
export function isValidIsoTimestamp(val) {
  if (typeof val !== 'string' || !val.trim()) return false;
  const time = Date.parse(val);
  return Number.isFinite(time);
}

/**
 * Determine whether Mock mode is allowed under strict environment isolation (FIX-01/F02).
 * Production build MUST ALWAYS use Real API.
 * Product Manager strictly operates on Real API; Mock mode is fail-closed.
 */
export function shouldRunMock(explicitFlag, runtimeEnv = import.meta.env) {
  if (!isMockAllowed(runtimeEnv)) {
    return false;
  }
  // Product Manager workflow is Real API only
  return false;
}

/**
 * F02 Fail-Closed Guard:
 * Ngăn chặn tuyệt đối việc gọi Real Product/Category API khi hệ thống đang ở chế độ Mock
 * (theo trạng thái đồng bộ từ axiosClient/AuthContext) hoặc khi đang mang danh tính/token Mock.
 * Không tạo nguồn trạng thái Mock thứ hai bên cạnh AuthContext/axiosClient.
 */
export function assertRealApiMode(explicitMockFlag = false) {
  const token = getClientToken();
  const hasMockToken =
    typeof token === 'string' && token.trim().startsWith('mock_jwt_');
  if (explicitMockFlag || getUseMock() || hasMockToken) {
    const err = new Error(
      'Chế độ Mock Demo không được hỗ trợ trong Quản lý sản phẩm. Vui lòng chuyển sang Real API.'
    );
    err.code = 'ERR_MOCK_NOT_SUPPORTED';
    throw err;
  }
}

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
 * - Accepts up to Number.MAX_SAFE_INTEGER (9,007,199,254,740,991) to match Backend BIGINT without precision loss.
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

  if (!Number.isFinite(num) || !Number.isSafeInteger(num) || num > Number.MAX_SAFE_INTEGER) {
    return {
      isValid: false,
      value: null,
      error: 'Giá bán vượt quá giới hạn số nguyên an toàn cho phép.',
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
 * Validate ProductRead contract (F01 Fail-closed).
 * Invariant: Never default missing quantity, stock_version, status, or timestamps.
 * Missing, null, or wrong type must be strictly rejected.
 */
export function validateProductRead(item) {
  if (!item || typeof item !== 'object') {
    throw new Error('Product payload must be an object.');
  }
  if (typeof item.id !== 'number' || !Number.isInteger(item.id) || item.id <= 0) {
    throw new Error(`Product missing valid integer id: ${JSON.stringify(item)}`);
  }
  if (typeof item.sku !== 'string' || !item.sku.trim() || item.sku.length > 64) {
    throw new Error(`Product ${item.id} missing valid sku (string <= 64 chars).`);
  }
  if (typeof item.name !== 'string' || !item.name.trim() || item.name.length > 160) {
    throw new Error(`Product ${item.id} missing valid name (string <= 160 chars).`);
  }
  if (typeof item.category_id !== 'number' || !Number.isInteger(item.category_id) || item.category_id <= 0) {
    throw new Error(`Product ${item.id} missing valid category_id.`);
  }
  if (
    typeof item.sale_price_vnd !== 'number' ||
    !Number.isInteger(item.sale_price_vnd) ||
    item.sale_price_vnd <= 0 ||
    item.sale_price_vnd > Number.MAX_SAFE_INTEGER
  ) {
    throw new Error(`Product ${item.id} missing valid positive integer sale_price_vnd.`);
  }

  // F01: Strict quantity invariant - Never default missing/null to 0
  if (typeof item.quantity !== 'number' || !Number.isInteger(item.quantity) || item.quantity < 0) {
    throw new Error(
      `Schema violation: Product "${item.name}" (SKU: ${item.sku}) has invalid or missing quantity: ${item.quantity}.`
    );
  }

  // F01: Strict stock_version invariant - Never default missing/null to 0
  if (
    typeof item.stock_version !== 'number' ||
    !Number.isInteger(item.stock_version) ||
    item.stock_version < 0
  ) {
    throw new Error(
      `Schema violation: Product "${item.name}" (SKU: ${item.sku}) has invalid or missing stock_version: ${item.stock_version}.`
    );
  }

  // F01: Strict status validation - Must be strictly ACTIVE or INACTIVE
  if (typeof item.status !== 'string' || !VALID_CATALOG_STATUSES.has(item.status)) {
    throw new Error(
      `Schema violation: Product "${item.name}" (SKU: ${item.sku}) has invalid status "${item.status}". Expected ACTIVE or INACTIVE.`
    );
  }

  // F01: Strict timestamp validation - Must be valid ISO string, no fallback
  if (!isValidIsoTimestamp(item.created_at)) {
    throw new Error(
      `Schema violation: Product "${item.name}" (SKU: ${item.sku}) has invalid or missing created_at timestamp: ${item.created_at}.`
    );
  }
  if (!isValidIsoTimestamp(item.updated_at)) {
    throw new Error(
      `Schema violation: Product "${item.name}" (SKU: ${item.sku}) has invalid or missing updated_at timestamp: ${item.updated_at}.`
    );
  }

  return {
    id: item.id,
    category_id: item.category_id,
    sku: item.sku.trim(),
    name: item.name.trim(),
    status: item.status,
    sale_price_vnd: item.sale_price_vnd,
    quantity: item.quantity,
    stock_version: item.stock_version,
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

/**
 * Validate CategoryRead contract (F01 Fail-closed).
 * Invariant: Never default missing id, name, status, or timestamps.
 */
export function validateCategoryRead(item) {
  if (!item || typeof item !== 'object') {
    throw new Error('Category payload must be an object.');
  }
  if (typeof item.id !== 'number' || !Number.isInteger(item.id) || item.id <= 0) {
    throw new Error(`Category missing valid integer id: ${JSON.stringify(item)}`);
  }
  if (typeof item.name !== 'string' || !item.name.trim() || item.name.length > 120) {
    throw new Error(`Category ${item.id} missing valid name (string <= 120 chars).`);
  }
  if (typeof item.status !== 'string' || !VALID_CATALOG_STATUSES.has(item.status)) {
    throw new Error(
      `Schema violation: Category "${item.name}" (ID: ${item.id}) has invalid status "${item.status}". Expected ACTIVE or INACTIVE.`
    );
  }
  if (!isValidIsoTimestamp(item.created_at)) {
    throw new Error(
      `Schema violation: Category "${item.name}" (ID: ${item.id}) has invalid or missing created_at timestamp: ${item.created_at}.`
    );
  }
  if (!isValidIsoTimestamp(item.updated_at)) {
    throw new Error(
      `Schema violation: Category "${item.name}" (ID: ${item.id}) has invalid or missing updated_at timestamp: ${item.updated_at}.`
    );
  }

  return {
    id: item.id,
    name: item.name.trim(),
    status: item.status,
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

/**
 * Unified Product API service connecting directly to FastAPI backend.
 */
export const productsApi = {
  /**
   * Fetch products with pagination, filters, and sorting.
   * Calls Real FastAPI backend GET /api/v1/products.
   * Fail-closed against Mock Mode (F02).
   */
  async getProducts({
    isMockMode,
    page = 1,
    pageSize = 20,
    keyword = '',
    categoryId = '',
    status = '',
    sort = '',
  } = {}) {
    assertRealApiMode(isMockMode);

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
    assertRealApiMode(payloadOrWrapper?.isMockMode);
    const data = payloadOrWrapper?.data ?? payloadOrWrapper;
    const response = await axiosClient.post('/products', data);
    return validateProductRead(response.data);
  },

  /**
   * Update an existing product master fields (PROD-01).
   * Note: SKU is strictly immutable in edit mode.
   */
  async updateProduct({ isMockMode, id, data } = {}) {
    assertRealApiMode(isMockMode);
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
  async updateProductStatus({ isMockMode, id, status } = {}) {
    assertRealApiMode(isMockMode);
    const response = await axiosClient.patch(`/products/${id}/status`, { status });
    return validateProductRead(response.data);
  },

  /**
   * Fetch categories list from FastAPI backend GET /api/v1/categories.
   * Supports bounded multi-page fetching (F06) to ensure complete list if total > 100.
   */
  async getCategories({ isMockMode, page = 1, pageSize = 100, fetchAll = false } = {}) {
    assertRealApiMode(isMockMode);

    const response = await axiosClient.get('/categories', {
      params: { page, page_size: pageSize },
    });
    const payload = response.data || {};
    let items = Array.isArray(payload.items) ? payload.items.map(validateCategoryRead) : [];
    const total = Number(payload.total) || items.length;

    // F06: Safe bounded pagination if total > 100 and caller requests fetchAll (capped at 10 pages / 1000 items)
    if (fetchAll && total > items.length && items.length > 0) {
      const maxPages = Math.min(Math.ceil(total / pageSize), 10);
      for (let p = 2; p <= maxPages; p++) {
        const nextRes = await axiosClient.get('/categories', {
          params: { page: p, page_size: pageSize },
        });
        const nextItems = Array.isArray(nextRes.data?.items)
          ? nextRes.data.items.map(validateCategoryRead)
          : [];
        items = items.concat(nextItems);
      }
    }

    return {
      items,
      total,
      page: Number(payload.page) || page,
      page_size: Number(payload.page_size) || pageSize,
    };
  },

  /**
   * Create a new category (Admin only - PROD-02).
   */
  async createCategory(payloadOrWrapper) {
    assertRealApiMode(payloadOrWrapper?.isMockMode);
    const name = typeof payloadOrWrapper === 'string' ? payloadOrWrapper : payloadOrWrapper?.name;
    const response = await axiosClient.post('/categories', { name });
    return validateCategoryRead(response.data);
  },

  /**
   * Update category name (Admin only - PROD-02).
   */
  async updateCategory({ isMockMode, id, name } = {}) {
    assertRealApiMode(isMockMode);
    const response = await axiosClient.patch(`/categories/${id}`, { name });
    return validateCategoryRead(response.data);
  },

  /**
   * Toggle category status ACTIVE / INACTIVE (Admin only - PROD-02).
   */
  async updateCategoryStatus({ isMockMode, id, status } = {}) {
    assertRealApiMode(isMockMode);
    const response = await axiosClient.patch(`/categories/${id}/status`, { status });
    return validateCategoryRead(response.data);
  },
};
