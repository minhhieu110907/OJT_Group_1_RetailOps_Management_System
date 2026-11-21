process.env.NODE_ENV = 'development';
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

import { JSDOM } from 'jsdom';
import path from 'path';
import fs from 'fs';
import { pathToFileURL } from 'url';
import test, { describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

const dom = new JSDOM('<!DOCTYPE html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/ai-assistant',
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
globalThis.HTMLInputElement = dom.window.HTMLInputElement;
globalThis.HTMLSelectElement = dom.window.HTMLSelectElement;
globalThis.HTMLTextAreaElement = dom.window.HTMLTextAreaElement;
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement;

const outDir = path.resolve('./node_modules/.cache_ai_test');
fs.mkdirSync(outDir, { recursive: true });
const entryPath = path.join(outDir, 'aiHarnessEntry.jsx');
fs.writeFileSync(
  entryPath,
  [
    "import { MemoryRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';",
    "import AiAssistant from '../../src/pages/AiAssistant/AiAssistant.jsx';",
    "import PurchaseList from '../../src/pages/Purchases/PurchaseList.jsx';",
    "import { ToastProvider } from '../../src/components/common/index.js';",
    "import { AuthContext } from '../../src/context/AuthContext.jsx';",
    "import axiosClient from '../../src/api/axiosClient.js';",
    'export { MemoryRouter, Routes, Route, useLocation, useNavigate, AiAssistant, PurchaseList, ToastProvider, AuthContext, axiosClient };',
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

const harnessUrl = pathToFileURL(path.join(outDir, 'aiHarnessEntry.js')).href;
const {
  MemoryRouter,
  Routes,
  Route,
  useLocation,
  useNavigate,
  AiAssistant,
  PurchaseList,
  ToastProvider,
  AuthContext,
  axiosClient,
} = await import(harnessUrl);
const { render, screen, waitFor, fireEvent, act, cleanup } = await import(
  '@testing-library/react'
);
const React = await import('react');

function renderAiAssistant(role = 'ADMIN') {
  return render(
    React.createElement(
      AuthContext.Provider,
      {
        value: {
          user: { id: 1, username: role === 'ADMIN' ? 'admin' : 'staff01', role },
          isMockMode: false,
        },
      },
      React.createElement(AiAssistant)
    )
  );
}

describe('T04AB25 AiAssistant Real React Component Integration Suite', () => {
  const originalPost = axiosClient.post;
  const originalGet = axiosClient.get;

  beforeEach(() => {
    cleanup();
    dom.window.document.body.innerHTML = '<div id="root"></div>';
    axiosClient.get = async (url) => {
      if (url === '/inventory/low-stock') {
        return { data: { items: [], total: 0, page: 1, page_size: 20 } };
      }
      if (url === '/analytics/products/top') {
        return { data: { items: [], total: 0, page: 1, page_size: 20 } };
      }
      if (url === '/suppliers') {
        return { data: { items: [], total: 0, page: 1, page_size: 100 } };
      }
      return { data: {} };
    };
  });

  afterEach(() => {
    cleanup();
    axiosClient.post = originalPost;
    axiosClient.get = originalGet;
  });

  test('ADMIN submits prompt -> shows processing state -> renders answer & evidence cards', async () => {
    let resolveAsk;
    const askPromise = new Promise((res) => {
      resolveAsk = res;
    });

    let capturedPayload = null;
    axiosClient.post = async (url, body) => {
      assert.equal(url, '/ai/query');
      capturedPayload = body;
      return askPromise;
    };

    const view = renderAiAssistant('ADMIN');
    const textarea = screen.getByLabelText('Nhập câu hỏi cho Trợ lý AI');
    fireEvent.change(textarea, { target: { value: 'Sản phẩm nào sắp hết hàng?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi câu hỏi' }));

    await waitFor(() => {
      assert.ok(screen.getByText('Đang phân tích dữ liệu bán hàng và tồn kho...'));
    });

    resolveAsk({
      data: {
        answer: 'Hiện có 2 sản phẩm dưới ngưỡng tồn an toàn, gợi ý nhập thêm.',
        evidence: [
          {
            source: 'inventory.low_stock',
            period: 'Hiện tại (17/11/2026)',
            summary: 'Coca Cola 330ml còn 3 lon; Nước suối còn 2 chai.',
          },
        ],
        insufficient_data: false,
      },
    });

    await waitFor(() => {
      assert.ok(screen.getByText('Hiện có 2 sản phẩm dưới ngưỡng tồn an toàn, gợi ý nhập thêm.'));
      assert.ok(screen.getByText(/Nguồn dữ liệu & Dẫn chứng/));
      assert.ok(screen.getByText('inventory.low_stock'));
      assert.ok(screen.getByText('Hiện tại (17/11/2026)'));
      assert.ok(screen.getByText('Coca Cola 330ml còn 3 lon; Nước suối còn 2 chai.'));
    });

    assert.deepEqual(capturedPayload, { message: 'Sản phẩm nào sắp hết hàng?' });
    view.unmount();
  });

  test('handles timeout (Thử lại) -> insufficient_data (Thu hẹp câu hỏi) and 429 quota (Đóng)', async () => {
    let attempt = 0;
    axiosClient.post = async () => {
      attempt += 1;
      if (attempt === 1) {
        const err = new Error('timeout');
        err.code = 'ECONNABORTED';
        throw err;
      }
      if (attempt === 2) {
        return {
          data: {
            answer: 'Chưa có đủ dữ liệu bán hàng trong kỳ để đưa ra dự báo.',
            evidence: [],
            insufficient_data: true,
          },
        };
      }
      const err = new Error('Too Many Requests');
      err.response = { status: 429, data: { detail: 'Rate limit' } };
      throw err;
    };

    const view = renderAiAssistant('ADMIN');
    const quickPrompt = 'Doanh thu và số đơn hoàn tất 7 ngày gần nhất như thế nào?';
    fireEvent.click(screen.getByRole('button', { name: quickPrompt }));

    // State 4: Timeout -> single safe action "Thử lại"
    await waitFor(() => {
      const alert = screen.getByRole('alert');
      assert.equal(alert.getAttribute('data-error-kind'), 'timeout');
      assert.match(alert.textContent, /Quá thời gian chờ/);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));

    // State 3: Insufficient data -> single safe action "Thu hẹp câu hỏi"
    await waitFor(() => {
      assert.ok(screen.getByText('Chưa đủ dữ liệu kết luận'));
      assert.ok(screen.getByRole('button', { name: 'Thu hẹp câu hỏi' }));
    });

    fireEvent.click(screen.getByRole('button', { name: 'Thu hẹp câu hỏi' }));
    assert.equal(screen.getByLabelText('Nhập câu hỏi cho Trợ lý AI').value, quickPrompt);

    // State 5: Quota 429 -> single safe action "Đóng" (no retry spam)
    fireEvent.click(screen.getByRole('button', { name: 'Gửi câu hỏi' }));
    await waitFor(() => {
      const alert = screen.getByRole('alert');
      assert.equal(alert.getAttribute('data-error-kind'), 'quota');
      assert.match(alert.textContent, /Đã đạt giới hạn sử dụng/);
      assert.ok(screen.getByRole('button', { name: 'Đóng' }));
    });

    fireEvent.click(screen.getByRole('button', { name: 'Đóng' }));
    assert.equal(screen.queryByRole('alert'), null);
    assert.equal(attempt, 3);
    view.unmount();
  });

  test('blocks STAFF user from calling /ai/query and renders access denied card', () => {
    let postCalled = false;
    axiosClient.post = async () => {
      postCalled = true;
      return { data: {} };
    };

    const view = renderAiAssistant('STAFF');
    assert.ok(screen.getByText('Không có quyền truy cập'));
    assert.equal(postCalled, false);
    view.unmount();
  });

  test('P1/P2: prevents synchronous double-submit, hides raw HTTP 500 details, and aborts on reset/role change', async () => {
    let postCount = 0;
    let firstSignal = null;
    let resolvePending = null;

    axiosClient.post = async (_url, _body, config) => {
      postCount += 1;
      if (postCount === 1) {
        firstSignal = config?.signal;
        return new Promise((res) => {
          resolvePending = res;
        });
      }
      const err500 = new Error('Internal Server Error');
      err500.response = {
        status: 500,
        data: { detail: 'SQL ERROR: SELECT * FROM orders WHERE secret_key=abc' },
      };
      throw err500;
    };

    const view = renderAiAssistant('ADMIN');
    const textarea = screen.getByLabelText('Nhập câu hỏi cho Trợ lý AI');
    fireEvent.change(textarea, { target: { value: 'Kiểm tra double submit' } });

    // Two synchronous submits before React re-render -> at most 1 HTTP call
    const form = textarea.closest('form');
    fireEvent.submit(form);
    fireEvent.submit(form);
    assert.equal(postCount, 1);

    // Reset conversation while pending -> aborts signal and ignores late response
    fireEvent.click(screen.getByRole('button', { name: 'Cuộc trò chuyện mới' }));
    assert.equal(firstSignal?.aborted, true);

    resolvePending({
      data: {
        answer: 'Late stale answer that must NOT appear',
        evidence: [],
        insufficient_data: false,
      },
    });
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(
      document.body.textContent.includes('Late stale answer that must NOT appear'),
      false
    );

    // HTTP 500 with SQL detail -> UI must NOT expose SQL/stack trace
    fireEvent.change(screen.getByLabelText('Nhập câu hỏi cho Trợ lý AI'), {
      target: { value: 'Trigger 500 safe error' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi câu hỏi' }));

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      assert.equal(alert.getAttribute('data-error-kind'), 'error');
      assert.equal(alert.textContent.includes('SQL ERROR'), false);
      assert.equal(alert.textContent.includes('secret_key'), false);
    });

    // Role transition ADMIN -> STAFF while pending invalidates request & clears chat
    let secondSignal = null;
    let resolveBeforeRoleChange = null;
    axiosClient.post = async (_url, _body, config) => {
      secondSignal = config?.signal;
      return new Promise((res) => {
        resolveBeforeRoleChange = res;
      });
    };

    fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
    assert.ok(secondSignal);

    view.rerender(
      React.createElement(
        AuthContext.Provider,
        {
          value: {
            user: { id: 2, username: 'staff01', role: 'STAFF' },
            isMockMode: false,
          },
        },
        React.createElement(AiAssistant)
      )
    );

    assert.equal(secondSignal.aborted, true);
    assert.ok(screen.getByText('Không có quyền truy cập'));

    resolveBeforeRoleChange({
      data: {
        answer: 'Leaked admin response after role change',
        evidence: [],
        insufficient_data: false,
      },
    });
    await Promise.resolve();
    assert.equal(
      document.body.textContent.includes('Leaked admin response after role change'),
      false
    );

    view.unmount();
  });

  test('T3C9F16: renders AI reorder suggestions table, selects row & supplier, and creates DRAFT purchase receipt', async () => {
    axiosClient.get = async (url) => {
      if (url === '/inventory/low-stock') {
        return {
          data: {
            items: [
              {
                product_id: 201,
                sku: 'SKU-201',
                name: 'Coca Cola 330ml',
                quantity: 1,
                threshold: 5,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        };
      }
      if (url === '/analytics/products/top') {
        return {
          data: {
            items: [
              {
                product_id: 201,
                sku: 'SKU-201',
                name: 'Coca Cola 330ml',
                sold_units: 24,
                revenue_vnd: 240000,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        };
      }
      if (url === '/suppliers') {
        return {
          data: {
            items: [
              {
                id: 7,
                name: 'Công ty Nước giải khát Việt',
                status: 'ACTIVE',
                contact_phone: '+84901234567',
                contact_email: 'contact@nuocgiaikhat.vn',
                created_at: '2026-11-10T01:00:00Z',
                updated_at: '2026-11-10T01:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 100,
          },
        };
      }
      return { data: {} };
    };

    let createdDraftBody = null;
    axiosClient.post = async (url, body) => {
      assert.equal(url, '/purchase-receipts');
      createdDraftBody = body;
      return {
        data: {
          id: 88,
          supplier_id: 7,
          supplier_name_snapshot: 'Công ty Nước giải khát Việt',
          status: 'DRAFT',
          draft_version: 1,
          total_vnd: 120000,
          created_by: 1,
          closed_by: null,
          created_at: '2026-11-19T10:00:00Z',
          updated_at: '2026-11-19T10:00:00Z',
          closed_at: null,
          items: [
            {
              product_id: 201,
              sku_snapshot: 'SKU-201',
              product_name_snapshot: 'Coca Cola 330ml',
              quantity: 15,
              unit_cost_vnd: 8000,
              line_total_vnd: 120000,
            },
          ],
        },
      };
    };

    const view = renderAiAssistant('ADMIN');

    await waitFor(() => {
      assert.ok(screen.getByText('SKU-201'));
      assert.ok(screen.getByText('Coca Cola 330ml'));
      assert.ok(screen.getByText('Tồn thấp (1/5) · Bán 24 SP/30 ngày'));
    });

    const rowCheckbox = screen.getByLabelText('Chọn sản phẩm SKU-201');
    fireEvent.click(rowCheckbox);

    const qtyInput = screen.getByLabelText('Số lượng nhập SKU-201');
    fireEvent.change(qtyInput, { target: { value: '15' } });

    const costInput = screen.getByLabelText('Đơn giá dự kiến SKU-201');
    fireEvent.change(costInput, { target: { value: '8000' } });

    const supplierSelect = screen.getByLabelText(
      'Chọn nhà cung cấp cho phiếu nhập nháp'
    );
    fireEvent.change(supplierSelect, { target: { value: '7' } });

    const createBtn = screen.getByRole('button', {
      name: 'Tạo phiếu nháp (1 sản phẩm)',
    });
    assert.equal(createBtn.disabled, false);
    fireEvent.click(createBtn);

    await waitFor(() => {
      const banner = screen.getByTestId('draft-created-banner');
      assert.match(banner.textContent, /#88/);
      assert.match(banner.textContent, /DRAFT/);
      assert.ok(
        screen.getByRole('button', {
          name: 'Kiểm tra & Xác nhận phiếu nháp',
        })
      );
    });

    assert.deepEqual(createdDraftBody, {
      supplier_id: 7,
      items: [{ product_id: 201, quantity: 15, unit_cost_vnd: 8000 }],
    });

    view.unmount();
  });

  test('T3C9F16 P1 & P2: shows unknown sales truthfully (never 0 SP), pagination notice, degraded notice, and unified prefill validation', async () => {
    axiosClient.get = async (url) => {
      if (url === '/inventory/low-stock') {
        return {
          data: {
            items: [
              {
                product_id: 301,
                sku: 'SKU-301',
                name: 'Dầu ăn Tường An 1L',
                quantity: 0,
                threshold: 5,
              },
            ],
            total: 35,
            page: 1,
            page_size: 20,
          },
        };
      }
      if (url === '/analytics/products/top') {
        // Top products does NOT include product 301, and total > loaded
        return {
          data: {
            items: [
              {
                product_id: 999,
                sku: 'SKU-999',
                name: 'Sản phẩm khác',
                sold_units: 40,
                revenue_vnd: 400000,
              },
            ],
            total: 42,
            page: 1,
            page_size: 20,
          },
        };
      }
      if (url === '/suppliers') {
        throw new Error('Suppliers service temporary failure');
      }
      return { data: {} };
    };

    const view = renderAiAssistant('ADMIN');

    await waitFor(() => {
      assert.ok(screen.getByText('SKU-301'));
      assert.ok(screen.getByText('Chưa có dữ liệu bán hàng đầy đủ'));
      assert.ok(
        screen.getByText('Hết hàng (0/5) · Chưa có dữ liệu bán hàng đầy đủ')
      );
      assert.equal(screen.queryByText('0 SP'), null);
    });

    // Pagination notice for both Low Stock (1/35) and Top Products (1/42)
    const pageNotice = screen.getByTestId('reorder-pagination-notice');
    assert.match(pageNotice.textContent, /Đang hiển thị 1\/35 sản phẩm tồn thấp/);
    assert.match(
      pageNotice.textContent,
      /Top 1\/42 sản phẩm bán chạy 30 ngày/
    );

    // Degraded notice for failed suppliers API
    const degradedNotice = screen.getByTestId('reorder-degraded-notice');
    assert.match(
      degradedNotice.textContent,
      /Chưa tải được danh sách nhà cung cấp hoạt động/
    );

    // Unified validation: selecting row and entering invalid quantity 0 blocks "Mở form tạo phiếu" and preserves raw input
    fireEvent.click(screen.getByLabelText('Chọn sản phẩm SKU-301'));
    const qtyInput = screen.getByLabelText('Số lượng nhập SKU-301');
    fireEvent.change(qtyInput, {
      target: { value: '0' },
    });
    assert.equal(qtyInput.value, '0');
    fireEvent.click(screen.getByRole('button', { name: 'Mở form tạo phiếu' }));

    await waitFor(() => {
      const errBanner = screen.getByTestId('draft-action-error');
      assert.match(errBanner.textContent, /Số lượng nhập/i);
    });

    // Unsafe integer string "9007199254740993" in unit cost is preserved verbatim (never rounded to 9007199254740992) and rejected
    fireEvent.change(qtyInput, { target: { value: '5' } });
    const costInput = screen.getByLabelText('Đơn giá dự kiến SKU-301');
    fireEvent.change(costInput, { target: { value: '9007199254740993' } });
    assert.equal(costInput.value, '9007199254740993');
    fireEvent.click(screen.getByRole('button', { name: 'Mở form tạo phiếu' }));

    await waitFor(() => {
      const errBanner = screen.getByTestId('draft-action-error');
      assert.match(errBanner.textContent, /Đơn giá nhập/i);
    });
    assert.equal(costInput.value, '9007199254740993');

    view.unmount();
  });

  test('T3C9F16 P2 Router Navigation: prefillDraft and openReceiptId flows wait for list load and clear router state', async () => {
    let resolveReceiptsList = null;
    let detailFetchCount = 0;

    axiosClient.get = async (url, config) => {
      if (url === '/inventory/low-stock') {
        return {
          data: {
            items: [
              {
                product_id: 201,
                sku: 'SKU-201',
                name: 'Coca Cola 330ml',
                quantity: 1,
                threshold: 5,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        };
      }
      if (url === '/analytics/products/top') {
        return {
          data: {
            items: [
              {
                product_id: 201,
                sku: 'SKU-201',
                name: 'Coca Cola 330ml',
                sold_units: 20,
                revenue_vnd: 200000,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        };
      }
      if (url === '/suppliers') {
        return {
          data: {
            items: [
              {
                id: 7,
                name: 'Công ty Nước giải khát Việt',
                status: 'ACTIVE',
                contact_phone: '+84901234567',
                contact_email: 'contact@nuocgiaikhat.vn',
                created_at: '2026-11-10T01:00:00Z',
                updated_at: '2026-11-10T01:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 100,
          },
        };
      }
      if (url === '/products') {
        return {
          data: {
            items: [
              {
                id: 201,
                category_id: 1,
                sku: 'SKU-201',
                name: 'Coca Cola 330ml',
                status: 'ACTIVE',
                sale_price_vnd: 10000,
                quantity: 1,
                stock_version: 1,
                created_at: '2026-11-10T01:00:00Z',
                updated_at: '2026-11-10T01:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 100,
          },
        };
      }
      if (url === '/purchase-receipts') {
        // Only hold the main DRAFT list query (page_size=10) when resolveReceiptsList gate is active
        if (resolveReceiptsList && config?.params?.page_size === 10) {
          return new Promise((res) => {
            const currentResolver = resolveReceiptsList;
            resolveReceiptsList = null;
            currentResolver(res);
          });
        }
        return {
          data: {
            items: [],
            total: 0,
            page: 1,
            page_size: config?.params?.page_size || 10,
          },
        };
      }
      if (url === '/purchase-receipts/88') {
        detailFetchCount += 1;
        return {
          data: {
            id: 88,
            supplier_id: 7,
            supplier_name_snapshot: 'Công ty Nước giải khát Việt',
            status: 'DRAFT',
            draft_version: 1,
            total_vnd: 120000,
            created_by: 1,
            closed_by: null,
            created_at: '2026-11-19T10:00:00Z',
            updated_at: '2026-11-19T10:00:00Z',
            closed_at: null,
            items: [
              {
                product_id: 201,
                sku_snapshot: 'SKU-201',
                product_name_snapshot: 'Coca Cola 330ml',
                quantity: 15,
                unit_cost_vnd: 8000,
                line_total_vnd: 120000,
              },
            ],
          },
        };
      }
      return { data: {} };
    };

    axiosClient.post = async (url) => {
      assert.equal(url, '/purchase-receipts');
      return {
        data: {
          id: 88,
          supplier_id: 7,
          supplier_name_snapshot: 'Công ty Nước giải khát Việt',
          status: 'DRAFT',
          draft_version: 1,
          total_vnd: 120000,
          created_by: 1,
          closed_by: null,
          created_at: '2026-11-19T10:00:00Z',
          updated_at: '2026-11-19T10:00:00Z',
          closed_at: null,
          items: [
            {
              product_id: 201,
              sku_snapshot: 'SKU-201',
              product_name_snapshot: 'Coca Cola 330ml',
              quantity: 15,
              unit_cost_vnd: 8000,
              line_total_vnd: 120000,
            },
          ],
        },
      };
    };

    let latestLocation = null;
    let triggerNavigate = null;
    function LocationProbe() {
      latestLocation = useLocation();
      triggerNavigate = useNavigate();
      return null;
    }

    const view = render(
      React.createElement(
        AuthContext.Provider,
        {
          value: {
            user: { id: 1, username: 'admin', role: 'ADMIN' },
            isMockMode: false,
          },
        },
        React.createElement(
          ToastProvider,
          null,
          React.createElement(
            MemoryRouter,
            { initialEntries: ['/ai-assistant'] },
            React.createElement(LocationProbe),
            React.createElement(
              Routes,
              null,
              React.createElement(Route, {
                path: '/ai-assistant',
                element: React.createElement(AiAssistant),
              }),
              React.createElement(Route, {
                path: '/purchases',
                element: React.createElement(PurchaseList),
              })
            )
          )
        )
      )
    );

    // 1. Flow A: Select suggestion -> click "Mở form tạo phiếu" -> navigates to /purchases & opens Create Modal with prefilled data
    await waitFor(() => {
      assert.ok(screen.getByText('SKU-201'));
    });

    fireEvent.click(screen.getByLabelText('Chọn sản phẩm SKU-201'));
    fireEvent.change(screen.getByLabelText('Số lượng nhập SKU-201'), {
      target: { value: '14' },
    });
    fireEvent.change(screen.getByLabelText('Đơn giá dự kiến SKU-201'), {
      target: { value: '7500' },
    });
    fireEvent.change(
      screen.getByLabelText('Chọn nhà cung cấp cho phiếu nhập nháp'),
      { target: { value: '7' } }
    );

    fireEvent.click(screen.getByRole('button', { name: 'Mở form tạo phiếu' }));

    await waitFor(() => {
      assert.equal(latestLocation?.pathname, '/purchases');
      // Router state must be cleared immediately after consumption
      assert.equal(latestLocation?.state, null);
      assert.ok(screen.getByText('Tạo mới phiếu nhập hàng'));
    });

    // Close Create modal, navigate back to /ai-assistant, then revisit /purchases without state -> modal must NOT reopen
    fireEvent.click(screen.getByRole('button', { name: 'Hủy bỏ' }));
    await waitFor(() => {
      assert.equal(screen.queryByText('Tạo mới phiếu nhập hàng'), null);
    });

    await act(async () => {
      triggerNavigate('/ai-assistant');
    });
    await waitFor(() => {
      assert.equal(latestLocation?.pathname, '/ai-assistant');
      assert.ok(screen.getByText('SKU-201'));
    });

    // 2. Flow B: Create DRAFT receipt #88 -> click "Kiểm tra & Xác nhận phiếu nháp" -> waits for list load -> opens receipt #88
    let finishListLoad = null;
    resolveReceiptsList = (res) => {
      finishListLoad = () =>
        res({
          data: {
            items: [
              {
                id: 88,
                supplier_id: 7,
                supplier_name_snapshot: 'Công ty Nước giải khát Việt',
                status: 'DRAFT',
                draft_version: 1,
                total_vnd: 120000,
                created_by: 1,
                closed_by: null,
                created_at: '2026-11-19T10:00:00Z',
                updated_at: '2026-11-19T10:00:00Z',
                closed_at: null,
                items: [
                  {
                    product_id: 201,
                    sku_snapshot: 'SKU-201',
                    product_name_snapshot: 'Coca Cola 330ml',
                    quantity: 15,
                    unit_cost_vnd: 8000,
                    line_total_vnd: 120000,
                  },
                ],
              },
            ],
            total: 1,
            page: 1,
            page_size: 10,
          },
        });
    };

    fireEvent.click(screen.getByLabelText('Chọn sản phẩm SKU-201'));
    fireEvent.change(
      screen.getByLabelText('Chọn nhà cung cấp cho phiếu nhập nháp'),
      { target: { value: '7' } }
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Tạo phiếu nháp (1 sản phẩm)' })
    );

    await waitFor(() => {
      assert.ok(
        screen.getByRole('button', { name: 'Kiểm tra & Xác nhận phiếu nháp' })
      );
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'Kiểm tra & Xác nhận phiếu nháp' })
    );

    await waitFor(() => {
      assert.equal(latestLocation?.pathname, '/purchases');
      assert.equal(latestLocation?.state, null);
      assert.ok(finishListLoad);
    });

    // While list is still loading, detail modal for #88 must NOT have fetched yet
    assert.equal(detailFetchCount, 0);

    // Finish list load -> detail modal for #88 automatically opens
    await act(async () => {
      finishListLoad();
    });

    await waitFor(() => {
      assert.equal(detailFetchCount, 1);
      assert.ok(screen.getByText(/Chi tiết phiếu nhập #88/));
    });

    view.unmount();
  });

  test('P2 renderFormattedAnswer renders Markdown lists/bold/code/table safely and escapes raw HTML', async () => {
    axiosClient.post = async () => ({
      data: {
        answer: [
          '### Tóm tắt tồn kho',
          '',
          '- **Sữa tươi**: còn `5` hộp',
          '1. Kiểm tra lô nhập',
          '',
          '| SKU | SL |',
          '| --- | --- |',
          '| SP01 | 5 |',
          '',
          '<script>alert(1)</script>',
        ].join('\n'),
        evidence: [],
        insufficient_data: false,
      },
    });

    const view = renderAiAssistant('ADMIN');
    fireEvent.change(screen.getByLabelText('Nhập câu hỏi cho Trợ lý AI'), {
      target: { value: 'Kiểm tra markdown' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi câu hỏi' }));

    await waitFor(() => {
      assert.ok(document.querySelector('h4'));
      assert.ok(document.querySelector('ul li strong'));
      assert.equal(document.querySelector('ul li strong')?.textContent, 'Sữa tươi');
      assert.equal(document.querySelector('ul li code')?.textContent, '5');
      assert.ok(document.querySelector('ol li'));
      assert.ok(document.querySelector('table thead th'));
      assert.ok(document.querySelector('table tbody td'));
    });

    assert.equal(document.querySelector('script'), null, 'Raw <script> must NOT be injected as DOM element');
    assert.ok(
      (document.body.textContent || '').includes('<script>alert(1)</script>'),
      'Raw HTML must be escaped as plain text'
    );

    view.unmount();
  });
});
