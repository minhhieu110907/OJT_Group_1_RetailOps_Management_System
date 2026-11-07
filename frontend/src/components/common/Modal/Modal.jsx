import { useEffect } from 'react';
import styles from './Modal.module.css';

export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  maxWidth = '420px',
}) {
  // Lắng nghe phím Esc để đóng Modal và khóa cuộn trang nền khi Modal đang mở
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && onClose) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = originalOverflow;
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Đóng Modal khi người dùng bấm trực tiếp vào vùng nền mờ (Backdrop)
  const handleBackdropClick = (event) => {
    if (event.target === event.currentTarget && onClose) {
      onClose();
    }
  };

  return (
    <div
      className={styles.backdrop}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className={styles.modalBox} style={{ maxWidth }}>
        {/* Phần Header & Nội dung (Padding đồng đều 24px, căn lề trái thẳng hàng) */}
        <div className={styles.bodySection}>
          <div className={styles.headerRow}>
            <h2 id="modal-title" className={styles.title}>
              {title}
            </h2>
            <button
              type="button"
              className={styles.closeBtn}
              onClick={onClose}
              aria-label="Đóng hộp thoại"
              title="Đóng (Esc)"
            >
              ✕
            </button>
          </div>

          <div className={styles.content}>{children}</div>
        </div>

        {/* Phần Footer chứa các nút hành động căn phải */}
        {footer && <div className={styles.footerSection}>{footer}</div>}
      </div>
    </div>
  );
}

