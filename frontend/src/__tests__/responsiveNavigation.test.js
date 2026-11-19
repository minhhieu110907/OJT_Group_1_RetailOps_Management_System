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
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.HTMLInputElement = dom.window.HTMLInputElement;
globalThis.HTMLButtonElement = dom.window.HTMLButtonElement;
Object.defineProperty(globalThis, 'navigator', {
  value: dom.window.navigator,
  configurable: true,
  writable: true,
});
globalThis.localStorage = dom.window.localStorage;

// 2. Build test harness via Vite once
const outDir = path.resolve('./node_modules/.cache_responsive_test');
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
      input: path.resolve('./src/__tests__/responsiveLayoutHarness.jsx'),
    },
  },
  logLevel: 'silent',
});

// 3. Import bundled components & testing library
const harnessUrl = pathToFileURL(path.join(outDir, 'responsiveLayoutHarness.js')).href;
const {
  Sidebar,
  AuthContext,
  ThemeProvider,
  TestLayoutApp,
} = await import(harnessUrl);

const testingLibrary = await import('@testing-library/react');
const { render, fireEvent, act } = testingLibrary;
const routerDom = await import('react-router-dom');
const { MemoryRouter } = routerDom;
const React = (await import('react')).default;

describe('Responsive Navigation & Accessibility Suite [T04AA6A]', () => {
  const mockAdminUser = {
    id: 1,
    name: 'Quản trị viên Demo',
    email: 'admin@retailops.vn',
    role: 'ADMIN',
    status: 'ACTIVE',
  };

  const mockStaffUser = {
    id: 2,
    name: 'Nhân viên Bán hàng',
    email: 'staff@retailops.vn',
    role: 'STAFF',
    status: 'ACTIVE',
  };

  const createAuthValue = (user) => ({
    user,
    role: user?.role,
    isAuthenticated: !!user,
    isMockMode: false,
    logout: async () => {},
    getMyProfile: async () => ({ full_name: user?.name, email: user?.email }),
    updateMyProfile: async () => {},
  });

  beforeEach(() => {
    let currentIsMobile = false;
    const listeners = [];

    window.matchMedia = (query) => {
      const isMobileQuery = query.includes('max-width: 1023px');
      const isDesktopQuery = query.includes('min-width: 1024px');
      return {
        get matches() {
          return isMobileQuery ? currentIsMobile : isDesktopQuery ? !currentIsMobile : false;
        },
        media: query,
        addEventListener: (event, cb) => {
          if (event === 'change') listeners.push({ query, cb });
        },
        removeEventListener: (event, cb) => {
          const idx = listeners.findIndex((item) => item.cb === cb);
          if (idx !== -1) listeners.splice(idx, 1);
        },
        addListener: (cb) => listeners.push({ query, cb }),
        removeListener: (cb) => {
          const idx = listeners.findIndex((item) => item.cb === cb);
          if (idx !== -1) listeners.splice(idx, 1);
        },
      };
    };

    window.__setMobileViewport = (isMobile) => {
      currentIsMobile = isMobile;
      for (const item of [...listeners]) {
        const isDesktopQuery = item.query.includes('min-width: 1024px');
        const matches = isDesktopQuery ? !isMobile : isMobile;
        item.cb({ matches });
      }
    };
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.body.style.overflow = '';
  });

  test('1. Mobile hamburger mở drawer, aria-expanded và aria-controls phản ánh đúng', () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const hamburger = container.querySelector('#mobile-nav-toggle-btn');
    assert.ok(hamburger, 'Nút hamburger phải tồn tại');
    assert.equal(hamburger.getAttribute('aria-expanded'), 'false');
    assert.equal(hamburger.getAttribute('aria-controls'), 'main-sidebar-drawer');

    const drawer = container.querySelector('#main-sidebar-drawer');
    assert.ok(drawer, 'Drawer sidebar phải tồn tại');

    // Click mở drawer
    act(() => {
      fireEvent.click(hamburger);
    });

    assert.equal(hamburger.getAttribute('aria-expanded'), 'true');
    assert.match(drawer.className, /sidebarMobileOpen/);
    assert.equal(drawer.getAttribute('role'), 'dialog');
    assert.equal(drawer.getAttribute('aria-modal'), 'true');
  });

  test('2. Click nút đóng và click backdrop đóng drawer', () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const hamburger = container.querySelector('#mobile-nav-toggle-btn');
    act(() => {
      fireEvent.click(hamburger);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'true');

    // Tìm close button trong drawer
    const closeBtn = container.querySelector('button[aria-label="Đóng thanh điều hướng"]');
    assert.ok(closeBtn, 'Nút đóng drawer phải tồn tại');

    act(() => {
      fireEvent.click(closeBtn);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'false');

    // Mở lại và test đóng bằng backdrop
    act(() => {
      fireEvent.click(hamburger);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'true');

    const backdrop = container.querySelector('[aria-hidden="true"]');
    assert.ok(backdrop, 'Backdrop mờ phải tồn tại');
    act(() => {
      fireEvent.click(backdrop);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'false');
  });

  test('3. Nhấn phím Escape đóng drawer và trả lại focus cho hamburger toggle', () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const hamburger = container.querySelector('#mobile-nav-toggle-btn');
    act(() => {
      fireEvent.click(hamburger);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'true');

    // Bấm phím Escape
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });

    assert.equal(hamburger.getAttribute('aria-expanded'), 'false');
  });

  test('4. Khi drawer đóng trên mobile, drawer bị inert và có aria-hidden=true', () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const drawer = container.querySelector('#main-sidebar-drawer');
    assert.equal(drawer.getAttribute('aria-hidden'), 'true');
    assert.ok(drawer.hasAttribute('inert'), 'Drawer đóng trên mobile phải có thuộc tính inert');
  });

  test('5. Viewport resize từ mobile sang desktop (>= 1024px) tự động reset drawer state về false', () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const hamburger = container.querySelector('#mobile-nav-toggle-btn');
    act(() => {
      fireEvent.click(hamburger);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'true');

    // Resize sang Desktop
    act(() => {
      window.__setMobileViewport(false);
    });

    // Khi quay lại desktop, drawer phải đóng và hamburger aria-expanded=false
    assert.equal(hamburger.getAttribute('aria-expanded'), 'false');

    // Resize ngược về mobile: drawer KHÔNG được tự động mở lại
    act(() => {
      window.__setMobileViewport(true);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'false');
  });

  test('6. RBAC Invariant: STAFF không thấy các menu của ADMIN (Tổng quan, Danh mục, NCC, Nhập hàng)', () => {
    const { container: adminContainer } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/pos'] },
        React.createElement(
          AuthContext.Provider,
          { value: createAuthValue(mockAdminUser) },
          React.createElement(
            ThemeProvider,
            null,
            React.createElement(Sidebar, { isOpen: true, onClose: () => {} })
          )
        )
      )
    );

    const adminLinks = Array.from(adminContainer.querySelectorAll('nav a')).map(
      (a) => a.textContent.trim()
    );
    assert.ok(adminLinks.includes('Tổng quan'), 'ADMIN phải thấy Tổng quan');
    assert.ok(adminLinks.includes('Danh mục'), 'ADMIN phải thấy Danh mục');
    assert.ok(adminLinks.includes('Nhà cung cấp'), 'ADMIN phải thấy Nhà cung cấp');

    const { container: staffContainer } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/pos'] },
        React.createElement(
          AuthContext.Provider,
          { value: createAuthValue(mockStaffUser) },
          React.createElement(
            ThemeProvider,
            null,
            React.createElement(Sidebar, { isOpen: true, onClose: () => {} })
          )
        )
      )
    );

    const staffLinks = Array.from(staffContainer.querySelectorAll('nav a')).map(
      (a) => a.textContent.trim()
    );
    assert.equal(staffLinks.includes('Tổng quan'), false, 'STAFF không được thấy Tổng quan');
    assert.equal(staffLinks.includes('Danh mục'), false, 'STAFF không được thấy Danh mục');
    assert.equal(staffLinks.includes('Nhà cung cấp'), false, 'STAFF không được thấy Nhà cung cấp');
    assert.ok(staffLinks.includes('Bán hàng'), 'STAFF thấy Bán hàng');
    assert.ok(staffLinks.includes('Tồn kho'), 'STAFF thấy Tồn kho');
  });

  test('8. P1 Regression: Mở Logout Modal từ Sidebar không chuyển focus về hamburger, Escape chỉ đóng modal, hủy modal trả focus về nút Logout', async () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const hamburger = container.querySelector('#mobile-nav-toggle-btn');
    act(() => {
      fireEvent.click(hamburger);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'true');

    // Chờ focus ban đầu vào closeBtn
    await new Promise((res) => setTimeout(res, 60));

    // Tìm nút Đăng xuất trong Sidebar
    const logoutBtn = container.querySelector('button[aria-label="Đăng xuất"]');
    assert.ok(logoutBtn, 'Nút Đăng xuất trong Sidebar phải tồn tại');

    // Bấm mở Logout Confirmation Modal
    act(() => {
      fireEvent.click(logoutBtn);
    });

    // 1. Kiểm tra focus KHÔNG bị chuyển về hamburger
    assert.notEqual(document.activeElement, hamburger, 'Focus KHÔNG được chuyển về hamburger khi mở Logout Modal');
    assert.equal(hamburger.getAttribute('aria-expanded'), 'true', 'Drawer vẫn phải đang mở');

    // 2. Body scroll lock vẫn được giữ khi mở Logout Modal
    assert.equal(document.body.style.overflow, 'hidden', 'Body scroll lock vẫn phải giữ khi Logout Modal mở');

    // 3. Nhấn Escape 1 lần -> CHỈ đóng Logout Modal, drawer vẫn mở
    act(() => {
      const modalBackdrop = document.querySelector('[class*="backdrop"]');
      fireEvent.keyDown(modalBackdrop || document, { key: 'Escape' });
    });

    assert.equal(hamburger.getAttribute('aria-expanded'), 'true', 'Drawer vẫn mở sau khi Escape đóng Logout Modal');
    assert.equal(document.body.style.overflow, 'hidden', 'Body scroll lock vẫn duy trì cho Drawer sau khi đóng Logout Modal');

    // Chờ trả focus về logout button
    await new Promise((res) => setTimeout(res, 60));
    assert.equal(document.activeElement, logoutBtn, 'Focus phải quay về nút Logout sau khi đóng Logout Modal');

    // 4. Nhấn Escape lần nữa -> Drawer đóng và focus trả về hamburger
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });

    assert.equal(hamburger.getAttribute('aria-expanded'), 'false', 'Drawer phải đóng sau Escape thứ 2');
    assert.equal(document.activeElement, hamburger, 'Focus phải trở về hamburger toggle khi drawer đóng bằng Escape');
    assert.equal(document.body.style.overflow, '', 'Body scroll lock được dọn dẹp sạch sẽ khi drawer đóng');
  });

  test('9. P1 Focus Trap: Phím Tab và Shift+Tab giữ focus tuần hoàn bên trong Drawer', async () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const hamburger = container.querySelector('#mobile-nav-toggle-btn');
    act(() => {
      fireEvent.click(hamburger);
    });

    await new Promise((res) => setTimeout(res, 60));

    const drawer = container.querySelector('#main-sidebar-drawer');
    const focusable = drawer.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    assert.ok(focusable.length > 1, 'Drawer phải có ít nhất 2 phần tử tương tác');

    const firstEl = focusable[0];
    const lastEl = focusable[focusable.length - 1];

    // Focus vào phần tử cuối và nhấn Tab -> quay về đầu
    lastEl.focus();
    assert.equal(document.activeElement, lastEl);

    act(() => {
      fireEvent.keyDown(document, { key: 'Tab' });
    });
    assert.equal(document.activeElement, firstEl, 'Tab từ phần tử cuối phải quay về phần tử đầu tiên');

    // Shift+Tab từ phần tử đầu -> quay về cuối
    firstEl.focus();
    assert.equal(document.activeElement, firstEl);

    act(() => {
      fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    });
    assert.equal(document.activeElement, lastEl, 'Shift+Tab từ phần tử đầu phải quay về phần tử cuối cùng');
  });

  test('10. Route Navigation: Click NavLink đóng drawer và KHÔNG ép focus về hamburger', () => {
    window.__setMobileViewport(true);

    const { container } = render(
      React.createElement(
        MemoryRouter,
        { initialEntries: ['/dashboard'] },
        React.createElement(TestLayoutApp, {
          authValue: createAuthValue(mockAdminUser),
        })
      )
    );

    const hamburger = container.querySelector('#mobile-nav-toggle-btn');
    act(() => {
      fireEvent.click(hamburger);
    });
    assert.equal(hamburger.getAttribute('aria-expanded'), 'true');

    // Tìm link POS và click
    const posLink = container.querySelector('a[href="/pos"]');
    assert.ok(posLink, 'Link Bán hàng phải tồn tại');

    act(() => {
      fireEvent.click(posLink);
    });

    // Drawer đóng và focus không bị cưỡng ép về hamburger
    assert.equal(hamburger.getAttribute('aria-expanded'), 'false', 'Drawer phải tự động đóng khi chuyển route');
    assert.notEqual(document.activeElement, hamburger, 'Không cưỡng ép focus về hamburger khi chuyển route');
  });
});
