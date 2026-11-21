import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient, { isSafeToReplayRequest } from '../api/axiosClient.js';
import { ordersApi, generateCheckoutIdempotencyKey } from '../api/ordersApi.js';
import {
  DEFAULT_POS_PRODUCT_LIMIT,
  PENDING_CHECKOUT_TTL_MS,
  addProductToCart,
  applyInsufficientStockResolution,
  applyPriceChangedAcceptance,
  buildCheckoutPayload,
  buildInsufficientStockViewModel,
  buildPendingCheckoutOwnerScope,
  buildPriceChangedViewModel,
  calculateCartTotals,
  clampMobileSheetMaxHeight,
  classifyCheckoutError,
  clearPendingCheckout,
  computeMobileSheetDragState,
  executeSafePosCheckout,
  formatVnd,
  getPendingCheckoutStorageKey,
  loadPendingCheckout,
  prioritizeCategoriesByLatestProducts,
  resolveMobileSheetSwipeEnd,
  resolvePendingCheckoutAction,
  savePendingCheckout,
  shouldCloseMobileCartOnEscape,
  triggerDateInputPicker,
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
        persistedBeforeSend = fakeSessionStorage.getItem(
          getPendingCheckoutStorageKey(scopeA)
        );
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

  test('Multi-user storage isolation A -> B -> A: concurrent/sequential users never overwrite or delete each other pending checkouts', async () => {
    const backingStore = new Map();
    const sharedStorage = {
      getItem: (k) => (backingStore.has(k) ? backingStore.get(k) : null),
      setItem: (k, v) => backingStore.set(k, String(v)),
      removeItem: (k) => backingStore.delete(k),
    };

    const scopeA = buildPendingCheckoutOwnerScope({ id: 101 }, false);
    const scopeB = buildPendingCheckoutOwnerScope({ id: 202 }, false);
    assert.notEqual(
      getPendingCheckoutStorageKey(scopeA),
      getPendingCheckoutStorageKey(scopeB)
    );
    assert.equal(getPendingCheckoutStorageKey(null), null);

    const keyA = generateCheckoutIdempotencyKey();
    const keyB = generateCheckoutIdempotencyKey();
    const itemsA = [{ product_id: 1, quantity: 1, viewed_unit_price_vnd: 28000 }];
    const itemsB = [{ product_id: 2, quantity: 3, viewed_unit_price_vnd: 15000 }];
    const nowMs = 1_700_000_000_000;

    // 1. User A hits ambiguous timeout -> pending A persisted under A's key
    const resA = await executeSafePosCheckout({
      storage: sharedStorage,
      ownerScope: scopeA,
      isMockMode: false,
      itemsSnapshot: itemsA,
      totalVnd: 28000,
      lineCount: 1,
      idempotencyKey: keyA,
      nowMs,
      checkoutOrderFn: async () => {
        const err = new Error('timeout');
        err.code = 'ECONNABORTED';
        throw err;
      },
    });
    assert.equal(resA.outcome, 'AMBIGUOUS');

    // 2. User A logs out, User B logs in on same browser and hits ambiguous timeout -> pending B persisted under B's key
    assert.equal(loadPendingCheckout(sharedStorage, scopeB, nowMs + 1000), null);
    const resB = await executeSafePosCheckout({
      storage: sharedStorage,
      ownerScope: scopeB,
      isMockMode: false,
      itemsSnapshot: itemsB,
      totalVnd: 45000,
      lineCount: 1,
      idempotencyKey: keyB,
      nowMs: nowMs + 2000,
      checkoutOrderFn: async () => {
        const err = new Error('network error');
        err.code = 'ERR_NETWORK';
        throw err;
      },
    });
    assert.equal(resB.outcome, 'AMBIGUOUS');

    // 3. User B retries and succeeds (clears B's storage) -> User A's pending checkout MUST remain untouched!
    const retryB = await executeSafePosCheckout({
      storage: sharedStorage,
      ownerScope: scopeB,
      isMockMode: false,
      pendingCheckout: loadPendingCheckout(sharedStorage, scopeB, nowMs + 3000),
      nowMs: nowMs + 3000,
      checkoutOrderFn: async () => ({ id: 200, total_vnd: 45000 }),
    });
    assert.equal(retryB.ok, true);
    assert.equal(loadPendingCheckout(sharedStorage, scopeB, nowMs + 3000), null);

    // 4. User A logs back in / reloads -> User A's exact pending checkout is restored independently
    const restoredA = loadPendingCheckout(sharedStorage, scopeA, nowMs + 4000);
    assert.ok(restoredA);
    assert.equal(restoredA.idempotencyKey, keyA);
    assert.deepEqual(restoredA.itemsSnapshot, itemsA);
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

  test('T04A869 behavioral: handles HTTP 409 PRICE_CHANGED and INSUFFICIENT_STOCK using real Backend details and rotates Idempotency-Key', async () => {
    const backingStore = new Map();
    const fakeStorage = {
      getItem: (k) => (backingStore.has(k) ? backingStore.get(k) : null),
      setItem: (k, v) => backingStore.set(k, String(v)),
      removeItem: (k) => backingStore.delete(k),
    };
    const ownerScope = 'api:101';

    const cart = [
      {
        productId: 1,
        sku: 'SP0001',
        name: 'Nước suối 500ml',
        unitPriceVnd: 5000,
        quantity: 5,
        availableStock: 10,
      },
      {
        productId: 2,
        sku: 'SP0002',
        name: 'Sữa tươi 1L',
        unitPriceVnd: 28000,
        quantity: 2,
        availableStock: 42,
      },
      {
        productId: 5,
        sku: 'SP0005',
        name: 'Dầu ăn Tường An 1L',
        unitPriceVnd: 54000,
        quantity: 1,
        availableStock: 15,
      },
    ];

    // 1. Simulate HTTP 409 INSUFFICIENT_STOCK from Backend
    const stockDetails = {
      items: [{ product_id: 1, available_quantity: 3 }],
    };
    const stockRes = await executeSafePosCheckout({
      storage: fakeStorage,
      ownerScope,
      isMockMode: false,
      itemsSnapshot: buildCheckoutPayload(cart),
      cartSnapshot: cart,
      totalVnd: calculateCartTotals(cart).totalVnd,
      lineCount: cart.length,
      idempotencyKey: generateCheckoutIdempotencyKey(),
      checkoutOrderFn: async () => {
        const err = new Error('Không đủ tồn kho.');
        err.response = {
          status: 409,
          data: {
            code: 'INSUFFICIENT_STOCK',
            message: 'Không đủ tồn kho.',
            details: stockDetails,
          },
        };
        throw err;
      },
    });
    assert.equal(stockRes.ok, false);
    assert.equal(stockRes.outcome, 'DEFINITE_FAILURE');
    assert.equal(stockRes.apiCode, 'INSUFFICIENT_STOCK');
    assert.equal(stockRes.rotateKey, true);
    assert.deepEqual(stockRes.details, stockDetails);

    const stockVm = buildInsufficientStockViewModel(cart, stockRes.details);
    assert.equal(stockVm.primaryConflict.name, 'Nước suối 500ml');
    assert.equal(stockVm.primaryConflict.requestedQty, 5);
    assert.equal(stockVm.primaryConflict.availableQty, 3);
    assert.equal(stockVm.primaryConflict.shortageQty, 2);
    assert.equal(stockVm.singleAdjustableQty, 3);

    // Adjust to max (3) preserves other valid items and clamps product 1 to 3
    const adjustedCart = applyInsufficientStockResolution(
      cart,
      stockRes.details,
      'ADJUST_TO_MAX'
    );
    assert.equal(adjustedCart.length, 3);
    assert.equal(adjustedCart[0].quantity, 3);
    assert.equal(adjustedCart[0].availableStock, 3);
    assert.equal(adjustedCart[1].quantity, 2);

    // Remove insufficient removes only product 1, keeping products 2 and 5 intact
    const removedCart = applyInsufficientStockResolution(
      cart,
      stockRes.details,
      'REMOVE_INSUFFICIENT'
    );
    assert.equal(removedCart.length, 2);
    assert.deepEqual(
      removedCart.map((i) => i.productId),
      [2, 5]
    );

    // 2. Simulate HTTP 409 PRICE_CHANGED from Backend
    const priceDetails = {
      changed_items: [
        {
          product_id: 5,
          viewed_unit_price_vnd: 54000,
          current_unit_price_vnd: 56000,
        },
      ],
    };
    const priceRes = await executeSafePosCheckout({
      storage: fakeStorage,
      ownerScope,
      isMockMode: false,
      itemsSnapshot: buildCheckoutPayload(adjustedCart),
      cartSnapshot: adjustedCart,
      totalVnd: calculateCartTotals(adjustedCart).totalVnd,
      lineCount: adjustedCart.length,
      idempotencyKey: generateCheckoutIdempotencyKey(),
      checkoutOrderFn: async () => {
        const err = new Error('Giá bán đã thay đổi.');
        err.response = {
          status: 409,
          data: {
            code: 'PRICE_CHANGED',
            message: 'Giá bán đã thay đổi. Vui lòng xác nhận lại.',
            details: priceDetails,
          },
        };
        throw err;
      },
    });
    assert.equal(priceRes.ok, false);
    assert.equal(priceRes.apiCode, 'PRICE_CHANGED');
    assert.equal(priceRes.rotateKey, true);

    const priceVm = buildPriceChangedViewModel(adjustedCart, priceRes.details);
    assert.equal(priceVm.changedItems.length, 1);
    assert.equal(priceVm.changedItems[0].oldPriceVnd, 54000);
    assert.equal(priceVm.changedItems[0].newPriceVnd, 56000);
    assert.equal(priceVm.changedItems[0].diffVnd, 2000);
    assert.equal(priceVm.oldTotalVnd, 3 * 5000 + 2 * 28000 + 54000); // 125000
    assert.equal(priceVm.newTotalVnd, 3 * 5000 + 2 * 28000 + 56000); // 127000

    const repricedCart = applyPriceChangedAcceptance(adjustedCart, priceRes.details);
    assert.equal(
      repricedCart.find((i) => i.productId === 5).unitPriceVnd,
      56000
    );

    // 3. Verify PosPage.jsx contains the 3 real-API modals without trigger badges or mock data
    const posContent = fs.readFileSync(posPagePath, 'utf8');
    assert.ok(posContent.includes('Tồn kho không đủ (Insufficient Stock)'));
    assert.ok(posContent.includes('Xung đột giá bán (HTTP 409)'));
    assert.ok(posContent.includes('Xác nhận bán hàng thành công'));
    assert.ok(posContent.includes('✓ Xác nhận bán hàng'));
    assert.equal(posContent.includes('Trigger:'), false);
  });

  test('P1 cart item line displays both unit price and line total (unitPriceVnd * quantity)', () => {
    const qty3Item = {
      productId: 10,
      sku: 'SP0010',
      name: 'Nước khoáng 500ml',
      unitPriceVnd: 15000,
      quantity: 3,
      availableStock: 20,
    };
    const totals = calculateCartTotals([qty3Item]);
    assert.equal(totals.totalVnd, 45000);
    assert.ok(formatVnd(qty3Item.unitPriceVnd).includes('15.000'));
    assert.ok(formatVnd(qty3Item.unitPriceVnd * qty3Item.quantity).includes('45.000'));

    const posContent = fs.readFileSync(posPagePath, 'utf8');
    assert.ok(posContent.includes('className={styles.cartItemMeta}'));
    assert.ok(posContent.includes('Đơn giá: {formatVnd(item.unitPriceVnd)}'));
    assert.ok(posContent.includes('className={styles.lineTotal}'));
    assert.ok(posContent.includes('{formatVnd(item.unitPriceVnd * item.quantity)}'));
  });

  test('PR #103: PosPage avoids first-add white flash, cleans up mobile cart sheet state, supports Escape, and removes cartQuoteNote', () => {
    const posContent = fs.readFileSync(posPagePath, 'utf8');
    const posCssPath = path.resolve(__dirname, '../pages/Pos/PosPage.module.css');
    const posCssContent = fs.readFileSync(posCssPath, 'utf8');

    // 1. hasLoadedProductsRef prevents setIsLoading(true) flash on 12 <-> 10 pageSize switches
    assert.ok(posContent.includes('const hasLoadedProductsRef = useRef(false)'));
    assert.ok(posContent.includes('if (!hasLoadedProductsRef.current)'));
    assert.ok(posContent.includes('hasLoadedProductsRef.current = true'));

    // 2. Mobile cart sheet locks scroll, handles Escape without clobbering modals, and resets on empty/checkout
    assert.ok(posContent.includes("document.body.style.overflow = 'hidden'"));
    assert.ok(posContent.includes('shouldCloseMobileCartOnEscape'));
    assert.ok(posContent.includes('clampMobileSheetMaxHeight'));
    assert.ok(posContent.includes('if (nextCart.length === 0)'));
    assert.ok(
      (posContent.match(/setIsMobileCartExpanded\(false\)/g) || []).length >= 4,
      'Must reset isMobileCartExpanded on Escape, handleUpdateQty empty, handleClearCart, and checkout success'
    );

    // 3. Unused cartQuoteNote removed from both JSX and CSS
    assert.equal(posContent.includes('cartQuoteNote'), false);
    assert.equal(posCssContent.includes('cartQuoteNote'), false);
  });

  test('PR #103 behavioral: mobile cart sheet clamps maxHeight to 56vh, computes drag height/progress, and resolves swipe thresholds', () => {
    // 1. Clamping measured scrollHeight to 56vh (matches CSS max-height: 56vh)
    assert.equal(clampMobileSheetMaxHeight(720, 800), Math.round(800 * 0.56)); // 448px
    assert.equal(clampMobileSheetMaxHeight(220, 800), 220); // smaller than 56vh -> keep exact height
    assert.equal(clampMobileSheetMaxHeight(0, 800), 260); // fallback when unmeasured
    assert.equal(clampMobileSheetMaxHeight(600, 400), Math.round(400 * 0.56)); // 224px on short viewport

    // 2. Dragging up from collapsed state grows height and progress smoothly in [0..1]
    assert.deepEqual(
      computeMobileSheetDragState({ isExpanded: false, deltaY: -100, maxHeight: 400 }),
      { height: 100, progress: 0.25 }
    );
    assert.deepEqual(
      computeMobileSheetDragState({ isExpanded: false, deltaY: -600, maxHeight: 400 }),
      { height: 400, progress: 1 }
    );
    assert.deepEqual(
      computeMobileSheetDragState({ isExpanded: false, deltaY: 40, maxHeight: 400 }),
      { height: 0, progress: 0 }
    );

    // 3. Dragging down from expanded state shrinks height and progress smoothly in [0..1]
    assert.deepEqual(
      computeMobileSheetDragState({ isExpanded: true, deltaY: 100, maxHeight: 400 }),
      { height: 300, progress: 0.75 }
    );
    assert.deepEqual(
      computeMobileSheetDragState({ isExpanded: true, deltaY: 500, maxHeight: 400 }),
      { height: 0, progress: 0 }
    );

    // 4. Swipe release open/close thresholds & quick flick
    assert.deepEqual(
      resolveMobileSheetSwipeEnd({ isExpanded: false, deltaY: -40, elapsedMs: 300, maxHeight: 400 }),
      { nextExpanded: true, handled: true }
    );
    assert.deepEqual(
      resolveMobileSheetSwipeEnd({ isExpanded: false, deltaY: -20, elapsedMs: 30, maxHeight: 400 }),
      { nextExpanded: true, handled: true }
    );
    assert.deepEqual(
      resolveMobileSheetSwipeEnd({ isExpanded: false, deltaY: -15, elapsedMs: 300, maxHeight: 400 }),
      { nextExpanded: false, handled: false }
    );
    assert.deepEqual(
      resolveMobileSheetSwipeEnd({ isExpanded: true, deltaY: 50, elapsedMs: 300, maxHeight: 400 }),
      { nextExpanded: false, handled: true }
    );
    assert.deepEqual(
      resolveMobileSheetSwipeEnd({ isExpanded: true, deltaY: 20, elapsedMs: 30, maxHeight: 400 }),
      { nextExpanded: false, handled: true }
    );
    assert.deepEqual(
      resolveMobileSheetSwipeEnd({ isExpanded: true, deltaY: 20, elapsedMs: 300, maxHeight: 400 }),
      { nextExpanded: true, handled: false }
    );
  });

  test('PR #103 behavioral: Escape closes mobile cart sheet only when no conflict or receipt modal is open', () => {
    assert.equal(
      shouldCloseMobileCartOnEscape({
        key: 'Escape',
        stockConflictDetails: null,
        priceConflictDetails: null,
        completedOrder: null,
      }),
      true
    );
    assert.equal(
      shouldCloseMobileCartOnEscape({
        key: 'Enter',
        stockConflictDetails: null,
        priceConflictDetails: null,
        completedOrder: null,
      }),
      false
    );
    assert.equal(
      shouldCloseMobileCartOnEscape({
        key: 'Escape',
        stockConflictDetails: { insufficient_items: [] },
        priceConflictDetails: null,
        completedOrder: null,
      }),
      false
    );
    assert.equal(
      shouldCloseMobileCartOnEscape({
        key: 'Escape',
        stockConflictDetails: null,
        priceConflictDetails: { changed_items: [] },
        completedOrder: null,
      }),
      false
    );
    assert.equal(
      shouldCloseMobileCartOnEscape({
        key: 'Escape',
        stockConflictDetails: null,
        priceConflictDetails: null,
        completedOrder: { id: 99 },
      }),
      false
    );
  });

  test('PR #103 behavioral: date picker wrapper triggers showPicker(), skips direct input clicks, and falls back to focus()', () => {
    let showPickerCalls = 0;
    let focusCalls = 0;
    const mockInput = {
      showPicker: () => {
        showPickerCalls += 1;
      },
      focus: () => {
        focusCalls += 1;
      },
    };
    const mockWrapper = {
      querySelector: (selector) => (selector === 'input[type="date"]' ? mockInput : null),
    };

    // Clicking wrapper calls showPicker() without focus()
    assert.equal(triggerDateInputPicker(mockWrapper, mockWrapper), true);
    assert.equal(showPickerCalls, 1);
    assert.equal(focusCalls, 0);

    // Clicking directly on the input avoids duplicate showPicker()
    assert.equal(triggerDateInputPicker(mockWrapper, mockInput), false);
    assert.equal(showPickerCalls, 1);
    assert.equal(focusCalls, 0);

    // Throwing showPicker() falls back cleanly to focus()
    const throwingInput = {
      showPicker: () => {
        throw new Error('InvalidStateError');
      },
      focus: () => {
        focusCalls += 1;
      },
    };
    const throwingWrapper = {
      querySelector: () => throwingInput,
    };
    assert.equal(triggerDateInputPicker(throwingWrapper, throwingWrapper), true);
    assert.equal(focusCalls, 1);
  });
});
