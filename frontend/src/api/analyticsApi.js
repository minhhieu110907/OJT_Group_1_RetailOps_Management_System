import axiosClient from './axiosClient.js';
import { assertRealApiMode, isValidIsoTimestamp } from './productsApi.js';

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function createClientValidationError(message) {
  const err = new Error(message);
  err.isClientValidation = true;
  return err;
}

function assertNonNegInt(value, fieldName) {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new Error(`Invalid ${fieldName}: expected non-negative integer.`);
  }
}

export function validateDateQueryParam(value, fieldName) {
  if (value === undefined || value === null || value === '') {
    return undefined;
  }
  const str = String(value).trim();
  if (!ISO_DATE_PATTERN.test(str)) {
    throw createClientValidationError(`Tham số ${fieldName} phải có định dạng YYYY-MM-DD.`);
  }
  return str;
}

export function validateSalesSummary(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('SalesSummary payload must be an object.');
  }
  if (!isValidIsoTimestamp(payload.period_start)) {
    throw new Error('SalesSummary missing valid period_start.');
  }
  if (!isValidIsoTimestamp(payload.period_end_exclusive)) {
    throw new Error('SalesSummary missing valid period_end_exclusive.');
  }
  assertNonNegInt(payload.revenue_vnd, 'revenue_vnd');
  assertNonNegInt(payload.completed_orders, 'completed_orders');
  assertNonNegInt(payload.cancelled_orders, 'cancelled_orders');
  assertNonNegInt(payload.aov_vnd, 'aov_vnd');
  return payload;
}

export function validateProductAnalyticsItem(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    throw new Error('ProductAnalyticsItem must be an object.');
  }
  if (typeof item.product_id !== 'number' || !Number.isInteger(item.product_id) || item.product_id <= 0) {
    throw new Error('ProductAnalyticsItem missing valid product_id.');
  }
  if (typeof item.sku !== 'string' || !item.sku.trim()) {
    throw new Error(`ProductAnalyticsItem ${item.product_id} missing valid sku.`);
  }
  if (typeof item.name !== 'string' || !item.name.trim()) {
    throw new Error(`ProductAnalyticsItem ${item.product_id} missing valid name.`);
  }
  assertNonNegInt(item.sold_units, 'sold_units');
  assertNonNegInt(item.revenue_vnd, 'revenue_vnd');
  if (item.quantity !== undefined && item.quantity !== null) {
    assertNonNegInt(item.quantity, 'quantity');
  }
  if (item.first_stocked_at !== undefined && item.first_stocked_at !== null) {
    if (!isValidIsoTimestamp(item.first_stocked_at)) {
      throw new Error(`ProductAnalyticsItem ${item.product_id} has invalid first_stocked_at.`);
    }
  }
  return item;
}

export function validateDashboardRead(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('DashboardRead payload must be an object.');
  }
  validateSalesSummary(payload.sales);
  assertNonNegInt(payload.low_stock_count, 'low_stock_count');
  if (!Array.isArray(payload.top_products)) {
    throw new Error('DashboardRead.top_products must be an array.');
  }
  payload.top_products.forEach(validateProductAnalyticsItem);
  return payload;
}

export function validateProductAnalyticsPage(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('ProductAnalyticsPage payload must be an object.');
  }
  if (!Array.isArray(payload.items)) {
    throw new Error('ProductAnalyticsPage.items must be an array.');
  }
  payload.items.forEach(validateProductAnalyticsItem);
  assertNonNegInt(payload.total, 'total');
  if (typeof payload.page !== 'number' || !Number.isInteger(payload.page) || payload.page < 1) {
    throw new Error('ProductAnalyticsPage.page must be >= 1.');
  }
  if (typeof payload.page_size !== 'number' || !Number.isInteger(payload.page_size) || payload.page_size < 1) {
    throw new Error('ProductAnalyticsPage.page_size must be >= 1.');
  }
  return payload;
}

export const analyticsApi = {
  async getDashboard({ isMockMode = false, from, to, signal } = {}) {
    assertRealApiMode(isMockMode);
    const params = {};
    const validFrom = validateDateQueryParam(from, 'from');
    const validTo = validateDateQueryParam(to, 'to');
    if (validFrom) params.from = validFrom;
    if (validTo) params.to = validTo;

    const response = await axiosClient.get('/dashboard', {
      params: Object.keys(params).length > 0 ? params : undefined,
      signal,
    });
    return validateDashboardRead(response.data);
  },

  async getSalesAnalytics({ isMockMode = false, from, to, signal } = {}) {
    assertRealApiMode(isMockMode);
    const params = {};
    const validFrom = validateDateQueryParam(from, 'from');
    const validTo = validateDateQueryParam(to, 'to');
    if (validFrom) params.from = validFrom;
    if (validTo) params.to = validTo;

    const response = await axiosClient.get('/analytics/sales', {
      params: Object.keys(params).length > 0 ? params : undefined,
      signal,
    });
    return validateSalesSummary(response.data);
  },

  async getTopProducts({ isMockMode = false, page = 1, page_size = 10, days = 30, signal } = {}) {
    assertRealApiMode(isMockMode);
    const safePage = Number.isInteger(page) && page >= 1 ? page : 1;
    const safePageSize = Number.isInteger(page_size) && page_size >= 1 && page_size <= 100 ? page_size : 10;
    const safeDays = Number.isInteger(days) && days >= 1 && days <= 366 ? days : 30;

    const response = await axiosClient.get('/analytics/products/top', {
      params: { page: safePage, page_size: safePageSize, days: safeDays },
      signal,
    });
    return validateProductAnalyticsPage(response.data);
  },

  async getSlowProducts({ isMockMode = false, page = 1, page_size = 10, signal } = {}) {
    assertRealApiMode(isMockMode);
    const safePage = Number.isInteger(page) && page >= 1 ? page : 1;
    const safePageSize = Number.isInteger(page_size) && page_size >= 1 && page_size <= 100 ? page_size : 10;

    const response = await axiosClient.get('/analytics/products/slow', {
      params: { page: safePage, page_size: safePageSize },
      signal,
    });
    return validateProductAnalyticsPage(response.data);
  },
};
