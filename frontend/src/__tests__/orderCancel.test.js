import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient from '../api/axiosClient.js';
import { ordersApi, generateCheckoutIdempotencyKey } from '../api/ordersApi.js';
import {
  VN_TIMEZONE,
  classifyCancelOrderError,
  evaluateCancelOrderEligibility,
  executeGuardedOrderListFetch,
  executeVerifiedOrderDetailFetch,
  formatOrderActorLabel,
  formatOrderDateTimeVN,
  getVietnamBusinessDateKey,
  isCancelReasonLocked,
  normalizeOrderSearchQuery,
  reconcileCancelIntentWithAuthoritativeOrder,
  resolveCancelIntentForOrder,
} from '../utils/orderUtils.js';

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const cancelModalPath = path.resolve(
  __dirname,
  '../pages/Orders/CancelOrderModal.jsx'
);
const orderListPath = path.resolve(
  __dirname,
  '../pages/Orders/OrderList.jsx'
);
const orderDetailModalPath = path.resolve(
  __dirname,
  '../pages/Orders/OrderDetailModal.jsx'
);
const appPath = path.resolve(__dirname, '../App.jsx');

describe('T04A883 Order History & Cancel Order Test Suite', () => {
  beforeEach(() => {
    delete axiosClient.get;
    delete axiosClient.post;
  });

  test('timezone is strictly Asia/Ho_Chi_Minh', () => {
    assert.equal(VN_TIMEZONE, 'Asia/Ho_Chi_Minh');
    assert.equal(
      getVietnamBusinessDateKey('2026-11-14T16:59:59Z'),
      '2026-11-14'
    );
    // 17:00:00Z = 00:00:00 next day in Asia/Ho_Chi_Minh (+07:00)
    assert.equal(
      getVietnamBusinessDateKey('2026-11-14T17:00:00Z'),
      '2026-11-15'
    );
    assert.ok(formatOrderDateTimeVN('2026-11-14T09:45:00Z').includes('16:45:00'));
  });

  test('ordersApi enforces Real API mode (no mock fallback) and sends strict CancelRequest + Idempotency-Key', async () => {
    await assert.rejects(
      () => ordersApi.getOrders({ isMockMode: true }),
      (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
    );
    await assert.rejects(
      () =>
        ordersApi.cancelOrder({
          isMockMode: true,
          orderId: 108,
          reason: 'Khách đổi ý',
        }),
      (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
    );

    // Client validation on empty reason
    await assert.rejects(
      () =>
        ordersApi.cancelOrder({
          isMockMode: false,
          orderId: 108,
          reason: '   ',
        }),
      (err) => err.isClientValidation === true
    );

    let capturedPost = null;
    axiosClient.post = async (url, body, config) => {
      capturedPost = { url, body, config };
      return {
        data: {
          id: 108,
          status: 'CANCELLED',
          total_vnd: 185000,
          created_by: 2,
          sold_at: '2026-11-14T08:00:00Z',
          cancelled_by: 2,
          cancelled_at: '2026-11-14T08:07:00Z',
          cancel_reason: 'Khách hàng yêu cầu hủy đơn hàng',
          items: [
            {
              product_id: 1,
              sku_snapshot: 'SP0001',
              product_name_snapshot: 'Sữa hạt',
              quantity: 2,
              unit_price_vnd: 35000,
              line_total_vnd: 70000,
            },
          ],
        },
      };
    };

    const key = generateCheckoutIdempotencyKey();
    const cancelled = await ordersApi.cancelOrder({
      isMockMode: false,
      orderId: 108,
      reason: '  Khách hàng yêu cầu hủy đơn hàng  ',
      idempotencyKey: key,
    });

    assert.equal(cancelled.status, 'CANCELLED');
    assert.equal(capturedPost.url, '/orders/108/cancel');
    assert.deepEqual(capturedPost.body, {
      reason: 'Khách hàng yêu cầu hủy đơn hàng',
    });
    assert.equal(capturedPost.config.headers['Idempotency-Key'], key);
  });

  test('evaluateCancelOrderEligibility enforces role, ownership, 15m window, and Asia/Ho_Chi_Minh business day', () => {
    const soldAt = '2026-11-14T08:00:00Z'; // 15:00 Asia/Ho_Chi_Minh
    const soldMs = Date.parse(soldAt);
    const order = {
      id: 108,
      status: 'COMPLETED',
      created_by: 2,
      sold_at: soldAt,
    };
    const staffOwner = { id: 2, role: 'STAFF' };
    const otherStaff = { id: 3, role: 'STAFF' };
    const admin = { id: 1, role: 'ADMIN' };

    // Staff owner within 7 minutes -> allowed with 8 minutes remaining
    const within = evaluateCancelOrderEligibility({
      order,
      user: staffOwner,
      nowMs: soldMs + 7 * 60 * 1000,
    });
    assert.equal(within.canCancel, true);
    assert.equal(within.remainingMinutes, 8);

    // Staff owner after 16 minutes -> blocked
    const expired = evaluateCancelOrderEligibility({
      order,
      user: staffOwner,
      nowMs: soldMs + 16 * 60 * 1000,
    });
    assert.equal(expired.canCancel, false);
    assert.equal(expired.reason, 'WINDOW_EXPIRED');

    // Another staff -> blocked
    const notOwner = evaluateCancelOrderEligibility({
      order,
      user: otherStaff,
      nowMs: soldMs + 2 * 60 * 1000,
    });
    assert.equal(notOwner.canCancel, false);
    assert.equal(notOwner.reason, 'NOT_OWNER');

    // Admin same VN business day after 2 hours -> allowed
    const adminSameDay = evaluateCancelOrderEligibility({
      order,
      user: admin,
      nowMs: soldMs + 2 * 60 * 60 * 1000,
    });
    assert.equal(adminSameDay.canCancel, true);

    // Admin next VN business day -> blocked
    const adminNextDay = evaluateCancelOrderEligibility({
      order,
      user: admin,
      nowMs: Date.parse('2026-11-14T17:05:00Z'), // 00:05 next day VN
    });
    assert.equal(adminNextDay.canCancel, false);
    assert.equal(adminNextDay.reason, 'DIFFERENT_BUSINESS_DAY');
  });

  test('classifyCancelOrderError separates INELIGIBLE (Lỗi 1), DATA_CHANGED (Lỗi 2), and AMBIGUOUS', () => {
    assert.equal(
      classifyCancelOrderError({
        response: { status: 403, data: { code: 'FORBIDDEN', message: 'Quá hạn 15 phút.' } },
      }).outcome,
      'INELIGIBLE'
    );
    assert.equal(
      classifyCancelOrderError({
        response: {
          status: 409,
          data: { code: 'CANCEL_WINDOW_EXPIRED', message: 'Quá thời hạn.' },
        },
      }).outcome,
      'INELIGIBLE'
    );
    assert.equal(
      classifyCancelOrderError({
        response: {
          status: 409,
          data: {
            code: 'INVALID_STATE',
            message: 'Đơn hàng không còn ở trạng thái COMPLETED.',
          },
        },
      }).outcome,
      'DATA_CHANGED'
    );
    assert.equal(
      classifyCancelOrderError({
        response: {
          status: 409,
          data: { code: 'ORDER_ALREADY_CANCELLED', message: 'Đơn đã hủy trước đó.' },
        },
      }).outcome,
      'DATA_CHANGED'
    );
    assert.equal(
      classifyCancelOrderError({ code: 'ECONNABORTED' }).outcome,
      'AMBIGUOUS'
    );
  });

  test('CancelOrderModal renders clean Vietnamese titles without BIẾN THỂ labels', () => {
    const content = fs.readFileSync(cancelModalPath, 'utf8');
    assert.ok(content.includes('Xác nhận hủy đơn hàng'));
    assert.ok(content.includes('Không đủ điều kiện hủy đơn'));
    assert.ok(content.includes('Dữ liệu đơn hàng bị thay đổi'));
    assert.ok(content.includes('Tải lại trạng thái đơn'));
    assert.equal(content.includes('BIẾN THỂ'), false);
  });

  test('normalizeOrderSearchQuery strips leading # from numeric order IDs and ordersApi.getOrders passes single-day filter', async () => {
    assert.equal(normalizeOrderSearchQuery('#108'), '108');
    assert.equal(normalizeOrderSearchQuery('  #99 '), '99');
    assert.equal(normalizeOrderSearchQuery('SP0001'), 'SP0001');

    let capturedGet = null;
    axiosClient.get = async (url, config) => {
      capturedGet = { url, config };
      return {
        data: {
          items: [
            {
              id: 108,
              status: 'COMPLETED',
              total_vnd: 185000,
              created_by: 2,
              sold_at: '2026-11-15T10:12:00Z',
              cancelled_by: null,
              cancelled_at: null,
              cancel_reason: null,
              items: [
                {
                  product_id: 1,
                  sku_snapshot: 'SP0001',
                  product_name_snapshot: 'Sữa hạt',
                  quantity: 2,
                  unit_price_vnd: 35000,
                  line_total_vnd: 70000,
                },
              ],
            },
          ],
          total: 1,
          page: 1,
          page_size: 10,
        },
      };
    };

    const result = await ordersApi.getOrders({
      isMockMode: false,
      page: 1,
      pageSize: 10,
      status: 'COMPLETED',
      fromDate: '2026-11-15',
      toDate: '2026-11-15',
      search: '#108',
    });

    assert.equal(result.total, 1);
    assert.equal(capturedGet.url, '/orders');
    assert.deepEqual(capturedGet.config.params, {
      page: 1,
      page_size: 10,
      status: 'COMPLETED',
      from_date: '2026-11-15',
      to_date: '2026-11-15',
      search: '108',
    });
  });

  test('OrderList, OrderDetailModal, and App route /orders match approved single-row filter and Đã hoàn tất UI design', () => {
    const orderListSrc = fs.readFileSync(orderListPath, 'utf8');
    const detailModalSrc = fs.readFileSync(orderDetailModalPath, 'utf8');
    const appSrc = fs.readFileSync(appPath, 'utf8');

    // Single-row filter bar & placeholder "Theo mã đơn"
    assert.ok(orderListSrc.includes('filterRowSingle'));
    assert.ok(orderListSrc.includes('placeholder="Theo mã đơn"'));
    assert.ok(orderListSrc.includes('Ngày bán:'));
    assert.ok(orderListSrc.includes('fromDate: selectedDate || undefined'));
    assert.ok(orderListSrc.includes('toDate: selectedDate || undefined'));

    // Status badge text "Đã hoàn tất" and "Đã hủy" (not "Đơn đã hoàn tất")
    assert.ok(orderListSrc.includes('Đã hoàn tất'));
    assert.ok(orderListSrc.includes('Đã hủy'));
    assert.equal(orderListSrc.includes('Đơn đã hoàn tất'), false);

    // Detail modal & CancelOrderModal integration
    assert.ok(orderListSrc.includes('Xem chi tiết'));
    assert.ok(detailModalSrc.includes('Chi tiết đơn hàng #'));
    assert.ok(detailModalSrc.includes('Đã hoàn tất'));
    assert.ok(detailModalSrc.includes('Hủy đơn hàng'));
    assert.equal(detailModalSrc.includes('BIẾN THỂ'), false);

    // Route /orders wired to OrderList in App.jsx
    assert.ok(appSrc.includes('path="/orders" element={<OrderList />}'));
  });

  test('P1 OrderList stale-response guard: slow A vs fast B, late error A, loading accuracy, and unmount isolation', async () => {
    const seqRef = { current: 0 };
    const isMountedRef = { current: true };
    const state = {
      orders: [],
      total: 0,
      errorMessage: '',
      isLoading: false,
    };

    const reqA = createDeferred();
    const reqB = createDeferred();

    // Start Request A (slow) then Request B (fast)
    const pA = executeGuardedOrderListFetch({
      seqRef,
      isMountedRef,
      fetchFn: () => reqA.promise,
      onStart: () => {
        state.isLoading = true;
        state.errorMessage = '';
      },
      onSuccess: (res) => {
        state.orders = res.items;
        state.total = res.total;
      },
      onError: () => {
        state.errorMessage = 'errA';
      },
      onFinally: () => {
        state.isLoading = false;
      },
    });

    const pB = executeGuardedOrderListFetch({
      seqRef,
      isMountedRef,
      fetchFn: () => reqB.promise,
      onStart: () => {
        state.isLoading = true;
        state.errorMessage = '';
      },
      onSuccess: (res) => {
        state.orders = res.items;
        state.total = res.total;
      },
      onError: () => {
        state.errorMessage = 'errB';
      },
      onFinally: () => {
        state.isLoading = false;
      },
    });

    // If A resolves while B is still pending -> isLoading MUST stay true and state untouched
    reqA.resolve({ items: [{ id: 101 }], total: 1 });
    const resA = await pA;
    assert.equal(resA.stale, true);
    assert.equal(state.isLoading, true);
    assert.deepEqual(state.orders, []);

    // B resolves -> B wins
    reqB.resolve({ items: [{ id: 202 }], total: 1 });
    const resB = await pB;
    assert.equal(resB.applied, true);
    assert.equal(state.isLoading, false);
    assert.deepEqual(state.orders, [{ id: 202 }]);
    assert.equal(state.total, 1);

    // Late error from a stale Request C while D succeeded must NOT overwrite D
    const reqC = createDeferred();
    const reqD = createDeferred();
    const pC = executeGuardedOrderListFetch({
      seqRef,
      isMountedRef,
      fetchFn: () => reqC.promise,
      onStart: () => {
        state.isLoading = true;
        state.errorMessage = '';
      },
      onSuccess: (res) => {
        state.orders = res.items;
        state.total = res.total;
      },
      onError: () => {
        state.errorMessage = 'stale-error';
        state.orders = [];
      },
      onFinally: () => {
        state.isLoading = false;
      },
    });
    const pD = executeGuardedOrderListFetch({
      seqRef,
      isMountedRef,
      fetchFn: () => reqD.promise,
      onStart: () => {
        state.isLoading = true;
        state.errorMessage = '';
      },
      onSuccess: (res) => {
        state.orders = res.items;
        state.total = res.total;
      },
      onError: () => {
        state.errorMessage = 'errD';
      },
      onFinally: () => {
        state.isLoading = false;
      },
    });
    reqD.resolve({ items: [{ id: 303 }], total: 1 });
    await pD;
    reqC.reject(new Error('late timeout'));
    await pC;
    assert.equal(state.errorMessage, '');
    assert.deepEqual(state.orders, [{ id: 303 }]);

    // Unmount while Request E is in flight -> no state mutation
    const reqE = createDeferred();
    let mutatedAfterUnmount = false;
    const pE = executeGuardedOrderListFetch({
      seqRef,
      isMountedRef,
      fetchFn: () => reqE.promise,
      onSuccess: () => {
        mutatedAfterUnmount = true;
      },
      onError: () => {
        mutatedAfterUnmount = true;
      },
      onFinally: () => {
        mutatedAfterUnmount = true;
      },
    });
    isMountedRef.current = false;
    reqE.resolve({ items: [{ id: 404 }], total: 1 });
    const resE = await pE;
    assert.equal(resE.stale, true);
    assert.equal(mutatedAfterUnmount, false);
  });

  test('P1 OrderDetail verified state: blocks stale A over B, blocks cancel on close/failure/CANCELLED, allows only verified COMPLETED', async () => {
    const seqRef = { current: 0 };
    const isMountedRef = { current: true };
    let detailState = { order: null, status: 'idle', error: '' };

    const deferredA = createDeferred();
    const deferredB = createDeferred();

    // Open Order A, then immediately open Order B
    const pA = executeVerifiedOrderDetailFetch({
      seqRef,
      isMountedRef,
      orderSnapshot: { id: 101, status: 'COMPLETED' },
      fetchByIdFn: () => deferredA.promise,
      onLoading: (snap) => {
        detailState = { order: snap, status: 'loading', error: '' };
      },
      onVerified: (fresh) => {
        detailState = { order: fresh, status: 'verified', error: '' };
      },
      onError: () => {
        detailState = { ...detailState, status: 'error', error: 'errA' };
      },
    });

    const pB = executeVerifiedOrderDetailFetch({
      seqRef,
      isMountedRef,
      orderSnapshot: { id: 102, status: 'COMPLETED' },
      fetchByIdFn: () => deferredB.promise,
      onLoading: (snap) => {
        detailState = { order: snap, status: 'loading', error: '' };
      },
      onVerified: (fresh) => {
        detailState = { order: fresh, status: 'verified', error: '' };
      },
      onError: () => {
        detailState = { ...detailState, status: 'error', error: 'errB' };
      },
    });

    // B resolves COMPLETED -> verified
    deferredB.resolve({ id: 102, status: 'COMPLETED', created_by: 1, sold_at: '2026-11-15T10:00:00Z' });
    await pB;
    assert.equal(detailState.status, 'verified');
    assert.equal(detailState.order.id, 102);

    // Stale A resolves late -> MUST NOT overwrite B
    deferredA.resolve({ id: 101, status: 'COMPLETED', created_by: 1, sold_at: '2026-11-15T09:00:00Z' });
    const resA = await pA;
    assert.equal(resA.stale, true);
    assert.equal(detailState.order.id, 102);

    // Close modal while request C is in flight -> invalidates C
    const deferredC = createDeferred();
    const pC = executeVerifiedOrderDetailFetch({
      seqRef,
      isMountedRef,
      orderSnapshot: { id: 103, status: 'COMPLETED' },
      fetchByIdFn: () => deferredC.promise,
      onLoading: (snap) => {
        detailState = { order: snap, status: 'loading', error: '' };
      },
      onVerified: (fresh) => {
        detailState = { order: fresh, status: 'verified', error: '' };
      },
      onError: () => {
        detailState = { ...detailState, status: 'error', error: 'errC' };
      },
    });
    seqRef.current += 1;
    detailState = { order: null, status: 'idle', error: '' };
    deferredC.resolve({ id: 103, status: 'COMPLETED' });
    const resC = await pC;
    assert.equal(resC.stale, true);
    assert.equal(detailState.status, 'idle');

    // GET detail fails -> status=error (cancel disabled)
    const pErr = executeVerifiedOrderDetailFetch({
      seqRef,
      isMountedRef,
      orderSnapshot: { id: 104, status: 'COMPLETED' },
      fetchByIdFn: async () => {
        throw new Error('403 Forbidden');
      },
      onLoading: (snap) => {
        detailState = { order: snap, status: 'loading', error: '' };
      },
      onVerified: (fresh) => {
        detailState = { order: fresh, status: 'verified', error: '' };
      },
      onError: () => {
        detailState = { ...detailState, status: 'error', error: 'Không thể xác minh' };
      },
    });
    await pErr;
    assert.equal(detailState.status, 'error');

    // GET detail returns CANCELLED -> cannot cancel even if list row looked COMPLETED
    const pCancelled = executeVerifiedOrderDetailFetch({
      seqRef,
      isMountedRef,
      orderSnapshot: { id: 105, status: 'COMPLETED' },
      fetchByIdFn: async () => ({ id: 105, status: 'CANCELLED', created_by: 1, sold_at: '2026-11-15T10:00:00Z' }),
      onLoading: (snap) => {
        detailState = { order: snap, status: 'loading', error: '' };
      },
      onVerified: (fresh) => {
        detailState = { order: fresh, status: 'verified', error: '' };
      },
      onError: () => {},
    });
    await pCancelled;
    assert.equal(detailState.status, 'verified');
    assert.equal(
      evaluateCancelOrderEligibility({ order: detailState.order, user: { id: 1, role: 'ADMIN' } }).canCancel,
      false
    );
  });

  test('P2 Cancel idempotency & reconciliation: preserves key/reason across modal reopen when ambiguous, reconciles authoritative state, and keeps feedback neutral', () => {
    let keyCounter = 0;
    const genKey = () => `pos-00000000-0000-4000-8000-00000000000${++keyCounter}`;

    const initial = resolveCancelIntentForOrder({
      existingIntent: null,
      orderId: 108,
      generateKeyFn: genKey,
    });
    assert.equal(initial.idempotencyKey, 'pos-00000000-0000-4000-8000-000000000001');

    // Simulate timeout -> ambiguous intent stored in parent
    const ambiguousIntent = {
      ...initial,
      reason: 'Khách đổi ý',
      normalizedReason: 'Khách đổi ý',
      outcome: 'ambiguous',
      ambiguousMessage: 'Mất kết nối',
    };
    assert.equal(isCancelReasonLocked(ambiguousIntent), true);

    // Closing and reopening modal for order 108 MUST reuse exact same key & reason
    const reopened = resolveCancelIntentForOrder({
      existingIntent: ambiguousIntent,
      orderId: 108,
      generateKeyFn: genKey,
    });
    assert.equal(reopened.idempotencyKey, ambiguousIntent.idempotencyKey);
    assert.equal(reopened.reason, 'Khách đổi ý');
    assert.equal(reopened.outcome, 'ambiguous');

    // Reconcile when authoritative order is still COMPLETED -> keep same key & ambiguous
    const stillCompleted = reconcileCancelIntentWithAuthoritativeOrder({
      intent: reopened,
      authoritativeOrder: { id: 108, status: 'COMPLETED' },
    });
    assert.equal(stillCompleted.status, 'STILL_COMPLETED');
    assert.equal(stillCompleted.nextIntent.idempotencyKey, ambiguousIntent.idempotencyKey);

    // Reconcile when authoritative order is CANCELLED -> neutral message, confirmed
    const alreadyCancelled = reconcileCancelIntentWithAuthoritativeOrder({
      intent: reopened,
      authoritativeOrder: { id: 108, status: 'CANCELLED' },
    });
    assert.equal(alreadyCancelled.status, 'ALREADY_CANCELLED');
    assert.equal(alreadyCancelled.nextIntent.outcome, 'confirmed');
    assert.equal(
      alreadyCancelled.message,
      'Đơn hàng đã ở trạng thái Đã hủy. Dữ liệu đã được cập nhật.'
    );

    // Definite failure -> reopening creates fresh key on new intent
    const failedIntent = { ...initial, outcome: 'definite_failure', reason: 'Lỗi' };
    const afterDefiniteFailure = resolveCancelIntentForOrder({
      existingIntent: failedIntent,
      orderId: 108,
      generateKeyFn: genKey,
    });
    assert.notEqual(afterDefiniteFailure.idempotencyKey, failedIntent.idempotencyKey);

    // Feedback clarity checks
    assert.equal(formatOrderActorLabel(99, { id: 2, role: 'STAFF' }), 'Tài khoản #99');
    assert.equal(formatOrderActorLabel(1, { id: 1, role: 'ADMIN' }), 'Admin #1');

    const adminIneligible = classifyCancelOrderError(
      { response: { status: 403, data: { code: 'FORBIDDEN' } } },
      { actorRole: 'ADMIN' }
    );
    assert.equal(adminIneligible.outcome, 'INELIGIBLE');
    assert.equal(adminIneligible.message.includes('15 phút'), false);

    const dataChanged = classifyCancelOrderError({
      response: { status: 409, data: { code: 'INVALID_STATE' } },
    });
    assert.equal(dataChanged.outcome, 'DATA_CHANGED');
    assert.equal(dataChanged.message.includes('đã được hủy trước đó'), false);
    assert.equal(dataChanged.message.includes('hoàn trả'), false);
  });
});
