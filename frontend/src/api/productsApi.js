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
 * Tùy chọn sắp xếp ưu tiên nhập hàng ("Cần nhập trước") trên trang Quản lý sản phẩm.
 */
export const RESTOCK_FIRST_SORT = 'restock_first';

/**
 * Ngưỡng tồn kho thấp hiện hành của hệ thống (INV-04 / ProductList baseline: 1..5).
 */
export const LOW_STOCK_THRESHOLD = 5;

/**
 * 3 bộ lọc thống kê tồn kho cố định trên trang Quản lý sản phẩm (CHANGE A).
 * Tuyệt đối chỉ có 3 mục: Tất cả, Hết hàng, Sắp hết.
 */
export const STOCK_FILTER_TABS = Object.freeze({
  ALL: 'ALL',
  OUT_OF_STOCK: 'OUT_OF_STOCK',
  LOW_STOCK: 'LOW_STOCK',
});

/**
 * Kiểm tra số lượng tồn kho có phải là số nguyên không âm hợp lệ hay không.
 * Tuyệt đối không ép kiểu null, undefined, chuỗi hoặc số âm thành 0.
 */
export function isValidInventoryQuantity(qty) {
  return typeof qty === 'number' && Number.isInteger(qty) && qty >= 0;
}

/**
 * Phân loại trạng thái tồn kho của sản phẩm dựa trên logic hiện có:
 * - OUT_OF_STOCK: tồn kho hợp lệ và bằng 0
 * - LOW_STOCK: tồn kho hợp lệ và nằm trong khoảng 1..LOW_STOCK_THRESHOLD (1..5)
 * - NORMAL_STOCK: tồn kho hợp lệ và > LOW_STOCK_THRESHOLD (> 5)
 * - INVALID_STOCK: dữ liệu tồn kho null, undefined hoặc bất thường (không coi là 0)
 */
export function classifyProductStock(productOrQty) {
  const qty =
    productOrQty !== null && typeof productOrQty === 'object'
      ? productOrQty.quantity
      : productOrQty;

  if (!isValidInventoryQuantity(qty)) {
    return 'INVALID_STOCK';
  }
  if (qty === 0) {
    return 'OUT_OF_STOCK';
  }
  if (qty <= LOW_STOCK_THRESHOLD) {
    return 'LOW_STOCK';
  }
  return 'NORMAL_STOCK';
}

/**
 * Kiểm tra sản phẩm có thực sự hết hàng (tồn kho hợp lệ === 0) hay không (CHANGE B).
 */
export function isOutOfStockProduct(product) {
  return classifyProductStock(product) === 'OUT_OF_STOCK';
}

/**
 * Tính toán số lượng cho 3 bộ lọc thống kê tồn kho (CHANGE A):
 * - all: tổng số sản phẩm trong phạm vi dữ liệu hiện tại
 * - outOfStock: số sản phẩm thuộc nhóm Hết hàng (quantity === 0)
 * - lowStock: số sản phẩm thuộc nhóm Sắp hết (1 <= quantity <= 5)
 */
export function computeProductStockStats(products = []) {
  if (!Array.isArray(products)) {
    return { all: 0, outOfStock: 0, lowStock: 0 };
  }

  let outOfStock = 0;
  let lowStock = 0;

  for (const product of products) {
    const stockClass = classifyProductStock(product);
    if (stockClass === 'OUT_OF_STOCK') {
      outOfStock += 1;
    } else if (stockClass === 'LOW_STOCK') {
      lowStock += 1;
    }
  }

  return {
    all: products.length,
    outOfStock,
    lowStock,
  };
}

/**
 * Lọc danh sách sản phẩm theo 1 trong 3 tab thống kê tồn kho (CHANGE A).
 */
export function filterProductsByStockTab(
  products = [],
  stockTab = STOCK_FILTER_TABS.ALL
) {
  if (!Array.isArray(products)) return [];
  if (stockTab === STOCK_FILTER_TABS.OUT_OF_STOCK) {
    return products.filter((p) => classifyProductStock(p) === 'OUT_OF_STOCK');
  }
  if (stockTab === STOCK_FILTER_TABS.LOW_STOCK) {
    return products.filter((p) => classifyProductStock(p) === 'LOW_STOCK');
  }
  return [...products];
}

/**
 * Xác định mức độ ưu tiên khi sắp xếp "Cần nhập trước" (CHANGE D):
 * 1: Hết hàng (OUT_OF_STOCK)
 * 2: Sắp hết (LOW_STOCK)
 * 3: Tồn kho bình thường (NORMAL_STOCK)
 * 4: Dữ liệu tồn kho bất thường (INVALID_STOCK) — luôn xếp sau bản ghi hợp lệ
 */
export function getRestockSortPriority(product) {
  const stockClass = classifyProductStock(product);
  if (stockClass === 'OUT_OF_STOCK') return 1;
  if (stockClass === 'LOW_STOCK') return 2;
  if (stockClass === 'NORMAL_STOCK') return 3;
  return 4;
}

/**
 * Hàm so sánh 2 sản phẩm theo quy tắc "Cần nhập trước" (CHANGE D):
 * - Ưu tiên 1: Hết hàng (quantity === 0)
 * - Ưu tiên 2: Sắp hết (1 <= quantity <= 5), tồn kho nhỏ hơn đứng trước
 * - Ưu tiên 3: Tồn kho bình thường (quantity > 5), tồn kho tăng dần
 * - Bản ghi tồn kho bất thường đặt sau các bản ghi hợp lệ
 * - Tie-breaker ổn định theo id -> sku -> name khi cùng mức ưu tiên và số lượng
 */
export function compareProductsForRestock(a, b) {
  const priorityA = getRestockSortPriority(a);
  const priorityB = getRestockSortPriority(b);

  if (priorityA !== priorityB) {
    return priorityA - priorityB;
  }

  if (priorityA < 4 && a.quantity !== b.quantity) {
    return a.quantity - b.quantity;
  }

  if (
    typeof a?.id === 'number' &&
    Number.isInteger(a.id) &&
    typeof b?.id === 'number' &&
    Number.isInteger(b.id) &&
    a.id !== b.id
  ) {
    return a.id - b.id;
  }

  if (typeof a?.sku === 'string' && typeof b?.sku === 'string' && a.sku !== b.sku) {
    return a.sku.localeCompare(b.sku);
  }

  if (typeof a?.name === 'string' && typeof b?.name === 'string' && a.name !== b.name) {
    return a.name.localeCompare(b.name);
  }

  return 0;
}

/**
 * Sắp xếp mảng sản phẩm theo tùy chọn "Cần nhập trước" mà không làm biến đổi mảng gốc (CHANGE D).
 */
export function sortProductsForRestock(products = []) {
  if (!Array.isArray(products)) return [];
  return products
    .map((item, index) => ({ item, index }))
    .sort((entryA, entryB) => {
      const cmp = compareProductsForRestock(entryA.item, entryB.item);
      return cmp !== 0 ? cmp : entryA.index - entryB.index;
    })
    .map((entry) => entry.item);
}

/**
 * Whitelist trạng thái sản phẩm và danh mục hợp lệ theo CatalogStatus enum.
 */
export const VALID_CATALOG_STATUSES = new Set(['ACTIVE', 'INACTIVE']);

/**
 * Validate ISO timestamp string according to FastAPI/Pydantic/MySQL contract (FIX-09).
 * Rejects missing, null, undefined, natural language words, invalid calendar dates (e.g. Feb 31),
 * or malformed timestamp strings.
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

  const time = Date.parse(trimmed);
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
  if (
    item.description !== undefined &&
    item.description !== null &&
    typeof item.description !== 'string'
  ) {
    throw new Error(`Category ${item.id} has invalid description.`);
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
    ...(item.description !== undefined ? { description: item.description } : {}),
    status: item.status,
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

/**
 * Validate paginated envelope contract (FIX-07 Fail-Closed).
 * Rules:
 * - payload must be a non-null, non-array object.
 * - items must be an Array.
 * - total must be a non-negative integer.
 * - page must be an integer >= minPage (default 1).
 * - page_size must be an integer between minPageSize (1) and maxPageSize (100).
 * - items.length <= page_size.
 * - total >= items.length.
 * - When total === 0, items.length must be 0.
 * - No implicit string-to-number coercion.
 * - Does not invent metadata.
 * - Each item is validated through itemValidator.
 * - Does NOT reject out-of-range pages when items is empty (valid backend behavior).
 */
export function validatePaginatedResponse(
  payload,
  itemValidator,
  { minPage = 1, minPageSize = 1, maxPageSize = 100 } = {}
) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('Paginated response payload must be a non-null object.');
  }

  if (!Array.isArray(payload.items)) {
    throw new Error('Paginated response "items" must be an array.');
  }

  if (
    typeof payload.total !== 'number' ||
    !Number.isInteger(payload.total) ||
    payload.total < 0
  ) {
    throw new Error(
      `Paginated response "total" must be a non-negative integer, got: ${JSON.stringify(payload.total)}`
    );
  }

  if (
    typeof payload.page !== 'number' ||
    !Number.isInteger(payload.page) ||
    payload.page < minPage
  ) {
    throw new Error(
      `Paginated response "page" must be an integer >= ${minPage}, got: ${JSON.stringify(payload.page)}`
    );
  }

  if (
    typeof payload.page_size !== 'number' ||
    !Number.isInteger(payload.page_size) ||
    payload.page_size < minPageSize ||
    payload.page_size > maxPageSize
  ) {
    throw new Error(
      `Paginated response "page_size" must be an integer between ${minPageSize} and ${maxPageSize}, got: ${JSON.stringify(payload.page_size)}`
    );
  }

  if (payload.items.length > payload.page_size) {
    throw new Error(
      `Paginated response items count (${payload.items.length}) exceeds page_size (${payload.page_size}).`
    );
  }

  if (payload.total === 0 && payload.items.length > 0) {
    throw new Error(
      `Paginated response has total=0 but contains ${payload.items.length} items.`
    );
  }

  if (payload.total < payload.items.length) {
    throw new Error(
      `Paginated response "total" (${payload.total}) cannot be less than items count (${payload.items.length}).`
    );
  }

  if (typeof itemValidator !== 'function') {
    throw new Error('validatePaginatedResponse requires an itemValidator function.');
  }

  const validatedItems = payload.items.map(itemValidator);

  return {
    items: validatedItems,
    total: payload.total,
    page: payload.page,
    page_size: payload.page_size,
  };
}

/**
 * Maximum pages allowed for bounded category and product pagination (FIX-08).
 */
export const MAX_CATEGORY_PAGES_LIMIT = 10;
export const MAX_PRODUCT_PAGES_LIMIT = 50;

/**
 * Unified Product API service connecting directly to FastAPI backend.
 */
export const productsApi = {
  /**
   * Fetch products with pagination, filters, and sorting.
   * Calls Real FastAPI backend GET /api/v1/products.
   * Fail-closed against Mock Mode (F02) and Malformed Envelopes (FIX-07).
   * Supports bounded multi-page fetching (fetchAll) when full dataset is required
   * for cross-page stock statistics, stock-status filtering, and restock-priority sorting.
   */
  async getProducts({
    isMockMode,
    page = 1,
    pageSize = 20,
    keyword = '',
    categoryId = '',
    status = '',
    sort = '',
    fetchAll = false,
    maxPages = MAX_PRODUCT_PAGES_LIMIT,
  } = {}) {
    assertRealApiMode(isMockMode);

    const initialPage =
      typeof page === 'number' && Number.isInteger(page) && page >= 1 ? page : 1;
    const initialPageSize =
      typeof pageSize === 'number' &&
      Number.isInteger(pageSize) &&
      pageSize >= 1 &&
      pageSize <= 100
        ? pageSize
        : 20;

    const buildQueryParams = (targetPage) => {
      const params = {
        page: targetPage,
        page_size: initialPageSize,
      };
      if (keyword && String(keyword).trim()) params.search = String(keyword).trim();
      if (categoryId) params.category_id = Number(categoryId);
      if (status) params.status = status;
      if (sort && ALLOWED_PRODUCT_SORTS.has(sort)) params.sort = sort;
      return params;
    };

    const firstResponse = await axiosClient.get('/products', {
      params: buildQueryParams(initialPage),
    });
    const firstResult = validatePaginatedResponse(
      firstResponse.data,
      validateProductRead,
      {
        minPageSize: 1,
        maxPageSize: 100,
      }
    );

    if (!fetchAll) {
      return firstResult;
    }

    const allItems = [...firstResult.items];
    const seenIds = new Set(allItems.map((item) => item.id));
    if (seenIds.size !== allItems.length) {
      throw new Error('Duplicate product ID detected on initial page.');
    }

    const total = firstResult.total;
    const totalPages = Math.max(1, Math.ceil(total / initialPageSize));
    const pagesToFetchLimit = Math.min(totalPages, initialPage + maxPages - 1);

    let currentPage = initialPage + 1;
    while (currentPage <= pagesToFetchLimit && allItems.length < total) {
      const nextResponse = await axiosClient.get('/products', {
        params: buildQueryParams(currentPage),
      });

      const nextResult = validatePaginatedResponse(
        nextResponse.data,
        validateProductRead,
        {
          minPageSize: 1,
          maxPageSize: 100,
        }
      );

      if (nextResult.total !== total) {
        throw new Error(
          `Product pagination metadata inconsistency: expected total ${total}, got ${nextResult.total} on page ${currentPage}.`
        );
      }
      if (nextResult.page !== currentPage) {
        throw new Error(
          `Product pagination page mismatch: requested page ${currentPage}, got ${nextResult.page}.`
        );
      }

      if (nextResult.items.length === 0) {
        break;
      }

      for (const item of nextResult.items) {
        if (seenIds.has(item.id)) {
          throw new Error(
            `Product pagination duplicate ID detected: ID ${item.id} already received in previous pages.`
          );
        }
        seenIds.add(item.id);
        allItems.push(item);
      }

      currentPage += 1;
    }

    const isTruncated = allItems.length < total;

    return {
      items: allItems,
      total,
      page: initialPage,
      page_size: initialPageSize,
      isTruncated,
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
   * Supports bounded multi-page fetching (FIX-08) with duplicate detection,
   * metadata consistency checks, and fail-closed pagination.
   */
  async getCategories({
    isMockMode,
    page = 1,
    pageSize = 100,
    fetchAll = false,
    maxPages = MAX_CATEGORY_PAGES_LIMIT,
  } = {}) {
    assertRealApiMode(isMockMode);

    const initialPage = typeof page === 'number' && Number.isInteger(page) && page >= 1 ? page : 1;
    const initialPageSize =
      typeof pageSize === 'number' && Number.isInteger(pageSize) && pageSize >= 1 && pageSize <= 100
        ? pageSize
        : 100;

    const firstResponse = await axiosClient.get('/categories', {
      params: { page: initialPage, page_size: initialPageSize },
    });

    const firstResult = validatePaginatedResponse(
      firstResponse.data,
      validateCategoryRead,
      { minPageSize: 1, maxPageSize: 100 }
    );

    if (!fetchAll) {
      return firstResult;
    }

    const allItems = [...firstResult.items];
    const seenIds = new Set(allItems.map((cat) => cat.id));
    if (seenIds.size !== allItems.length) {
      throw new Error('Duplicate category ID detected on initial page.');
    }

    const total = firstResult.total;
    const totalPages = Math.max(1, Math.ceil(total / initialPageSize));
    const pagesToFetchLimit = Math.min(totalPages, initialPage + maxPages - 1);

    let currentPage = initialPage + 1;
    while (currentPage <= pagesToFetchLimit && allItems.length < total) {
      const nextResponse = await axiosClient.get('/categories', {
        params: { page: currentPage, page_size: initialPageSize },
      });

      const nextResult = validatePaginatedResponse(
        nextResponse.data,
        validateCategoryRead,
        { minPageSize: 1, maxPageSize: 100 }
      );

      // Verify metadata consistency across pages
      if (nextResult.total !== total) {
        throw new Error(
          `Category pagination metadata inconsistency: expected total ${total}, got ${nextResult.total} on page ${currentPage}.`
        );
      }
      if (nextResult.page !== currentPage) {
        throw new Error(
          `Category pagination page mismatch: requested page ${currentPage}, got ${nextResult.page}.`
        );
      }

      if (nextResult.items.length === 0) {
        break;
      }

      for (const item of nextResult.items) {
        if (seenIds.has(item.id)) {
          throw new Error(
            `Category pagination duplicate ID detected: ID ${item.id} already received in previous pages.`
          );
        }
        seenIds.add(item.id);
        allItems.push(item);
      }

      currentPage += 1;
    }

    const isTruncated = allItems.length < total;

    return {
      items: allItems,
      total,
      page: initialPage,
      page_size: initialPageSize,
      isTruncated,
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
