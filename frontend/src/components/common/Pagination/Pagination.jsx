import styles from './Pagination.module.css';

/**
 * Hàm tính toán danh sách số trang hiển thị kèm dấu '...' khi tổng số trang > 7
 * Ví dụ: [1, 2, 3, '...', 41] hoặc [1, '...', 5, 6, 7, '...', 41]
 */
function getPageNumbers(currentPage, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  // Trường hợp đang ở gần đầu (trang 1, 2, 3) -> 1, 2, 3, 4, '...', N
  if (currentPage <= 3) {
    return [1, 2, 3, '...', totalPages];
  }

  // Trường hợp đang ở gần cuối -> 1, '...', N-2, N-1, N
  if (currentPage >= totalPages - 2) {
    return [1, '...', totalPages - 2, totalPages - 1, totalPages];
  }

  // Trường hợp ở khoảng giữa -> 1, '...', currentPage - 1, currentPage, currentPage + 1, '...', N
  return [
    1,
    '...',
    currentPage - 1,
    currentPage,
    currentPage + 1,
    '...',
    totalPages,
  ];
}

export default function Pagination({
  currentPage = 1,
  totalPages = 1,
  onPageChange,
}) {
  if (!totalPages || totalPages <= 0) return null;

  const pages = getPageNumbers(currentPage, totalPages);

  const handlePrev = () => {
    if (currentPage > 1 && onPageChange) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages && onPageChange) {
      onPageChange(currentPage + 1);
    }
  };

  return (
    <nav className={styles.pagination} aria-label="Điều hướng phân trang">
      {/* Nút mũi tên Trái (<) lùi 1 trang */}
      <button
        type="button"
        className={`${styles.pageBtn} ${styles.arrowBtn}`}
        onClick={handlePrev}
        disabled={currentPage <= 1}
        aria-label="Trang trước"
        title="Trang trước"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>

      {/* Danh sách các ô số trang và dấu '...' */}
      {pages.map((item, index) => {
        if (item === '...') {
          return (
            <span key={`ellipsis-${index}`} className={styles.ellipsis}>
              ...
            </span>
          );
        }

        const isCurrent = item === currentPage;

        return (
          <button
            key={item}
            type="button"
            className={`${styles.pageBtn} ${isCurrent ? styles.active : ''}`}
            onClick={() => !isCurrent && onPageChange && onPageChange(item)}
            aria-current={isCurrent ? 'page' : undefined}
          >
            {item}
          </button>
        );
      })}

      {/* Nút mũi tên Phải (>) tiến 1 trang */}
      <button
        type="button"
        className={`${styles.pageBtn} ${styles.arrowBtn}`}
        onClick={handleNext}
        disabled={currentPage >= totalPages}
        aria-label="Trang tiếp theo"
        title="Trang tiếp theo"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>
    </nav>
  );
}

