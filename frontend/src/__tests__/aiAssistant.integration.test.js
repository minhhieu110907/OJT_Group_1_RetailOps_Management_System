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
    "import AiAssistant from '../../src/pages/AiAssistant/AiAssistant.jsx';",
    "import { AuthContext } from '../../src/context/AuthContext.jsx';",
    "import axiosClient from '../../src/api/axiosClient.js';",
    'export { AiAssistant, AuthContext, axiosClient };',
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
const { AiAssistant, AuthContext, axiosClient } = await import(harnessUrl);
const { render, screen, waitFor, fireEvent, cleanup } = await import(
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
});
