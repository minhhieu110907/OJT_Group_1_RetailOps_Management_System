import { useEffect, useRef } from 'react';
import { acquireModalScrollLock } from '../../../utils/modalScrollLock';
import styles from './Modal.module.css';

export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  maxWidth = '420px',
}) {
  const backdropMouseDownRef = useRef(false);

  // Lắng nghe phím Esc để đóng Modal và khóa cuộn trang nền khi Modal đang mở
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && onClose) {
        event.stopPropagation();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    const releaseScrollLock = acquireModalScrollLock();

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      releaseScrollLock();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Chỉ đóng Modal khi cả thao tác nhấn chuột (mousedown) lẫn thả chuột (click) đều nằm trực tiếp trên nền mờ
  // Tránh đóng nhầm khi người dùng bôi đen văn bản trong ô nhập rồi kéo chuột ra ngoài
  const handleBackdropMouseDown = (event) => {
    backdropMouseDownRef.current = event.target === event.currentTarget;
  };

  const handleBackdropClick = (event) => {
    const startedOnBackdrop = backdropMouseDownRef.current;
    backdropMouseDownRef.current = false;
    if (startedOnBackdrop && event.target === event.currentTarget && onClose) {
      onClose();
    }
  };

  return (
    <div
      className={styles.backdrop}
      onMouseDown={handleBackdropMouseDown}
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

