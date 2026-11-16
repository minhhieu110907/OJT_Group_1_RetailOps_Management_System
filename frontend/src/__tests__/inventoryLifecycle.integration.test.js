process.env.NODE_ENV = 'development';
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

import { JSDOM } from 'jsdom';
import path from 'path';
import fs from 'fs';
import { pathToFileURL } from 'url';
import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

// 1. Setup DOM environment
const dom = new JSDOM('<!DOCTYPE html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/inventory',
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

// 2. Build test harness via Vite once
const outDir = path.resolve('./node_modules/.cache_lifecycle');
fs.mkdirSync(outDir, { recursive: true });

const { build } = await import('vite');
const react = (await import('@vitejs/plugin-react')).default;

await build({
  plugins: [react()],
  build: {
    ssr: true,
    write: true,
    outDir,
    rollupOptions: {
      input: path.resolve('./src/__tests__/integrationHarness.jsx'),
    },
  },
  logLevel: 'silent',
});

// 3. Import bundled components & testing library
const harnessUrl = pathToFileURL(path.join(outDir, 'integrationHarness.js')).href;
const {
  InventoryList,
  InventoryAdjustModal,
  InventorySessionProvider,
  useInventorySession,
  AuthContext,
  ToastProvider,
  TestAppRouter,
  axiosClient,
  inventoryApi,
} = await import(harnessUrl);

const { render, waitFor, fireEvent, act, cleanup } = await import('@testing-library/react');
const React = await import('react');
const { MemoryRouter } = await import('react-router-dom');

assert.ok(InventoryAdjustModal, 'Modal component must be defined');
assert.ok(inventoryApi, 'Inventory API must be defined');

describe('T04A89D Real React Component Integration Suite', () => {
  let postAdjustmentCalls = 0;
  let lastCapturedPayload = null;
  let lastCapturedHeaders = null;

  beforeEach(() => {
    cleanup();
    dom.window.document.body.innerHTML = '<div id="root"></div>';
    postAdjustmentCalls = 0;
    lastCapturedPayload = null;
    lastCapturedHeaders = null;

    // Default mock GET endpoints
    axiosClient.get = async (url) => {
      if (url.includes('/categories')) {
        return { data: { items: [{ id: 1, name: 'Đồ uống' }], total: 1 } };
      }
      if (url.includes('/inventory/low-stock')) {
        return { data: { items: [], total: 0, page: 1, page_size: 20 } };
      }
      if (url.includes('/inventory/101')) {
        return {
          data: {
            product_id: 101,
            sku: 'SP-101',
            name: 'Trà xanh không độ',
            quantity: 22,
            stock_version: 2,
            category_id: 1,
            status: 'ACTIVE',
            unit: 'Chai',
          },
        };
      }
      // GET /inventory list
      return {
        data: {
          items: [
            {
              product_id: 101,
              sku: 'SP-101',
              name: 'Trà xanh không độ',
              quantity: 20,
              stock_version: 1,
              category_id: 1,
              status: 'ACTIVE',
              unit: 'Chai',
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        },
      };
    };
  });

  // =========================================================================
  // TEST A: Ambiguous & Effect Stability Component Test
  // Mount InventorySessionProvider + InventoryList + InventoryAdjustModal
  // Trigger ambiguous adjustment (network error / timeout)
  // Check modal moves to AMBIGUOUS
  // Assert effect runs without causing re-render loop / Maximum update depth exceeded
  // Assert child does not repeatedly call parent update session
  // =========================================================================
  test('TEST A — Ambiguous & Effect Stability Component Test', async () => {
    let parentStateUpdateCount = 0;

    // Intercept POST /inventory/:id/adjustments to simulate network timeout (AMBIGUOUS)
    axiosClient.post = async (url, payload, config) => {
      if (url.includes('/adjustments')) {
        postAdjustmentCalls++;
        lastCapturedPayload = payload;
        lastCapturedHeaders = config?.headers;
        const err = new Error('timeout of 10000ms exceeded');
        err.code = 'ECONNABORTED';
        throw err;
      }
      return { data: {} };
    };

    const adminAuth = {
      user: { id: 1, role: 'ADMIN', name: 'Admin Tân' },
      isAdmin: true,
      isLoggingOut: false,
      authInitializing: false,
    };

    // Component spy to monitor child -> parent session sync calls
    function SessionWatcher({ children }) {
      const { liftedSession } = useInventorySession();
      const prevRef = React.useRef(null);
      React.useEffect(() => {
        if (liftedSession !== prevRef.current) {
          prevRef.current = liftedSession;
          if (liftedSession !== null) {
            parentStateUpdateCount++;
          }
        }
      }, [liftedSession]);
      return children;
    }

    render(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: adminAuth },
          React.createElement(
            InventorySessionProvider,
            null,
            React.createElement(
              SessionWatcher,
              null,
              React.createElement(
                MemoryRouter,
                { initialEntries: ['/inventory'] },
                React.createElement(InventoryList, null)
              )
            )
          )
        )
      )
    );

    // 1. Wait for inventory table to render product SP-101
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('SP-101')) {
        throw new Error('Waiting for SP-101 table row');
      }
    });

    // 2. Click "Điều chỉnh" button on row
    const adjustBtn = dom.window.document.querySelector('button[title="Điều chỉnh tồn kho"]');
    assert.ok(adjustBtn, 'Điều chỉnh button must exist in product row');
    act(() => {
      fireEvent.click(adjustBtn);
    });

    // 3. Modal opens in DOM
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('Điều chỉnh tồn kho')) {
        throw new Error('Waiting for modal title');
      }
    });

    // 4. Fill counted quantity and reason
    const countedInput = dom.window.document.querySelector('input[type="number"]');
    assert.ok(countedInput, 'Counted quantity input must exist');
    act(() => {
      fireEvent.change(countedInput, { target: { value: '25' } });
    });

    const reasonTextarea = dom.window.document.querySelector('textarea');
    assert.ok(reasonTextarea, 'Reason textarea must exist');
    act(() => {
      fireEvent.change(reasonTextarea, { target: { value: 'Kiểm kê định kỳ phát hiện thừa' } });
    });

    // 5. Submit adjustment
    const submitBtn = dom.window.document.querySelector('button[type="submit"]');
    assert.ok(submitBtn, 'Submit button must exist');
    assert.equal(submitBtn.disabled, false, 'Submit button must be enabled before submitting');

    act(() => {
      fireEvent.click(submitBtn);
    });

    // 6. Modal transitions to AMBIGUOUS upon ECONNABORTED
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ')) {
        throw new Error('Waiting for AMBIGUOUS badge');
      }
    });

    assert.ok(
      dom.window.document.body.innerHTML.includes('Kết quả điều chỉnh chưa thể xác minh'),
      'Must render ambiguous title'
    );
    assert.ok(
      dom.window.document.body.innerHTML.includes('Mã giao dịch (Idempotency Key):'),
      'Must render Idempotency-Key label'
    );

    // 7. Verify Idempotency-Key header was sent
    assert.equal(postAdjustmentCalls, 1, 'Exactly 1 POST request must have been sent');
    assert.equal(lastCapturedPayload.counted_quantity, 25, 'Counted quantity payload must match input');
    assert.ok(lastCapturedHeaders && lastCapturedHeaders['Idempotency-Key'], 'Idempotency-Key header must be present');
    const sentKey = lastCapturedHeaders['Idempotency-Key'];
    assert.match(sentKey, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i, 'Must be valid UUID');

    // 8. Effect Stability Verification:
    // Child called parent update session exactly once; areAdjustmentSessionsEqual prevented infinite update loops!
    assert.equal(parentStateUpdateCount, 1, 'Parent lifted session update count must be strictly 1, confirming no re-render loop');

    // Submit and close buttons are locked in AMBIGUOUS state
    const closeBtn = dom.window.document.querySelector('button[title="Đóng modal"]') || dom.window.document.querySelector('button[aria-label="Đóng"]');
    if (closeBtn) {
      assert.equal(closeBtn.disabled, true, 'Close button must be disabled in AMBIGUOUS state');
    }
    assert.equal(submitBtn.disabled, true, 'Submit button must be disabled in AMBIGUOUS state');
  });

  // =========================================================================
  // TEST B: Router unmount / remount preserving Idempotency-Key
  // Mount app with MemoryRouter, route /inventory
  // Create ambiguous adjustment state
  // Navigate away (/orders) -> InventoryList unmounts
  // Navigate back (/inventory) -> InventoryList remounts
  // Assert modal automatically restores state AMBIGUOUS
  // Assert Idempotency-Key preserves exact original key, NO new UUID generated
  // Assert no additional POST request sent on remount
  // =========================================================================
  test('TEST B — Router unmount / remount preserving Idempotency-Key', async () => {
    let capturedOriginalKey = null;

    // Simulate network error on submission
    axiosClient.post = async (url, payload, config) => {
      if (url.includes('/adjustments')) {
        postAdjustmentCalls++;
        capturedOriginalKey = config?.headers?.['Idempotency-Key'];
        const err = new Error('Network Error: Gateway Timeout 504');
        err.code = 'ECONNABORTED';
        throw err;
      }
      return { data: {} };
    };

    const adminAuth = {
      user: { id: 1, role: 'ADMIN', name: 'Admin Tân' },
      isAdmin: true,
      isLoggingOut: false,
      authInitializing: false,
    };

    const navigateRef = { current: null };

    render(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: adminAuth },
          React.createElement(
            InventorySessionProvider,
            null,
            React.createElement(
              MemoryRouter,
              { initialEntries: ['/inventory'] },
              React.createElement(TestAppRouter, { navigateRef })
            )
          )
        )
      )
    );

    // 1. Wait for inventory row & open adjustment modal
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('SP-101')) {
        throw new Error('Waiting for SP-101');
      }
    });

    const adjustBtn = dom.window.document.querySelector('button[title="Điều chỉnh tồn kho"]');
    act(() => {
      fireEvent.click(adjustBtn);
    });

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('Điều chỉnh tồn kho')) {
        throw new Error('Waiting for modal');
      }
    });

    // 2. Fill inputs and submit to trigger AMBIGUOUS
    const countedInput = dom.window.document.querySelector('input[type="number"]');
    act(() => {
      fireEvent.change(countedInput, { target: { value: '30' } });
    });

    const reasonTextarea = dom.window.document.querySelector('textarea');
    act(() => {
      fireEvent.change(reasonTextarea, { target: { value: 'Kiem ke kho cuoi ngay' } });
    });

    const submitBtn = dom.window.document.querySelector('button[type="submit"]');
    act(() => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ')) {
        throw new Error('Waiting for AMBIGUOUS status');
      }
    });

    assert.ok(capturedOriginalKey, 'Original Idempotency-Key must have been generated and sent');
    assert.equal(postAdjustmentCalls, 1, 'Must have made exactly 1 POST call before unmount');

    // 3. User navigates away: /inventory -> /orders
    act(() => {
      navigateRef.current('/orders');
    });

    // Wait until Orders page placeholder is rendered
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('Trang danh sách đơn hàng')) {
        throw new Error('Waiting for orders route');
      }
    });

    // InventoryList and modal are completely unmounted from DOM
    assert.equal(
      dom.window.document.body.innerHTML.includes('Tổng quan tồn kho'),
      false,
      'InventoryList must be completely unmounted from DOM'
    );
    assert.equal(
      dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ'),
      false,
      'Modal must be completely unmounted from DOM'
    );

    // 4. User navigates back: /orders -> /inventory
    act(() => {
      navigateRef.current('/inventory');
    });

    // Wait until InventoryList is mounted back in DOM
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('Tổng quan tồn kho')) {
        throw new Error('Waiting for InventoryList remount');
      }
    });

    // Modal is automatically restored in AMBIGUOUS state because of liftedSession in InventorySessionProvider!
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ')) {
        throw new Error('Modal must automatically restore in AMBIGUOUS state');
      }
    });

    // 5. Assert: Idempotency-Key displayed on remounted modal strictly matches originalKey!
    assert.ok(
      dom.window.document.body.innerHTML.includes(capturedOriginalKey),
      `Remounted modal must preserve exact original Idempotency-Key (${capturedOriginalKey}), NO new UUID generated`
    );

    // 6. Assert: No additional POST request was sent during route transition or remount
    assert.equal(
      postAdjustmentCalls,
      1,
      'POST call count must strictly remain 1 after route unmount/remount (fail-closed, no auto-replay)'
    );

    // 7. Assert: Controls remain securely locked on remount
    const remountSubmitBtn = dom.window.document.querySelector('button[type="submit"]');
    assert.ok(remountSubmitBtn, 'Submit button must exist on remounted modal');
    assert.equal(remountSubmitBtn.disabled, true, 'Submit button must remain disabled on remount');
  });

  // =========================================================================
  // TEST C: Role Downgrade Security in Mounted Tree
  // Role change ADMIN -> STAFF immediately suppresses modal and clears lifted session
  // =========================================================================
  test('TEST C — Role downgrade immediately suppresses adjustment modal and clears lifted session', async () => {
    let authState = {
      user: { id: 1, role: 'ADMIN', name: 'Admin Tân' },
      isAdmin: true,
      isLoggingOut: false,
      authInitializing: false,
    };

    let setAuthFn = null;
    function DynamicAuthProvider({ children }) {
      const [auth, setAuth] = React.useState(authState);
      setAuthFn = setAuth;
      return React.createElement(AuthContext.Provider, { value: auth }, children);
    }

    // Intercept POST to enter AMBIGUOUS
    axiosClient.post = async () => {
      const err = new Error('Network Timeout');
      err.code = 'ECONNABORTED';
      throw err;
    };

    render(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          DynamicAuthProvider,
          null,
          React.createElement(
            InventorySessionProvider,
            null,
            React.createElement(
              MemoryRouter,
              { initialEntries: ['/inventory'] },
              React.createElement(InventoryList, null)
            )
          )
        )
      )
    );

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('SP-101')) throw new Error('Waiting row');
    });

    const adjustBtn = dom.window.document.querySelector('button[title="Điều chỉnh tồn kho"]');
    act(() => {
      fireEvent.click(adjustBtn);
    });

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('Điều chỉnh tồn kho')) throw new Error('Waiting modal');
    });

    const countedInput = dom.window.document.querySelector('input[type="number"]');
    act(() => {
      fireEvent.change(countedInput, { target: { value: '28' } });
    });
    const reasonTextarea = dom.window.document.querySelector('textarea');
    act(() => {
      fireEvent.change(reasonTextarea, { target: { value: 'Kiem ke dinh ky' } });
    });
    const submitBtn = dom.window.document.querySelector('button[type="submit"]');
    act(() => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ')) throw new Error('Waiting AMBIGUOUS');
    });

    // Role downgrade ADMIN -> STAFF
    act(() => {
      setAuthFn({
        user: { id: 1, role: 'STAFF', name: 'Staff Tân' },
        isAdmin: false,
        isLoggingOut: false,
        authInitializing: false,
      });
    });

    // Modal must be immediately suppressed from DOM
    await waitFor(() => {
      if (dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ')) {
        throw new Error('Modal must not be visible to STAFF');
      }
    });

    assert.equal(
      dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ'),
      false,
      'Privileged adjustment modal must be completely suppressed when downgraded to STAFF'
    );
  });

  // =========================================================================
  // TEST D: Authoritative Reload Validation and Explicit Acknowledgement
  // Valid authoritative reload enters AWAITING_ACKNOWLEDGEMENT
  // Requires user explicit acknowledgement before unlocking controls
  // =========================================================================
  test('TEST D — Authoritative reload validation and explicit user acknowledgement gate', async () => {
    // Intercept POST to enter AMBIGUOUS
    axiosClient.post = async () => {
      const err = new Error('Gateway Timeout');
      err.code = 'ECONNABORTED';
      throw err;
    };

    const adminAuth = {
      user: { id: 1, role: 'ADMIN', name: 'Admin Tân' },
      isAdmin: true,
      isLoggingOut: false,
      authInitializing: false,
    };

    render(
      React.createElement(
        ToastProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: adminAuth },
          React.createElement(
            InventorySessionProvider,
            null,
            React.createElement(
              MemoryRouter,
              { initialEntries: ['/inventory'] },
              React.createElement(InventoryList, null)
            )
          )
        )
      )
    );

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('SP-101')) throw new Error('Waiting row');
    });

    const adjustBtn = dom.window.document.querySelector('button[title="Điều chỉnh tồn kho"]');
    act(() => {
      fireEvent.click(adjustBtn);
    });

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('Điều chỉnh tồn kho')) throw new Error('Waiting modal');
    });

    const countedInput = dom.window.document.querySelector('input[type="number"]');
    act(() => {
      fireEvent.change(countedInput, { target: { value: '25' } });
    });
    const reasonTextarea = dom.window.document.querySelector('textarea');
    act(() => {
      fireEvent.change(reasonTextarea, { target: { value: 'Kiem ke dot xuat' } });
    });
    const submitBtn = dom.window.document.querySelector('button[type="submit"]');
    act(() => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ')) throw new Error('Waiting AMBIGUOUS');
    });

    // 1. Click "Tải lại tồn kho từ máy chủ"
    const reloadBtn = Array.from(dom.window.document.querySelectorAll('button')).find(
      (btn) => btn.textContent.includes('Tải lại tồn kho')
    );
    assert.ok(reloadBtn, 'Reload button must be available in ambiguous state');
    act(() => {
      fireEvent.click(reloadBtn);
    });

    // 2. Modal enters AWAITING_ACKNOWLEDGEMENT
    await waitFor(() => {
      if (!dom.window.document.body.innerHTML.includes('Đã kiểm tra đối soát')) {
        throw new Error('Waiting for acknowledgement button');
      }
    });

    // In AWAITING_ACKNOWLEDGEMENT, submit remains locked
    assert.equal(submitBtn.disabled, true, 'Submit button must remain disabled in AWAITING_ACKNOWLEDGEMENT');

    // 3. User clicks explicit acknowledgement button
    const ackBtn = Array.from(dom.window.document.querySelectorAll('button')).find(
      (btn) => btn.textContent.includes('Đã kiểm tra đối soát')
    );
    assert.ok(ackBtn, 'Acknowledgement button must exist');
    act(() => {
      fireEvent.click(ackBtn);
    });

    // 4. Modal returns to IDLE with authoritative data, submit button unlocks!
    await waitFor(() => {
      if (dom.window.document.body.innerHTML.includes('Đã kiểm tra đối soát')) {
        throw new Error('Waiting for reconciliation notice to clear');
      }
    });

    assert.equal(
      dom.window.document.body.innerHTML.includes('CHƯA RÕ KẾT QUẢ'),
      false,
      'Ambiguous banner cleared after explicit acknowledgement'
    );
  });
});
