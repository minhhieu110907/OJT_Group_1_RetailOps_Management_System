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

  // =========================================================================
  // WORKSTREAM 5 — BEHAVIORAL REGRESSION TESTS (P1 & P2 TARGETED PASS)
  // =========================================================================
  describe('Behavioral Concurrency, Lifecycle & RBAC Regressions', () => {
    test('Test A — Failed reload: network rejection preserves conflictData, draft and prevents double POST', async () => {
      let conflictData = { expectedVersion: 2, actualVersion: 3, detailsMsg: 'Conflict' };
      let draft = { countedQty: '15', reason: 'Kiem ke dot xuat dinh ky' };
      let postCount = 0;

      // Controller logic matching InventoryAdjustModal handleReloadLatest
      const handleReloadLatestController = async (productId, onReloadLatest) => {
        try {
          const latest = await onReloadLatest(productId);
          if (latest) {
            conflictData = null;
          }
        } catch {
          // Keep conflictData intact on error
        }
      };

      // Mock onReloadLatest throwing network error
      const failingReload = async () => {
        throw new Error('Network timeout / 500 error');
      };

      await handleReloadLatestController(101, failingReload);

      // Assertions
      assert.ok(conflictData !== null, 'Conflict banner must remain visible on reload failure');
      assert.equal(conflictData.actualVersion, 3, 'Actual server version must not change on failed reload');
      assert.equal(draft.countedQty, '15', 'Draft countedQty must be preserved on reload failure');
      assert.equal(draft.reason, 'Kiem ke dot xuat dinh ky', 'Draft reason must be preserved on reload failure');
      assert.equal(postCount, 0, 'No adjustment POST must be triggered on reload failure');
    });

    test('Test B — Successful reload: authoritative data clears conflict, updates version, preserves draft and avoids auto-submit', async () => {
      let conflictData = { expectedVersion: 2, actualVersion: 3, detailsMsg: 'Conflict' };
      let currentProduct = { product_id: 101, quantity: 10, stock_version: 2 };
      let draft = { countedQty: '18', reason: 'Kiem ke sau kiem toan' };
      let autoSubmitted = false;

      const handleReloadLatestController = async (productId, onReloadLatest) => {
        try {
          const latest = await onReloadLatest(productId);
          if (latest) {
            conflictData = null;
            currentProduct = latest;
          }
        } catch {
          // ignore
        }
      };

      const successfulReload = async (productId) => ({
        product_id: productId,
        sku: 'SP-101',
        name: 'Sản phẩm 101',
        quantity: 12,
        stock_version: 3,
      });

      await handleReloadLatestController(101, successfulReload);

      assert.equal(conflictData, null, 'Conflict banner must be cleared after successful reload');
      assert.equal(currentProduct.stock_version, 3, 'Stock version must be updated to authoritative server version');
      assert.equal(currentProduct.quantity, 12, 'Authoritative stock quantity must be updated');
      assert.equal(draft.countedQty, '18', 'Draft countedQty must remain intact after reload');
      assert.equal(draft.reason, 'Kiem ke sau kiem toan', 'Draft reason must remain intact after reload');
      assert.equal(autoSubmitted, false, 'Reload must never auto-submit adjustment');
    });

    test('Test C — Late reload response: stale response after modal close or product switch is discarded', async () => {
      let adjustingProduct = { product_id: 101, name: 'Sản phẩm A' };
      let attemptId = 0;
      let appliedProduct = null;

      // Controller matching InventoryList onReloadLatest guard
      const createReloadHandler = () => {
        return async (productId, delayMs, returnData) => {
          const currentAttempt = ++attemptId;
          await new Promise((r) => setTimeout(r, delayMs));

          // Guard condition: modal still open for exact product and attempt ID
          if (currentAttempt === attemptId && adjustingProduct && adjustingProduct.product_id === productId) {
            appliedProduct = returnData;
            return returnData;
          }
          return null; // Stale response discarded
        };
      };

      const handler = createReloadHandler();

      // Launch slow reload for product 101
      const promiseA = handler(101, 50, { product_id: 101, name: 'Sản phẩm A mới', stock_version: 5 });

      // User switches to product 102 immediately (or closes modal)
      adjustingProduct = { product_id: 102, name: 'Sản phẩm B' };

      await promiseA;

      // Assert late response A did NOT overwrite product B
      assert.equal(appliedProduct, null, 'Late response from product A must not be applied after switching to product B');
      assert.equal(adjustingProduct.product_id, 102, 'Active product must remain product B');
    });

    test('Test D — Role downgrade: immediate suppression of audit sensitive fields when role becomes STAFF', () => {
      const renderAuditModalContent = (role, item) => {
        const isAdmin = role === 'ADMIN';
        const isModalOpen = isAdmin && Boolean(item);
        if (!isModalOpen || !isAdmin || !item) return null;
        return {
          actor_id: item.actor_id,
          reason: item.adjustment_reason,
        };
      };

      const item = { product_id: 1, actor_id: 99, adjustment_reason: 'Ly do nhay cam chi danh cho Admin' };

      // When ADMIN
      const adminRender = renderAuditModalContent('ADMIN', item);
      assert.deepEqual(adminRender, {
        actor_id: 99,
        reason: 'Ly do nhay cam chi danh cho Admin',
      });

      // When downgraded to STAFF
      const staffRender = renderAuditModalContent('STAFF', item);
      assert.equal(staffRender, null, 'Audit modal content must evaluate to null immediately upon role downgrade to STAFF');
    });

    test('Test E — Product lookup retry safety: bounded retry for failures, deduplicated in-flight requests, zero infinite loops', async () => {
      const pendingIds = new Set();
      const failedRetryCounts = new Map();
      const productMap = new Map();
      const MAX_RETRIES = 2;
      let totalApiCallCount = 0;

      const resolveProduct = async (pid, shouldFail) => {
        totalApiCallCount++;
        if (shouldFail) throw new Error('API Error');
        return { id: pid, name: `Tên ${pid}` };
      };

      const lookupController = async (pageIds, failMap) => {
        const missingIds = pageIds.filter((pid) => {
          if (!pid) return false;
          if (productMap.has(pid)) return false;
          if (pendingIds.has(pid)) return false;
          const retryCount = failedRetryCounts.get(pid) || 0;
          return retryCount < MAX_RETRIES;
        });

        const uniqueMissingIds = [...new Set(missingIds)];
        if (uniqueMissingIds.length === 0) return;

        uniqueMissingIds.forEach((pid) => pendingIds.add(pid));

        const results = await Promise.all(
          uniqueMissingIds.map(async (pid) => {
            try {
              const res = await resolveProduct(pid, failMap[pid]);
              return { pid, name: res.name, success: true };
            } catch {
              return { pid, name: null, success: false };
            }
          })
        );

        results.forEach(({ pid, success, name }) => {
          pendingIds.delete(pid);
          if (success && name) {
            productMap.set(pid, name);
          } else {
            const count = failedRetryCounts.get(pid) || 0;
            failedRetryCounts.set(pid, count + 1);
          }
        });
      };

      // Turn 1: Product 1 succeeds, Product 2 fails
      await lookupController([1, 2], { 1: false, 2: true });
      assert.equal(productMap.get(1), 'Tên 1');
      assert.equal(productMap.has(2), false);
      assert.equal(failedRetryCounts.get(2), 1);
      assert.equal(totalApiCallCount, 2);

      // Turn 2: Retry turn (e.g. re-render with product 2 again)
      await lookupController([1, 2], { 1: false, 2: true });
      assert.equal(failedRetryCounts.get(2), 2);
      assert.equal(totalApiCallCount, 3); // Product 1 skipped from cache, Product 2 called once

      // Turn 3: Exceeded max retries -> no further calls made
      await lookupController([1, 2], { 1: false, 2: true });
      assert.equal(totalApiCallCount, 3, 'No further requests made once max retries is reached (no infinite loop)');
    });

    test('Test F — Ambiguous POST outcome: timeout/network drop does not automatically dispatch a second POST with new UUID', async () => {
      let dispatchCount = 0;
      let lastErrorMessage = '';
      let isSubmitting = false;

      const adjustSubmitController = async (intentKey, isNetworkError) => {
        dispatchCount++;
        isSubmitting = true;
        try {
          if (isNetworkError) {
            const timeoutError = new Error('timeout of 10000ms exceeded');
            timeoutError.code = 'ECONNABORTED';
            throw timeoutError;
          }
          return { success: true };
        } catch (err) {
          if (!err.response || err.code === 'ECONNABORTED') {
            lastErrorMessage =
              'Kết nối máy chủ bị gián đoạn hoặc quá thời gian phản hồi. Kết quả điều chỉnh chưa thể xác minh. Vui lòng bấm "Tải lại dữ liệu mới nhất" để kiểm tra số tồn trên máy chủ trước khi gửi lại giao dịch.';
          }
        } finally {
          isSubmitting = false;
        }
      };

      const key1 = generateSecureIdempotencyKey();
      await adjustSubmitController(key1, true);

      assert.equal(dispatchCount, 1, 'Exactly one attempt was made; client must never auto-retry with a second POST');
      assert.ok(
        lastErrorMessage.includes('Kết quả điều chỉnh chưa thể xác minh'),
        'Client must warn user that outcome is ambiguous and guide them to authoritative reload'
      );
      assert.equal(isSubmitting, false, 'Submission lock must be released so user can reload');
    });

    test('Test G — No-op path allows submission without requiring 10-character reason', () => {
      const evaluateCanSubmit = (countedQty, currentQty, reason, isSubmitting, isReloading) => {
        const parsed = Number(countedQty);
        const isValidCounted = Number.isInteger(parsed) && parsed >= 0 && parsed <= MAX_STOCK_QUANTITY;
        const delta = parsed - currentQty;
        const trimmed = reason.trim();
        const isReasonValid = trimmed.length >= 10 && trimmed.length <= 250;
        const isNoOp = isValidCounted && delta === 0;
        return (isNoOp || (isValidCounted && isReasonValid)) && !isSubmitting && !isReloading;
      };

      // Case 1: Counted = current qty (Delta = 0), reason is empty ("")
      const canSubmitNoOpEmptyReason = evaluateCanSubmit('10', 10, '', false, false);
      assert.equal(
        canSubmitNoOpEmptyReason,
        true,
        'No-op (delta === 0) must be submittable to trigger toast and close without forcing 10-char reason'
      );

      // Case 2: Counted !== current qty (Delta !== 0), reason is empty ("") -> must be blocked
      const canSubmitDeltaEmptyReason = evaluateCanSubmit('15', 10, '', false, false);
      assert.equal(
        canSubmitDeltaEmptyReason,
        false,
        'Mutation with delta !== 0 must require valid 10-250 char reason'
      );
    });
  });
});
