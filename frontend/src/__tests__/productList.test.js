import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import axiosClient from '../api/axiosClient.js';
import {
  productsApi,
  validateProductRead,
  validateCategoryRead,
  parseAndValidateSalePriceVnd,
  ALLOWED_PRODUCT_SORTS,
} from '../api/productsApi.js';

describe('T3C9C86 Product Management & Real API Integration Test Suite', () => {
  // ==========================================================================
  // 1. FIX-01: ProductRead Schema Validation & Quantity Invariant
  // ==========================================================================
  describe('FIX-01: ProductRead Schema Validation & Quantity Invariant', () => {
    test('strictly rejects payloads with missing or non-numeric quantity (never defaults to 0)', () => {
      const missingQuantity = {
        id: 1,
        sku: 'TEST-SKU',
        name: 'Sản phẩm lỗi',
        category_id: 1,
        sale_price_vnd: 20000,
      };

      assert.throws(
        () => validateProductRead(missingQuantity),
        /invalid or missing quantity/,
        'Should throw schema violation when quantity is missing'
      );

      const nullQuantity = {
        ...missingQuantity,
        quantity: null,
      };
      assert.throws(
        () => validateProductRead(nullQuantity),
        /invalid or missing quantity/,
        'Should throw schema violation when quantity is null'
      );

      const stringQuantity = {
        ...missingQuantity,
        quantity: '5',
      };
      assert.throws(
        () => validateProductRead(stringQuantity),
        /invalid or missing quantity/,
        'Should throw schema violation when quantity is string instead of integer'
      );
    });

    test('validates valid ProductRead payload correctly', () => {
      const valid = {
        id: 10,
        sku: 'VALID-01',
        name: 'Trà Chanh',
        category_id: 2,
        sale_price_vnd: 15000,
        quantity: 0,
        stock_version: 0,
      };
      const result = validateProductRead(valid);
      assert.equal(result.id, 10);
      assert.equal(result.quantity, 0);
      assert.equal(result.status, 'ACTIVE');
    });

    test('validates CategoryRead payload correctly', () => {
      assert.throws(() => validateCategoryRead({}), /missing valid id/);
      assert.throws(() => validateCategoryRead({ id: 1, name: '' }), /missing valid name/);
      const validCat = validateCategoryRead({ id: 1, name: 'Bánh kẹo', status: 'ACTIVE' });
      assert.equal(validCat.name, 'Bánh kẹo');
      assert.equal(validCat.status, 'ACTIVE');
    });
  });

  // ==========================================================================
  // 2. SALE PRICE VALIDATION: parseAndValidateSalePriceVnd
  // ==========================================================================
  describe('FIX-04: Strict Sale Price Validation (VND Integer)', () => {
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

    test('rejects values exceeding 32-bit integer limit (2,147,483,647)', () => {
      const res = parseAndValidateSalePriceVnd('99999999999999999999');
      assert.equal(res.isValid, false);
      assert.match(res.error, /vượt quá giới hạn/);
    });
  });

  // ==========================================================================
  // 3. REAL API INTEGRATION & QUERY CONTRACT (T3C9D97)
  // ==========================================================================
  describe('FIX-02: Real API Query Parameters & Contract Integration', () => {
    let capturedCalls = [];

    beforeEach(() => {
      capturedCalls = [];
      axiosClient.get = async (url, config) => {
        capturedCalls.push({ method: 'GET', url, config });
        if (url === '/products') {
          return {
            data: {
              items: [
                {
                  id: 101,
                  category_id: 1,
                  sku: 'COCA-330ML',
                  name: 'Coca Cola 330ml',
                  sale_price_vnd: 12000,
                  quantity: 48,
                  stock_version: 1,
                  status: 'ACTIVE',
                },
              ],
              total: 1,
              page: config?.params?.page || 1,
              page_size: config?.params?.page_size || 20,
            },
          };
        }
        if (url === '/categories') {
          return {
            data: {
              items: [
                { id: 1, name: 'Đồ uống', status: 'ACTIVE' },
                { id: 2, name: 'Bánh kẹo', status: 'INACTIVE' },
              ],
              total: 2,
              page: 1,
              page_size: 100,
            },
          };
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
            },
          };
        }
        if (url === '/categories') {
          return {
            data: {
              id: 888,
              name: data.name,
              status: 'ACTIVE',
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
              id: 101,
              category_id: 1,
              sku: 'COCA-330ML',
              name: 'Coca Cola 330ml',
              sale_price_vnd: 12000,
              quantity: 48,
              stock_version: 2,
              status: data.status,
            },
          };
        }
        if (url.startsWith('/products/')) {
          return {
            data: {
              id: 101,
              category_id: data.category_id || 1,
              sku: 'COCA-330ML',
              name: data.name || 'Coca Cola 330ml',
              sale_price_vnd: data.sale_price_vnd || 12000,
              quantity: 48,
              stock_version: 2,
              status: 'ACTIVE',
            },
          };
        }
        if (url.startsWith('/categories/') && url.endsWith('/status')) {
          return {
            data: {
              id: 1,
              name: 'Đồ uống',
              status: data.status,
            },
          };
        }
        if (url.startsWith('/categories/')) {
          return {
            data: {
              id: 1,
              name: data.name,
              status: 'ACTIVE',
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
      // sort must be omitted if not in whitelist
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

    test('Category endpoints operate correctly with real contract (PROD-02)', async () => {
      // 1. Get categories
      const list = await productsApi.getCategories();
      assert.equal(capturedCalls[0].url, '/categories');
      assert.equal(list.items.length, 2);

      // 2. Create category
      const created = await productsApi.createCategory({ name: 'Đồ đông lạnh' });
      assert.equal(capturedCalls[1].url, '/categories');
      assert.deepEqual(capturedCalls[1].data, { name: 'Đồ đông lạnh' });
      assert.equal(created.name, 'Đồ đông lạnh');

      // 3. Rename category
      const renamed = await productsApi.updateCategory({ id: 1, name: 'Đồ uống có ga' });
      assert.equal(capturedCalls[2].url, '/categories/1');
      assert.deepEqual(capturedCalls[2].data, { name: 'Đồ uống có ga' });
      assert.equal(renamed.name, 'Đồ uống có ga');

      // 4. Toggle category status
      const toggled = await productsApi.updateCategoryStatus({ id: 1, status: 'INACTIVE' });
      assert.equal(capturedCalls[3].url, '/categories/1/status');
      assert.deepEqual(capturedCalls[3].data, { status: 'INACTIVE' });
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
});
