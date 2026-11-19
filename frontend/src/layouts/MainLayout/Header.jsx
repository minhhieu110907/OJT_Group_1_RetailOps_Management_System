import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { Modal, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import { getApiErrorMessage } from '../../api/axiosClient';
import {
  formatNotificationTimeVN,
  notificationsApi,
} from '../../api/notificationsApi';
import ChangePasswordModal from '../../components/ChangePasswordModal';
import fieldStyles from '../../components/ChangePasswordModal.module.css';
import { MENU_ITEMS } from './Sidebar';
import styles from './MainLayout.module.css';

export default function Header({
  isMobileNavOpen = false,
  onToggleMobileNav = () => {},
}) {
  const { user, logout, isMockMode, getMyProfile, updateMyProfile } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const toast = useToast();
  const location = useLocation();
  const navigate = useNavigate();

  // State quản lý đóng/mở User Dropdown, Notification Popover, Modal Thông tin cá nhân, Modal Đổi mật khẩu và Modal xác nhận đăng xuất
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [profileFullName, setProfileFullName] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);

  useEffect(() => {
    if (!isProfileModalOpen) return undefined;
    let current = true;
    Promise.resolve().then(() => {
      if (!current) return;
      setProfileFullName(user?.full_name || '');
      setProfileError('');
      setProfileLoading(!isMockMode);
    });
    if (!isMockMode) {
      getMyProfile()
        .then((profile) => {
          if (current) setProfileFullName(profile.full_name || '');
        })
        .catch((err) => {
          if (current) setProfileError(getApiErrorMessage(err));
        })
        .finally(() => {
          if (current) setProfileLoading(false);
        });
    }
    return () => { current = false; };
    // Loading a profile once when the modal opens is deliberate.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isProfileModalOpen, isMockMode, user?.id]);

  const handleSaveProfile = async () => {
    if (profileSaving || isMockMode) return;
    const normalizedName = profileFullName.trim();
    if (profileFullName.length && !normalizedName) {
      setProfileError('Họ và tên không được chỉ chứa khoảng trắng.');
      return;
    }
    setProfileError('');
    setProfileSaving(true);
    try {
      await updateMyProfile(normalizedName || null);
      toast.success('Đã cập nhật thông tin cá nhân.');
      setIsProfileModalOpen(false);
    } catch (err) {
      setProfileError(getApiErrorMessage(err) || err.message);
    } finally {
      setProfileSaving(false);
    }
  };

  // State dữ liệu Thông báo xét duyệt nhân viên (AUTH-05 — Real API)
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoadingNotifications, setIsLoadingNotifications] = useState(false);
  const [notificationError, setNotificationError] = useState('');
  const [isMarkingAll, setIsMarkingAll] = useState(false);
  const [markingIds, setMarkingIds] = useState([]);

  const dropdownRef = useRef(null);
  const notificationRef = useRef(null);
  const fetchGenRef = useRef(0);
  const badgeGenRef = useRef(0);
  const markingIdsRef = useRef(new Set());
  const isMarkingAllRef = useRef(false);

  const isAdmin =
    user?.role === 'ADMIN' &&
    (user?.status === 'APPROVED' || user?.status === 'ACTIVE');
  const roleLabel = user?.role === 'ADMIN' ? 'Quản trị viên' : 'Nhân viên';
  const avatarInitials = user?.role === 'ADMIN' ? 'A' : 'NV';
  const displayName = (user?.name || '').replace(/\s*\(admin\)/gi, '').trim();

  // Tự động đóng Dropdown / Popover khi bấm ra ngoài hoặc nhấn phím Esc
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
      if (
        notificationRef.current &&
        !notificationRef.current.contains(event.target)
      ) {
        setIsNotificationOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsDropdownOpen(false);
        setIsNotificationOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  // Tải danh sách thông báo và số lượng chưa đọc từ API thật khi mở chuông
  const fetchNotificationFeed = useCallback(async () => {
    if (!isAdmin) {
      return;
    }
    const currentGen = ++fetchGenRef.current;
    setIsLoadingNotifications(true);
    setNotificationError('');

    try {
      const [listData, countData] = await Promise.all([
        notificationsApi.getNotifications({
          isMockMode,
          page: 1,
          pageSize: 20,
          unreadOnly: false,
        }),
        notificationsApi.getUnreadCount({ isMockMode }),
      ]);

      if (currentGen !== fetchGenRef.current) {
        return;
      }

      setNotifications(listData.items);
      setUnreadCount(countData.count);
    } catch (error) {
      if (currentGen !== fetchGenRef.current) {
        return;
      }
      const message =
        error?.code === 'ERR_MOCK_NOT_SUPPORTED'
          ? 'Thông báo xét duyệt chỉ hoạt động trên API thật. Vui lòng tắt chế độ Mock Demo.'
          : getApiErrorMessage(error) ||
            'Không thể tải danh sách thông báo từ máy chủ.';
      setNotificationError(message);
    } finally {
      if (currentGen === fetchGenRef.current) {
        setIsLoadingNotifications(false);
      }
    }
  }, [isAdmin, isMockMode]);

  // Đồng bộ badge chưa đọc từ API thật khi Admin đăng nhập hoặc chuyển trang; xóa sạch state khi đăng xuất / không phải Admin
  useEffect(() => {
    if (!isAdmin || isMockMode) {
      fetchGenRef.current += 1;
      badgeGenRef.current += 1;
      Promise.resolve().then(() => {
        setNotifications([]);
        setUnreadCount(0);
        setNotificationError('');
        setIsNotificationOpen(false);
      });
      return undefined;
    }
    const badgeGen = ++badgeGenRef.current;
    notificationsApi
      .getUnreadCount({ isMockMode })
      .then((res) => {
        if (badgeGen === badgeGenRef.current) {
          setUnreadCount(Math.max(0, res.count));
        }
      })
      .catch(() => {
        // Không làm gián đoạn giao diện chung khi nền kiểm tra badge lỗi
      });

    return () => {
      badgeGenRef.current += 1;
    };
  }, [isAdmin, isMockMode, location.pathname, user?.id]);

  // Bấm vào nút Chuông thông báo
  const handleToggleNotification = () => {
    setIsDropdownOpen(false);
    setIsNotificationOpen((prev) => {
      const next = !prev;
      if (next) {
        fetchNotificationFeed();
      }
      return next;
    });
  };

  // Đánh dấu đã đọc 1 thông báo qua PATCH /api/v1/admin/notifications/{id}/read
  const handleMarkSingleRead = async (notificationId) => {
    if (!isAdmin || markingIdsRef.current.has(notificationId)) {
      return false;
    }

    const target = notifications.find((item) => item.id === notificationId);
    if (!target || target.read_at !== null) {
      return true;
    }

    markingIdsRef.current.add(notificationId);
    setMarkingIds(Array.from(markingIdsRef.current));

    try {
      const updated = await notificationsApi.markAsRead({
        isMockMode,
        id: notificationId,
      });

      setNotifications((prev) =>
        prev.map((item) => (item.id === notificationId ? updated : item))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
      return true;
    } catch (error) {
      toast.error(
        getApiErrorMessage(error) ||
          'Không thể cập nhật trạng thái đã đọc cho thông báo.'
      );
      return false;
    } finally {
      markingIdsRef.current.delete(notificationId);
      setMarkingIds(Array.from(markingIdsRef.current));
    }
  };

  // Đánh dấu tất cả đã đọc qua PATCH /api/v1/admin/notifications/read-all
  const handleMarkAllRead = async () => {
    if (
      !isAdmin ||
      isMarkingAllRef.current ||
      isLoadingNotifications ||
      unreadCount === 0
    ) {
      return;
    }

    isMarkingAllRef.current = true;
    setIsMarkingAll(true);

    try {
      await notificationsApi.markAllAsRead({ isMockMode });
      await fetchNotificationFeed();
      toast.success('Đã đánh dấu đã đọc toàn bộ thông báo.');
    } catch (error) {
      toast.error(
        getApiErrorMessage(error) ||
          'Không thể đánh dấu đã đọc toàn bộ thông báo.'
      );
    } finally {
      isMarkingAllRef.current = false;
      setIsMarkingAll(false);
    }
  };

  // Mở danh sách chờ duyệt từ 1 thông báo cụ thể
  const handleOpenApprovalFromNotification = async (item) => {
    if (item.read_at === null) {
      await handleMarkSingleRead(item.id);
    }
    setIsNotificationOpen(false);
    navigate(`/staff?approval_request_id=${item.approval_request_id}`, {
      state: { approvalRequestId: item.approval_request_id },
    });
  };

  // Mở toàn bộ hàng đợi phê duyệt (AUTH-03)
  const handleViewAllApprovalQueue = () => {
    setIsNotificationOpen(false);
    navigate('/staff');
  };

  // Tìm tên trang hiện tại dựa trên đường dẫn URL để hiển thị trên Breadcrumb
  const currentMenu = MENU_ITEMS.find(
    (item) => item.path === location.pathname
  );
  const currentPageLabel = currentMenu
    ? currentMenu.label
    : 'Không gian làm việc';

  // Khi bấm vào hàng "Đăng xuất" trong Dropdown -> Đóng Dropdown và mở Modal xác nhận
  const handleOpenLogoutModal = () => {
    setIsDropdownOpen(false);
    setIsLogoutModalOpen(true);
  };

  // Khi bấm nút "Đăng xuất" màu đỏ trong Modal xác nhận (FIX-03)
  const handleConfirmLogout = async () => {
    setIsLogoutModalOpen(false);
    await logout();
    navigate('/login', { replace: true });
  };

  const firstUnreadNotification = notifications.find(
    (item) => item.read_at === null
  );
  const firstUnreadId = firstUnreadNotification
    ? firstUnreadNotification.id
    : null;

  return (
    <>
      <header className={styles.header}>
        {/* Bên trái Header: Nút bật mở Sidebar trên Mobile/Tablet và Breadcrumb */}
        <div className={styles.headerLeftGroup}>
          <button
            type="button"
            id="mobile-nav-toggle-btn"
            className={styles.mobileMenuToggle}
            onClick={onToggleMobileNav}
            aria-label={isMobileNavOpen ? 'Đóng thanh điều hướng' : 'Mở thanh điều hướng'}
            title={isMobileNavOpen ? 'Đóng menu' : 'Mở menu'}
            aria-expanded={isMobileNavOpen}
            aria-controls="main-sidebar-drawer"
          >
            {isMobileNavOpen ? (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            ) : (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            )}
          </button>

          <div className={styles.breadcrumb}>
            <span className={styles.breadcrumbRoot}>RetailOps v1.0</span>
            <span className={styles.breadcrumbSeparator}>/</span>
            <span className={styles.breadcrumbCurrent}>{currentPageLabel}</span>
          </div>
        </div>

        {/* Bên phải Header: Trợ giúp (?), Chuông thông báo Admin, Cụm User Dropdown */}
        <div className={styles.headerActions}>
          {/* Nút icon Trợ giúp (?) */}
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => toast.info('Trung tâm trợ giúp RetailOps v1.0')}
            title="Trợ giúp & Hướng dẫn"
            aria-label="Trợ giúp"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </button>

          {/* Nút chuyển chế độ Sáng / Tối */}
          <button
            type="button"
            className={styles.iconBtn}
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}
            aria-label={theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}
          >
            {theme === 'dark' ? (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>

          {/* Nút icon Chuông thông báo xét duyệt Staff (AUTH-05 — Chỉ dành cho ADMIN) */}
          {isAdmin && (
            <div className={styles.notificationWrapper} ref={notificationRef}>
              <button
                type="button"
                className={`${styles.iconBtn} ${
                  isNotificationOpen ? styles.iconBtnActive : ''
                }`}
                onClick={handleToggleNotification}
                title="Thông báo xét duyệt tài khoản nhân viên"
                aria-label="Thông báo xét duyệt tài khoản nhân viên"
                aria-expanded={isNotificationOpen}
                aria-haspopup="dialog"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                {unreadCount > 0 && <span className={styles.notificationDot} />}
              </button>

              {isNotificationOpen && (
                <div
                  className={styles.notificationPopover}
                  role="dialog"
                  aria-label="Thông báo xét duyệt tài khoản nhân viên"
                >
                  {/* 1. Header Popover */}
                  <div className={styles.notificationHeader}>
                    <h2 className={styles.notificationHeaderTitle}>
                      Thông báo xét duyệt tài khoản nhân viên
                    </h2>
                    <div className={styles.notificationHeaderRight}>
                      <span
                        className={`${styles.unreadPillBadge} ${
                          unreadCount === 0 ? styles.unreadPillBadgeZero : ''
                        }`}
                      >
                        {unreadCount} chưa đọc
                      </span>
                      <button
                        type="button"
                        className={styles.markAllReadBtn}
                        onClick={handleMarkAllRead}
                        disabled={
                          unreadCount === 0 ||
                          isMarkingAll ||
                          isLoadingNotifications
                        }
                        title="Chỉ đánh dấu đã xem toàn bộ thông báo, không tự động duyệt nhân viên"
                      >
                        {isMarkingAll
                          ? 'Đang đánh dấu...'
                          : 'Đánh dấu tất cả đã đọc'}
                      </button>
                    </div>
                  </div>

                  {/* 2. Danh sách thông báo từ API thật (/api/v1/admin/notifications) */}
                  {isLoadingNotifications ? (
                    <div className={styles.notificationStateBox}>
                      <p className={styles.notificationStateText}>
                        Đang tải thông báo xét duyệt từ máy chủ...
                      </p>
                    </div>
                  ) : notificationError ? (
                    <div className={styles.notificationStateBox} role="alert">
                      <p className={styles.notificationErrorText}>
                        {notificationError}
                      </p>
                      <button
                        type="button"
                        className={styles.notificationRetryBtn}
                        onClick={fetchNotificationFeed}
                      >
                        Thử lại
                      </button>
                    </div>
                  ) : notifications.length === 0 ? (
                    <div className={styles.notificationStateBox}>
                      <p className={styles.notificationStateText}>
                        Chưa có thông báo đăng ký nhân viên mới.
                      </p>
                    </div>
                  ) : (
                    <div className={styles.notificationList}>
                      {notifications.map((item) => {
                        const isUnread = item.read_at === null;
                        const isFirstUnread =
                          isUnread && item.id === firstUnreadId;
                        const isItemMarking = markingIds.includes(item.id);
                        const timeLabel = formatNotificationTimeVN(
                          item.created_at,
                          {
                            includeTimezoneLabel: isFirstUnread,
                            isRead: !isUnread,
                          }
                        );

                        return (
                          <div
                            key={item.id}
                            className={styles.notificationCard}
                          >
                            {/* Icon bên trái: User-plus xanh khi chưa đọc, Thẻ ID xám khi đã đọc */}
                            <div
                              className={
                                isUnread
                                  ? styles.notificationAvatarUnread
                                  : styles.notificationAvatarRead
                              }
                              aria-hidden="true"
                            >
                              {isUnread ? (
                                <svg
                                  width="18"
                                  height="18"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2.2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                                  <circle cx="8.5" cy="7" r="4" />
                                  <line x1="20" y1="8" x2="20" y2="14" />
                                  <line x1="23" y1="11" x2="17" y2="11" />
                                </svg>
                              ) : (
                                <svg
                                  width="18"
                                  height="18"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <rect
                                    x="4"
                                    y="3"
                                    width="16"
                                    height="18"
                                    rx="2"
                                  />
                                  <circle cx="12" cy="10" r="2.5" />
                                  <path d="M8 16c1.2-1.5 2.6-2 4-2s2.8.5 4 2" />
                                </svg>
                              )}
                            </div>

                            {/* Nội dung chính của thẻ thông báo (thuần trường từ API NotificationRead) */}
                            <div className={styles.notificationBody}>
                              <div className={styles.notificationTopRow}>
                                <span
                                  className={
                                    isUnread
                                      ? styles.notificationItemTitle
                                      : styles.notificationItemTitleRead
                                  }
                                >
                                  Yêu cầu xét duyệt nhân viên: Hồ sơ #
                                  {item.approval_request_id}
                                </span>

                                {isUnread ? (
                                  <span
                                    className={styles.unreadDotIndicator}
                                    title="Thông báo chưa đọc"
                                    aria-hidden="true"
                                  />
                                ) : (
                                  <span className={styles.readLabel}>
                                    Đã đọc
                                  </span>
                                )}
                              </div>

                              <span className={styles.notificationSubtext}>
                                Mã yêu cầu xét duyệt #{item.approval_request_id}{' '}
                                • Thông báo #{item.id}
                              </span>

                              <div className={styles.notificationMetaRow}>
                                {isUnread ? (
                                  <span className={styles.pendingApprovalTag}>
                                    <span
                                      className={styles.pendingApprovalDot}
                                      aria-hidden="true"
                                    />
                                    <span>Thông báo mới • Chờ xét duyệt</span>
                                  </span>
                                ) : (
                                  <span className={styles.processedApprovalTag}>
                                    <span aria-hidden="true">✓</span>
                                    <span>Đã xem thông báo</span>
                                  </span>
                                )}
                                {timeLabel && (
                                  <span
                                    className={styles.notificationTimestamp}
                                  >
                                    {timeLabel}
                                  </span>
                                )}
                              </div>

                              <div className={styles.notificationActionRow}>
                                {isFirstUnread ? (
                                  <button
                                    type="button"
                                    className={styles.openQueueBtnPrimary}
                                    disabled={isItemMarking}
                                    onClick={() =>
                                      handleOpenApprovalFromNotification(item)
                                    }
                                  >
                                    <svg
                                      width="15"
                                      height="15"
                                      viewBox="0 0 24 24"
                                      fill="none"
                                      stroke="currentColor"
                                      strokeWidth="2.2"
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                    >
                                      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                                      <circle cx="8.5" cy="7" r="4" />
                                      <polyline points="17 11 19 13 23 9" />
                                    </svg>
                                    <span>Mở danh sách chờ duyệt</span>
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className={styles.openQueueBtnSecondary}
                                    disabled={isItemMarking}
                                    onClick={() =>
                                      handleOpenApprovalFromNotification(item)
                                    }
                                  >
                                    <span>Mở danh sách chờ duyệt</span>
                                    <span aria-hidden="true">→</span>
                                  </button>
                                )}

                                {isUnread && (
                                  <button
                                    type="button"
                                    className={styles.markSingleReadBtn}
                                    disabled={isItemMarking}
                                    onClick={() =>
                                      handleMarkSingleRead(item.id)
                                    }
                                    title="Chỉ đánh dấu đã xem thông báo này (không duyệt tài khoản)"
                                  >
                                    {isItemMarking
                                      ? 'Đang đánh dấu...'
                                      : 'Đánh dấu đã đọc'}
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* 3. Hộp thông tin Cơ chế chống thông báo trùng lặp (AUTH-05) */}
                  <div className={styles.notificationSafeguardBanner}>
                    <span className={styles.safeguardIcon} aria-hidden="true">
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                      </svg>
                    </span>
                    <p className={styles.safeguardText}>
                      <strong>Cơ chế chống thông báo trùng lặp:</strong> Khi
                      nhân viên gửi lại yêu cầu đăng ký hoặc hệ thống thực hiện
                      thử lại kết nối, hệ thống tự động nhận diện và không tạo
                      thông báo trùng lặp cho Quản trị viên.
                    </p>
                  </div>

                  {/* 4. Footer chuyển hướng sang toàn bộ hàng đợi phê duyệt (AUTH-03) */}
                  <div className={styles.notificationFooter}>
                    <button
                      type="button"
                      className={styles.viewAllQueueBtn}
                      onClick={handleViewAllApprovalQueue}
                    >
                      <span>Xem toàn bộ hàng đợi phê duyệt (AUTH-03)</span>
                      <span aria-hidden="true">→</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className={styles.headerDivider} />

          {/* Cụm nút User Trigger & Menu Tài khoản thả xuống (User Dropdown) */}
          <div className={styles.userDropdownWrapper} ref={dropdownRef}>
            <button
              type="button"
              onClick={() => {
                setIsNotificationOpen(false);
                setIsDropdownOpen((prev) => !prev);
              }}
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
                {displayName && (
                  <span className={styles.headerUserName}>{displayName}</span>
                )}
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
                      {displayName && (
                        <span className={styles.dropdownUserName}>
                          {displayName}
                        </span>
                      )}
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
                      setIsProfileModalOpen(true);
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
                      setIsChangePasswordOpen(true);
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

      {/* MODAL THÔNG TIN CÁ NHÂN KHI BẤM TỪ DROPDOWN HEADER */}
      <Modal
        isOpen={isProfileModalOpen}
        onClose={() => setIsProfileModalOpen(false)}
        title="Thông tin cá nhân"
        maxWidth="460px"
        footer={
          <>
            <button
              type="button"
              className={modalStyles.cancelBtn}
              disabled={profileSaving}
              onClick={() => setIsProfileModalOpen(false)}
            >
              Đóng
            </button>
            <button
              type="button"
              className={modalStyles.confirmBtn}
              disabled={profileSaving || profileLoading || isMockMode}
              onClick={handleSaveProfile}
            >
              {profileSaving ? 'Đang lưu...' : 'Lưu thay đổi'}
            </button>
          </>
        }
      >
        <div className={styles.profileModalContent}>
          <label className={fieldStyles.label} htmlFor="profile-full-name">Họ và tên</label>
          <input
            id="profile-full-name"
            className={fieldStyles.input}
            value={profileFullName}
            onChange={(event) => setProfileFullName(event.target.value)}
            maxLength={120}
            disabled={profileSaving || profileLoading || isMockMode}
            placeholder="Nhập họ và tên"
          />
          {profileLoading && <p role="status">Đang tải hồ sơ...</p>}
          {isMockMode && <p role="status">Chỉnh sửa hồ sơ chỉ hoạt động với API thật.</p>}
          {profileError && <p role="alert" className={fieldStyles.error}>{profileError}</p>}
          <div className={styles.profileSummaryHeader}>
            <div className={styles.profileAvatarLarge}>{avatarInitials}</div>
            <div className={styles.profileSummaryMeta}>
              <h3 className={styles.profileSummaryName}>
                {displayName || '—'}
              </h3>
              <span className={styles.profileRoleBadge}>{roleLabel}</span>
            </div>
          </div>

          <div className={styles.profileInfoList}>
            <div className={styles.profileInfoCard}>
              <div className={styles.profileInfoText}>
                <span className={styles.profileInfoLabel}>Họ và tên</span>
                <span className={styles.profileInfoValue}>
                  {displayName || '—'}
                </span>
              </div>
              <span className={styles.profileInfoIcon} aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="16" rx="2" />
                  <circle cx="9" cy="10" r="2" />
                  <path d="M15 8h2" />
                  <path d="M15 12h2" />
                  <path d="M7 16h10" />
                </svg>
              </span>
            </div>

            <div className={styles.profileInfoCard}>
              <div className={styles.profileInfoText}>
                <span className={styles.profileInfoLabel}>Vai trò hệ thống</span>
                <span className={styles.profileInfoValue}>{roleLabel}</span>
              </div>
              <span className={styles.profileInfoIcon} aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </span>
            </div>

            <div className={styles.profileInfoCard}>
              <div className={styles.profileInfoText}>
                <span className={styles.profileInfoLabel}>Địa chỉ email</span>
                <span className={styles.profileInfoValue}>
                  {user?.email || '—'}
                </span>
              </div>
              <span className={styles.profileInfoIcon} aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                </svg>
              </span>
            </div>

            <div className={styles.profileInfoCard}>
              <div className={styles.profileInfoText}>
                <span className={styles.profileInfoLabel}>
                  Trạng thái tài khoản
                </span>
                <span
                  className={
                    user?.status === 'ACTIVE' || user?.status === 'APPROVED'
                      ? styles.profileStatusPillActive
                      : styles.profileStatusPillMuted
                  }
                >
                  <span>•</span>
                  <span>
                    {user?.status === 'ACTIVE' || user?.status === 'APPROVED'
                      ? 'Đang hoạt động'
                      : user?.status === 'PENDING' ||
                        user?.status === 'PENDING_APPROVAL'
                      ? 'Chờ duyệt'
                      : user?.status === 'REJECTED'
                      ? 'Đã từ chối'
                      : user?.status || '—'}
                  </span>
                </span>
              </div>
              <span
                className={
                  user?.status === 'ACTIVE' || user?.status === 'APPROVED'
                    ? styles.profileStatusIconActive
                    : styles.profileInfoIcon
                }
                aria-hidden="true"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="m9 12 2 2 4-4" />
                </svg>
              </span>
            </div>
          </div>
        </div>
      </Modal>

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

      {/* MODAL ĐỔI MẬT KHẨU (TRẠNG THÁI 4A, 4B, 4C) KHI BẤM TỪ DROPDOWN HEADER */}
      {isChangePasswordOpen && (
        <ChangePasswordModal
          onClose={() => setIsChangePasswordOpen(false)}
        />
      )}
    </>
  );
}

