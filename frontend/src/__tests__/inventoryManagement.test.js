import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient from '../api/axiosClient.js';
import {
  MAX_STOCK_QUANTITY,
  classifyStockLevel,
  formatReferenceCode,
  formatVietnamDateTime,
  generateSecureIdempotencyKey,
  inventoryApi,
} from '../api/inventoryApi.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const inventoryListPath = path.resolve(__dirname, '../pages/Inventory/InventoryList.jsx');
const adjustModalPath = path.resolve(__dirname, '../pages/Inventory/InventoryAdjustModal.jsx');
const movementListPath = path.resolve(__dirname, '../pages/Inventory/StockMovementList.jsx');

describe('T04A89D Inventory & Storage Management Regression Suite', () => {
  beforeEach(() => {
    // Reset any Axios interceptors or test spies if needed
  });

  // =========================================================================
  // WORKSTREAM 1 — API CONTRACT & REASONABLE BOUNDS
  // =========================================================================
  describe('API Contracts, Parameters and Fail-Closed Validation', () => {
    test('getInventory forwards page, pageSize, categoryId, status and inStock correctly to GET /inventory', async () => {
      let capturedConfig = null;
      const originalGet = axiosClient.get;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return {
          data: {
            items: [{ product_id: 1, sku: 'SP01', name: 'Sản phẩm 1', quantity: 10, stock_version: 1 }],
            total: 1,
            page: 2,
            page_size: 15,
          },
        };
      };

      try {
        const res = await inventoryApi.getInventory({
          page: 2,
          pageSize: 15,
          categoryId: 5,
          status: 'ACTIVE',
          inStock: true,
        });

        assert.equal(capturedConfig.url, '/inventory');
        assert.deepEqual(capturedConfig.config.params, {
          page: 2,
          page_size: 15,
          category_id: 5,
          status: 'ACTIVE',
          in_stock: true,
        });
        assert.equal(res.total, 1);
        assert.equal(res.items.length, 1);
      } finally {
        axiosClient.get = originalGet;
      }
    });

    test('getLowStock sends page and pageSize to GET /inventory/low-stock', async () => {
      let capturedConfig = null;
      const originalGet = axiosClient.get;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return { data: { items: [], total: 3, page: 1, page_size: 1 } };
      };

      try {
        const res = await inventoryApi.getLowStock({ page: 1, pageSize: 1 });
        assert.equal(capturedConfig.url, '/inventory/low-stock');
        assert.deepEqual(capturedConfig.config.params, { page: 1, page_size: 1 });
        assert.equal(res.total, 3);
      } finally {
        axiosClient.get = originalGet;
      }
    });

    test('getStockMovements forwards page, pageSize, productId and kind to GET /stock-movements', async () => {
      let capturedConfig = null;
      const originalGet = axiosClient.get;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return { data: { items: [], total: 0, page: 1, page_size: 20 } };
      };

      try {
        await inventoryApi.getStockMovements({ page: 1, pageSize: 20, kind: 'SALE', productId: 10 });
        assert.equal(capturedConfig.url, '/stock-movements');
        assert.deepEqual(capturedConfig.config.params, { page: 1, page_size: 20, kind: 'SALE', product_id: 10 });
      } finally {
        axiosClient.get = originalGet;
      }
    });

    test('adjustInventory sends correct AdjustRequest body with Idempotency-Key and guards bounds', async () => {
      let capturedCall = null;
      const originalPost = axiosClient.post;
      axiosClient.post = async (url, body, config) => {
        capturedCall = { url, body, config };
        return { data: { product_id: 2, quantity: 20, stock_version: 3, audit_id: 101, movement_created: true } };
      };

      try {
        const customKey = 'a0000000-0000-4000-8000-000000000001';
        const res = await inventoryApi.adjustInventory({
          productId: 2,
          countedQuantity: 20,
          expectedStockVersion: 2,
          reason: 'Kiểm kê định kỳ phát hiện dư hàng trên kệ thực tế',
          idempotencyKey: customKey,
        });

        assert.equal(capturedCall.url, '/inventory/2/adjustments');
        assert.equal(capturedCall.body.counted_quantity, 20);
        assert.equal(capturedCall.body.expected_stock_version, 2);
        assert.equal(capturedCall.body.reason, 'Kiểm kê định kỳ phát hiện dư hàng trên kệ thực tế');
        assert.equal(capturedCall.config.headers['Idempotency-Key'], customKey);
        assert.equal(res.quantity, 20);
      } finally {
        axiosClient.post = originalPost;
      }
    });

    test('adjustInventory rejects negative quantity, over-max quantity, invalid version, and empty reason', async () => {
      await assert.rejects(
        () => inventoryApi.adjustInventory({ productId: 1, countedQuantity: -1, expectedStockVersion: 1, reason: 'Valid reason' }),
        /Số lượng kiểm kê thực tế phải là số nguyên từ 0/
      );
      await assert.rejects(
        () => inventoryApi.adjustInventory({ productId: 1, countedQuantity: MAX_STOCK_QUANTITY + 1, expectedStockVersion: 1, reason: 'Valid reason' }),
        /Số lượng kiểm kê thực tế phải là số nguyên từ 0/
      );
      await assert.rejects(
        () => inventoryApi.adjustInventory({ productId: 1, countedQuantity: 10, expectedStockVersion: -1, reason: 'Valid reason' }),
        /Phiên bản tồn kho không hợp lệ/
      );
      await assert.rejects(
        () => inventoryApi.adjustInventory({ productId: 1, countedQuantity: 10, expectedStockVersion: 0, reason: '   ' }),
        /Lý do điều chỉnh không được để trống/
      );
    });

    test('generateSecureIdempotencyKey generates cryptographically random UUID v4 without Math.random', () => {
      const key1 = generateSecureIdempotencyKey();
      const key2 = generateSecureIdempotencyKey();
      assert.notEqual(key1, key2);
      // Valid RFC4122 UUID v4 regex
      const uuidV4Regex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
      assert.ok(uuidV4Regex.test(key1), `Generated key ${key1} must match UUID v4 format`);
      assert.ok(uuidV4Regex.test(key2), `Generated key ${key2} must match UUID v4 format`);
    });
  });

  // =========================================================================
  // WORKSTREAM 2 — KPI SEMANTICS & NO FAKE STATS
  // =========================================================================
  describe('Global KPI Counts & Classification Semantics (INV-01 / INV-04)', () => {
    test('classifyStockLevel correctly marks ACTIVE status with NORMAL, LOW, OUT_OF_STOCK and INACTIVE', () => {
      // ACTIVE with quantity 0 -> OUT_OF_STOCK
      assert.equal(classifyStockLevel(0, 'ACTIVE').code, 'OUT_OF_STOCK');
      // ACTIVE with quantity 1..5 -> LOW
      assert.equal(classifyStockLevel(1, 'ACTIVE').code, 'LOW');
      assert.equal(classifyStockLevel(5, 'ACTIVE').code, 'LOW');
      // ACTIVE with quantity > 5 -> NORMAL
      assert.equal(classifyStockLevel(6, 'ACTIVE').code, 'NORMAL');
      // INACTIVE with quantity 0 or > 0 -> INACTIVE (Never in low-stock / out-of-stock warning)
      assert.equal(classifyStockLevel(0, 'INACTIVE').code, 'INACTIVE');
      assert.equal(classifyStockLevel(10, 'INACTIVE').code, 'INACTIVE');
    });

    test('InventoryList source verifies Global KPIs are fetched via server total queries instead of current page filter', () => {
      const source = fs.readFileSync(inventoryListPath, 'utf8');
      // Must not calculate KPI from inventoryItems.filter(...)
      assert.ok(
        !source.includes('inventoryItems.filter((i) => i.status ==='),
        'InventoryList must not calculate active or out-of-stock KPIs from current page inventoryItems'
      );
      // Must fetch KPIs using authoritative total endpoints
      assert.ok(source.includes('loadKpiStats'), 'InventoryList must define loadKpiStats function');
      assert.ok(source.includes('kpiStats.totalProducts'), 'InventoryList must bind totalProducts from kpiStats');
      assert.ok(source.includes('kpiStats.activeProducts'), 'InventoryList must bind activeProducts from kpiStats');
      assert.ok(source.includes('kpiStats.lowStock'), 'InventoryList must bind lowStock from kpiStats');
      assert.ok(source.includes('kpiStats.outOfStock'), 'InventoryList must bind outOfStock from kpiStats');
    });

    test('InventoryList source verifies inactive search input has been removed completely', () => {
      const source = fs.readFileSync(inventoryListPath, 'utf8');
      assert.ok(!source.includes('searchKeyword'), 'InventoryList must not contain fake searchKeyword state');
      assert.ok(!source.includes('placeholder="Tìm theo tên sản phẩm, mã SKU..."'), 'Non-functional search input must be removed');
    });
  });

  // =========================================================================
  // WORKSTREAM 3 — ADJUSTMENT SAFETY, NO-OP & 409 CONFLICT
  // =========================================================================
  describe('Inventory Adjustment Safety (INV-02 / Concurrency)', () => {
    test('InventoryAdjustModal source verifies No-Op does not dispatch POST and informs user', () => {
      const source = fs.readFileSync(adjustModalPath, 'utf8');
      assert.ok(
        source.includes('if (delta === 0)'),
        'InventoryAdjustModal must guard against delta === 0'
      );
      assert.ok(
        source.includes('toast.info(') && source.includes('Số đếm trùng với tồn kho đang hiển thị'),
        'InventoryAdjustModal must toast info and return without sending POST on delta === 0'
      );
    });

    test('InventoryAdjustModal source verifies STALE_STOCK_VERSION strict check', () => {
      const source = fs.readFileSync(adjustModalPath, 'utf8');
      assert.ok(
        source.includes("errCode === 'STALE_STOCK_VERSION'"),
        'InventoryAdjustModal must strictly check error code STALE_STOCK_VERSION'
      );
      assert.ok(
        !source.includes('currentVersion + 1'),
        'InventoryAdjustModal must not guess actual server version using currentVersion + 1'
      );
      assert.ok(
        !source.includes('formatNow()') && !source.includes('Nhà cung cấp: Hệ thống'),
        'InventoryAdjustModal must not display fake server timestamps or fake suppliers'
      );
    });

    test('InventoryAdjustModal source verifies Draft preservation on reload and product identity tracking', () => {
      const source = fs.readFileSync(adjustModalPath, 'utf8');
      assert.ok(
        source.includes('lastOpenedProductIdRef'),
        'InventoryAdjustModal must track product ID ref to preserve draft during reload of same product'
      );
      assert.ok(
        source.includes('handleReloadLatest'),
        'InventoryAdjustModal must define handleReloadLatest function'
      );
      assert.ok(
        source.includes('isSubmittingSyncRef'),
        'InventoryAdjustModal must have synchronous guard against double submission'
      );
    });
  });

  // =========================================================================
  // WORKSTREAM 4 — STOCK MOVEMENT AUDIT & TIMEZONE INTEGRITY
  // =========================================================================
  describe('Stock Movement History (INV-03 / RBAC / Timezone)', () => {
    test('formatReferenceCode maps official document prefixes with genuine referenceId without fake dates', () => {
      assert.equal(formatReferenceCode('SALE', 108), 'HĐ-108');
      assert.equal(formatReferenceCode('ORDER_CANCEL', 205), 'HỦY-HĐ-205');
      assert.equal(formatReferenceCode('PURCHASE_CONFIRM', 45), 'PN-45');
      assert.equal(formatReferenceCode('ADJUSTMENT', 9), 'KK-9');
      assert.equal(formatReferenceCode('UNKNOWN', 99), '#99');
      assert.equal(formatReferenceCode('SALE', null), '-');
    });

    test('formatVietnamDateTime formats UTC ISO string to Asia/Ho_Chi_Minh timezone correctly', () => {
      // 2026-11-15 14:30:00 UTC -> 21:30:00 GMT+7 (Asia/Ho_Chi_Minh)
      const formatted = formatVietnamDateTime('2026-11-15T14:30:00Z');
      assert.equal(formatted, '15/11/2026 21:30:00');

      // Invalid or null returns '-'
      assert.equal(formatVietnamDateTime(null), '-');
      assert.equal(formatVietnamDateTime(''), '-');
    });

    test('StockMovementList source verifies non-functional search and time filters are removed', () => {
      const source = fs.readFileSync(movementListPath, 'utf8');
      assert.ok(!source.includes('selectedTimeFilter'), 'StockMovementList must not retain fake selectedTimeFilter state');
      assert.ok(!source.includes('searchKeyword'), 'StockMovementList must not retain fake searchKeyword state');
    });

    test('StockMovementList source verifies RBAC session guard closes reason modal on role switch', () => {
      const source = fs.readFileSync(movementListPath, 'utf8');
      assert.ok(
        source.includes('if (!isAdmin) {') && source.includes('setViewingReasonItem(null)'),
        'StockMovementList must close viewingReasonItem modal immediately if session loses ADMIN role'
      );
    });

    test('StockMovementList source verifies targeted product name resolution for current page only', () => {
      const source = fs.readFileSync(movementListPath, 'utf8');
      // Must not preload blanket 100 products
      assert.ok(
        !source.includes('productsApi.getProducts({ page: 1, pageSize: 100 })'),
        'StockMovementList must not preload blanket 100 products'
      );
      assert.ok(
        source.includes('productsApi.getProduct('),
        'StockMovementList must fetch individual product names on demand for page missing IDs'
      );
    });
  });
});
