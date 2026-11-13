import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient, { isSafeToReplayRequest } from '../api/axiosClient.js';
import { ordersApi, generateCheckoutIdempotencyKey } from '../api/ordersApi.js';
import {
  DEFAULT_POS_PRODUCT_LIMIT,
  PENDING_CHECKOUT_STORAGE_KEY,
  PENDING_CHECKOUT_TTL_MS,
  addProductToCart,
  buildCheckoutPayload,
  buildPendingCheckoutOwnerScope,
  calculateCartTotals,
  classifyCheckoutError,
  clearPendingCheckout,
  executeSafePosCheckout,
  formatVnd,
  loadPendingCheckout,
  prioritizeCategoriesByLatestProducts,
  resolvePendingCheckoutAction,
  savePendingCheckout,
  updateCartItemQuantity,
} from '../utils/posUtils.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const posPagePath = path.resolve(__dirname, '../pages/Pos/PosPage.jsx');
const appPath = path.resolve(__dirname, '../App.jsx');

describe('T04A7A8 POS Sales UI & Checkout Integration Suite', () => {
  beforeEach(() => {
    delete axiosClient.post;
  });

  test('prioritizeCategoriesByLatestProducts puts categories of newest ACTIVE products first', () => {
    const categories = [
      { id: 1, name: 'Gia vị', status: 'ACTIVE' },
      { id: 2, name: 'Đồ uống', status: 'ACTIVE' },
      { id: 3, name: 'Bánh kẹo', status: 'ACTIVE' },
      { id: 4, name: 'Ngừng dùng', status: 'INACTIVE' },
    ];
    const latestProducts = [
      { id: 101, category_id: 3, status: 'ACTIVE' },
      { id: 100, category_id: 2, status: 'ACTIVE' },
      { id: 99, category_id: 3, status: 'ACTIVE' },
    ];

    const result = prioritizeCategoriesByLatestProducts(categories, latestProducts);
    assert.deepEqual(
      result.map((c) => c.id),
      [3, 2, 1]
    );
  });

  test('cart helpers add items, respect reference stock, update quantities, and build checkout payload', () => {
    const milk = {
      id: 1,
      sku: 'SP0001',
      name: 'Sữa tươi 1L',
      sale_price_vnd: 28000,
      quantity: 2,
    };
    const outOfStock = {
      id: 2,
      sku: 'SP0002',
      name: 'Hết hàng',
      sale_price_vnd: 10000,
      quantity: 0,
    };

    const r0 = addProductToCart([], outOfStock);
    assert.equal(r0.added, false);
    assert.equal(r0.reason, 'OUT_OF_STOCK');

    const r1 = addProductToCart([], milk);
    assert.equal(r1.added, true);
    const r2 = addProductToCart(r1.nextCart, milk);
    assert.equal(r2.added, true);
    const r3 = addProductToCart(r2.nextCart, milk);
    assert.equal(r3.added, false);
    assert.equal(r3.reason, 'EXCEEDS_STOCK');

    const totals = calculateCartTotals(r2.nextCart);
    assert.equal(totals.lineCount, 1);
    assert.equal(totals.totalUnits, 2);
    assert.equal(totals.totalVnd, 56000);
    assert.ok(formatVnd(56000).includes('56.000'));

    assert.deepEqual(buildCheckoutPayload(r2.nextCart), [
      { product_id: 1, quantity: 2, viewed_unit_price_vnd: 28000 },
    ]);

    const cleared = updateCartItemQuantity(r2.nextCart, 1, 0);
    assert.equal(cleared.length, 0);
  });

  test('ordersApi.checkoutOrder sends POST /orders/checkout with Idempotency-Key and fails closed in mock mode', async () => {
    let capturedUrl = null;
    let capturedPayload = null;
    let capturedConfig = null;

    axiosClient.post = async (url, payload, config) => {
      capturedUrl = url;
      capturedPayload = payload;
      capturedConfig = config;
      return {
        data: {
          id: 55,
          status: 'COMPLETED',
          total_vnd: 56000,
          created_by: 2,
          sold_at: '2026-11-13T15:00:00Z',
          cancelled_by: null,
          cancelled_at: null,
          cancel_reason: null,
          items: [
            {
              product_id: 1,
              sku_snapshot: 'SP0001',
              product_name_snapshot: 'Sữa tươi 1L',
              quantity: 2,
              unit_price_vnd: 28000,
              line_total_vnd: 56000,
            },
          ],
        },
      };
    };

    const key = generateCheckoutIdempotencyKey();
    assert.match(key, /^[A-Za-z0-9._:-]{16,128}$/);

    const order = await ordersApi.checkoutOrder({
      isMockMode: false,
      idempotencyKey: key,
      items: [{ product_id: 1, quantity: 2, viewed_unit_price_vnd: 28000 }],
    });

    assert.equal(capturedUrl, '/orders/checkout');
    assert.equal(capturedConfig.headers['Idempotency-Key'], key);
    assert.deepEqual(capturedPayload, {
      items: [{ product_id: 1, quantity: 2, viewed_unit_price_vnd: 28000 }],
    });
    assert.equal(order.id, 55);

    await assert.rejects(
      () =>
        ordersApi.checkoutOrder({
          isMockMode: true,
          items: [{ product_id: 1, quantity: 1, viewed_unit_price_vnd: 28000 }],
        }),
      /Mock Demo không được hỗ trợ/i
    );
  });

  test('PosPage uses Real API (created_desc, limit 6), hides cart when empty, and is wired in App.jsx', () => {
    const posContent = fs.readFileSync(posPagePath, 'utf8');
    const appContent = fs.readFileSync(appPath, 'utf8');

    assert.equal(DEFAULT_POS_PRODUCT_LIMIT, 6);
    assert.ok(posContent.includes("sort: 'created_desc'"));
    assert.ok(posContent.includes('DEFAULT_POS_PRODUCT_LIMIT'));
    assert.ok(posContent.includes('hasCartItems && ('));
    assert.ok(posContent.includes('product?.image_url'));
    assert.ok(posContent.includes('prioritizeCategoriesByLatestProducts'));
    assert.ok(appContent.includes('path="/pos" element={<PosPage />}'));
  });

  test('classifyCheckoutError distinguishes definite failures, idempotency conflicts, and ambiguous outcomes', () => {
    // 1. HTTP 422 / 409 business conflict -> DEFINITE_FAILURE
    const validationErr = {
      response: {
        status: 422,
        data: { code: 'VALIDATION_ERROR', message: 'Số lượng không hợp lệ.' },
      },
    };
    assert.equal(classifyCheckoutError(validationErr).outcome, 'DEFINITE_FAILURE');

    const stockConflictErr = {
      response: {
        status: 409,
        data: { code: 'INSUFFICIENT_STOCK', message: 'Tồn kho không đủ.' },
      },
    };
    assert.equal(classifyCheckoutError(stockConflictErr).outcome, 'DEFINITE_FAILURE');

    // 2. Timeout / Network loss / 5xx / REQUEST_IN_PROGRESS -> AMBIGUOUS
    assert.equal(
      classifyCheckoutError({ code: 'ECONNABORTED', message: 'timeout of 15000ms exceeded' }).outcome,
      'AMBIGUOUS'
    );
    assert.equal(
      classifyCheckoutError({ code: 'ERR_NETWORK', message: 'Network Error' }).outcome,
      'AMBIGUOUS'
    );
    assert.equal(
      classifyCheckoutError({ response: { status: 504, data: {} } }).outcome,
      'AMBIGUOUS'
    );
    assert.equal(
      classifyCheckoutError({
        response: { status: 409, data: { code: 'REQUEST_IN_PROGRESS' } },
      }).outcome,
      'AMBIGUOUS'
    );

    // 3. IDEMPOTENCY_KEY_REUSED -> IDEMPOTENCY_CONFLICT
    assert.equal(
      classifyCheckoutError({
        response: { status: 409, data: { code: 'IDEMPOTENCY_KEY_REUSED' } },
      }).outcome,
      'IDEMPOTENCY_CONFLICT'
    );

    // 4. 401 / unsafe replay block -> DEFINITE_FAILURE (never auto-replayed dangerously)
    assert.equal(
      classifyCheckoutError({
        isReplayBlocked: true,
        code: 'ERR_UNSAFE_MUTATION_REPLAY',
      }).outcome,
      'DEFINITE_FAILURE'
    );
  });

  test('checkout retry after lost response preserves exact snapshot and Idempotency-Key without creating a duplicate order', async () => {
    const sentRequests = [];
    let attempt = 0;

    axiosClient.post = async (url, payload, config) => {
      attempt += 1;
      sentRequests.push({
        url,
        payload: structuredClone(payload),
        key: config.headers['Idempotency-Key'],
        timeout: config.timeout,
      });
      if (attempt === 1) {
        const timeoutErr = new Error('timeout of 15000ms exceeded');
        timeoutErr.code = 'ECONNABORTED';
        throw timeoutErr;
      }
      return {
        data: {
          id: 88,
          status: 'COMPLETED',
          total_vnd: 28000,
          created_by: 2,
          sold_at: '2026-11-14T00:00:00Z',
          cancelled_by: null,
          cancelled_at: null,
          cancel_reason: null,
          items: [
            {
              product_id: 1,
              sku_snapshot: 'SP0001',
              product_name_snapshot: 'Sữa tươi 1L',
              quantity: 1,
              unit_price_vnd: 28000,
              line_total_vnd: 28000,
            },
          ],
        },
      };
    };

    const key = generateCheckoutIdempotencyKey();
    const items = [{ product_id: 1, quantity: 1, viewed_unit_price_vnd: 28000 }];

    await assert.rejects(
      () => ordersApi.checkoutOrder({ isMockMode: false, items, idempotencyKey: key }),
      (err) => classifyCheckoutError(err).outcome === 'AMBIGUOUS'
    );

    // Retry with exact same snapshot and Idempotency-Key
    const recoveredOrder = await ordersApi.checkoutOrder({
      isMockMode: false,
      items,
      idempotencyKey: key,
    });

    assert.equal(recoveredOrder.id, 88);
    assert.equal(sentRequests.length, 2);
    assert.equal(sentRequests[0].key, sentRequests[1].key);
    assert.deepEqual(sentRequests[0].payload, sentRequests[1].payload);
    assert.equal(sentRequests[0].timeout, 15000);
  });

  test('PosPage enforces double-click lock, cart lock during pendingCheckout, and blocks unsafe 401 replay on /orders/checkout', () => {
    const posContent = fs.readFileSync(posPagePath, 'utf8');

    // Double-click and cart mutation locks
    assert.ok(posContent.includes('isCheckingOutRef.current'));
    assert.ok(posContent.includes('isCartLocked'));
    assert.ok(posContent.includes('if (isCartLocked || isCheckingOutRef.current) return;'));
    assert.ok(posContent.includes('executeSafePosCheckout'));
    assert.ok(posContent.includes('buildPendingCheckoutOwnerScope'));
    assert.ok(posContent.includes('resolvePendingCheckoutAction'));
    assert.ok(posContent.includes('beforeunload'));
    assert.ok(posContent.includes('Kiểm tra lại kết quả đơn này'));

    // Axios 401 interceptor must NOT auto-replay POST /orders/checkout unless explicitly registered
    assert.equal(
      isSafeToReplayRequest({
        method: 'POST',
        url: '/orders/checkout',
        headers: { 'Idempotency-Key': 'pos-1234567890abcdef' },
      }),
      false
    );
  });

  test('Crash-safety: persists snapshot+key BEFORE request, recovers after mid-flight crash/reload, blocks on persist failure, isolates users, and clears on success', async () => {
    const backingStore = new Map();
    const fakeSessionStorage = {
      getItem: (k) => (backingStore.has(k) ? backingStore.get(k) : null),
      setItem: (k, v) => backingStore.set(k, String(v)),
      removeItem: (k) => backingStore.delete(k),
    };

    const staffA = { id: 101, role: 'STAFF', status: 'ACTIVE' };
    const staffB = { id: 202, role: 'STAFF', status: 'ACTIVE' };
    const scopeA = buildPendingCheckoutOwnerScope(staffA, false);
    const scopeB = buildPendingCheckoutOwnerScope(staffB, false);
    assert.equal(scopeA, 'api:101');
    assert.equal(scopeB, 'api:202');

    const snapshot = [{ product_id: 1, quantity: 2, viewed_unit_price_vnd: 28000 }];
    const cartSnap = [
      { productId: 1, sku: 'SP0001', name: 'Sữa tươi 1L', unitPriceVnd: 28000, quantity: 2 },
    ];
    const key = generateCheckoutIdempotencyKey();

    // 1. Persist failure BEFORE checkout blocks sending checkoutOrderFn completely
    let blockedCalls = 0;
    const failingStorage = {
      getItem: () => null,
      setItem: () => {
        throw new Error('QuotaExceededError');
      },
      removeItem: () => {},
    };
    const persistFailResult = await executeSafePosCheckout({
      storage: failingStorage,
      ownerScope: scopeA,
      isMockMode: false,
      itemsSnapshot: snapshot,
      cartSnapshot: cartSnap,
      totalVnd: 56000,
      lineCount: 1,
      idempotencyKey: key,
      checkoutOrderFn: async () => {
        blockedCalls += 1;
        return { id: 1 };
      },
    });
    assert.equal(persistFailResult.ok, false);
    assert.equal(persistFailResult.outcome, 'PERSIST_FAILED');
    assert.equal(blockedCalls, 0);

    // 2. Crash/reload AFTER request starts (before response arrives):
    // Verify storage was already written BEFORE checkoutOrderFn executed, and contains NO tokens
    let persistedBeforeSend = null;
    const midFlightRes = await executeSafePosCheckout({
      storage: fakeSessionStorage,
      ownerScope: scopeA,
      isMockMode: false,
      itemsSnapshot: snapshot,
      cartSnapshot: cartSnap,
      totalVnd: 56000,
      lineCount: 1,
      idempotencyKey: key,
      nowMs: 1_700_000_000_000,
      checkoutOrderFn: async () => {
        persistedBeforeSend = fakeSessionStorage.getItem(PENDING_CHECKOUT_STORAGE_KEY);
        const dropErr = new Error('tab crashed / network dropped');
        dropErr.code = 'ERR_NETWORK';
        throw dropErr;
      },
    });
    assert.ok(persistedBeforeSend);
    const parsedBeforeSend = JSON.parse(persistedBeforeSend);
    assert.equal(parsedBeforeSend.status, 'IN_FLIGHT');
    assert.equal(parsedBeforeSend.idempotencyKey, key);
    assert.equal(parsedBeforeSend.ownerScope, scopeA);
    assert.equal('access_token' in parsedBeforeSend, false);
    assert.equal('refresh_token' in parsedBeforeSend, false);
    assert.equal(midFlightRes.outcome, 'AMBIGUOUS');

    // 3. Switching user on same browser (Staff B) MUST NOT inherit Staff A's pending checkout
    assert.equal(loadPendingCheckout(fakeSessionStorage, scopeB, 1_700_000_010_000), null);
    clearPendingCheckout(fakeSessionStorage, scopeB);
    assert.ok(loadPendingCheckout(fakeSessionStorage, scopeA, 1_700_000_010_000));

    // 4. Backend 24h TTL check: after 24h, retry is flagged as expired and blocked
    const expiredLoad = loadPendingCheckout(
      fakeSessionStorage,
      scopeA,
      1_700_000_000_000 + PENDING_CHECKOUT_TTL_MS + 1
    );
    assert.equal(expiredLoad.isExpired, true);
    const expiredRetry = await executeSafePosCheckout({
      storage: fakeSessionStorage,
      ownerScope: scopeA,
      isMockMode: false,
      pendingCheckout: expiredLoad,
      nowMs: 1_700_000_000_000 + PENDING_CHECKOUT_TTL_MS + 1,
      checkoutOrderFn: async () => {
        throw new Error('Should not send expired retry');
      },
    });
    assert.equal(expiredRetry.ok, false);
    assert.equal(expiredRetry.outcome, 'IDEMPOTENCY_EXPIRED');

    // 5. Retry after reload within 24h preserves exact key & payload, and clears pending state on 201 success
    const restoredA = loadPendingCheckout(
      fakeSessionStorage,
      scopeA,
      1_700_000_010_000
    );
    assert.equal(restoredA.isExpired, false);
    assert.equal(restoredA.idempotencyKey, key);

    let retrySent = null;
    const successRes = await executeSafePosCheckout({
      storage: fakeSessionStorage,
      ownerScope: scopeA,
      isMockMode: false,
      pendingCheckout: restoredA,
      nowMs: 1_700_000_010_000,
      checkoutOrderFn: async (args) => {
        retrySent = args;
        return { id: 105, total_vnd: 56000 };
      },
    });
    assert.equal(successRes.ok, true);
    assert.equal(successRes.outcome, 'SUCCESS');
    assert.equal(retrySent.idempotencyKey, key);
    assert.deepEqual(retrySent.items, snapshot);
    assert.equal(loadPendingCheckout(fakeSessionStorage, scopeA, 1_700_000_010_000), null);
  });

  test('P1-A behavioral: server commits order while client loses response, unconfirmed abandon is blocked, reload preserves pendingCheckout, and retry recovers original order', async () => {
    // Fake sessionStorage for reload/navigation simulation
    const backingStore = new Map();
    const fakeSessionStorage = {
      getItem: (k) => (backingStore.has(k) ? backingStore.get(k) : null),
      setItem: (k, v) => backingStore.set(k, String(v)),
      removeItem: (k) => backingStore.delete(k),
    };

    // Fake backend that actually commits order #99 on first request even though client sees ECONNABORTED
    const committedByKey = new Map();
    let backendCreateCount = 0;
    axiosClient.post = async (_url, payload, config) => {
      const key = config.headers['Idempotency-Key'];
      if (!committedByKey.has(key)) {
        backendCreateCount += 1;
        const committedOrder = {
          id: 99,
          status: 'COMPLETED',
          total_vnd: 56000,
          created_by: 2,
          sold_at: '2026-11-14T01:00:00Z',
          cancelled_by: null,
          cancelled_at: null,
          cancel_reason: null,
          items: payload.items.map((line) => ({
            product_id: line.product_id,
            sku_snapshot: 'SP0001',
            product_name_snapshot: 'Sữa tươi 1L',
            quantity: line.quantity,
            unit_price_vnd: line.viewed_unit_price_vnd,
            line_total_vnd: line.quantity * line.viewed_unit_price_vnd,
          })),
        };
        committedByKey.set(key, committedOrder);
        // Simulate network drop / timeout before client receives response
        const timeoutErr = new Error('timeout of 15000ms exceeded');
        timeoutErr.code = 'ECONNABORTED';
        throw timeoutErr;
      }
      // Subsequent replay with same key returns original committed order (Backend 24h idempotency)
      return { data: committedByKey.get(key) };
    };

    const key = generateCheckoutIdempotencyKey();
    const snapshot = [{ product_id: 1, quantity: 2, viewed_unit_price_vnd: 28000 }];

    // 1. First checkout hits timeout after backend already committed #99
    await assert.rejects(
      () => ordersApi.checkoutOrder({ isMockMode: false, items: snapshot, idempotencyKey: key }),
      (err) => classifyCheckoutError(err).outcome === 'AMBIGUOUS'
    );

    const ownerScope = 'api:2';
    const pendingCreatedMs = Date.parse('2026-11-14T01:00:00Z');
    const pending = {
      ownerScope,
      idempotencyKey: key,
      itemsSnapshot: snapshot,
      cartSnapshot: [
        { productId: 1, sku: 'SP0001', name: 'Sữa tươi 1L', unitPriceVnd: 28000, quantity: 2 },
      ],
      totalVnd: 56000,
      lineCount: 1,
      reasonMessage: 'Chưa xác định được kết quả đơn hàng',
      createdAt: '2026-11-14T01:00:00Z',
    };
    assert.equal(savePendingCheckout(fakeSessionStorage, pending, ownerScope), true);

    // 2. User attempts to click "Mở khóa giỏ hàng" / start new checkout WITHOUT manual reconciliation confirmation -> BLOCKED
    const blockedAbandon = resolvePendingCheckoutAction({
      action: 'ABANDON',
      pendingCheckout: pending,
      manualReconciliationConfirmed: false,
      nowMs: pendingCreatedMs + 1000,
    });
    assert.equal(blockedAbandon.allowed, false);
    assert.equal(blockedAbandon.rotateKey, false);
    assert.equal(blockedAbandon.reason, 'MANUAL_RECONCILIATION_REQUIRED');
    assert.equal(blockedAbandon.nextPendingCheckout.idempotencyKey, key);

    const blockedNew = resolvePendingCheckoutAction({
      action: 'NEW_CHECKOUT',
      pendingCheckout: pending,
      manualReconciliationConfirmed: false,
      nowMs: pendingCreatedMs + 1000,
    });
    assert.equal(blockedNew.allowed, false);
    assert.equal(blockedNew.rotateKey, false);

    // 3. Simulate page reload/navigation: restored pendingCheckout keeps exact key and snapshot
    const restoredAfterReload = loadPendingCheckout(
      fakeSessionStorage,
      ownerScope,
      pendingCreatedMs + 1000
    );
    assert.ok(restoredAfterReload);
    assert.equal(restoredAfterReload.idempotencyKey, key);
    assert.deepEqual(restoredAfterReload.itemsSnapshot, snapshot);

    // 4. Retry with restored pendingCheckout recovers original order #99 without creating a duplicate
    const retryPlan = resolvePendingCheckoutAction({
      action: 'RETRY',
      pendingCheckout: restoredAfterReload,
      nowMs: pendingCreatedMs + 1000,
    });
    assert.equal(retryPlan.allowed, true);
    assert.equal(retryPlan.idempotencyKey, key);

    const recoveredOrder = await ordersApi.checkoutOrder({
      isMockMode: false,
      items: retryPlan.itemsSnapshot,
      idempotencyKey: retryPlan.idempotencyKey,
    });
    assert.equal(recoveredOrder.id, 99);
    assert.equal(backendCreateCount, 1);

    // 5. Clearing after confirmation/recovery works and allows manual reconciliation when explicitly confirmed
    const manualAbandon = resolvePendingCheckoutAction({
      action: 'ABANDON',
      pendingCheckout: pending,
      manualReconciliationConfirmed: true,
    });
    assert.equal(manualAbandon.allowed, true);
    assert.equal(manualAbandon.rotateKey, true);
    clearPendingCheckout(fakeSessionStorage, ownerScope);
    assert.equal(
      loadPendingCheckout(fakeSessionStorage, ownerScope, pendingCreatedMs + 1000),
      null
    );
  });
});
