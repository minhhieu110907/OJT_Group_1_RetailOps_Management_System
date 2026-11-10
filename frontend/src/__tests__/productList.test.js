import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  productsApi,
  validateProductRead,
  validateCategoryRead,
  resetMockCatalogStore,
  shouldRunMock,
  parseAndValidateSalePriceVnd,
  ALLOWED_PRODUCT_SORTS,
} from '../api/productsApi.js';

const TEST_DEV_MOCK_ENV = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };
const TEST_PROD_ENV = { DEV: false, PROD: true, MODE: 'production', VITE_USE_MOCK: 'true' };

describe('T3C9C86 Product Management & API Strategy Test Suite', () => {
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
        // quantity is undefined
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
  // 2. CRITICAL BUG REGRESSION: Mock Mode Environment Isolation
  // ==========================================================================
  describe('CRITICAL: Mock Mode Isolation & Environment Guard', () => {
    test('production environment strictly prevents Mock mode even with explicit isMockMode=true', () => {
      // Production must NEVER allow mock mode, regardless of explicitFlag
      assert.equal(shouldRunMock(true, TEST_PROD_ENV), false);
      assert.equal(shouldRunMock(false, TEST_PROD_ENV), false);
      assert.equal(shouldRunMock(undefined, TEST_PROD_ENV), false);
    });

    test('development without VITE_USE_MOCK="true" strictly prevents Mock mode', () => {
      const devNoMock = { DEV: true, PROD: false, VITE_USE_MOCK: 'false' };
      assert.equal(shouldRunMock(true, devNoMock), false);
      assert.equal(shouldRunMock(undefined, devNoMock), false);
    });

    test('development with VITE_USE_MOCK="true" honors explicit flag and global state', () => {
      assert.equal(shouldRunMock(true, TEST_DEV_MOCK_ENV), true);
      assert.equal(shouldRunMock(false, TEST_DEV_MOCK_ENV), false);
    });
  });

  // ==========================================================================
  // 3. SALE PRICE VALIDATION: parseAndValidateSalePriceVnd
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
  // 4. MOCK DATA OPERATIONS & DATASET FILTERING
  // ==========================================================================
  describe('FIX-02: Real vs Mock Strategy & Full Dataset Filtering', () => {
    test('Mock Mode filters across entire dataset before paginating (keyword & category)', async () => {
      resetMockCatalogStore();

      // Search for Coca Cola across all pages
      const res = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        page: 1,
        pageSize: 5,
        keyword: 'COCA',
      });

      assert.equal(res.total, 1);
      assert.equal(res.items.length, 1);
      assert.equal(res.items[0].sku, 'COCA-330ML');
      assert.equal(res.page, 1);
    });

    test('Mock Mode sorts correctly across whitelisted sort criteria', async () => {
      resetMockCatalogStore();

      // Verify sort whitelist
      assert.ok(ALLOWED_PRODUCT_SORTS.has('name_asc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('name_desc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('sku_asc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('sku_desc'));
      assert.ok(ALLOWED_PRODUCT_SORTS.has('created_desc'));

      const resAsc = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        sort: 'name_asc',
      });
      for (let i = 0; i < resAsc.items.length - 1; i++) {
        assert.ok(resAsc.items[i].name.localeCompare(resAsc.items[i + 1].name, 'vi') <= 0);
      }
    });

    test('Mock Mode mutations actually create and mutate data in mock store', async () => {
      resetMockCatalogStore();

      // Create product in mock store
      const created = await productsApi.createProduct({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        data: {
          sku: 'NEW-ITEM-001',
          name: 'Nước ép cam tươi',
          category_id: 1,
          sale_price_vnd: 25000,
        },
      });

      assert.equal(created.sku, 'NEW-ITEM-001');
      assert.equal(created.quantity, 0, 'PROD-01: Newly created product must start with 0 quantity');

      // Verify that query returns the newly created item
      const listRes = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        keyword: 'NEW-ITEM-001',
      });
      assert.equal(listRes.total, 1);
      assert.equal(listRes.items[0].sku, 'NEW-ITEM-001');

      // Update product status in mock store
      const toggled = await productsApi.updateProductStatus({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        id: created.id,
        status: 'INACTIVE',
      });
      assert.equal(toggled.status, 'INACTIVE');

      // Update product master fields (PROD-01: does not alter stock or sku)
      const updated = await productsApi.updateProduct({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        id: created.id,
        data: {
          name: 'Nước ép cam tươi nguyên chất',
          category_id: 1,
          sale_price_vnd: 28000,
        },
      });
      assert.equal(updated.name, 'Nước ép cam tươi nguyên chất');
      assert.equal(updated.sale_price_vnd, 28000);
      assert.equal(updated.quantity, 0, 'PROD-01: Product update must never alter stock quantity');
      assert.equal(updated.sku, 'NEW-ITEM-001', 'SKU must remain immutable during product edit');
    });

    test('Mock Mode prevents duplicate SKU creation with 409 error', async () => {
      resetMockCatalogStore();

      await assert.rejects(
        async () => {
          await productsApi.createProduct({
            isMockMode: true,
            runtimeEnv: TEST_DEV_MOCK_ENV,
            data: {
              sku: 'COCA-330ML', // Already exists in mock store
              name: 'Trùng SKU',
              category_id: 1,
              sale_price_vnd: 10000,
            },
          });
        },
        (err) => err.status === 409
      );
    });

    test('Filter Bar: filters accurately by keyword, category, status, and reset', async () => {
      resetMockCatalogStore();

      // 1. Keyword search (case-insensitive and trimmed)
      const keywordRes = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        keyword: '  pepsi  ',
      });
      assert.equal(keywordRes.total, 1);
      assert.equal(keywordRes.items[0].sku, 'PEPSI-330ML');

      // 2. Filter by Category (Category 1: Đồ uống)
      const catRes = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        categoryId: 1,
      });
      assert.equal(catRes.total, 3);
      assert.ok(catRes.items.every((p) => p.category_id === 1));

      // 3. Filter by Status INACTIVE
      const inactiveRes = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        status: 'INACTIVE',
      });
      assert.equal(inactiveRes.total, 1);
      assert.equal(inactiveRes.items[0].sku, 'CHINSU-CHAI-500G');

      // 4. Combined Filter: Category 1 + Status ACTIVE
      const combinedRes = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        categoryId: 1,
        status: 'ACTIVE',
      });
      assert.equal(combinedRes.total, 3);
      assert.ok(combinedRes.items.every((p) => p.category_id === 1 && p.status === 'ACTIVE'));

      // 5. Keyword search with no matches
      const noMatchRes = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        keyword: 'NON_EXISTENT_PRODUCT_XYZ',
      });
      assert.equal(noMatchRes.total, 0);
      assert.equal(noMatchRes.items.length, 0);

      // 6. Reset filters (all empty) returns all default products
      const resetRes = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        keyword: '',
        categoryId: '',
        status: '',
      });
      assert.equal(resetRes.total, 8);
      assert.equal(resetRes.items.length, 8);
    });
  });

  // ==========================================================================
  // 5. FIX-03: PROD-02 Category Management in Adapter
  // ==========================================================================
  describe('FIX-03: PROD-02 Category Management in Adapter', () => {
    test('supports Category create, rename, and status toggle in adapter', async () => {
      resetMockCatalogStore();

      // Create category
      const newCat = await productsApi.createCategory({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        name: 'Hàng đông lạnh',
      });
      assert.equal(newCat.name, 'Hàng đông lạnh');
      assert.equal(newCat.status, 'ACTIVE');

      // Rename category
      const renamed = await productsApi.updateCategory({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        id: newCat.id,
        name: 'Thực phẩm đông lạnh',
      });
      assert.equal(renamed.name, 'Thực phẩm đông lạnh');

      // Toggle status to INACTIVE
      const inactive = await productsApi.updateCategoryStatus({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
        id: newCat.id,
        status: 'INACTIVE',
      });
      assert.equal(inactive.status, 'INACTIVE');
    });
  });

  // ==========================================================================
  // 6. FIX-04: RBAC & Codebase Security Invariants
  // ==========================================================================
  describe('FIX-04: RBAC & Codebase Security Invariants', () => {
    test('ProductRead never contains costPrice or unit_cost_vnd', async () => {
      resetMockCatalogStore();
      const res = await productsApi.getProducts({
        isMockMode: true,
        runtimeEnv: TEST_DEV_MOCK_ENV,
      });
      for (const item of res.items) {
        assert.equal(item.costPrice, undefined);
        assert.equal(item.unit_cost_vnd, undefined);
        assert.equal(item.cost, undefined);
      }
    });
  });
});
