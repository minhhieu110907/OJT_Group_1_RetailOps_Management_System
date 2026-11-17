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
  url: 'http://localhost',
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

// 2. Build production ThemeProvider via Vite SSR
const outDir = path.resolve('./node_modules/.cache_theme_test');
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
      input: {
        themeContext: path.resolve('./src/context/ThemeContext.jsx'),
      },
    },
  },
  logLevel: 'silent',
});

// 3. Import bundled ThemeContext & testing library
const themeModUrl = pathToFileURL(path.join(outDir, 'themeContext.js')).href;
const { ThemeProvider, useTheme } = await import(themeModUrl);
const { render, fireEvent, act, cleanup } = await import('@testing-library/react');
const React = await import('react');

// Test consumer component
function ThemeConsumer() {
  const { theme, toggleTheme } = useTheme();
  return React.createElement(
    'div',
    null,
    React.createElement('span', { 'data-testid': 'theme-text' }, theme),
    React.createElement(
      'button',
      {
        'data-testid': 'theme-toggle-btn',
        'aria-label': theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối',
        onClick: toggleTheme,
      },
      'Toggle'
    )
  );
}

describe('Theme Toggle (Light / Dark Mode) Suite', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    // Default matchMedia mock returning light
    window.matchMedia = (query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
  });

  afterEach(() => {
    cleanup();
  });

  test('TEST A — Light → Dark → Light toggle interaction and DOM synchronization', () => {
    localStorage.removeItem('retailops_theme');
    window.matchMedia = () => ({ matches: false });

    const { getByTestId } = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );

    // Initial state: light
    assert.equal(getByTestId('theme-text').textContent, 'light');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
    assert.equal(localStorage.getItem('retailops_theme'), 'light');

    // Toggle 1: Light -> Dark
    act(() => {
      fireEvent.click(getByTestId('theme-toggle-btn'));
    });

    assert.equal(getByTestId('theme-text').textContent, 'dark');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
    assert.equal(localStorage.getItem('retailops_theme'), 'dark');

    // Toggle 2: Dark -> Light
    act(() => {
      fireEvent.click(getByTestId('theme-toggle-btn'));
    });

    assert.equal(getByTestId('theme-text').textContent, 'light');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
    assert.equal(localStorage.getItem('retailops_theme'), 'light');
  });

  test('TEST B — Persistence after remount without API or auth coupling', () => {
    localStorage.setItem('retailops_theme', 'dark');

    // Mount 1
    const { getByTestId, unmount } = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );

    assert.equal(getByTestId('theme-text').textContent, 'dark');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');

    // Unmount
    unmount();

    // Mount 2: New instance must restore dark
    const view2 = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );

    assert.equal(view2.getByTestId('theme-text').textContent, 'dark');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
    assert.equal(localStorage.getItem('retailops_theme'), 'dark');
  });

  test('TEST C — OS preference fallback when no theme saved in localStorage', () => {
    // Case C1: OS dark
    localStorage.removeItem('retailops_theme');
    window.matchMedia = (query) => ({
      matches: query.includes('dark'),
    });

    const view1 = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );
    assert.equal(view1.getByTestId('theme-text').textContent, 'dark');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
    view1.unmount();

    // Case C2: OS light
    localStorage.removeItem('retailops_theme');
    window.matchMedia = () => ({ matches: false });

    const view2 = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );
    assert.equal(view2.getByTestId('theme-text').textContent, 'light');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
    view2.unmount();

    // Case C3: Saved theme takes strict precedence over OS preference
    localStorage.setItem('retailops_theme', 'light');
    window.matchMedia = () => ({ matches: true }); // OS is dark, but saved is light

    const view3 = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );
    assert.equal(view3.getByTestId('theme-text').textContent, 'light');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
    view3.unmount();
  });

  test('TEST D — Invalid storage values and storage access errors fail-closed gracefully', () => {
    // Case D1: Corrupted / invalid storage string
    localStorage.setItem('retailops_theme', 'invalid_mode_xyz');
    window.matchMedia = () => ({ matches: false });

    const view1 = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );
    // Should fallback safely to light (or OS)
    assert.equal(view1.getByTestId('theme-text').textContent, 'light');
    view1.unmount();

    // Case D2: localStorage.getItem throws SecurityError (e.g. private mode / cookies disabled)
    const originalGetItem = localStorage.getItem;
    const originalSetItem = localStorage.setItem;

    localStorage.getItem = () => {
      throw new Error('SecurityError: Access is denied for this document');
    };
    localStorage.setItem = () => {
      throw new Error('SecurityError: Access is denied for this document');
    };

    let crashed = false;
    let view2;
    try {
      view2 = render(
        React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
      );
      act(() => {
        fireEvent.click(view2.getByTestId('theme-toggle-btn'));
      });
    } catch {
      crashed = true;
    }

    assert.equal(crashed, false, 'ThemeProvider must NEVER crash when localStorage throws');
    if (view2) {
      view2.unmount();
    }

    // Restore localStorage
    localStorage.getItem = originalGetItem;
    localStorage.setItem = originalSetItem;
  });

  test('TEST E — Header theme button accessibility name and toggle contract', () => {
    localStorage.setItem('retailops_theme', 'light');

    const { getByTestId } = render(
      React.createElement(ThemeProvider, null, React.createElement(ThemeConsumer))
    );

    const toggleBtn = getByTestId('theme-toggle-btn');
    assert.equal(toggleBtn.getAttribute('aria-label'), 'Chuyển sang chế độ tối');

    act(() => {
      fireEvent.click(toggleBtn);
    });

    assert.equal(toggleBtn.getAttribute('aria-label'), 'Chuyển sang chế độ sáng');
    assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
  });

  test('Source Code Static Invariants — App.jsx and Header.jsx integration', () => {
    const appSource = fs.readFileSync(path.resolve('./src/App.jsx'), 'utf8');
    assert.match(appSource, /<ThemeProvider>/, 'App.jsx must wrap application subtree in ThemeProvider');
    assert.match(appSource, /<\/ThemeProvider>/, 'App.jsx must close ThemeProvider');

    const headerSource = fs.readFileSync(path.resolve('./src/layouts/MainLayout/Header.jsx'), 'utf8');
    assert.match(headerSource, /useTheme\(\)/, 'Header.jsx must consume useTheme()');
    assert.match(headerSource, /onClick=\{toggleTheme\}/, 'Header.jsx must bind toggleTheme to button');
    assert.match(headerSource, /Chuyển sang chế độ sáng/, 'Header.jsx must have accessible Vietnamese label');
  });
});
