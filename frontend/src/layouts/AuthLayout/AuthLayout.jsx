import { Outlet } from 'react-router-dom';
import styles from './AuthLayout.module.css';

export default function AuthLayout() {
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

        {/* Bên phải: Chấm tròn xanh lá nhấp nháy kèm chữ Hệ thống trực tuyến */}
        <div className={styles.onlineStatus}>
          <span className={styles.statusDot} aria-hidden="true" />
          <span>Hệ thống trực tuyến</span>
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

