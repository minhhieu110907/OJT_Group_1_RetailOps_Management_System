process.env.NODE_ENV = 'development';
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

import { JSDOM } from 'jsdom';
import path from 'path';
import fs from 'fs';
import { pathToFileURL } from 'url';
import test, { describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

const dom = new JSDOM('<!DOCTYPE html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/forgot-password',
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
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement;

const outDir = path.resolve('./node_modules/.cache_forgot_reset_test');
fs.mkdirSync(outDir, { recursive: true });
const entryPath = path.join(outDir, 'forgotResetHarnessEntry.jsx');
fs.writeFileSync(
  entryPath,
  [
    "import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';",
    "import ForgotPassword from '../../src/pages/Auth/ForgotPassword.jsx';",
    "import ResetPassword from '../../src/pages/Auth/ResetPassword.jsx';",
    "import { AuthProvider } from '../../src/context/AuthContext.jsx';",
    "import { ToastProvider } from '../../src/components/common';",
    "import axiosClient, { setUseMock, invalidateSession } from '../../src/api/axiosClient.js';",
    'function LocationProbe() { const loc = useLocation(); return <div data-testid="current-path">{loc.pathname}</div>; }',
    'export { MemoryRouter, Routes, Route, LocationProbe, ForgotPassword, ResetPassword, AuthProvider, ToastProvider, axiosClient, setUseMock, invalidateSession };',
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

const harnessUrl = pathToFileURL(path.join(outDir, 'forgotResetHarnessEntry.js')).href;
const {
  MemoryRouter,
  Routes,
  Route,
  LocationProbe,
  ForgotPassword,
  ResetPassword,
  AuthProvider,
  ToastProvider,
  axiosClient,
  setUseMock,
  invalidateSession,
} = await import(harnessUrl);
const { render, screen, waitFor, fireEvent, cleanup } = await import(
  '@testing-library/react'
);
const React = await import('react');

function renderAuthRoute(initialEntry) {
  return render(
    React.createElement(
      ToastProvider,
      null,
      React.createElement(
        AuthProvider,
        null,
        React.createElement(
          MemoryRouter,
          { initialEntries: [initialEntry] },
          React.createElement(
            React.Fragment,
            null,
            React.createElement(LocationProbe),
            React.createElement(
              Routes,
              null,
              React.createElement(Route, {
                path: '/forgot-password',
                element: React.createElement(ForgotPassword),
              }),
              React.createElement(Route, {
                path: '/reset-password',
                element: React.createElement(ResetPassword),
              }),
              React.createElement(Route, {
                path: '/login',
                element: React.createElement('div', null, 'Login Destination'),
              })
            )
          )
        )
      )
    )
  );
}

describe('T04AA1C Forgot & Reset Password Real React Integration Suite', () => {
  const originalAdapter = axiosClient.defaults.adapter;

  beforeEach(() => {
    cleanup();
    setUseMock(false);
    invalidateSession();
    dom.window.document.body.innerHTML = '<div id="root"></div>';
  });

  afterEach(() => {
    cleanup();
    axiosClient.defaults.adapter = originalAdapter;
    setUseMock(false);
    invalidateSession();
  });

  test('ForgotPassword sends normalized email and renders generic 202 message without Mock fallback or double-submit', async () => {
    let postCount = 0;
    let capturedPayload = null;
    let resolvePending;
    const gate = new Promise((resolve) => {
      resolvePending = resolve;
    });

    axiosClient.defaults.adapter = async (config) => {
      if (config.url === '/health') {
        return { status: 200, data: { status: 'ok' }, headers: {}, config };
      }
      if (config.url === '/auth/forgot-password') {
        postCount += 1;
        capturedPayload = JSON.parse(config.data);
        await gate;
        return {
          status: 202,
          statusText: 'Accepted',
          headers: {},
          config,
          data: {
            message: 'Nếu email hợp lệ, hướng dẫn đặt lại mật khẩu đã được gửi.',
          },
        };
      }
      throw new Error(`Unexpected ${config.url}`);
    };

    renderAuthRoute('/forgot-password');

    const emailInput = screen.getByLabelText(/EMAIL ĐĂNG KÝ/i);
    fireEvent.change(emailInput, { target: { value: '  Staff.One@RetailOps.VN  ' } });

    const form = emailInput.closest('form');
    fireEvent.submit(form);
    fireEvent.submit(form);

    await waitFor(() => assert.equal(postCount, 1));
    resolvePending();

    await waitFor(() => {
      assert.ok(
        screen.getByText('Nếu email hợp lệ, hướng dẫn đặt lại mật khẩu đã được gửi.')
      );
    });
    assert.deepEqual(capturedPayload, { email: 'staff.one@retailops.vn' });
    assert.equal(screen.queryByText(/Hộp thư mô phỏng/i), null);
  });

  test('ForgotPassword handles HTTP 429, 422, and 500 safely without leaking raw backend detail or faking success', async () => {
    let statusCode = 429;
    axiosClient.defaults.adapter = async (config) => {
      if (config.url === '/health') {
        return { status: 200, data: { status: 'ok' }, headers: {}, config };
      }
      if (config.url === '/auth/forgot-password') {
        const err = new Error('Request failed');
        err.isAxiosError = true;
        err.config = config;
        err.response = {
          status: statusCode,
          data: {
            message: 'Sensitive internal error detail',
            detail: 'Sensitive internal error detail',
          },
          headers: {},
          config,
        };
        throw err;
      }
      throw new Error(`Unexpected ${config.url}`);
    };

    renderAuthRoute('/forgot-password');

    const emailInput = screen.getByLabelText(/EMAIL ĐĂNG KÝ/i);
    fireEvent.change(emailInput, { target: { value: 'staff@retailops.vn' } });

    statusCode = 429;
    fireEvent.submit(emailInput.closest('form'));
    await waitFor(() => {
      assert.ok(
        screen.getByText(/Bạn đã gửi quá nhiều yêu cầu khôi phục mật khẩu/i)
      );
    });
    assert.equal(screen.queryByText(/Sensitive internal error detail/i), null);
    assert.equal(screen.queryByText(/Đã tiếp nhận yêu cầu/i), null);

    statusCode = 422;
    fireEvent.submit(emailInput.closest('form'));
    await waitFor(() => {
      assert.ok(
        screen.getByText(/Địa chỉ email không hợp lệ theo định dạng yêu cầu/i)
      );
    });
    assert.equal(screen.queryByText(/Sensitive internal error detail/i), null);
    assert.equal(screen.queryByText(/Đã tiếp nhận yêu cầu/i), null);

    statusCode = 500;
    fireEvent.submit(emailInput.closest('form'));
    await waitFor(() => {
      assert.ok(
        screen.getByText(/Không thể gửi yêu cầu khôi phục mật khẩu tới máy chủ/i)
      );
    });
    assert.equal(screen.queryByText(/Sensitive internal error detail/i), null);
    assert.equal(screen.queryByText(/Đã tiếp nhận yêu cầu/i), null);
  });

  test('ResetPassword submits token + new_password, prevents double-submit, and navigates to /login on HTTP 200', async () => {
    let resetCalls = 0;
    let capturedPayload = null;
    let resolveReset;
    const resetGate = new Promise((resolve) => {
      resolveReset = resolve;
    });

    axiosClient.defaults.adapter = async (config) => {
      if (config.url === '/health') {
        return { status: 200, data: { status: 'ok' }, headers: {}, config };
      }
      if (config.url === '/auth/reset-password') {
        resetCalls += 1;
        capturedPayload = JSON.parse(config.data);
        await resetGate;
        return {
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
          data: { message: 'Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại.' },
        };
      }
      throw new Error(`Unexpected ${config.url}`);
    };

    renderAuthRoute('/reset-password?token=one-time-token-xyz');

    const newPwd = screen.getByLabelText(/^Mật khẩu mới/i);
    const confirmPwd = screen.getByLabelText(/^Xác nhận mật khẩu mới/i);
    fireEvent.change(newPwd, { target: { value: 'NewStrongPass123' } });
    fireEvent.change(confirmPwd, { target: { value: 'NewStrongPass123' } });

    const form = newPwd.closest('form');
    fireEvent.submit(form);
    fireEvent.submit(form);

    await waitFor(() => assert.equal(resetCalls, 1));
    resolveReset();

    await waitFor(() => {
      assert.equal(screen.getByTestId('current-path').textContent, '/login');
    });
    assert.deepEqual(capturedPayload, {
      token: 'one-time-token-xyz',
      new_password: 'NewStrongPass123',
    });
  });

  test('ResetPassword handles 401 invalid/expired token, 422 validation, and 429 rate-limit without navigating to /login', async () => {
    let nextStatus = 401;
    axiosClient.defaults.adapter = async (config) => {
      if (config.url === '/health') {
        return { status: 200, data: { status: 'ok' }, headers: {}, config };
      }
      if (config.url === '/auth/reset-password') {
        const err = new Error(`HTTP ${nextStatus}`);
        err.isAxiosError = true;
        err.config = config;
        err.response = {
          status: nextStatus,
          data: { message: 'raw backend error' },
          headers: {},
          config,
        };
        throw err;
      }
      throw new Error(`Unexpected ${config.url}`);
    };

    renderAuthRoute('/reset-password?token=bad-token-123');

    const newPwd = screen.getByLabelText(/^Mật khẩu mới/i);
    const confirmPwd = screen.getByLabelText(/^Xác nhận mật khẩu mới/i);
    fireEvent.change(newPwd, { target: { value: 'NewStrongPass123' } });
    fireEvent.change(confirmPwd, { target: { value: 'NewStrongPass123' } });
    const form = newPwd.closest('form');

    nextStatus = 401;
    fireEvent.submit(form);
    await waitFor(() => {
      assert.ok(
        screen.getAllByText(
          /Liên kết đặt lại mật khẩu không hợp lệ, đã hết hạn hoặc đã được sử dụng/i
        ).length >= 1
      );
    });
    assert.equal(screen.getByTestId('current-path').textContent, '/reset-password');

    nextStatus = 422;
    fireEvent.submit(form);
    await waitFor(() => {
      assert.ok(
        screen.getAllByText(
          /Mật khẩu mới hoặc mã xác thực không đáp ứng định dạng hợp lệ/i
        ).length >= 1
      );
    });
    assert.equal(screen.getByTestId('current-path').textContent, '/reset-password');

    nextStatus = 429;
    fireEvent.submit(form);
    await waitFor(() => {
      assert.ok(
        screen.getAllByText(/Bạn đã thử đặt lại mật khẩu quá nhiều lần/i).length >= 1
      );
    });
    assert.equal(screen.getByTestId('current-path').textContent, '/reset-password');
  });
});
