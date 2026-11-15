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
  formatOrderDateTimeVN,
  getVietnamBusinessDateKey,
  normalizeOrderSearchQuery,
} from '../utils/orderUtils.js';

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
});
