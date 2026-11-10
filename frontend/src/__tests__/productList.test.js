import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  productsApi,
  validateProductRead,
  validateCategoryRead,
  resetMockCatalogStore,
} from '../api/productsApi.js';

describe('T3C9C86 Product Management & API Strategy Test Suite', () => {
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

  describe('FIX-02: Real vs Mock Strategy & Full Dataset Filtering', () => {
    test('Mock Mode filters across entire dataset before paginating (keyword & category)', async () => {
      resetMockCatalogStore();

      // Search for Coca Cola across all pages
      const res = await productsApi.getProducts({
        isMockMode: true,
        page: 1,
        pageSize: 5,
        keyword: 'COCA',
      });

      assert.equal(res.total, 1);
      assert.equal(res.items.length, 1);
      assert.equal(res.items[0].sku, 'COCA-330ML');
      assert.equal(res.page, 1);
    });

    test('Mock Mode filters by stock status across all items', async () => {
      resetMockCatalogStore();

      const outOfStock = await productsApi.getProducts({
        isMockMode: true,
        page: 1,
        pageSize: 10,
        stockStatus: 'OUT_OF_STOCK',
      });

      assert.ok(outOfStock.total >= 1);
      assert.ok(outOfStock.items.every((item) => item.quantity <= 0));

      const lowStock = await productsApi.getProducts({
        isMockMode: true,
        page: 1,
        pageSize: 10,
        stockStatus: 'LOW_STOCK',
      });
      assert.ok(lowStock.items.every((item) => item.quantity > 0 && item.quantity <= 5));
    });

    test('Mock Mode mutations actually create and mutate data in mock store', async () => {
      resetMockCatalogStore();

      // Create product in mock store
      const created = await productsApi.createProduct({
        isMockMode: true,
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
        keyword: 'NEW-ITEM-001',
      });
      assert.equal(listRes.total, 1);
      assert.equal(listRes.items[0].sku, 'NEW-ITEM-001');

      // Update product status in mock store
      const toggled = await productsApi.updateProductStatus({
        isMockMode: true,
        id: created.id,
        status: 'INACTIVE',
      });
      assert.equal(toggled.status, 'INACTIVE');
    });

    test('Mock Mode prevents duplicate SKU creation with 409 error', async () => {
      resetMockCatalogStore();

      await assert.rejects(
        async () => {
          await productsApi.createProduct({
            isMockMode: true,
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
        keyword: '  pepsi  ',
      });
      assert.equal(keywordRes.total, 1);
      assert.equal(keywordRes.items[0].sku, 'PEPSI-330ML');

      // 2. Filter by Category (Category 1: Đồ uống)
      const catRes = await productsApi.getProducts({
        isMockMode: true,
        categoryId: 1,
      });
      assert.equal(catRes.total, 3);
      assert.ok(catRes.items.every((p) => p.category_id === 1));

      // 3. Filter by Status INACTIVE
      const inactiveRes = await productsApi.getProducts({
        isMockMode: true,
        status: 'INACTIVE',
      });
      assert.equal(inactiveRes.total, 1);
      assert.equal(inactiveRes.items[0].sku, 'CHINSU-CHAI-500G');

      // 4. Combined Filter: Category 1 + Status ACTIVE
      const combinedRes = await productsApi.getProducts({
        isMockMode: true,
        categoryId: 1,
        status: 'ACTIVE',
      });
      assert.equal(combinedRes.total, 3);
      assert.ok(combinedRes.items.every((p) => p.category_id === 1 && p.status === 'ACTIVE'));

      // 5. Keyword search with no matches
      const noMatchRes = await productsApi.getProducts({
        isMockMode: true,
        keyword: 'NON_EXISTENT_PRODUCT_XYZ',
      });
      assert.equal(noMatchRes.total, 0);
      assert.equal(noMatchRes.items.length, 0);

      // 6. Reset filters (all empty) returns all default products
      const resetRes = await productsApi.getProducts({
        isMockMode: true,
        keyword: '',
        categoryId: '',
        status: '',
      });
      assert.equal(resetRes.total, 8);
      assert.equal(resetRes.items.length, 8);
    });
  });

  describe('FIX-03: PROD-02 Category Management in Adapter', () => {
    test('supports Category create, rename, and status toggle in adapter', async () => {
      resetMockCatalogStore();

      // Create category
      const newCat = await productsApi.createCategory({
        isMockMode: true,
        name: 'Hàng đông lạnh',
      });
      assert.equal(newCat.name, 'Hàng đông lạnh');
      assert.equal(newCat.status, 'ACTIVE');

      // Rename category
      const renamed = await productsApi.updateCategory({
        isMockMode: true,
        id: newCat.id,
        name: 'Thực phẩm đông lạnh',
      });
      assert.equal(renamed.name, 'Thực phẩm đông lạnh');

      // Toggle status to INACTIVE
      const inactive = await productsApi.updateCategoryStatus({
        isMockMode: true,
        id: newCat.id,
        status: 'INACTIVE',
      });
      assert.equal(inactive.status, 'INACTIVE');
    });
  });

  describe('FIX-04: RBAC & Codebase Security Invariants', () => {
    test('ProductRead never contains costPrice or unit_cost_vnd', async () => {
      resetMockCatalogStore();
      const res = await productsApi.getProducts({ isMockMode: true });
      for (const item of res.items) {
        assert.equal(item.costPrice, undefined);
        assert.equal(item.unit_cost_vnd, undefined);
        assert.equal(item.cost, undefined);
      }
    });
  });
});

