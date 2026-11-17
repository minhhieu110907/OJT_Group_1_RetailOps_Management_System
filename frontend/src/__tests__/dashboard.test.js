import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient from '../api/axiosClient.js';
import {
  analyticsApi,
  validateDashboardRead,
  validateProductAnalyticsPage,
  validateSalesSummary,
} from '../api/analyticsApi.js';
import {
  buildDashboardSeriesBuckets,
  computeOrderStructureMetrics,
  computeProductBarPercent,
  DASHBOARD_PRESETS,
  executeGuardedDashboardFetch,
  formatVietnamDateTime,
  formatVietnamPeriodRange,
  getVietnamTodayIsoDate,
  resolveDashboardDateRange,
  shiftIsoDate,
} from '../utils/analyticsUtils.js';

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const VALID_SALES = {
  period_start: '2026-11-15T00:00:00+07:00',
  period_end_exclusive: '2026-11-16T00:00:00+07:00',
  revenue_vnd: 1250000,
  completed_orders: 5,
  cancelled_orders: 1,
  aov_vnd: 250000,
};

const VALID_TOP_PRODUCT = {
  product_id: 101,
  sku: 'SP-001',
  name: 'Cà phê sữa đá',
  sold_units: 12,
  revenue_vnd: 420000,
  quantity: 18,
  first_stocked_at: '2026-10-01T09:00:00+07:00',
};

describe('analyticsApi — T04AB25 Real API contract & fail-closed behavior', () => {
  let originalGet;

  beforeEach(() => {
    originalGet = axiosClient.get;
  });

  test('fails closed when isMockMode=true on all analytics endpoints', async () => {
    let called = false;
    axiosClient.get = async () => {
      called = true;
      return { data: {} };
    };

    try {
      await assert.rejects(
        () => analyticsApi.getDashboard({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () => analyticsApi.getSalesAnalytics({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () => analyticsApi.getTopProducts({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () => analyticsApi.getSlowProducts({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      assert.equal(called, false);
    } finally {
      axiosClient.get = originalGet;
    }
  });

  test('getDashboard passes from/to query params and validates DashboardRead', async () => {
    let capturedUrl = null;
    let capturedConfig = null;
    axiosClient.get = async (url, config) => {
      capturedUrl = url;
      capturedConfig = config;
      return {
        data: {
          sales: VALID_SALES,
          low_stock_count: 3,
          top_products: [VALID_TOP_PRODUCT],
        },
      };
    };

    try {
      const result = await analyticsApi.getDashboard({
        isMockMode: false,
        from: '2026-11-01',
        to: '2026-11-15',
      });
      assert.equal(capturedUrl, '/dashboard');
      assert.deepEqual(capturedConfig.params, {
        from: '2026-11-01',
        to: '2026-11-15',
      });
      assert.equal(result.low_stock_count, 3);
      assert.equal(result.sales.revenue_vnd, 1250000);
      assert.equal(result.top_products.length, 1);
    } finally {
      axiosClient.get = originalGet;
    }
  });

  test('rejects invalid date format before calling backend', async () => {
    let called = false;
    axiosClient.get = async () => {
      called = true;
      return { data: {} };
    };

    try {
      await assert.rejects(
        () => analyticsApi.getDashboard({ from: '15/11/2026', to: '2026-11-15' }),
        (err) => err.isClientValidation === true
      );
      assert.equal(called, false);
    } finally {
      axiosClient.get = originalGet;
    }
  });

  test('validates SalesSummary, DashboardRead, and ProductAnalyticsPage strictly', () => {
    assert.throws(() => validateSalesSummary(null));
    assert.throws(() => validateSalesSummary({ ...VALID_SALES, revenue_vnd: -1 }));
    assert.throws(() => validateDashboardRead({ sales: VALID_SALES, low_stock_count: 0 }));
    assert.throws(() =>
      validateProductAnalyticsPage({ items: [], total: 0, page: 0, page_size: 10 })
    );
    const validPage = validateProductAnalyticsPage({
      items: [VALID_TOP_PRODUCT],
      total: 1,
      page: 1,
      page_size: 10,
    });
    assert.equal(validPage.items[0].sku, 'SP-001');
  });

  test('propagates 401/403 errors without mock fallback', async () => {
    axiosClient.get = async () => {
      const err = new Error('Forbidden');
      err.response = { status: 403, data: { detail: 'Admin required' } };
      throw err;
    };

    try {
      await assert.rejects(
        () => analyticsApi.getDashboard({ isMockMode: false }),
        (err) => err.response?.status === 403
      );
    } finally {
      axiosClient.get = originalGet;
    }
  });
});

describe('analyticsUtils — 4 filter presets, weekly buckets & order breakdown', () => {
  test('resolves all 4 presets in Asia/Ho_Chi_Minh timezone', () => {
    // 2026-11-15T18:30:00Z is 2026-11-16T01:30:00+07:00 in Vietnam
    const nowUtc = new Date('2026-11-15T18:30:00Z');
    assert.equal(getVietnamTodayIsoDate(nowUtc), '2026-11-16');
    assert.equal(shiftIsoDate('2026-11-16', -6), '2026-11-10');

    const todayRange = resolveDashboardDateRange(DASHBOARD_PRESETS.TODAY, {}, nowUtc);
    assert.equal(todayRange.from, '2026-11-16');
    assert.equal(todayRange.to, '2026-11-16');

    const last7Range = resolveDashboardDateRange(DASHBOARD_PRESETS.LAST_7_DAYS, {}, nowUtc);
    assert.equal(last7Range.from, '2026-11-10');
    assert.equal(last7Range.to, '2026-11-16');

    const last30Range = resolveDashboardDateRange(DASHBOARD_PRESETS.LAST_30_DAYS, {}, nowUtc);
    assert.equal(last30Range.from, '2026-10-18');
    assert.equal(last30Range.to, '2026-11-16');

    const monthRange = resolveDashboardDateRange(DASHBOARD_PRESETS.THIS_MONTH, {}, nowUtc);
    assert.equal(monthRange.from, '2026-11-01');
    assert.equal(monthRange.to, '2026-11-16');
  });

  test('buildDashboardSeriesBuckets builds 7 daily buckets and 4-5 weekly buckets accurately', () => {
    const nowUtc = new Date('2026-11-15T18:30:00Z'); // 2026-11-16 VN

    const dailyBuckets = buildDashboardSeriesBuckets(DASHBOARD_PRESETS.LAST_7_DAYS, nowUtc);
    assert.equal(dailyBuckets.length, 7);
    assert.equal(dailyBuckets[0].from, '2026-11-10');
    assert.equal(dailyBuckets[6].to, '2026-11-16');

    const thirtyDayBuckets = buildDashboardSeriesBuckets(
      DASHBOARD_PRESETS.LAST_30_DAYS,
      nowUtc
    );
    assert.equal(thirtyDayBuckets.length, 5);
    assert.equal(thirtyDayBuckets[0].from, '2026-10-18');
    assert.equal(thirtyDayBuckets[4].to, '2026-11-16');

    const monthBuckets = buildDashboardSeriesBuckets(DASHBOARD_PRESETS.THIS_MONTH, nowUtc);
    assert.equal(monthBuckets.length, 3); // 01-07, 08-14, 15-16
    assert.equal(monthBuckets[0].from, '2026-11-01');
    assert.equal(monthBuckets[2].to, '2026-11-16');
  });

  test('computeOrderStructureMetrics computes completion & cancellation rates cleanly', () => {
    const empty = computeOrderStructureMetrics(0, 0);
    assert.equal(empty.total, 0);
    assert.equal(empty.completedPctLabel, '0%');

    const sample = computeOrderStructureMetrics(86, 2);
    assert.equal(sample.total, 88);
    assert.equal(sample.completedPctLabel, '97,7%');
    assert.equal(sample.cancelledPctLabel, '2,3%');
  });

  test('formats exclusive period range and timestamps in Asia/Ho_Chi_Minh', () => {
    const singleDay = formatVietnamPeriodRange(
      '2026-11-15T00:00:00+07:00',
      '2026-11-16T00:00:00+07:00'
    );
    assert.equal(singleDay, '15/11/2026');

    const multiDay = formatVietnamPeriodRange(
      '2026-11-01T00:00:00+07:00',
      '2026-11-16T00:00:00+07:00'
    );
    assert.equal(multiDay, '01/11/2026 – 15/11/2026');

    const dt = formatVietnamDateTime('2026-11-15T02:05:00Z');
    assert.match(dt, /15\/11\/2026/);
    assert.equal(computeProductBarPercent(50, 200), 25);
  });

  test('executeGuardedDashboardFetch prevents stale response A from overwriting B', async () => {
    const seqRef = { current: 0 };
    const isMountedRef = { current: true };
    const reqA = createDeferred();
    const reqB = createDeferred();

    let appliedData = null;
    let appliedError = null;
    let loading = true;

    const pA = executeGuardedDashboardFetch({
      seqRef,
      isMountedRef,
      fetcher: () => reqA.promise,
      onSuccess: (d) => {
        appliedData = d;
      },
      onError: (e) => {
        appliedError = e;
      },
      onFinally: () => {
        loading = false;
      },
    });

    const pB = executeGuardedDashboardFetch({
      seqRef,
      isMountedRef,
      fetcher: () => reqB.promise,
      onSuccess: (d) => {
        appliedData = d;
      },
      onError: (e) => {
        appliedError = e;
      },
      onFinally: () => {
        loading = false;
      },
    });

    reqB.resolve({ tag: 'B' });
    await pB;
    assert.deepEqual(appliedData, { tag: 'B' });
    assert.equal(loading, false);

    reqA.reject(new Error('Stale A failure'));
    const resA = await pA;
    assert.equal(resA.status, 'stale');
    assert.deepEqual(appliedData, { tag: 'B' });
    assert.equal(appliedError, null);
  });
});

describe('Dashboard routing, RBAC & approved UI labels checks', () => {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const appPath = path.resolve(__dirname, '../App.jsx');
  const dashboardPath = path.resolve(__dirname, '../pages/Dashboard/Dashboard.jsx');

  test('App.jsx wires /dashboard to <Dashboard /> under ADMIN ProtectedRoute', () => {
    const appSource = fs.readFileSync(appPath, 'utf8');
    assert.match(appSource, /import Dashboard from '\.\/pages\/Dashboard\/Dashboard'/);
    assert.match(appSource, /<Route path="\/dashboard" element=\{<Dashboard \/>\} \/>/);
    assert.doesNotMatch(appSource, /PlaceholderPage title="Báo cáo Tổng quan Dashboard"/);
  });

  test('Dashboard.jsx enforces ADMIN guard and renders approved sections', () => {
    const dashSource = fs.readFileSync(dashboardPath, 'utf8');
    assert.match(dashSource, /user\?\.role === 'ADMIN'/);
    assert.match(dashSource, /Cơ cấu đơn &amp; Tỷ lệ hủy/);
    assert.match(dashSource, /Doanh thu trong ngày/);
    assert.match(dashSource, /Doanh thu theo ngày/);
    assert.match(dashSource, /Doanh thu theo tuần/);
  });
});
