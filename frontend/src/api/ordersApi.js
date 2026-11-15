import axiosClient from './axiosClient.js';
import { assertRealApiMode, isValidIsoTimestamp } from './productsApi.js';
import { normalizeOrderSearchQuery } from '../utils/orderUtils.js';

const MAX_CHECKOUT_LINES = 100;
const CHECKOUT_REQUEST_TIMEOUT_MS = 15000;
const CANCEL_REASON_MAX_LENGTH = 500;
const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9._:-]{16,128}$/;

function createClientValidationError(message) {
  const err = new Error(message);
  err.isClientValidation = true;
  return err;
}

export function generateCheckoutIdempotencyKey() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `pos-${globalThis.crypto.randomUUID()}`;
  }
  const rand = Math.random().toString(36).slice(2, 10);
  return `pos-${Date.now()}-${rand}`;
}

export function validateOrderRead(order) {
  if (!order || typeof order !== 'object' || Array.isArray(order)) {
    throw new Error('Order response payload must be an object.');
  }
  if (typeof order.id !== 'number' || !Number.isInteger(order.id) || order.id <= 0) {
    throw new Error(`Order missing valid integer id: ${JSON.stringify(order)}`);
  }
  if (typeof order.status !== 'string' || !order.status.trim()) {
    throw new Error(`Order ${order.id} missing valid status.`);
  }
  if (
    typeof order.total_vnd !== 'number' ||
    !Number.isInteger(order.total_vnd) ||
    order.total_vnd <= 0
  ) {
    throw new Error(`Order ${order.id} has invalid total_vnd.`);
  }
  if (!isValidIsoTimestamp(order.sold_at)) {
    throw new Error(`Order ${order.id} has invalid sold_at timestamp.`);
  }
  if (!Array.isArray(order.items) || order.items.length === 0) {
    throw new Error(`Order ${order.id} missing order line items.`);
  }
  return order;
}

export const ordersApi = {
  /**
   * Confirm POS sale via POST /api/v1/orders/checkout (ORD-01 / SALE-01).
   * Requires a valid Idempotency-Key header and strict CheckoutLine items.
   */
  async checkoutOrder({ isMockMode, items, idempotencyKey } = {}) {
    assertRealApiMode(isMockMode);

    if (!Array.isArray(items) || items.length === 0) {
      throw createClientValidationError('Giỏ hàng trống, không thể xác nhận bán hàng.');
    }
    if (items.length > MAX_CHECKOUT_LINES) {
      throw createClientValidationError(
        `Mỗi đơn hàng chỉ hỗ trợ tối đa ${MAX_CHECKOUT_LINES} dòng sản phẩm.`
      );
    }

    const normalizedItems = items.map((item) => {
      if (
        !item ||
        !Number.isInteger(item.product_id) ||
        item.product_id <= 0 ||
        !Number.isInteger(item.quantity) ||
        item.quantity <= 0 ||
        !Number.isInteger(item.viewed_unit_price_vnd) ||
        item.viewed_unit_price_vnd <= 0
      ) {
        throw createClientValidationError('Dữ liệu dòng sản phẩm thanh toán không hợp lệ.');
      }
      return {
        product_id: item.product_id,
        quantity: item.quantity,
        viewed_unit_price_vnd: item.viewed_unit_price_vnd,
      };
    });

    const key =
      typeof idempotencyKey === 'string' && IDEMPOTENCY_KEY_PATTERN.test(idempotencyKey)
        ? idempotencyKey
        : generateCheckoutIdempotencyKey();

    const response = await axiosClient.post(
      '/orders/checkout',
      { items: normalizedItems },
      {
        timeout: CHECKOUT_REQUEST_TIMEOUT_MS,
        headers: {
          'Idempotency-Key': key,
        },
      }
    );

    return validateOrderRead(response.data);
  },

  /**
   * Fetch paginated order history via GET /api/v1/orders (Real API only).
   */
  async getOrders({
    isMockMode,
    page = 1,
    pageSize = 20,
    status,
    fromDate,
    toDate,
    search,
  } = {}) {
    assertRealApiMode(isMockMode);

    const params = {
      page,
      page_size: pageSize,
    };
    if (status) params.status = status;
    if (fromDate) params.from_date = fromDate;
    if (toDate) params.to_date = toDate;
    const normalizedSearch = normalizeOrderSearchQuery(search);
    if (normalizedSearch) {
      params.search = normalizedSearch;
    }

    const response = await axiosClient.get('/orders', { params });
    const data = response.data;
    if (!data || !Array.isArray(data.items) || typeof data.total !== 'number') {
      throw new Error('Order list response payload is invalid.');
    }

    return {
      items: data.items.map(validateOrderRead),
      total: data.total,
      page: data.page ?? page,
      pageSize: data.page_size ?? pageSize,
    };
  },

  /**
   * Fetch single order details via GET /api/v1/orders/{order_id} (Real API only).
   */
  async getOrderById({ isMockMode, orderId } = {}) {
    assertRealApiMode(isMockMode);

    if (!Number.isInteger(orderId) || orderId <= 0) {
      throw createClientValidationError('Mã đơn hàng không hợp lệ.');
    }

    const response = await axiosClient.get(`/orders/${orderId}`);
    return validateOrderRead(response.data);
  },

  /**
   * Cancel a COMPLETED order via POST /api/v1/orders/{order_id}/cancel (Real API only).
   */
  async cancelOrder({ isMockMode, orderId, reason, idempotencyKey } = {}) {
    assertRealApiMode(isMockMode);

    if (!Number.isInteger(orderId) || orderId <= 0) {
      throw createClientValidationError('Mã đơn hàng không hợp lệ.');
    }

    const trimmedReason = typeof reason === 'string' ? reason.trim() : '';
    if (!trimmedReason) {
      throw createClientValidationError('Vui lòng nhập lý do hủy đơn hàng.');
    }
    if (trimmedReason.length > CANCEL_REASON_MAX_LENGTH) {
      throw createClientValidationError(
        `Lý do hủy đơn không được vượt quá ${CANCEL_REASON_MAX_LENGTH} ký tự.`
      );
    }

    const key =
      typeof idempotencyKey === 'string' && IDEMPOTENCY_KEY_PATTERN.test(idempotencyKey)
        ? idempotencyKey
        : generateCheckoutIdempotencyKey();

    const response = await axiosClient.post(
      `/orders/${orderId}/cancel`,
      { reason: trimmedReason },
      {
        timeout: CHECKOUT_REQUEST_TIMEOUT_MS,
        headers: {
          'Idempotency-Key': key,
        },
      }
    );

    return validateOrderRead(response.data);
  },

  /**
   * Contract alias: ordersApi.list(query) -> GET /api/v1/orders
   */
  async list(options = {}) {
    return this.getOrders(options);
  },

  /**
   * Contract alias: ordersApi.get(orderId) -> GET /api/v1/orders/{order_id}
   */
  async get(orderId, options = {}) {
    if (orderId && typeof orderId === 'object') {
      return this.getOrderById(orderId);
    }
    return this.getOrderById({ ...options, orderId });
  },

  /**
   * Contract alias: ordersApi.cancel(orderId, reason, key) -> POST /api/v1/orders/{order_id}/cancel
   */
  async cancel(orderId, reason, idempotencyKey, options = {}) {
    if (orderId && typeof orderId === 'object') {
      return this.cancelOrder(orderId);
    }
    return this.cancelOrder({
      ...options,
      orderId,
      reason,
      idempotencyKey,
    });
  },
};

export const checkoutApi = {
  /**
   * Contract alias: checkoutApi.checkout(items, key) -> POST /api/v1/orders/checkout
   */
  async checkout(items, idempotencyKey, options = {}) {
    if (items && !Array.isArray(items) && typeof items === 'object') {
      const payloadItems = Array.isArray(items.items) ? items.items : [];
      return ordersApi.checkoutOrder({
        ...options,
        ...items,
        items: payloadItems,
        idempotencyKey: idempotencyKey || items.idempotencyKey,
      });
    }
    return ordersApi.checkoutOrder({
      ...options,
      items,
      idempotencyKey,
    });
  },
};
