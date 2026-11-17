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

  beforeEach(() => {
    cleanup();
    dom.window.document.body.innerHTML = '<div id="root"></div>';
  });

  afterEach(() => {
    cleanup();
    axiosClient.post = originalPost;
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
});
