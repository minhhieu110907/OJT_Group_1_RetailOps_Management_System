import axiosClient, { getUseMock, isMockAllowed } from './axiosClient.js';

/**
 * Determine whether Mock mode is active under strict environment isolation (FIX-01).
 * Production build MUST ALWAYS use Real API.
 */
function shouldRunMock(explicitFlag) {
  if (typeof explicitFlag === 'boolean') {
    return explicitFlag;
  }
  return Boolean(isMockAllowed() && getUseMock());
}

/**
 * Initial mock data for Category and Product catalog.
 * Conforms strictly to backend schemas (CategoryRead and ProductRead).
 */
const DEFAULT_MOCK_CATEGORIES = [
  { id: 1, name: 'Đồ uống & Giải khát', status: 'ACTIVE', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' },
  { id: 2, name: 'Bánh kẹo & Snack', status: 'ACTIVE', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' },
  { id: 3, name: 'Mì gói & Thực phẩm đóng hộp', status: 'ACTIVE', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' },
  { id: 4, name: 'Gia vị & Đồ khô', status: 'ACTIVE', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' },
  { id: 5, name: 'Sữa & Sản phẩm từ sữa', status: 'INACTIVE', created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' },
];

const DEFAULT_MOCK_PRODUCTS = [
  { id: 101, category_id: 1, sku: 'COCA-330ML', name: 'Nước ngọt Coca Cola lon 330ml', status: 'ACTIVE', sale_price_vnd: 12000, quantity: 48, stock_version: 3, created_at: '2026-11-01T08:00:00Z', updated_at: '2026-11-02T10:00:00Z' },
  { id: 102, category_id: 1, sku: 'PEPSI-330ML', name: 'Nước ngọt Pepsi lon 330ml', status: 'ACTIVE', sale_price_vnd: 11000, quantity: 3, stock_version: 1, created_at: '2026-11-01T08:15:00Z', updated_at: '2026-11-03T11:00:00Z' },
  { id: 103, category_id: 1, sku: 'AQUA-500ML', name: 'Nước khoáng Aquafina 500ml', status: 'ACTIVE', sale_price_vnd: 7000, quantity: 0, stock_version: 2, created_at: '2026-11-01T08:30:00Z', updated_at: '2026-11-04T09:00:00Z' },
  { id: 104, category_id: 2, sku: 'LAY-ORIG-54G', name: 'Khoai tây sấy Lay\'s vị tự nhiên 54g', status: 'ACTIVE', sale_price_vnd: 18000, quantity: 24, stock_version: 1, created_at: '2026-11-01T09:00:00Z', updated_at: '2026-11-01T09:00:00Z' },
  { id: 105, category_id: 2, sku: 'OREO-VAN-133G', name: 'Bánh quy kem vani Oreo 133g', status: 'ACTIVE', sale_price_vnd: 16000, quantity: 4, stock_version: 2, created_at: '2026-11-01T09:15:00Z', updated_at: '2026-11-02T14:00:00Z' },
  { id: 106, category_id: 3, sku: 'HAOHAO-TCH-75G', name: 'Mì Hảo Hảo tôm chua cay 75g', status: 'ACTIVE', sale_price_vnd: 4500, quantity: 150, stock_version: 5, created_at: '2026-11-01T09:30:00Z', updated_at: '2026-11-05T08:00:00Z' },
  { id: 107, category_id: 3, sku: 'OMACHI-XB-80G', name: 'Mì Omachi xốt bò hầm 80g', status: 'ACTIVE', sale_price_vnd: 8500, quantity: 2, stock_version: 1, created_at: '2026-11-01T09:45:00Z', updated_at: '2026-11-03T16:00:00Z' },
  { id: 108, category_id: 4, sku: 'CHINSU-CHAI-500G', name: 'Tương ớt Chinsu chai 500g', status: 'INACTIVE', sale_price_vnd: 19500, quantity: 10, stock_version: 1, created_at: '2026-11-01T10:00:00Z', updated_at: '2026-11-06T12:00:00Z' },
];

/**
 * Mutable in-memory store for Mock Mode.
 */
let mockCategories = [...DEFAULT_MOCK_CATEGORIES];
let mockProducts = [...DEFAULT_MOCK_PRODUCTS];

export function resetMockCatalogStore() {
  mockCategories = [...DEFAULT_MOCK_CATEGORIES];
  mockProducts = [...DEFAULT_MOCK_PRODUCTS];
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
 * Unified Product API service / adapter.
 */
export const productsApi = {
  /**
   * Fetch products with pagination and filters.
   * In Mock mode: filters ENTIRE dataset before paginating.
   * In Real mode: calls backend API with validation.
   */
  async getProducts({ isMockMode, page = 1, pageSize = 20, keyword = '', categoryId = '', status = '', stockStatus = '' } = {}) {
    if (shouldRunMock(isMockMode)) {
      // Filter ENTIRE dataset first
      let filtered = [...mockProducts];

      if (keyword.trim()) {
        const kw = keyword.trim().toLowerCase();
        filtered = filtered.filter(
          (p) => p.sku.toLowerCase().includes(kw) || p.name.toLowerCase().includes(kw)
        );
      }

      if (categoryId) {
        filtered = filtered.filter((p) => String(p.category_id) === String(categoryId));
      }

      if (status) {
        filtered = filtered.filter((p) => p.status === status);
      }

      if (stockStatus) {
        filtered = filtered.filter((p) => {
          if (stockStatus === 'OUT_OF_STOCK') return p.quantity <= 0;
          if (stockStatus === 'LOW_STOCK') return p.quantity > 0 && p.quantity <= 5;
          if (stockStatus === 'IN_STOCK') return p.quantity > 5;
          return true;
        });
      }

      const total = filtered.length;
      const offset = (page - 1) * pageSize;
      const pagedItems = filtered.slice(offset, offset + pageSize);

      return {
        items: pagedItems.map(validateProductRead),
        total,
        page,
        page_size: pageSize,
      };
    }

    // Real API mode
    const params = {
      page,
      page_size: pageSize,
    };
    if (keyword.trim()) params.search = keyword.trim();
    if (categoryId) params.category_id = Number(categoryId);
    if (status) params.status = status;

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
   * Create a new product.
   * Initial quantity is always 0.
   */
  async createProduct({ isMockMode, data }) {
    if (shouldRunMock(isMockMode)) {
      const existingSku = mockProducts.find((p) => p.sku.toUpperCase() === data.sku.toUpperCase());
      if (existingSku) {
        const err = new Error(`Mã SKU "${data.sku}" đã tồn tại trong hệ thống.`);
        err.status = 409;
        err.response = { status: 409, data: { message: `Mã SKU "${data.sku}" đã tồn tại.` } };
        throw err;
      }
      const newProduct = {
        id: Date.now(),
        sku: data.sku.trim().toUpperCase(),
        name: data.name.trim(),
        category_id: Number(data.category_id),
        sale_price_vnd: Number(data.sale_price_vnd),
        status: 'ACTIVE',
        quantity: 0,
        stock_version: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      mockProducts.unshift(newProduct);
      return validateProductRead(newProduct);
    }

    const response = await axiosClient.post('/products', data);
    return validateProductRead(response.data);
  },

  /**
   * Update an existing product.
   */
  async updateProduct({ isMockMode, id, data }) {
    if (shouldRunMock(isMockMode)) {
      const idx = mockProducts.findIndex((p) => p.id === id);
      if (idx === -1) {
        const err = new Error('Không tìm thấy sản phẩm.');
        err.status = 404;
        throw err;
      }
      if (data.sku) {
        const duplicate = mockProducts.find((p) => p.sku.toUpperCase() === data.sku.toUpperCase() && p.id !== id);
        if (duplicate) {
          const err = new Error(`Mã SKU "${data.sku}" đã tồn tại.`);
          err.status = 409;
          throw err;
        }
      }
      const updated = {
        ...mockProducts[idx],
        ...(data.sku ? { sku: data.sku.trim().toUpperCase() } : {}),
        ...(data.name ? { name: data.name.trim() } : {}),
        ...(data.category_id ? { category_id: Number(data.category_id) } : {}),
        ...(data.sale_price_vnd ? { sale_price_vnd: Number(data.sale_price_vnd) } : {}),
        updated_at: new Date().toISOString(),
      };
      mockProducts[idx] = updated;
      return validateProductRead(updated);
    }

    const response = await axiosClient.patch(`/products/${id}`, data);
    return validateProductRead(response.data);
  },

  /**
   * Toggle product active/inactive status.
   */
  async updateProductStatus({ isMockMode, id, status }) {
    if (shouldRunMock(isMockMode)) {
      const idx = mockProducts.findIndex((p) => p.id === id);
      if (idx === -1) {
        const err = new Error('Không tìm thấy sản phẩm.');
        err.status = 404;
        throw err;
      }
      mockProducts[idx] = {
        ...mockProducts[idx],
        status,
        updated_at: new Date().toISOString(),
      };
      return validateProductRead(mockProducts[idx]);
    }

    const response = await axiosClient.patch(`/products/${id}/status`, { status });
    return validateProductRead(response.data);
  },

  /**
   * Fetch categories list.
   */
  async getCategories({ isMockMode, page = 1, pageSize = 100 } = {}) {
    if (shouldRunMock(isMockMode)) {
      return {
        items: mockCategories.map(validateCategoryRead),
        total: mockCategories.length,
        page,
        page_size: pageSize,
      };
    }

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
   * Create a new category (Admin only).
   */
  async createCategory({ isMockMode, name }) {
    if (shouldRunMock(isMockMode)) {
      const newCategory = {
        id: Date.now(),
        name: name.trim(),
        status: 'ACTIVE',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      mockCategories.unshift(newCategory);
      return validateCategoryRead(newCategory);
    }

    const response = await axiosClient.post('/categories', { name });
    return validateCategoryRead(response.data);
  },

  /**
   * Update category name (Admin only - PROD-02).
   */
  async updateCategory({ isMockMode, id, name }) {
    if (shouldRunMock(isMockMode)) {
      const idx = mockCategories.findIndex((c) => c.id === id);
      if (idx === -1) throw new Error('Không tìm thấy danh mục.');
      mockCategories[idx] = {
        ...mockCategories[idx],
        name: name.trim(),
        updated_at: new Date().toISOString(),
      };
      return validateCategoryRead(mockCategories[idx]);
    }

    const response = await axiosClient.patch(`/categories/${id}`, { name });
    return validateCategoryRead(response.data);
  },

  /**
   * Toggle category status ACTIVE / INACTIVE (Admin only - PROD-02).
   */
  async updateCategoryStatus({ isMockMode, id, status }) {
    if (shouldRunMock(isMockMode)) {
      const idx = mockCategories.findIndex((c) => c.id === id);
      if (idx === -1) throw new Error('Không tìm thấy danh mục.');
      mockCategories[idx] = {
        ...mockCategories[idx],
        status,
        updated_at: new Date().toISOString(),
      };
      return validateCategoryRead(mockCategories[idx]);
    }

    const response = await axiosClient.patch(`/categories/${id}/status`, { status });
    return validateCategoryRead(response.data);
  },
};
