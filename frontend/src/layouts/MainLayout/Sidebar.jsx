import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Modal } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import styles from './MainLayout.module.css';

// Cấu hình 10 mục menu theo đúng thứ tự và phân quyền yêu cầu
export const MENU_ITEMS = [
  {
    path: '/dashboard',
    label: 'Tổng quan',
    roles: ['ADMIN'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    path: '/pos',
    label: 'Bán hàng (POS)',
    roles: ['ADMIN', 'STAFF'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M6 16h12" />
      </svg>
    ),
  },
  {
    path: '/products',
    label: 'Sản phẩm',
    roles: ['ADMIN', 'STAFF'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
        <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
        <line x1="12" y1="22.08" x2="12" y2="12" />
      </svg>
    ),
  },
  {
    path: '/categories',
    label: 'Danh mục',
    roles: ['ADMIN'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
        <line x1="7" y1="7" x2="7.01" y2="7" />
      </svg>
    ),
  },
  {
    path: '/suppliers',
    label: 'Nhà cung cấp',
    roles: ['ADMIN'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="3" width="15" height="13" />
        <polygon points="16 8 20 8 23 11 23 16 16 16 16 8" />
        <circle cx="5.5" cy="18.5" r="2.5" />
        <circle cx="18.5" cy="18.5" r="2.5" />
      </svg>
    ),
  },
  {
    path: '/purchases',
    label: 'Nhập hàng',
    roles: ['ADMIN'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2m5.66 0H14a2 2 0 0 1 2 2v3.34" />
        <path d="M14 3v4a1 1 0 0 0 1 1h4" />
        <path d="M18 12v9" />
        <path d="m15 18 3 3 3-3" />
      </svg>
    ),
  },
  {
    path: '/inventory',
    label: 'Tồn kho',
    roles: ['ADMIN', 'STAFF'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
  },
  {
    path: '/orders',
    label: 'Đơn hàng',
    roles: ['ADMIN', 'STAFF'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <line x1="10" y1="9" x2="8" y2="9" />
      </svg>
    ),
  },
  {
    path: '/staff',
    label: 'Nhân viên',
    roles: ['ADMIN'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    path: '/ai-assistant',
    label: 'Trợ lý AI',
    roles: ['ADMIN'],
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3z" />
      </svg>
    ),
  },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);

  if (!user) return null;

  const isAdmin = user.role === 'ADMIN';

  // Lọc danh sách menu dựa theo vai trò của người dùng hiện tại
  const visibleMenuItems = MENU_ITEMS.filter((item) =>
    item.roles.includes(user.role)
  );

  // Xác nhận đăng xuất thực sự khi bấm nút "Đăng xuất" màu đỏ trong Modal (FIX-03)
  const handleConfirmLogout = async () => {
    setIsLogoutModalOpen(false);
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <>
      <aside className={styles.sidebar}>
        {/* 1. PHẦN ĐẦU: THƯƠNG HIỆU (Đồng nhất cho cả ADMIN và STAFF) */}
        <div className={styles.brandSection}>
          <div className={styles.logoBox} aria-hidden="true">
            {/* Icon cửa hàng màu trắng */}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l1.5-5h15L21 9" />
              <path d="M3 9c0 1.66 1.34 3 3 3s3-1.34 3-3c0 1.66 1.34 3 3 3s3-1.34 3-3c0 1.66 1.34 3 3 3s3-1.34 3-3" />
              <path d="M5 12v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8" />
              <path d="M10 16h4v5h-4z" />
            </svg>
          </div>
          <div className={styles.brandTitleGroup}>
            <span className={styles.brandName}>RetailOps</span>
            <span className={styles.versionBadge}>v1.0</span>
          </div>
        </div>

        {/* 2. PHẦN GIỮA: DANH SÁCH MENU ĐIỀU HƯỚNG (Data-driven theo user.role) */}
        <nav className={styles.navSection} aria-label="Menu điều hướng chính">
          {visibleMenuItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                isActive
                  ? `${styles.navItem} ${styles.navItemActive}`
                  : styles.navItem
              }
            >
              <span className={styles.navIcon}>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* 3. PHẦN CUỐI: THẺ THÔNG TIN TÀI KHOẢN & NÚT ĐĂNG XUẤT NHANH */}
        <div className={styles.accountFooter}>
          <div className={styles.accountCard}>
            {/* Bên trái: Avatar chữ viết tắt (A hoặc NV) */}
            <div
              className={`${styles.avatarCircle} ${
                isAdmin ? styles.avatarAdmin : styles.avatarStaff
              }`}
            >
              {isAdmin ? 'A' : 'NV'}
            </div>

            {/* Ở giữa: Tên hiển thị & Vai trò */}
            <div className={styles.accountInfo}>
              <span className={styles.accountName} title={user.name}>
                {user.name}
              </span>
              <span className={styles.accountRole}>
                {isAdmin ? 'Quản lý' : 'Nhân viên'}
              </span>
            </div>

            {/* Bên phải: Nút icon Đăng xuất -> Bật Modal xác nhận */}
            <button
              type="button"
              onClick={() => setIsLogoutModalOpen(true)}
              className={styles.logoutButton}
              title="Đăng xuất"
              aria-label="Đăng xuất"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* MODAL XÁC NHẬN ĐĂNG XUẤT */}
      <Modal
        isOpen={isLogoutModalOpen}
        onClose={() => setIsLogoutModalOpen(false)}
        title="Xác nhận đăng xuất"
        maxWidth="420px"
        footer={
          <>
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={() => setIsLogoutModalOpen(false)}
            >
              Hủy
            </button>
            <button
              type="button"
              className={modalStyles.dangerBtn}
              onClick={handleConfirmLogout}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              <span>Đăng xuất</span>
            </button>
          </>
        }
      >
        Bạn có chắc chắn muốn đăng xuất khỏi hệ thống không?
      </Modal>
    </>
  );
}
