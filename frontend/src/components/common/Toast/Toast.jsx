import styles from './Toast.module.css';

// Bộ icon SVG nhúng trực tiếp cho 4 trạng thái thông báo
const TOAST_ICONS = {
  success: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  error: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  ),
  warning: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  info: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  ),
};

// Component hiển thị 1 hộp thông báo Toast đơn lẻ
export default function Toast({ id, type = 'success', message, onClose }) {
  const variantClass = styles[`toastCard_${type}`] || styles.toastCard_success;
  const iconClass = styles[`icon_${type}`] || styles.icon_success;

  return (
    <div className={`${styles.toastCard} ${variantClass}`} role="status">
      {/* Bên trái: Vòng tròn chứa Icon trạng thái */}
      <span className={`${styles.iconWrapper} ${iconClass}`} aria-hidden="true">
        {TOAST_ICONS[type] || TOAST_ICONS.success}
      </span>

      {/* Ở giữa: Nội dung thông báo */}
      <span className={styles.message}>{message}</span>

      {/* Bên phải: Nút ✕ đóng nhanh */}
      <button
        type="button"
        className={styles.closeBtn}
        onClick={() => onClose(id)}
        aria-label="Đóng thông báo"
        title="Đóng"
      >
        ✕
      </button>
    </div>
  );
}

// Component khung chứa danh sách các Toast đang hiển thị ở góc trên bên phải
export function ToastViewport({ toasts, onClose }) {
  if (!toasts || toasts.length === 0) return null;

  return (
    <div className={styles.toastViewport} aria-live="polite">
      {toasts.map((item) => (
        <Toast
          key={item.id}
          id={item.id}
          type={item.type}
          message={item.message}
          onClose={onClose}
        />
      ))}
    </div>
  );
}

