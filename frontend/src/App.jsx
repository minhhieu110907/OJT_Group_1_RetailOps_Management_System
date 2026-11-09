import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './App.css';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './components/common';
import AuthLayout from './layouts/AuthLayout/AuthLayout';
import MainLayout from './layouts/MainLayout/MainLayout';
import Login from './pages/Auth/Login';
import Register from './pages/Auth/Register';
import ForgotPassword from './pages/Auth/ForgotPassword';
import ResetPassword from './pages/Auth/ResetPassword';
import AccountStatus from './pages/Auth/AccountStatus';
import ProductList from './pages/Products/ProductList';
import { HealthCheckPage } from './pages/HealthCheckPage';
import ProtectedRoute from './routes/ProtectedRoute';
import styles from './layouts/MainLayout/MainLayout.module.css';

// Component giữ chỗ cho các tính năng đang phát triển theo lộ trình Sprint
function PlaceholderPage({ title }) {
  return (
    <div className={styles.demoCard}>
      <div className={styles.demoHeader}>
        <h1 className={styles.demoTitle}>{title}</h1>
      </div>
      <p className={styles.demoDesc}>
        Tính năng đang được phát triển theo lộ trình Sprint
      </p>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* 0. Route kiểm tra kết nối hệ thống (Bảo toàn minh chứng Sprint 0) */}
            <Route path="/health" element={<HealthCheckPage />} />

            {/* 1. Nhóm Route Công khai (AuthLayout) */}
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/account-status" element={<AccountStatus />} />
            </Route>

            {/* 2. Nhóm Route Nội bộ được bảo vệ (Bọc trong <ProtectedRoute /> và <MainLayout />) */}
            <Route
              element={<ProtectedRoute allowedRoles={['ADMIN', 'STAFF']} />}
            >
              <Route element={<MainLayout />}>
                {/* 2.1. Nhánh dùng chung (cả ADMIN và STAFF đều truy cập được) */}
                <Route
                  path="/pos"
                  element={<PlaceholderPage title="Màn hình Bán hàng (POS)" />}
                />
                <Route path="/products" element={<ProductList />} />
                <Route
                  path="/inventory"
                  element={<PlaceholderPage title="Màn hình Quản lý Tồn kho" />}
                />
                <Route
                  path="/orders"
                  element={<PlaceholderPage title="Màn hình Quản lý Đơn hàng" />}
                />

                {/* 2.2. Nhánh Quản trị (CHỈ DÀNH RIÊNG CHO ADMIN) */}
                <Route element={<ProtectedRoute allowedRoles={['ADMIN']} />}>
                  <Route
                    path="/dashboard"
                    element={
                      <PlaceholderPage title="Báo cáo Tổng quan Dashboard" />
                    }
                  />
                  <Route
                    path="/categories"
                    element={<PlaceholderPage title="Quản lý Danh mục" />}
                  />
                  <Route
                    path="/suppliers"
                    element={<PlaceholderPage title="Quản lý Nhà cung cấp" />}
                  />
                  <Route
                    path="/purchases"
                    element={<PlaceholderPage title="Quản lý Nhập hàng" />}
                  />
                  <Route
                    path="/customers"
                    element={<PlaceholderPage title="Quản lý Khách hàng" />}
                  />
                  <Route
                    path="/analytics"
                    element={
                      <PlaceholderPage title="Báo cáo & Phân tích Doanh thu" />
                    }
                  />
                  <Route
                    path="/staff"
                    element={<PlaceholderPage title="Quản lý Nhân viên" />}
                  />
                  <Route
                    path="/ai-assistant"
                    element={<PlaceholderPage title="Trợ lý AI (RetailOps AI)" />}
                  />
                </Route>
              </Route>
            </Route>

            {/* 3. Điều hướng mặc định: "/" hoặc "*" đều chuyển hướng an toàn về "/login" */}
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}
