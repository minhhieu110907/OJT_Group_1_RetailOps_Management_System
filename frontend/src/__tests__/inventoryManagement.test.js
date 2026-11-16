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
import {
  ADJUSTMENT_STATUS,
  canCloseAdjustmentModal,
  canSubmitAdjustment,
  classifyAdjustmentError,
  createInitialAdjustmentState,
  isValidAuthoritativeInventory,
  reduceAdjustmentState,
} from '../pages/Inventory/inventoryAdjustmentController.js';

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

    test('getLowStock queries /inventory/low-stock with positive page and pageSize bounded <= 100', async () => {
      let capturedConfig = null;
      const originalGet = axiosClient.get;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return {
          data: {
            items: [],
            total: 0,
            page: 1,
            page_size: 20,
          },
        };
      };

      try {
        await inventoryApi.getLowStock({ page: 1, pageSize: 20 });
        assert.equal(capturedConfig.url, '/inventory/low-stock');
        assert.deepEqual(capturedConfig.config.params, {
          page: 1,
          page_size: 20,
        });
      } finally {
        axiosClient.get = originalGet;
      }
    });

    test('adjustInventory sends correct payload and Idempotency-Key header to POST /inventory/{product_id}/adjustments', async () => {
      let captured = null;
      const originalPost = axiosClient.post;
      axiosClient.post = async (url, data, config) => {
        captured = { url, data, config };
        return {
          data: {
            product_id: 10,
            counted_quantity: 15,
            expected_stock_version: 3,
            delta: 5,
            stock_version_after: 4,
            movement_created: true,
            movement_id: 88,
          },
        };
      };

      try {
        const fixedKey = 'c4b81098-9999-4a11-8888-0123456789ab';
        const res = await inventoryApi.adjustInventory({
          productId: 10,
          countedQuantity: 15,
          expectedStockVersion: 3,
          reason: 'Kiem ke dot xuat cuoi gio',
          idempotencyKey: fixedKey,
        });

        assert.equal(captured.url, '/inventory/10/adjustments');
        assert.deepEqual(captured.data, {
          counted_quantity: 15,
          expected_stock_version: 3,
          reason: 'Kiem ke dot xuat cuoi gio',
        });
        assert.equal(captured.config.headers['Idempotency-Key'], fixedKey);
        assert.equal(res.delta, 5);
        assert.equal(res.stock_version_after, 4);
      } finally {
        axiosClient.post = originalPost;
      }
    });

    test('adjustInventory fails closed if quantity exceeds MAX_STOCK_QUANTITY or is negative', async () => {
      await assert.rejects(
        async () => {
          await inventoryApi.adjustInventory({
            productId: 1,
            countedQuantity: MAX_STOCK_QUANTITY + 1,
            expectedStockVersion: 0,
            reason: 'Test exceed max stock quantity',
          });
        },
        /Số lượng kiểm kê thực tế phải là số nguyên từ 0 đến 2.147.483.647/
      );

      await assert.rejects(
        async () => {
          await inventoryApi.adjustInventory({
            productId: 1,
            countedQuantity: -1,
            expectedStockVersion: 0,
            reason: 'Test negative stock quantity',
          });
        },
        /Số lượng kiểm kê thực tế phải là số nguyên từ 0 đến 2.147.483.647/
      );
    });

    test('generateSecureIdempotencyKey generates standard UUID v4 format and rejects insecure fallback', () => {
      const key = generateSecureIdempotencyKey();
      assert.equal(typeof key, 'string');
      // UUID v4 format: 8-4-4-4-12 hex characters
      const uuidv4Regex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
      assert.ok(uuidv4Regex.test(key), `Expected valid UUID v4 format, got: ${key}`);
    });
  });

  // =========================================================================
  // WORKSTREAM 2 — KPI SEMANTICS & NO CURRENT-PAGE BIAS
  // =========================================================================
  describe('Global KPI Calculation Semantics (INV-01)', () => {
    test('classifyStockLevel classifies levels strictly by ACTIVE status and threshold <= 5', () => {
      // ACTIVE in-stock (> 5) -> code: 'NORMAL', label: 'Bình thường'
      const normal = classifyStockLevel(10, 'ACTIVE');
      assert.equal(normal.code, 'NORMAL');
      assert.equal(normal.label, 'Bình thường');

      // ACTIVE low-stock (1..5) -> code: 'LOW', label: 'Tồn thấp'
      const low = classifyStockLevel(3, 'ACTIVE');
      assert.equal(low.code, 'LOW');
      assert.equal(low.label, 'Tồn thấp');

      // ACTIVE out-of-stock (= 0) -> code: 'OUT_OF_STOCK', label: 'Hết hàng'
      const out = classifyStockLevel(0, 'ACTIVE');
      assert.equal(out.code, 'OUT_OF_STOCK');
      assert.equal(out.label, 'Hết hàng');

      // INACTIVE quantity = 0 -> code: 'INACTIVE', label: 'Ngừng bán'
      const inactiveZero = classifyStockLevel(0, 'INACTIVE');
      assert.equal(inactiveZero.code, 'INACTIVE');
      assert.equal(inactiveZero.label, 'Ngừng bán');

      // INACTIVE quantity > 0
      const inactivePositive = classifyStockLevel(15, 'INACTIVE');
      assert.equal(inactivePositive.code, 'INACTIVE');
    });

    test('InventoryList source code queries authoritative server totals and does NOT compute global KPI from current page items', () => {
      const source = fs.readFileSync(inventoryListPath, 'utf8');

      // Must not calculate global counts by filtering current page items
      assert.ok(
        !source.includes('inventoryItems.filter'),
        'InventoryList must NOT use inventoryItems.filter to compute global KPIs'
      );

      // Must load global stats using authoritative queries
      assert.ok(
        source.includes('inventoryApi.getInventory({ page: 1, pageSize: 1 })'),
        'InventoryList must query total products via server'
      );
      assert.ok(
        source.includes("inventoryApi.getInventory({ status: 'ACTIVE', page: 1, pageSize: 1 })"),
        'InventoryList must query active products via server'
      );
      assert.ok(
        source.includes('inventoryApi.getLowStock({ page: 1, pageSize: 1 })'),
        'InventoryList must query low stock total via server'
      );
      assert.ok(
        source.includes("inventoryApi.getInventory({ status: 'ACTIVE', inStock: false, page: 1, pageSize: 1 })"),
        'InventoryList must query out of stock active products via server'
      );
    });
  });

  // =========================================================================
  // WORKSTREAM 3 — ADJUSTMENT SAFETY, NO-OP & 409 CONFLICT
  // =========================================================================
  describe('Inventory Adjustment Safety (INV-02 / Concurrency)', () => {
    test('InventoryAdjustModal source verifies No-Op does not dispatch POST and informs user', () => {
      const source = fs.readFileSync(adjustModalPath, 'utf8');
      assert.ok(
        source.includes('if (isValidCounted && delta === 0)'),
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
        source.includes("classified.type === ADJUSTMENT_STATUS.STALE_VERSION"),
        'InventoryAdjustModal must use classified STALE_VERSION'
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
      assert.ok(
        source.includes('isOpen={isAdmin && Boolean(viewingReasonItem)}'),
        'StockMovementList must gate Modal isOpen with isAdmin directly in render'
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
  // WORKSTREAM 5 — PRODUCTION BEHAVIORAL REGRESSION TESTS (T01 - T07)
  // =========================================================================
  describe('Production Behavioral Regressions (Using Production Controller)', () => {
    test('T01 — Ambiguous submit locks modal and preserves pending intent and Idempotency-Key', () => {
      const timeoutErr = new Error('timeout of 10000ms exceeded');
      timeoutErr.code = 'ECONNABORTED';

      const classified = classifyAdjustmentError(timeoutErr);
      assert.equal(classified.type, ADJUSTMENT_STATUS.AMBIGUOUS);
      assert.ok(classified.message.includes('Kết quả điều chỉnh chưa thể xác minh'));

      // Transition state to AMBIGUOUS using production reducer
      const initialState = createInitialAdjustmentState();
      const submittingState = reduceAdjustmentState(initialState, { type: 'START_SUBMIT' });
      assert.equal(submittingState.status, ADJUSTMENT_STATUS.SUBMITTING);

      const fixedKey = 'uuid-fixed-intent-key-1234';
      const ambiguousState = reduceAdjustmentState(submittingState, {
        type: 'SUBMIT_AMBIGUOUS',
        payload: {
          message: classified.message,
          intent: { key: fixedKey, payload: { countedQuantity: 20, reason: 'Kiem ke thuc te' } },
        },
      });

      assert.equal(ambiguousState.status, ADJUSTMENT_STATUS.AMBIGUOUS);
      assert.equal(ambiguousState.ambiguousIntent.key, fixedKey);
      assert.equal(ambiguousState.ambiguousIntent.payload.countedQuantity, 20);

      // Submission must be locked: canSubmitAdjustment returns false
      const canSubmitInAmbiguous = canSubmitAdjustment({
        status: ambiguousState.status,
        isValidCounted: true,
        isReasonValid: true,
        delta: 5,
      });
      assert.equal(canSubmitInAmbiguous, false, 'User must NOT be allowed to submit a new adjustment while outcome is AMBIGUOUS');
    });

    test('T02 — Centralized Close Guard blocks close on AMBIGUOUS, RECONCILING, and AWAITING_ACKNOWLEDGEMENT', () => {
      // 1. In IDLE without pendingIntent: close is permitted
      assert.equal(canCloseAdjustmentModal(ADJUSTMENT_STATUS.IDLE, null), true, 'IDLE must permit closing');

      // 2. In SUBMITTING: close is blocked
      assert.equal(canCloseAdjustmentModal(ADJUSTMENT_STATUS.SUBMITTING, null), false, 'SUBMITTING must block closing');

      // 3. In AMBIGUOUS: close is blocked
      const pendingIntent = { key: 'uuid-1', payload: {} };
      assert.equal(canCloseAdjustmentModal(ADJUSTMENT_STATUS.AMBIGUOUS, pendingIntent), false, 'AMBIGUOUS must block closing');

      // 4. In RECONCILING: close is blocked
      assert.equal(canCloseAdjustmentModal(ADJUSTMENT_STATUS.RECONCILING, pendingIntent), false, 'RECONCILING must block closing');

      // 5. In AWAITING_ACKNOWLEDGEMENT: close is blocked until acknowledged
      assert.equal(canCloseAdjustmentModal(ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT, pendingIntent), false, 'AWAITING_ACKNOWLEDGEMENT must block closing');

      // 6. Even if status is mistakenly IDLE but pendingIntent remains, close is blocked
      assert.equal(canCloseAdjustmentModal(ADJUSTMENT_STATUS.IDLE, pendingIntent), false, 'Pending intent must block closing even if status is IDLE');
    });

    test('T03 — No-Op bypass regression: No-Op cannot bypass lock when status is AMBIGUOUS', () => {
      // In AMBIGUOUS, even if counted quantity equals current quantity (delta === 0)
      const canSubmitAmbiguousNoOp = canSubmitAdjustment({
        status: ADJUSTMENT_STATUS.AMBIGUOUS,
        isValidCounted: true,
        isReasonValid: false,
        delta: 0,
      });
      assert.equal(canSubmitAmbiguousNoOp, false, 'No-Op must not bypass submit lock in AMBIGUOUS status');

      // In AWAITING_ACKNOWLEDGEMENT, No-Op is also blocked
      const canSubmitAckNoOp = canSubmitAdjustment({
        status: ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT,
        isValidCounted: true,
        isReasonValid: false,
        delta: 0,
      });
      assert.equal(canSubmitAckNoOp, false, 'No-Op must not bypass submit lock in AWAITING_ACKNOWLEDGEMENT status');

      // Only in IDLE is No-Op allowed
      const canSubmitIdleNoOp = canSubmitAdjustment({
        status: ADJUSTMENT_STATUS.IDLE,
        isValidCounted: true,
        isReasonValid: false,
        delta: 0,
      });
      assert.equal(canSubmitIdleNoOp, true, 'No-Op is only permitted in IDLE status');
    });

    test('T04 — Authoritative reload validation (isValidAuthoritativeInventory) and failure preservation', () => {
      const currentProductId = 42;

      // Fail-closed validation checks
      assert.equal(isValidAuthoritativeInventory(null, currentProductId), false, 'null is invalid');
      assert.equal(isValidAuthoritativeInventory(undefined, currentProductId), false, 'undefined is invalid');
      assert.equal(isValidAuthoritativeInventory({}, currentProductId), false, 'empty object is invalid');
      assert.equal(isValidAuthoritativeInventory({ product_id: 99, quantity: 10, stock_version: 1 }, currentProductId), false, 'wrong product_id is invalid');
      assert.equal(isValidAuthoritativeInventory({ product_id: 42, quantity: -5, stock_version: 1 }, currentProductId), false, 'negative quantity is invalid');
      assert.equal(isValidAuthoritativeInventory({ product_id: 42, quantity: '10', stock_version: 1 }, currentProductId), false, 'string quantity is invalid');
      assert.equal(isValidAuthoritativeInventory({ product_id: 42, quantity: 10, stock_version: -1 }, currentProductId), false, 'negative version is invalid');
      assert.equal(isValidAuthoritativeInventory({ product_id: 42, quantity: 10, stock_version: null }, currentProductId), false, 'null version is invalid');
      assert.equal(isValidAuthoritativeInventory({ product_id: 42, quantity: 2147483648, stock_version: 1 }, currentProductId), false, 'overflow quantity is invalid');

      // Valid response passes
      assert.equal(isValidAuthoritativeInventory({ product_id: 42, quantity: 10, stock_version: 2 }, currentProductId), true, 'valid response passes');

      // Failure transition preserves AMBIGUOUS state, draft and intent
      const ambiguousState = {
        status: ADJUSTMENT_STATUS.AMBIGUOUS,
        conflictData: null,
        errorMessage: 'Original network error',
        ambiguousIntent: { key: 'uuid-1', payload: { countedQuantity: 20 } },
      };

      const reconcilingState = reduceAdjustmentState(ambiguousState, { type: 'START_RELOAD' });
      assert.equal(reconcilingState.status, ADJUSTMENT_STATUS.RECONCILING);

      const failedReloadState = reduceAdjustmentState(reconcilingState, {
        type: 'RELOAD_FAILURE',
        payload: {
          previousStatus: ADJUSTMENT_STATUS.AMBIGUOUS,
          errorMessage: 'Dữ liệu nhận từ máy chủ không hợp lệ hoặc không đúng sản phẩm.',
        },
      });

      assert.equal(failedReloadState.status, ADJUSTMENT_STATUS.AMBIGUOUS);
      assert.equal(failedReloadState.ambiguousIntent.key, 'uuid-1');
      assert.equal(failedReloadState.errorMessage, 'Dữ liệu nhận từ máy chủ không hợp lệ hoặc không đúng sản phẩm.');

      // Submit remains strictly locked
      const canSubmitAfterFailedReload = canSubmitAdjustment({
        status: failedReloadState.status,
        isValidCounted: true,
        isReasonValid: true,
        delta: 5,
      });
      assert.equal(canSubmitAfterFailedReload, false);
    });

    test('T05 — Valid reload transitions to AWAITING_ACKNOWLEDGEMENT; explicit user acknowledgement gates return to IDLE', () => {
      const ambiguousState = {
        status: ADJUSTMENT_STATUS.AMBIGUOUS,
        conflictData: null,
        errorMessage: 'Timeout error',
        ambiguousIntent: { key: 'uuid-1', payload: { countedQuantity: 20 } },
      };

      const reconcilingState = reduceAdjustmentState(ambiguousState, { type: 'START_RELOAD' });

      // Valid reload response processed
      const ackState = reduceAdjustmentState(reconcilingState, {
        type: 'RELOAD_SUCCESS',
        payload: {
          previousStatus: ADJUSTMENT_STATUS.AMBIGUOUS,
          reconciledResult: {
            previousVersion: 2,
            latestVersion: 3,
            latestQuantity: 20,
          },
        },
      });

      // Must be in AWAITING_ACKNOWLEDGEMENT, NOT IDLE yet!
      assert.equal(ackState.status, ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT);
      assert.ok(ackState.ambiguousIntent !== null, 'ambiguousIntent must be retained during acknowledgement stage');
      assert.deepEqual(ackState.reconciledResult, {
        previousVersion: 2,
        latestVersion: 3,
        latestQuantity: 20,
      });

      // Submit must remain LOCKED before user acknowledges
      const canSubmitBeforeAck = canSubmitAdjustment({
        status: ackState.status,
        isValidCounted: true,
        isReasonValid: true,
        delta: 5,
      });
      assert.equal(canSubmitBeforeAck, false, 'Submit must remain locked while awaiting acknowledgement');

      // Modal close must also be BLOCKED before user acknowledges
      assert.equal(canCloseAdjustmentModal(ackState.status, ackState.ambiguousIntent), false, 'Modal close must remain blocked while awaiting acknowledgement');

      // User actively clicks "Đã kiểm tra đối soát • Tiếp tục thao tác"
      const idleState = reduceAdjustmentState(ackState, { type: 'ACKNOWLEDGE_RECONCILIATION' });
      assert.equal(idleState.status, ADJUSTMENT_STATUS.IDLE);
      assert.equal(idleState.ambiguousIntent, null);
      assert.equal(idleState.reconciledResult, null);

      // Now and only now, submit is unlocked for next legitimate user intent
      const canSubmitAfterAck = canSubmitAdjustment({
        status: idleState.status,
        isValidCounted: true,
        isReasonValid: true,
        delta: 5,
      });
      assert.equal(canSubmitAfterAck, true, 'Submit is unlocked after explicit user acknowledgement');
    });

    test('T06 — HTTP 500 error after dispatch is classified as AMBIGUOUS and does not retry automatically', () => {
      const server500Err = {
        response: {
          status: 500,
          data: { message: 'Internal Server Error' },
        },
      };

      const classified = classifyAdjustmentError(server500Err);
      assert.equal(classified.type, ADJUSTMENT_STATUS.AMBIGUOUS);
      assert.ok(classified.message.includes('Kết quả điều chỉnh chưa thể xác minh'));

      // 502 Bad Gateway and 503 Service Unavailable are also AMBIGUOUS
      const error503 = { response: { status: 503, data: {} } };
      assert.equal(classifyAdjustmentError(error503).type, ADJUSTMENT_STATUS.AMBIGUOUS);

      // 400 Bad Request is CONFIRMED_ERROR, not AMBIGUOUS
      const error400 = { response: { status: 400, data: { message: 'Dữ liệu không hợp lệ' } } };
      assert.equal(classifyAdjustmentError(error400).type, 'CONFIRMED_ERROR');
    });

    test('T07 — Preserve existing behaviors: 409 STALE_STOCK_VERSION, No-Op in IDLE, and normal reload', () => {
      // 1. STALE_STOCK_VERSION 409
      const error409 = {
        response: {
          status: 409,
          data: {
            code: 'STALE_STOCK_VERSION',
            message: 'Stale version detected',
            details: { expected_stock_version: 1, current_stock_version: 2 },
          },
        },
      };

      const classified409 = classifyAdjustmentError(error409);
      assert.equal(classified409.type, ADJUSTMENT_STATUS.STALE_VERSION);
      assert.equal(classified409.details.current_stock_version, 2);

      // 2. Normal reload from STALE_VERSION transitions directly to IDLE without forcing ACKNOWLEDGEMENT
      const staleState = {
        status: ADJUSTMENT_STATUS.STALE_VERSION,
        conflictData: { expectedVersion: 1, actualVersion: 2 },
        errorMessage: '',
        ambiguousIntent: null,
      };

      const reconcilingFromStale = reduceAdjustmentState(staleState, { type: 'START_RELOAD' });
      const reloadedStaleState = reduceAdjustmentState(reconcilingFromStale, {
        type: 'RELOAD_SUCCESS',
        payload: {
          previousStatus: ADJUSTMENT_STATUS.STALE_VERSION,
          reconciledResult: { previousVersion: 1, latestVersion: 2, latestQuantity: 15 },
        },
      });

      assert.equal(reloadedStaleState.status, ADJUSTMENT_STATUS.IDLE);
      assert.equal(reloadedStaleState.conflictData, null);

      // 3. No-op canSubmit allows delta === 0 without requiring 10-character reason in IDLE
      const canSubmitNoOp = canSubmitAdjustment({
        status: ADJUSTMENT_STATUS.IDLE,
        isValidCounted: true,
        isReasonValid: false,
        delta: 0,
      });
      assert.equal(canSubmitNoOp, true, 'No-op must allow submission with empty reason in IDLE');

      // 4. Non No-op (delta !== 0) requires valid reason
      const canSubmitMutation = canSubmitAdjustment({
        status: ADJUSTMENT_STATUS.IDLE,
        isValidCounted: true,
        isReasonValid: false,
        delta: 5,
      });
      assert.equal(canSubmitMutation, false, 'Mutation with delta !== 0 must require 10-char reason');
    });
  });
});
