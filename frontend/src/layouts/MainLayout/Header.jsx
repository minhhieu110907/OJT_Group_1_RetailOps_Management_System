import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Modal, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import { MENU_ITEMS } from './Sidebar';
import styles from './MainLayout.module.css';

export default function Header() {
  const { user, logout } = useAuth();
  const toast = useToast();
  const location = useLocation();
  const navigate = useNavigate();

  // State quản lý đóng/mở User Dropdown và Modal xác nhận đăng xuất
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Tự động đóng Dropdown khi bấm ra ngoài hoặc nhấn phím Esc
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  // Tìm tên trang hiện tại dựa trên đường dẫn URL để hiển thị trên Breadcrumb
  const currentMenu = MENU_ITEMS.find((item) => item.path === location.pathname);
  const currentPageLabel = currentMenu ? currentMenu.label : 'Không gian làm việc';

  const isAdmin = user?.role === 'ADMIN';
  const roleLabel = isAdmin ? 'Quản trị viên' : 'Nhân viên';
  const avatarInitials = isAdmin ? 'A' : 'NV';

  // Khi bấm vào hàng "Đăng xuất" trong Dropdown -> Đóng Dropdown và mở Modal xác nhận
  const handleOpenLogoutModal = () => {
    setIsDropdownOpen(false);
    setIsLogoutModalOpen(true);
  };

  // Khi bấm nút "Đăng xuất" màu đỏ trong Modal xác nhận
  const handleConfirmLogout = async () => {
    setIsLogoutModalOpen(false);
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <>
      <header className={styles.header}>
        {/* Bên trái Header: Breadcrumb đơn giản */}
        <div className={styles.breadcrumb}>
          <span className={styles.breadcrumbRoot}>RetailOps v1.0</span>
          <span className={styles.breadcrumbSeparator}>/</span>
          <span className={styles.breadcrumbCurrent}>{currentPageLabel}</span>
        </div>

        {/* Bên phải Header: Trợ giúp (?), Chuông thông báo, Cụm User Dropdown */}
        <div className={styles.headerActions}>
          {/* Nút icon Trợ giúp (?) */}
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => toast.info('Trung tâm trợ giúp RetailOps v1.0')}
            title="Trợ giúp & Hướng dẫn"
            aria-label="Trợ giúp"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </button>

          {/* Nút icon Chuông thông báo (🔔) */}
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => toast.info('Bạn có 1 thông báo hệ thống mới')}
            title="Thông báo hệ thống"
            aria-label="Thông báo"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <span className={styles.notificationDot} />
          </button>

          <div className={styles.headerDivider} />

          {/* Cụm nút User Trigger & Menu Tài khoản thả xuống (User Dropdown) */}
          <div className={styles.userDropdownWrapper} ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setIsDropdownOpen((prev) => !prev)}
              className={`${styles.userDropdownTrigger} ${
                isDropdownOpen ? styles.userDropdownTriggerActive : ''
              }`}
              aria-expanded={isDropdownOpen}
              aria-haspopup="menu"
            >
              {/* Avatar hình tròn/bo góc xanh lá #087F5B chữ A hoặc NV màu trắng */}
              <div className={styles.headerUserAvatar}>{avatarInitials}</div>

              {/* Tên người dùng & Nhãn vai trò màu xanh #087F5B */}
              <div className={styles.headerUserText}>
                <span className={styles.headerUserName}>{user?.name}</span>
                <span className={styles.headerUserRoleBadge}>{roleLabel}</span>
              </div>

              {/* Icon mũi tên lên/xuống (Chevron) tự động đổi hướng khi đóng/mở */}
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`${styles.chevronIcon} ${
                  isDropdownOpen ? styles.chevronIconActive : ''
                }`}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {/* Khung Dropdown hiển thị khi bấm mở */}
            {isDropdownOpen && (
              <div className={styles.dropdownMenu} role="menu">
                {/* 1. Phần Đầu Dropdown (Padding 16px 20px) */}
                <div className={styles.dropdownHeader}>
                  <div className={styles.dropdownAvatarLarge}>
                    {avatarInitials}
                  </div>
                  <div className={styles.dropdownUserInfo}>
                    <div className={styles.dropdownNameRow}>
                      <span className={styles.dropdownUserName}>
                        {user?.name}
                      </span>
                      <span className={styles.dropdownRoleBadge}>
                        {roleLabel}
                      </span>
                    </div>
                    <span className={styles.dropdownUserEmail}>
                      {user?.email}
                    </span>
                  </div>
                </div>

                {/* 2. Phần Giữa Dropdown (Menu thao tác - Padding 8px 0) */}
                <div className={styles.dropdownSection}>
                  {/* Hàng 1: Thông tin cá nhân */}
                  <button
                    type="button"
                    className={styles.dropdownItem}
                    role="menuitem"
                    onClick={() => {
                      setIsDropdownOpen(false);
                      toast.info('Đang mở trang Thông tin cá nhân');
                    }}
                  >
                    <span className={styles.dropdownItemIcon}>
                      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                        <circle cx="12" cy="7" r="4" />
                      </svg>
                    </span>
                    <span>Thông tin cá nhân</span>
                  </button>

                  {/* Hàng 2: Đổi mật khẩu */}
                  <button
                    type="button"
                    className={styles.dropdownItem}
                    role="menuitem"
                    onClick={() => {
                      setIsDropdownOpen(false);
                      toast.info('Đang mở hộp thoại Đổi mật khẩu');
                    }}
                  >
                    <span className={styles.dropdownItemIcon}>
                      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                        <circle cx="12" cy="16.5" r="1" fill="currentColor" />
                      </svg>
                    </span>
                    <span>Đổi mật khẩu</span>
                  </button>
                </div>

                <div className={styles.dropdownDivider} />

                {/* 3. Phần Cuối Dropdown (Đăng xuất - Padding 12px 20px) */}
                <button
                  type="button"
                  className={styles.dropdownLogoutItem}
                  role="menuitem"
                  onClick={handleOpenLogoutModal}
                >
                  <span className={styles.dropdownLogoutIcon}>
                    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                      <polyline points="16 17 21 12 16 7" />
                      <line x1="21" y1="12" x2="9" y2="12" />
                    </svg>
                  </span>
                  <span>Đăng xuất</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* MODAL XÁC NHẬN ĐĂNG XUẤT KHI BẤM TỪ DROPDOWN HEADER */}
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

