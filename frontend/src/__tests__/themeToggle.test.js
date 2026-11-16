import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const headerPath = path.resolve(__dirname, '../layouts/MainLayout/Header.jsx');
const themeContextPath = path.resolve(__dirname, '../context/ThemeContext.jsx');
const appPath = path.resolve(__dirname, '../App.jsx');

describe('Theme Toggle (Light / Dark Mode) Suite', () => {
  test('ThemeContext.jsx provides ThemeProvider, useTheme and manages data-theme & localStorage', () => {
    const source = fs.readFileSync(themeContextPath, 'utf8');
    assert.match(source, /createContext/);
    assert.match(source, /ThemeProvider/);
    assert.match(source, /useTheme/);
    assert.match(source, /retailops_theme/);
    assert.match(source, /document\.documentElement\.setAttribute\('data-theme', theme\)/);
    assert.match(source, /localStorage\.setItem/);
  });

  test('App.jsx wraps the application tree inside ThemeProvider', () => {
    const source = fs.readFileSync(appPath, 'utf8');
    assert.match(source, /import.*ThemeProvider.*from.*ThemeContext/);
    assert.match(source, /<ThemeProvider>/);
    assert.match(source, /<\/ThemeProvider>/);
  });

  test('Header.jsx places Light/Dark mode toggle button right beside Help button', () => {
    const source = fs.readFileSync(headerPath, 'utf8');
    assert.match(source, /import.*useTheme.*from.*ThemeContext/);
    assert.match(source, /const.*theme.*toggleTheme.*= useTheme\(\)/);
    
    // Help button
    assert.match(source, /title="Trợ giúp & Hướng dẫn"/);
    
    // Theme toggle button right beside Help button
    assert.match(source, /onClick={toggleTheme}/);
    assert.match(source, /Chuyển sang chế độ (sáng|tối)/);
  });
});
