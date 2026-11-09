import { Outlet } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import styles from './AuthLayout.module.css';

export default function AuthLayout() {
  const {
    backendOnline,
    isCheckingBackend,
    isMockMode,
    canUseMock,
    checkBackendConnection,
    toggleMockMode,
  } = useAuth();

  let statusLabel = 'Hệ thống trực tuyến';
  let dotClass = styles.statusDot;

  if (isCheckingBackend) {
    statusLabel = 'Đang kiểm tra kết nối BE...';
    dotClass = styles.statusDotReady;
  } else if (backendOnline && !isMockMode) {
    statusLabel = 'Backend: Đã kết nối (API thật)';
    dotClass = styles.statusDot;
  } else if (!backendOnline && !isMockMode) {
    statusLabel = 'Backend: Mất kết nối (Cần bật BE)';
    dotClass = styles.statusDotMock;
  } else if (backendOnline && isMockMode) {
    statusLabel = 'Chế độ: Mock Demo (BE sẵn sàng)';
    dotClass = styles.statusDotReady;
  } else {
    statusLabel = 'Chế độ: Mock Demo (BE ngoại tuyến)';
    dotClass = styles.statusDotMock;
  }

  return (
    <div className={styles.authLayout}>
      {/* 1. Phần Header trên cùng */}
      <header className={styles.header}>
        <div className={styles.brandGroup}>
          <div className={styles.logoBox} aria-hidden="true">
            {/* Icon cửa hàng màu trắng trên nền xanh lá #087F5B */}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l1.5-5h15L21 9" />
              <path d="M3 9c0 1.66 1.34 3 3 3s3-1.34 3-3c0 1.66 1.34 3 3 3s3-1.34 3-3c0 1.66 1.34 3 3 3s3-1.34 3-3" />
              <path d="M5 12v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8" />
              <path d="M10 16h4v5h-4z" />
            </svg>
          </div>

          <div>
            <div className={styles.brandTitleRow}>
              <span className={styles.brandName}>RetailOps</span>
              <span className={styles.versionBadge}>v1.0</span>
            </div>
            <p className={styles.brandSubtitle}>
              Hệ thống điều hành bán lẻ đơn điểm &amp; Kho nội bộ
            </p>
          </div>
        </div>

        {/* Bên phải: Trạng thái kết nối FE - BE (Chỉ cho phép bật/tắt Mock khi môi trường DEV cho phép) */}
        <div className={styles.onlineStatusGroup}>
          {canUseMock ? (
            <button
              type="button"
              className={styles.onlineStatus}
              onClick={toggleMockMode}
              title="Môi trường DEV: Bấm để chuyển đổi giữa API thật và Mock Demo"
            >
              <span className={dotClass} aria-hidden="true" />
              <span>{statusLabel}</span>
            </button>
          ) : (
            <div
              className={styles.onlineStatus}
              role="status"
              title="Trạng thái kết nối tới FastAPI Backend (/api/v1/health)"
            >
              <span className={dotClass} aria-hidden="true" />
              <span>{statusLabel}</span>
            </div>
          )}

          <button
            type="button"
            className={styles.pingBtn}
            onClick={() =>
              checkBackendConnection({ notify: true, forceRealIfOnline: true })
            }
            disabled={isCheckingBackend}
            title="Kiểm tra lại kết nối tới FastAPI Backend (/api/v1/health)"
            aria-label="Kiểm tra kết nối Backend"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.3"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={isCheckingBackend ? styles.spinIcon : ''}
            >
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
          </button>
        </div>
      </header>

      {/* 2. Phần Thân giữa màn hình: Căn giữa khung Card trắng 460px */}
      <main className={styles.mainContent}>
        <div className={styles.authCard}>
          <Outlet />
        </div>
      </main>

      {/* 3. Phần Footer dưới đáy màn hình */}
      <footer className={styles.footer}>
        RetailOps v1.0 • Một cửa hàng / Một kho • Múi giờ Asia/Ha_Noi • Bảo mật nội bộ nghiêm ngặt
      </footer>
    </div>
  );
}
