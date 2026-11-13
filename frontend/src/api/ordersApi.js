import axiosClient from './axiosClient.js';
import { assertRealApiMode, isValidIsoTimestamp } from './productsApi.js';

const MAX_CHECKOUT_LINES = 100;
const CHECKOUT_REQUEST_TIMEOUT_MS = 15000;
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
};
