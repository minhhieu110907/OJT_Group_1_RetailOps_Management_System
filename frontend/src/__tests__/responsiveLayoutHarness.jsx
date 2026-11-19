import React from 'react';
import { Routes, Route } from 'react-router-dom';
import MainLayout from '../layouts/MainLayout/MainLayout.jsx';
import Header from '../layouts/MainLayout/Header.jsx';
import Sidebar, { MENU_ITEMS } from '../layouts/MainLayout/Sidebar.jsx';
import { AuthContext } from '../context/AuthContext.jsx';
import { ThemeProvider } from '../context/ThemeContext.jsx';
import { ToastProvider } from '../components/common/Toast/ToastContext.jsx';

export {
  MainLayout,
  Header,
  Sidebar,
  MENU_ITEMS,
  AuthContext,
  ThemeProvider,
  ToastProvider,
};

export function TestLayoutApp({ authValue, initialRoute = '/dashboard' }) {
  return (
    <AuthContext.Provider value={authValue}>
      <ThemeProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<MainLayout />}>
              <Route path="dashboard" element={<div data-testid="dashboard-content">Dashboard Content</div>} />
              <Route path="pos" element={<div data-testid="pos-content">POS Content</div>} />
              <Route path="inventory" element={<div data-testid="inventory-content">Inventory Content</div>} />
            </Route>
          </Routes>
        </ToastProvider>
      </ThemeProvider>
    </AuthContext.Provider>
  );
}
