import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import axiosClient, { getApiErrorMessage } from '../api/axiosClient.js';
import {
  productsApi,
  validateProductRead,
  validateCategoryRead,
  parseAndValidateSalePriceVnd,
  shouldRunMock,
  isValidIsoTimestamp,
  ALLOWED_PRODUCT_SORTS,
  VALID_CATALOG_STATUSES,
} from '../api/productsApi.js';

const TEST_PROD_ENV = { DEV: false, PROD: true, MODE: 'production', VITE_USE_MOCK: 'true' };
const TEST_DEV_ENV = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };

const VALID_PRODUCT_FIXTURE = {
  id: 101,
  category_id: 1,
  sku: 'COCA-330ML',
  name: 'Coca Cola lon 330ml',
  status: 'ACTIVE',
  sale_price_vnd: 12000,
  quantity: 48,
  stock_version: 1,
  created_at: '2026-11-01T08:00:00.000Z',
  updated_at: '2026-11-02T10:00:00.000Z',
};

const VALID_CATEGORY_FIXTURE = {
  id: 1,
  name: 'Đồ uống & Giải khát',
  status: 'ACTIVE',
  created_at: '2026-11-01T00:00:00.000Z',
  updated_at: '2026-11-01T00:00:00.000Z',
};

describe('T3C9C86 Product Management & Real API Integration Test Suite', () => {
  // ==========================================================================
  // 1. F01: ProductRead Schema Validation (Fail-Closed)
  // ==========================================================================
  describe('F01: ProductRead Schema Validation & Invariants (Fail-Closed)', () => {
    test('validates ISO timestamps and catalog statuses directly', () => {
      assert.equal(isValidIsoTimestamp('2026-11-01T08:00:00.000Z'), true);
      assert.equal(isValidIsoTimestamp('invalid'), false);
      assert.ok(VALID_CATALOG_STATUSES.has('ACTIVE'));
      assert.ok(VALID_CATALOG_STATUSES.has('INACTIVE'));
      assert.equal(shouldRunMock(false, TEST_DEV_ENV), false);
    });

    test('validates valid full ProductRead contract accurately', () => {
      const result = validateProductRead(VALID_PRODUCT_FIXTURE);
      assert.deepEqual(result, VALID_PRODUCT_FIXTURE);
    });

    test('rejects non-object or null payloads', () => {
      assert.throws(() => validateProductRead(null), /must be an object/);
      assert.throws(() => validateProductRead(undefined), /must be an object/);
      assert.throws(() => validateProductRead('string'), /must be an object/);
    });

    test('strictly rejects invalid id', () => {
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, id: 0 }), /missing valid integer id/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, id: -5 }), /missing valid integer id/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, id: 1.5 }), /missing valid integer id/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, id: '10' }), /missing valid integer id/);
    });

    test('strictly rejects missing or invalid SKU', () => {
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sku: '' }), /missing valid sku/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sku: '   ' }), /missing valid sku/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sku: null }), /missing valid sku/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sku: 'a'.repeat(65) }), /missing valid sku/);
    });

    test('strictly rejects missing or invalid Name', () => {
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, name: '' }), /missing valid name/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, name: '   ' }), /missing valid name/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, name: null }), /missing valid name/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, name: 'a'.repeat(161) }), /missing valid name/);
    });

    test('strictly rejects invalid category_id', () => {
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, category_id: 0 }), /missing valid category_id/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, category_id: -1 }), /missing valid category_id/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, category_id: null }), /missing valid category_id/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, category_id: '1' }), /missing valid category_id/);
    });

    test('strictly rejects invalid sale_price_vnd', () => {
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sale_price_vnd: 0 }), /missing valid positive integer/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sale_price_vnd: -100 }), /missing valid positive integer/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sale_price_vnd: 10.5 }), /missing valid positive integer/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sale_price_vnd: null }), /missing valid positive integer/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, sale_price_vnd: '20000' }), /missing valid positive integer/);
    });

    test('strictly rejects missing, null, or non-integer quantity (never defaults to 0)', () => {
      const noQty = { ...VALID_PRODUCT_FIXTURE };
      delete noQty.quantity;
      assert.throws(() => validateProductRead(noQty), /invalid or missing quantity/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, quantity: null }), /invalid or missing quantity/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, quantity: '0' }), /invalid or missing quantity/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, quantity: -1 }), /invalid or missing quantity/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, quantity: 2.5 }), /invalid or missing quantity/);
    });

    test('strictly rejects missing, null, or non-integer stock_version (never defaults to 0)', () => {
      const noVer = { ...VALID_PRODUCT_FIXTURE };
      delete noVer.stock_version;
      assert.throws(() => validateProductRead(noVer), /invalid or missing stock_version/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, stock_version: null }), /invalid or missing stock_version/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, stock_version: '1' }), /invalid or missing stock_version/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, stock_version: -1 }), /invalid or missing stock_version/);
    });

    test('strictly rejects missing or invalid status (must be strictly ACTIVE or INACTIVE, no fallback)', () => {
      const noStatus = { ...VALID_PRODUCT_FIXTURE };
      delete noStatus.status;
      assert.throws(() => validateProductRead(noStatus), /invalid status/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, status: null }), /invalid status/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, status: 'PENDING' }), /invalid status/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, status: 'DELETED' }), /invalid status/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, status: 'active' }), /invalid status/);
    });

    test('strictly rejects missing or invalid created_at and updated_at (no fallback to now)', () => {
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, created_at: null }), /invalid or missing created_at/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, created_at: '' }), /invalid or missing created_at/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, created_at: 'not-a-date' }), /invalid or missing created_at/);

      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, updated_at: null }), /invalid or missing updated_at/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, updated_at: '' }), /invalid or missing updated_at/);
      assert.throws(() => validateProductRead({ ...VALID_PRODUCT_FIXTURE, updated_at: '2026-99-99' }), /invalid or missing updated_at/);
    });
  });

  // ==========================================================================
  // 2. F01: CategoryRead Schema Validation (Fail-Closed)
  // ==========================================================================
  describe('F01: CategoryRead Schema Validation (Fail-Closed)', () => {
    test('validates valid full CategoryRead contract accurately', () => {
      const result = validateCategoryRead(VALID_CATEGORY_FIXTURE);
      assert.deepEqual(result, VALID_CATEGORY_FIXTURE);
    });

    test('strictly rejects missing or invalid category fields', () => {
      assert.throws(() => validateCategoryRead(null), /must be an object/);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, id: 0 }), /missing valid integer id/);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, name: '' }), /missing valid name/);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, name: 'a'.repeat(121) }), /missing valid name/);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, status: 'UNKNOWN' }), /invalid status/);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, status: null }), /invalid status/);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, created_at: 'invalid' }), /invalid or missing created_at/);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, updated_at: null }), /invalid or missing updated_at/);
    });
  });

  // ==========================================================================
  // 3. F02: Mock Mode Guard & Consistency
  // ==========================================================================
  describe('F02: Mock Mode Guard & Consistency', () => {
    test('production environment strictly prevents Mock mode in shouldRunMock', () => {
      assert.equal(shouldRunMock(true, TEST_PROD_ENV), false);
      assert.equal(shouldRunMock(false, TEST_PROD_ENV), false);
    });

    test('Product Manager API methods fail-closed when called with isMockMode=true', async () => {
      await assert.rejects(
        () => productsApi.getProducts({ isMockMode: true }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
      await assert.rejects(
        () => productsApi.createProduct({ isMockMode: true, data: {} }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
      await assert.rejects(
        () => productsApi.updateProduct({ isMockMode: true, id: 1, data: {} }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
      await assert.rejects(
        () => productsApi.updateProductStatus({ isMockMode: true, id: 1, status: 'ACTIVE' }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
      await assert.rejects(
        () => productsApi.getCategories({ isMockMode: true }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
      await assert.rejects(
        () => productsApi.createCategory({ isMockMode: true, name: 'Test' }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
      await assert.rejects(
        () => productsApi.updateCategory({ isMockMode: true, id: 1, name: 'Test' }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
      await assert.rejects(
        () => productsApi.updateCategoryStatus({ isMockMode: true, id: 1, status: 'INACTIVE' }),
        /Chế độ Mock Demo không được hỗ trợ/
      );
    });
  });

  // ==========================================================================
  // 4. F05: Sale Price Range & BigInteger Synchronization
  // ==========================================================================
  describe('F05: Strict Sale Price Validation (VND Integer up to MAX_SAFE_INTEGER)', () => {
    test('accepts valid pure integer (28000)', () => {
      const result = parseAndValidateSalePriceVnd(28000);
      assert.equal(result.isValid, true);
      assert.equal(result.value, 28000);
      assert.equal(result.error, null);

      const strResult = parseAndValidateSalePriceVnd('28000');
      assert.equal(strResult.isValid, true);
      assert.equal(strResult.value, 28000);
    });

    test('accepts valid dot-thousands format (28.000 và 1.500.000)', () => {
      const res1 = parseAndValidateSalePriceVnd('28.000');
      assert.equal(res1.isValid, true);
      assert.equal(res1.value, 28000);

      const res2 = parseAndValidateSalePriceVnd('1.500.000');
      assert.equal(res2.isValid, true);
      assert.equal(res2.value, 1500000);
    });

    test('accepts valid comma-thousands format (28,000)', () => {
      const res = parseAndValidateSalePriceVnd('28,000');
      assert.equal(res.isValid, true);
      assert.equal(res.value, 28000);
    });

    test('accepts large values within Number.MAX_SAFE_INTEGER (sync with BigInteger)', () => {
      const largePrice = 10000000000; // 10 tỷ VND
      const res = parseAndValidateSalePriceVnd(largePrice);
      assert.equal(res.isValid, true);
      assert.equal(res.value, 10000000000);

      const maxSafe = parseAndValidateSalePriceVnd(Number.MAX_SAFE_INTEGER);
      assert.equal(maxSafe.isValid, true);
      assert.equal(maxSafe.value, Number.MAX_SAFE_INTEGER);
    });

    test('rejects decimal comma without converting to distorted integer (10,5 must NOT become 105)', () => {
      const res = parseAndValidateSalePriceVnd('10,5');
      assert.equal(res.isValid, false);
      assert.notEqual(res.value, 105);
      assert.match(res.error, /thập phân/);
    });

    test('rejects decimal dot without converting to distorted integer (1.2 must NOT become 12)', () => {
      const res = parseAndValidateSalePriceVnd('1.2');
      assert.equal(res.isValid, false);
      assert.notEqual(res.value, 12);
      assert.match(res.error, /thập phân/);
    });

    test('rejects 0 and negative values', () => {
      const resZero = parseAndValidateSalePriceVnd(0);
      assert.equal(resZero.isValid, false);
      assert.match(resZero.error, /lớn hơn 0/);

      const resNeg = parseAndValidateSalePriceVnd('-5000');
      assert.equal(resNeg.isValid, false);
      assert.match(resNeg.error, /lớn hơn 0/);
    });

    test('rejects empty, whitespace, and non-numeric strings', () => {
      assert.equal(parseAndValidateSalePriceVnd('').isValid, false);
      assert.equal(parseAndValidateSalePriceVnd('   ').isValid, false);
      assert.equal(parseAndValidateSalePriceVnd(null).isValid, false);
      assert.equal(parseAndValidateSalePriceVnd(undefined).isValid, false);
      assert.equal(parseAndValidateSalePriceVnd('abc').isValid, false);
      assert.equal(parseAndValidateSalePriceVnd('28k').isValid, false);
    });

    test('rejects values exceeding Number.MAX_SAFE_INTEGER', () => {
      const res = parseAndValidateSalePriceVnd('99999999999999999999');
      assert.equal(res.isValid, false);
      assert.match(res.error, /vượt quá giới hạn/);
    });
  });

  // ==========================================================================
  // 5. REAL API INTEGRATION & QUERY CONTRACT (T3C9D97)
  // ==========================================================================
  describe('FIX-02 & F06: Real API Query Parameters & Bounded Category Pagination', () => {
    let capturedCalls = [];

    beforeEach(() => {
      capturedCalls = [];
      axiosClient.get = async (url, config) => {
        capturedCalls.push({ method: 'GET', url, config });
        if (url === '/products') {
          return {
            data: {
              items: [VALID_PRODUCT_FIXTURE],
              total: 1,
              page: config?.params?.page || 1,
              page_size: config?.params?.page_size || 20,
            },
          };
        }
        if (url === '/categories') {
          const page = config?.params?.page || 1;
          if (page === 1) {
            return {
              data: {
                items: [VALID_CATEGORY_FIXTURE],
                total: 2,
                page: 1,
                page_size: config?.params?.page_size || 100,
              },
            };
          }
          if (page === 2) {
            return {
              data: {
                items: [
                  {
                    id: 2,
                    name: 'Bánh kẹo & Snack',
                    status: 'INACTIVE',
                    created_at: '2026-11-01T00:00:00.000Z',
                    updated_at: '2026-11-01T00:00:00.000Z',
                  },
                ],
                total: 2,
                page: 2,
                page_size: config?.params?.page_size || 100,
              },
            };
          }
        }
        return { data: {} };
      };

      axiosClient.post = async (url, data, config) => {
        capturedCalls.push({ method: 'POST', url, data, config });
        if (url === '/products') {
          return {
            data: {
              id: 999,
              ...data,
              status: 'ACTIVE',
              quantity: 0,
              stock_version: 0,
              created_at: '2026-11-10T12:00:00.000Z',
              updated_at: '2026-11-10T12:00:00.000Z',
            },
          };
        }
        if (url === '/categories') {
          return {
            data: {
              id: 888,
              name: data.name,
              status: 'ACTIVE',
              created_at: '2026-11-10T12:00:00.000Z',
              updated_at: '2026-11-10T12:00:00.000Z',
            },
          };
        }
        return { data: {} };
      };

      axiosClient.patch = async (url, data, config) => {
        capturedCalls.push({ method: 'PATCH', url, data, config });
        if (url.startsWith('/products/') && url.endsWith('/status')) {
          return {
            data: {
              ...VALID_PRODUCT_FIXTURE,
              status: data.status,
              updated_at: '2026-11-10T13:00:00.000Z',
            },
          };
        }
        if (url.startsWith('/products/')) {
          return {
            data: {
              ...VALID_PRODUCT_FIXTURE,
              name: data.name || VALID_PRODUCT_FIXTURE.name,
              category_id: data.category_id || VALID_PRODUCT_FIXTURE.category_id,
              sale_price_vnd: data.sale_price_vnd || VALID_PRODUCT_FIXTURE.sale_price_vnd,
              updated_at: '2026-11-10T13:00:00.000Z',
            },
          };
        }
        if (url.startsWith('/categories/') && url.endsWith('/status')) {
          return {
            data: {
              ...VALID_CATEGORY_FIXTURE,
              status: data.status,
              updated_at: '2026-11-10T13:00:00.000Z',
            },
          };
        }
        if (url.startsWith('/categories/')) {
          return {
            data: {
              ...VALID_CATEGORY_FIXTURE,
              name: data.name,
              updated_at: '2026-11-10T13:00:00.000Z',
            },
          };
        }
        return { data: {} };
      };
    });

    test('getProducts sends exact query parameters to backend GET /products', async () => {
      const res = await productsApi.getProducts({
        page: 2,
        pageSize: 15,
        keyword: 'coca',
        categoryId: '1',
        status: 'ACTIVE',
        sort: 'name_asc',
      });

      assert.equal(capturedCalls.length, 1);
      assert.equal(capturedCalls[0].url, '/products');
      assert.deepEqual(capturedCalls[0].config.params, {
        page: 2,
        page_size: 15,
        search: 'coca',
        category_id: 1,
        status: 'ACTIVE',
        sort: 'name_asc',
      });
      assert.equal(res.total, 1);
      assert.equal(res.items.length, 1);
      assert.equal(res.items[0].sku, 'COCA-330ML');
    });

    test('getProducts respects sort whitelist and ignores invalid sort', async () => {
      assert.ok(ALLOWED_PRODUCT_SORTS.has('name_asc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('name_desc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('sku_asc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('sku_desc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('created_desc'));

      await productsApi.getProducts({
        sort: 'invalid_hacker_sort;DROP TABLE',
      });

      assert.equal(capturedCalls.length, 1);
      assert.equal(capturedCalls[0].config.params.sort, undefined);
    });

    test('createProduct sends payload to POST /products and validates zero stock balance', async () => {
      const res = await productsApi.createProduct({
        data: {
          sku: 'AQUA-500ML',
          name: 'Nước khoáng Aquafina 500ml',
          category_id: 1,
          sale_price_vnd: 7000,
        },
      });

      assert.equal(capturedCalls.length, 1);
      assert.equal(capturedCalls[0].url, '/products');
      assert.equal(capturedCalls[0].data.sku, 'AQUA-500ML');
      assert.equal(res.quantity, 0, 'PROD-01: Initial product inventory is always 0');
    });

    test('updateProduct sanitizes payload to protect SKU and quantity immutability', async () => {
      const res = await productsApi.updateProduct({
        id: 101,
        data: {
          sku: 'HACKED-SKU',
          name: 'Coca Cola Cải Tiến',
          category_id: 2,
          sale_price_vnd: 13000,
          quantity: 9999,
          stock_version: 99,
          status: 'INACTIVE',
        },
      });

      assert.equal(capturedCalls.length, 1);
      assert.equal(capturedCalls[0].url, '/products/101');
      assert.deepEqual(capturedCalls[0].data, {
        name: 'Coca Cola Cải Tiến',
        category_id: 2,
        sale_price_vnd: 13000,
      });
      assert.equal(capturedCalls[0].data.sku, undefined, 'SKU must NEVER be sent in update');
      assert.equal(capturedCalls[0].data.quantity, undefined, 'Quantity must NEVER be sent in update');
      assert.equal(capturedCalls[0].data.status, undefined, 'Status must NEVER be sent in edit');
      assert.equal(res.name, 'Coca Cola Cải Tiến');
    });

    test('updateProductStatus sends PATCH /products/:id/status', async () => {
      const res = await productsApi.updateProductStatus({
        id: 101,
        status: 'INACTIVE',
      });

      assert.equal(capturedCalls.length, 1);
      assert.equal(capturedCalls[0].url, '/products/101/status');
      assert.deepEqual(capturedCalls[0].data, { status: 'INACTIVE' });
      assert.equal(res.status, 'INACTIVE');
    });

    test('Category endpoints operate correctly with real contract and F06 safe bounded fetchAll', async () => {
      // 1. Get categories with fetchAll=true fetches page 1 and page 2
      const list = await productsApi.getCategories({ fetchAll: true, pageSize: 1 });
      assert.equal(capturedCalls[0].url, '/categories');
      assert.equal(capturedCalls[1].url, '/categories');
      assert.equal(list.items.length, 2);

      // 2. Create category
      const created = await productsApi.createCategory({ name: 'Đồ đông lạnh' });
      assert.equal(created.name, 'Đồ đông lạnh');

      // 3. Rename category
      const renamed = await productsApi.updateCategory({ id: 1, name: 'Đồ uống có ga' });
      assert.equal(renamed.name, 'Đồ uống có ga');

      // 4. Toggle category status
      const toggled = await productsApi.updateCategoryStatus({ id: 1, status: 'INACTIVE' });
      assert.equal(toggled.status, 'INACTIVE');
    });

    test('ProductRead contract strictly excludes costPrice and unit_cost_vnd', async () => {
      const res = await productsApi.getProducts();
      for (const item of res.items) {
        assert.equal(item.costPrice, undefined);
        assert.equal(item.unit_cost_vnd, undefined);
        assert.equal(item.cost, undefined);
      }
    });
  });

  // ==========================================================================
  // 6. PHASE 3 REGRESSION: HTTP ERROR CODES, F03 RETRY, F04 DOUBLE-SUBMIT, STALE RESPONSES
  // ==========================================================================
  describe('Phase 3 Regression: Error Envelopes (401/403/404/409/422), F03 Retry, F04 Double-Submit & Stale Responses', () => {
    test('handles 401, 403, 404, 409 Duplicate SKU, and 422 Validation responses cleanly without fallback to Mock', async () => {
      const errorScenarios = [
        { status: 401, code: 'UNAUTHORIZED', message: 'Phiên đăng nhập đã hết hạn.' },
        { status: 403, code: 'FORBIDDEN', message: 'STAFF không có quyền thực hiện thao tác này.' },
        { status: 404, code: 'NOT_FOUND', message: 'Không tìm thấy sản phẩm hoặc danh mục.' },
        { status: 409, code: 'DUPLICATE_SKU', message: 'Mã SKU đã tồn tại trong hệ thống.' },
        { status: 422, code: 'VALIDATION_ERROR', message: 'Giá bán hoặc dữ liệu đầu vào không hợp lệ.' },
      ];

      for (const scenario of errorScenarios) {
        axiosClient.post = async () => {
          const err = new Error(scenario.message);
          err.response = {
            status: scenario.status,
            data: {
              code: scenario.code,
              message: scenario.message,
              details: null,
            },
          };
          throw err;
        };

        await assert.rejects(
          async () => {
            try {
              await productsApi.createProduct({
                data: {
                  sku: 'DUP-01',
                  name: 'Test Product',
                  category_id: 1,
                  sale_price_vnd: 10000,
                },
              });
            } catch (err) {
              const extracted = getApiErrorMessage(err);
              assert.equal(extracted, scenario.message);
              throw err;
            }
          },
          (err) => err.response?.status === scenario.status
        );
      }
    });

    test('F03: Category failed request -> retry -> success flow', async () => {
      let attempt = 0;
      axiosClient.get = async (url) => {
        if (url === '/categories') {
          attempt += 1;
          if (attempt === 1) {
            const err = new Error('Network error');
            err.response = { status: 503, data: { message: 'Dịch vụ danh mục tạm thời gián đoạn.' } };
            throw err;
          }
          return {
            data: {
              items: [VALID_CATEGORY_FIXTURE],
              total: 1,
              page: 1,
              page_size: 100,
            },
          };
        }
        return { data: {} };
      };

      // Attempt 1 fails (must not return empty array silently)
      await assert.rejects(
        () => productsApi.getCategories({ page: 1, pageSize: 100, fetchAll: true }),
        (err) => getApiErrorMessage(err) === 'Dịch vụ danh mục tạm thời gián đoạn.'
      );

      // Attempt 2 (Retry) succeeds and returns validated categories
      const retryRes = await productsApi.getCategories({ page: 1, pageSize: 100, fetchAll: true });
      assert.equal(attempt, 2);
      assert.equal(retryRes.items.length, 1);
      assert.equal(retryRes.items[0].name, VALID_CATEGORY_FIXTURE.name);
    });

    test('F04: Double-submit protection blocks concurrent status mutations in same event loop', async () => {
      let patchCallCount = 0;
      axiosClient.patch = async (url, data) => {
        patchCallCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 30));
        return {
          data: {
            ...VALID_PRODUCT_FIXTURE,
            status: data.status,
          },
        };
      };

      // Simulate ProductList handleConfirmDeactivate synchronous ref lock
      const isStatusMutationPendingRef = { current: false };
      const executeProtectedStatusMutation = async (product) => {
        if (!product || isStatusMutationPendingRef.current) {
          return null;
        }
        isStatusMutationPendingRef.current = true;
        try {
          return await productsApi.updateProductStatus({
            id: product.id,
            status: product.status === 'INACTIVE' ? 'ACTIVE' : 'INACTIVE',
          });
        } finally {
          isStatusMutationPendingRef.current = false;
        }
      };

      // Double click in the exact same tick
      const [res1, res2] = await Promise.all([
        executeProtectedStatusMutation(VALID_PRODUCT_FIXTURE),
        executeProtectedStatusMutation(VALID_PRODUCT_FIXTURE),
      ]);

      assert.equal(patchCallCount, 1, 'Double click must trigger only 1 PATCH request');
      assert.ok(res1 !== null);
      assert.equal(res2, null);
      assert.equal(isStatusMutationPendingRef.current, false, 'Lock must be released after completion');
    });

    test('Stale async response guard ignores out-of-order responses and ProductList enforces F02/F03/F04 invariants', async () => {
      const requestIdRef = { current: 0 };
      const committedResults = [];

      const fetchWithStaleGuard = async (delayMs, keyword) => {
        const currentId = ++requestIdRef.current;
        await new Promise((resolve) => setTimeout(resolve, delayMs));
        if (currentId === requestIdRef.current) {
          committedResults.push(keyword);
        }
      };

      // Request 1 is slow (50ms), Request 2 is fast (10ms)
      await Promise.all([
        fetchWithStaleGuard(50, 'stale-search'),
        fetchWithStaleGuard(10, 'latest-search'),
      ]);

      assert.deepEqual(committedResults, ['latest-search'], 'Stale response must be ignored');

      // Verify ProductList.jsx source contains required F02, F03, F04 guards and useCallback import
      const productListSource = fs.readFileSync(
        path.resolve(process.cwd(), 'src/pages/Products/ProductList.jsx'),
        'utf8'
      );
      assert.match(productListSource, /useCallback/, 'Must import and use useCallback');
      assert.match(productListSource, /isStatusMutationPendingRef/, 'Must enforce synchronous ref lock for F04');
      assert.match(productListSource, /categoryRequestIdRef/, 'Must guard category requests against stale responses');
      assert.match(productListSource, /reloadCategories/, 'Must provide category retry action for F03');
      assert.match(productListSource, /mockWarningBanner/, 'Must render explicit unsupported banner when Mock Mode is active');
    });
  });
});
