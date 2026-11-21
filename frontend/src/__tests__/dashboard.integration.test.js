process.env.NODE_ENV = 'development';
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

import { JSDOM } from 'jsdom';
import path from 'path';
import fs from 'fs';
import { pathToFileURL } from 'url';
import test, { describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// 1. Setup DOM environment
const dom = new JSDOM('<!DOCTYPE html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/dashboard',
  pretendToBeVisual: true,
});
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, 'navigator', {
  value: dom.window.navigator,
  configurable: true,
  writable: true,
});
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.SVGElement = dom.window.SVGElement;
globalThis.HTMLInputElement = dom.window.HTMLInputElement;
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement;

// 2. Build minimal Dashboard test harness via Vite SSR into node_modules cache
const outDir = path.resolve('./node_modules/.cache_dashboard_test');
fs.mkdirSync(outDir, { recursive: true });
const entryPath = path.join(outDir, 'dashboardHarnessEntry.jsx');
fs.writeFileSync(
  entryPath,
  [
    "import Dashboard from '../../src/pages/Dashboard/Dashboard.jsx';",
    "import { AuthContext } from '../../src/context/AuthContext.jsx';",
    "import axiosClient from '../../src/api/axiosClient.js';",
    'export { Dashboard, AuthContext, axiosClient };',
    '',
  ].join('\n'),
  'utf8'
);

const { build } = await import('vite');
const react = (await import('@vitejs/plugin-react')).default;

await build({
  plugins: [react()],
  build: {
    ssr: true,
    write: true,
    outDir,
    rollupOptions: {
      input: entryPath,
    },
  },
  logLevel: 'silent',
});

const harnessUrl = pathToFileURL(path.join(outDir, 'dashboardHarnessEntry.js')).href;
const { Dashboard, AuthContext, axiosClient } = await import(harnessUrl);
const { render, screen, waitFor, fireEvent, act, cleanup } = await import(
  '@testing-library/react'
);
const React = await import('react');
const { MemoryRouter } = await import('react-router-dom');

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeSalesSummary({
  from = '2026-11-10',
  to = '2026-11-16',
  revenue = 1250000,
  completed = 5,
  cancelled = 1,
  aov = 250000,
} = {}) {
  return {
    period_start: `${from}T00:00:00+07:00`,
    period_end_exclusive: `${to}T23:59:59+07:00`,
    revenue_vnd: revenue,
    completed_orders: completed,
    cancelled_orders: cancelled,
    aov_vnd: aov,
  };
}

function renderDashboard() {
  return render(
    React.createElement(
      MemoryRouter,
      { initialEntries: ['/dashboard'] },
      React.createElement(
        AuthContext.Provider,
        {
          value: {
            user: { id: 1, username: 'admin', role: 'ADMIN' },
            isMockMode: false,
          },
        },
        React.createElement(Dashboard)
      )
    )
  );
}

describe('T04AB25 Dashboard Real React Component Regression Suite', () => {
  const originalGet = axiosClient.get;

  beforeEach(() => {
    cleanup();
    dom.window.document.body.innerHTML = '<div id="root"></div>';
  });

  afterEach(() => {
    cleanup();
    axiosClient.get = originalGet;
  });

  test('P1: switching from loaded Period A to failing Period B clears stale KPI/chart/table and renders fail-closed error', async () => {
    let failNextRequests = false;
    let requestCountDuringFailure = 0;

    axiosClient.get = async (url, config) => {
      if (failNextRequests) {
        requestCountDuringFailure += 1;
        const err = new Error('Server error');
        err.response = { status: 500, data: { detail: 'Lỗi máy chủ kỳ 30 ngày' } };
        throw err;
      }

      if (url === '/dashboard') {
        return {
          data: {
            sales: makeSalesSummary({
              from: config?.params?.from,
              to: config?.params?.to,
              revenue: 1250000,
              completed: 5,
              cancelled: 1,
              aov: 250000,
            }),
            low_stock_count: 3,
            top_products: [],
          },
        };
      }

      if (url === '/analytics/sales') {
        return {
          data: makeSalesSummary({
            from: config?.params?.from,
            to: config?.params?.to,
            revenue: 250000,
            completed: 1,
            cancelled: 0,
            aov: 250000,
          }),
        };
      }

      if (url === '/orders') {
        return {
          data: { items: [], total: 0, page: 1, page_size: 6 },
        };
      }

      throw new Error(`Unexpected GET ${url}`);
    };

    const view = renderDashboard();

    // Select Period A: "7 ngày gần nhất"
    const periodABtn = screen.getByRole('button', { name: '7 ngày gần nhất' });
    fireEvent.click(periodABtn);

    await waitFor(() => {
      assert.ok(screen.getAllByText('1.250.000 ₫').length > 0);
      assert.ok(screen.getByText('Doanh thu theo ngày'));
    });

    // Switch to Period B ("30 ngày qua") with HTTP 500 failure
    failNextRequests = true;
    const periodBBtn = screen.getByRole('button', { name: '30 ngày qua' });
    fireEvent.click(periodBBtn);

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      assert.match(alert.textContent, /Không thể tải dữ liệu Dashboard/);
      assert.match(alert.textContent, /Lỗi máy chủ kỳ 30 ngày/);
      assert.ok(screen.getByRole('button', { name: 'Thử lại' }));
    });

    const bodyText = document.body.textContent || '';
    // Period B header & weekly labels active
    assert.match(bodyText, /Biểu đồ xu hướng doanh thu theo tuần/);
    assert.match(bodyText, /Doanh thu theo tuần/);

    // Period A stale data MUST NOT appear anywhere under Period B
    assert.equal(bodyText.includes('1.250.000 ₫'), false, 'Stale KPI revenue from Period A leaked');
    assert.equal(bodyText.includes('250.000 ₫'), false, 'Stale AOV/bucket revenue from Period A leaked');
    assert.equal(bodyText.includes('Doanh thu theo ngày'), false, 'Stale Period A table title leaked');
    assert.equal(bodyText.includes('3 sản phẩm sắp hết'), false, 'Stale low_stock_count leaked');

    // Fail-closed: must NOT report 0 ₫ as verified revenue when Period B failed
    assert.equal(bodyText.includes('0 ₫'), false, 'Must not display 0 ₫ as verified revenue on error');

    // Bounded requests (no infinite retry loop)
    assert.ok(
      requestCountDuringFailure >= 1 && requestCountDuringFailure <= 10,
      `Expected bounded request count on failure, got ${requestCountDuringFailure}`
    );

    view.unmount();
  });

  test('P1 race: late-resolving Period A response does not overwrite newer Period B data', async () => {
    const slowPeriodADeferred = createDeferred();
    let mode = 'initial';

    axiosClient.get = async (url, config) => {
      if (mode === 'slowA' && url === '/dashboard') {
        const data = await slowPeriodADeferred.promise;
        return { data };
      }

      if (url === '/dashboard') {
        const revenue = mode === 'periodB' ? 9870000 : 100000;
        const completed = mode === 'periodB' ? 42 : 1;
        return {
          data: {
            sales: makeSalesSummary({
              from: config?.params?.from,
              to: config?.params?.to,
              revenue,
              completed,
              cancelled: 0,
              aov: Math.round(revenue / completed),
            }),
            low_stock_count: mode === 'periodB' ? 7 : 0,
            top_products: [],
          },
        };
      }

      if (url === '/analytics/sales') {
        const rev = mode === 'periodB' ? 1974000 : 50000;
        return {
          data: makeSalesSummary({
            from: config?.params?.from,
            to: config?.params?.to,
            revenue: rev,
            completed: mode === 'periodB' ? 8 : 1,
            cancelled: 0,
            aov: 250000,
          }),
        };
      }

      if (url === '/orders') {
        return { data: { items: [], total: 0, page: 1, page_size: 6 } };
      }

      throw new Error(`Unexpected GET ${url}`);
    };

    const view = renderDashboard();
    await waitFor(() => {
      assert.ok(screen.getAllByText('100.000 ₫').length > 0);
    });

    // Trigger slow Period A
    mode = 'slowA';
    fireEvent.click(screen.getByRole('button', { name: '7 ngày gần nhất' }));

    // Immediately switch to Period B and let it succeed
    mode = 'periodB';
    fireEvent.click(screen.getByRole('button', { name: '30 ngày qua' }));

    await waitFor(() => {
      assert.ok(screen.getAllByText('9.870.000 ₫').length > 0);
      assert.match(document.body.textContent || '', /42\s*đơn/);
    });

    // Now resolve slow Period A late with distinct revenue
    await act(async () => {
      slowPeriodADeferred.resolve({
        sales: makeSalesSummary({
          revenue: 555000,
          completed: 9,
          cancelled: 2,
          aov: 61667,
        }),
        low_stock_count: 99,
        top_products: [],
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    const finalText = document.body.textContent || '';
    assert.equal(finalText.includes('9.870.000 ₫'), true, 'Period B data must remain visible');
    assert.equal(finalText.includes('555.000 ₫'), false, 'Late Period A data must NOT overwrite Period B');

    view.unmount();
  });

  test('P2 fail-closed: nearlyOutOfStockCount shows "—" when out-of-stock count fails and drilldown links include date range', async () => {
    axiosClient.get = async (url, config) => {
      if (url === '/dashboard') {
        return {
          data: {
            sales: makeSalesSummary({ revenue: 500000, completed: 4, cancelled: 1, aov: 125000 }),
            low_stock_count: 8,
            top_products: [],
          },
        };
      }
      if (url === '/dashboard/revenue-chart') {
        return {
          data: makeChartResponse(config?.params?.days === 30 ? 'week' : 'day'),
        };
      }
      if (url === '/orders') {
        return { data: { items: [], total: 0, page: 1, page_size: 6 } };
      }
      if (url === '/inventory/low-stock') {
        return { data: { items: [], total: 8 } };
      }
      if (url === '/products') {
        throw new Error('Products count failed');
      }
      throw new Error(`Unexpected GET ${url}`);
    };

    const view = renderDashboard();

    await waitFor(() => {
      assert.match(document.body.textContent || '', /—\s*sản phẩm sắp hết/);
      assert.match(document.body.textContent || '', /—\s*sản phẩm hết hàng/);
    });

    const links = Array.from(document.querySelectorAll('a')).map((el) => el.getAttribute('href') || '');
    assert.ok(links.some((href) => href.startsWith('/orders?status=COMPLETED&from_date=') && href.includes('&to_date=')));
    assert.ok(links.some((href) => href.startsWith('/orders?status=CANCELLED&from_date=') && href.includes('&to_date=')));

    view.unmount();
  });
});
