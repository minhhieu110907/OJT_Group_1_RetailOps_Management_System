import { useState, useEffect, useRef } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
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
    label: 'Bán hàng',
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

export default function Sidebar({
  isOpen = false,
  onClose = () => {},
}) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  // Theo dõi breakpoint mobile/tablet (< 1024px) khởi tạo một cách an toàn
  const [isMobileViewport, setIsMobileViewport] = useState(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(max-width: 1023px)').matches;
    }
    return false;
  });

  const sidebarRef = useRef(null);
  const closeBtnRef = useRef(null);
  const logoutBtnRef = useRef(null);
  const prevPathnameRef = useRef(location.pathname);
  const prevIsOpenRef = useRef(isOpen);
  const isNavigatingRef = useRef(false);
  const isDesktopResizingRef = useRef(false);
  const drawerOriginalOverflowRef = useRef(null);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia('(max-width: 1023px)');

    const handleMediaChange = (e) => {
      if (!e.matches && isOpen) {
        // Chuyển sang desktop: đánh dấu cờ để không trả focus về hamburger đang bị ẩn
        isDesktopResizingRef.current = true;
      }
      setIsMobileViewport(e.matches);
    };

    if (mql.addEventListener) {
      mql.addEventListener('change', handleMediaChange);
    } else if (mql.addListener) {
      mql.addListener(handleMediaChange);
    }

    return () => {
      if (mql.removeEventListener) {
        mql.removeEventListener('change', handleMediaChange);
      } else if (mql.removeListener) {
        mql.removeListener(handleMediaChange);
      }
    };
  }, [isOpen]);

  // Section 5: Đóng sidebar khi route thực sự thay đổi
  useEffect(() => {
    if (prevPathnameRef.current !== location.pathname) {
      prevPathnameRef.current = location.pathname;
      if (isOpen) {
        isNavigatingRef.current = true;
        onClose();
      }
    }
  }, [location.pathname, isOpen, onClose]);

  // Trách nhiệm 1: Focus restoration CHỈ khi drawer thực sự chuyển từ Mở -> Đóng
  useEffect(() => {
    const wasOpen = prevIsOpenRef.current;
    prevIsOpenRef.current = isOpen;

    // Khi drawer đóng lại thực sự
    if (wasOpen && !isOpen) {
      if (!isNavigatingRef.current && !isDesktopResizingRef.current) {
        const toggleBtn = document.getElementById('mobile-nav-toggle-btn');
        if (toggleBtn) {
          toggleBtn.focus();
        }
      }
      isNavigatingRef.current = false;
      isDesktopResizingRef.current = false;
    } else if (!wasOpen && isOpen && isMobileViewport) {
      // Khi drawer vừa mở: focus vào nút đóng drawer
      const initialFocusTimer = setTimeout(() => {
        if (closeBtnRef.current) {
          closeBtnRef.current.focus();
        }
      }, 50);
      return () => clearTimeout(initialFocusTimer);
    }
  }, [isOpen, isMobileViewport]);

  // Trách nhiệm 2: Scroll lock an toàn cho drawer trên mobile
  useEffect(() => {
    if (!isOpen || !isMobileViewport) {
      // Khi drawer đóng hoặc unmount/chuyển desktop: khôi phục overflow ban đầu nếu drawer từng khóa
      if (drawerOriginalOverflowRef.current !== null) {
        document.body.style.overflow = drawerOriginalOverflowRef.current;
        drawerOriginalOverflowRef.current = null;
      }
      return;
    }

    // Khi drawer mở: chỉ chụp overflow một lần nếu chưa từng chụp
    if (drawerOriginalOverflowRef.current === null) {
      drawerOriginalOverflowRef.current = document.body.style.overflow;
    }
    document.body.style.overflow = 'hidden';

    // Cleanup khi unmount component
    return () => {
      if (drawerOriginalOverflowRef.current !== null) {
        document.body.style.overflow = drawerOriginalOverflowRef.current;
        drawerOriginalOverflowRef.current = null;
      }
    };
  }, [isOpen, isMobileViewport]);

  // Trách nhiệm 3: Keyboard Navigation & Focus Trap trong Drawer
  useEffect(() => {
    if (!isOpen || !isMobileViewport) return;

    const handleKeyDown = (e) => {
      // Khi Logout Modal đang mở: drawer nhường quyền xử lý hoàn toàn cho Modal
      if (isLogoutModalOpen) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
        return;
      }

      if (e.key === 'Tab') {
        if (!sidebarRef.current) return;
        const focusableElements = sidebarRef.current.querySelectorAll(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, isMobileViewport, isLogoutModalOpen, onClose]);

  // Khi đóng Logout Modal mà drawer vẫn mở: trả focus về nút mở Logout
  const handleCloseLogoutModal = () => {
    setIsLogoutModalOpen(false);
    setTimeout(() => {
      if (logoutBtnRef.current) {
        logoutBtnRef.current.focus();
      }
    }, 50);
  };

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

  // Drawer mobile đóng thì vô hiệu hóa focusable và ẩn khỏi accessibility tree
  const isMobileClosed = isMobileViewport && !isOpen;

  return (
    <>
      {/* Backdrop mờ phía sau Sidebar khi mở trên Mobile / Tablet */}
      {isOpen && isMobileViewport && (
        <div
          className={styles.sidebarBackdrop}
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        id="main-sidebar-drawer"
        ref={sidebarRef}
        className={`${styles.sidebar} ${isOpen ? styles.sidebarMobileOpen : ''}`}
        aria-label="Thanh điều hướng chính"
        aria-hidden={isMobileClosed ? 'true' : undefined}
        inert={isMobileClosed ? true : undefined}
        {...(isMobileViewport && isOpen ? { role: 'dialog', 'aria-modal': 'true' } : {})}
      >
        {/* 1. PHẦN ĐẦU: THƯƠNG HIỆU (Đồng nhất cho cả ADMIN và STAFF) */}
        <div className={styles.brandSection}>
          <div className={styles.brandTitleWrap}>
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

          {/* Nút đóng Sidebar trên Mobile */}
          <button
            ref={closeBtnRef}
            type="button"
            className={styles.mobileCloseBtn}
            onClick={onClose}
            aria-label="Đóng thanh điều hướng"
            title="Đóng menu"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
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
              <span
                className={styles.accountName}
                title={(user.name || '').replace(/\s*\(admin\)/gi, '').trim()}
              >
                {(user.name || '').replace(/\s*\(admin\)/gi, '').trim()}
              </span>
              <span className={styles.accountRole}>
                {isAdmin ? 'Quản lý' : 'Nhân viên'}
              </span>
            </div>

            {/* Bên phải: Nút icon Đăng xuất -> Bật Modal xác nhận */}
            <button
              ref={logoutBtnRef}
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
        onClose={handleCloseLogoutModal}
        title="Xác nhận đăng xuất"
        maxWidth="420px"
        footer={
          <>
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={handleCloseLogoutModal}
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
