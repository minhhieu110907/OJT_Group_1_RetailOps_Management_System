import { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import { inventoryApi } from '../../api/inventoryApi';
import { getApiErrorMessage } from '../../api/axiosClient';
import styles from './InventoryAdjustModal.module.css';

/**
 * Format số lượng: ví dụ 11 -> "11"
 */
function formatNumber(num) {
  if (num === null || num === undefined || Number.isNaN(Number(num))) return '0';
  return Number(num).toLocaleString('vi-VN');
}

/**
 * Lấy thời điểm hiển thị hiện tại định dạng HH:mm:ss - DD/MM/YYYY
 */
function formatNow() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const hours = pad(d.getHours());
  const minutes = pad(d.getMinutes());
  const seconds = pad(d.getSeconds());
  const day = pad(d.getDate());
  const month = pad(d.getMonth() + 1);
  const year = d.getFullYear();
  return `${hours}:${minutes}:${seconds} - ${day}/${month}/${year}`;
}

export default function InventoryAdjustModal({
  isOpen,
  product,
  categoryName,
  onClose,
  onSuccess,
}) {
  const { user } = useAuth();
  const toast = useToast();

  const [countedQty, setCountedQty] = useState('');
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [capturedTime, setCapturedTime] = useState('');

  // Đồng bộ giá trị khởi tạo khi mở Modal
  useEffect(() => {
    if (isOpen && product) {
      setCountedQty(product.quantity !== undefined && product.quantity !== null ? String(product.quantity) : '0');
      setReason('');
      setErrorMessage('');
      setCapturedTime(formatNow());
    }
  }, [isOpen, product]);

  // Lắng nghe phím Esc để đóng modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen || !product) return null;

  const currentQty = Number(product.quantity) || 0;
  const currentVersion = Number(product.stock_version) || 0;

  // Tính toán Delta và Tỷ lệ %
  const parsedCounted = countedQty.trim() === '' ? NaN : Number(countedQty);
  const isValidCounted = !Number.isNaN(parsedCounted) && Number.isInteger(parsedCounted) && parsedCounted >= 0;

  const delta = isValidCounted ? parsedCounted - currentQty : 0;
  const deltaSign = delta > 0 ? `+${delta}` : `${delta}`;

  let deltaPercentText = '';
  if (isValidCounted) {
    if (delta === 0) {
      deltaPercentText = 'Tồn kho không đổi';
    } else if (delta > 0) {
      if (currentQty > 0) {
        const pct = ((delta / currentQty) * 100).toFixed(1).replace(/\.0$/, '');
        deltaPercentText = `Tăng tồn kho (+${pct}%)`;
      } else {
        deltaPercentText = 'Tăng tồn kho';
      }
    } else {
      if (currentQty > 0) {
        const pct = ((Math.abs(delta) / currentQty) * 100).toFixed(1).replace(/\.0$/, '');
        deltaPercentText = `Giảm tồn kho (-${pct}%)`;
      } else {
        deltaPercentText = 'Giảm tồn kho';
      }
    }
  }

  // Delta color class
  let deltaColorClass = styles.deltaNeutral;
  if (delta > 0) deltaColorClass = styles.deltaPositive;
  else if (delta < 0) deltaColorClass = styles.deltaNegative;

  // Thông tin người thực hiện
  const actorDisplay = user ? `${user.name || 'Admin'} (#${user.role || 'ADMIN'}-${String(user.id || 1).padStart(3, '0')})` : 'Admin Quản Trị (#ADM-001)';

  // Dự kiến bản ghi Stock Movement & Phiên bản mới
  let expectedMovementText = 'Không có bất kỳ sự thay đổi'
  if (delta > 0) {
    expectedMovementText = `Phiên bản mới: v${currentVersion + 1}`;
  } else if (delta < 0) {
    expectedMovementText = `Tạo bản ghi Stock Movement (OUT) ${delta} • Phiên bản mới: v${currentVersion + 1}`;
  }

  // Validation
  const trimmedReason = reason.trim();
  const isReasonValid = trimmedReason.length >= 10;
  const canSubmit = isValidCounted && isReasonValid && !isSubmitting;

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!canSubmit) return;

    // Nếu không có thay đổi gì về số lượng tồn kho (delta === 0)
    if (delta === 0) {
      toast.info('Không có thay đổi gì về số lượng tồn kho.');
      onClose();
      return;
    }

    setIsSubmitting(true);
    setErrorMessage('');

    try {
      const response = await inventoryApi.adjustInventory({
        productId: product.product_id,
        countedQuantity: parsedCounted,
        expectedStockVersion: currentVersion,
        reason: trimmedReason,
      });

      if (onSuccess) {
        onSuccess(response);
      }
      onClose();
    } catch (err) {
      const msg = getApiErrorMessage(err, 'Không thể điều chỉnh tồn kho.');
      // Nếu là xung đột phiên bản (409 Conflict)
      if (err?.response?.status === 409) {
        setErrorMessage('Dữ liệu tồn kho của sản phẩm này đã bị thay đổi bởi phiên làm việc khác. Vui lòng đóng modal và tải lại trang.');
      } else {
        setErrorMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.backdrop} onClick={(e) => { if (e.target === e.currentTarget && !isSubmitting) onClose(); }}>
      <div className={styles.modalBox}>
        {/* Header với SKU, Category, Tên sản phẩm, stock_version */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.badgeRow}>
              {categoryName && <span className={styles.categoryBadge}>{categoryName.toUpperCase()}</span>}
              <span className={styles.skuText}>Mã SKU: <strong>{product.sku}</strong></span>
            </div>
            <h2 className={styles.productName}>{product.name}</h2>
            <div className={styles.subInfo}>
              <span>Nhà cung cấp: Hệ thống • Đơn vị tính: Cái</span>
            </div>
          </div>

          <div className={styles.versionBadgeContainer}>
            <div className={styles.versionBadge}>
              <span className={styles.versionLabel}>stock_version:</span>
              <span className={styles.versionValue}>{currentVersion}</span>
            </div>
            <span className={styles.versionSubtext}>Bảo vệ chống ghi đè phiên bản cũ</span>
          </div>
        </div>

        {errorMessage && (
          <div className={styles.errorAlert}>
            {errorMessage}
          </div>
        )}

        {/* 3 Thẻ thống kê: Tồn kho hiện ghi nhận | Số kiểm kê thực tế | Chênh lệch (Delta) */}
        <div className={styles.statsCardsRow}>
          <div className={styles.statCard}>
            <span className={styles.statCardTitle}>TỒN KHO HIỆN GHI NHẬN</span>
            <div className={styles.statCardMain}>
              <span className={styles.statCardNumber}>{formatNumber(currentQty)}</span>
              <span className={styles.statCardUnit}>cái</span>
            </div>
            <span className={styles.statCardSub}>Dữ liệu từ máy chủ (v{currentVersion})</span>
          </div>

          <div className={styles.statCard}>
            <span className={styles.statCardTitle}>SỐ KIỂM KÊ THỰC TẾ</span>
            <div className={styles.statCardMain}>
              <span className={styles.statCardNumberHighlight}>
                {isValidCounted ? formatNumber(parsedCounted) : '-'}
              </span>
              <span className={styles.statCardUnit}>cái</span>
            </div>
            <span className={styles.statCardSub}>Đã nhập vào phiếu</span>
          </div>

          <div className={`${styles.statCard} ${styles.statCardDelta}`}>
            <span className={styles.statCardTitle}>CHÊNH LỆCH (DELTA)</span>
            <div className={styles.statCardMain}>
              <span className={`${styles.statCardDeltaNumber} ${deltaColorClass}`}>
                {isValidCounted ? deltaSign : '-'}
              </span>
              <span className={styles.statCardUnit}>cái</span>
            </div>
            <span className={styles.statCardSub}>
              {isValidCounted ? deltaPercentText : 'Chưa nhập số thực tế'}
            </span>
          </div>
        </div>

        {/* Form nhập liệu */}
        <form onSubmit={handleSubmit} className={styles.formBody}>
          {/* Ô nhập Số lượng kiểm kê thực tế */}
          <div className={styles.formGroup}>
            <div className={styles.labelRow}>
              <label htmlFor="adjust-counted-qty" className={styles.fieldLabel}>
                Số lượng kiểm kê thực tế <span className={styles.requiredStar}>*</span>
              </label>
              <span className={styles.helperLabel}>Số nguyên không âm (≥ 0)</span>
            </div>
            <div className={styles.inputWrapper}>
              <input
                id="adjust-counted-qty"
                type="number"
                min="0"
                step="1"
                className={styles.textInput}
                value={countedQty}
                onChange={(e) => setCountedQty(e.target.value)}
                placeholder="Nhập số lượng đếm được..."
                disabled={isSubmitting}
                autoFocus
              />
              <span className={styles.inputUnit}>cái</span>
            </div>
            <span className={styles.inputHint}>
              Lưu ý: Không điều chỉnh theo mức tăng giảm tương đối. Hãy nhập chính xác số lượng hàng đếm được thực tế trên kệ.
            </span>
          </div>

          {/* Ô nhập Lý do điều chỉnh */}
          <div className={styles.formGroup}>
            <div className={styles.labelRow}>
              <label htmlFor="adjust-reason" className={styles.fieldLabel}>
                Lý do điều chỉnh <span className={styles.requiredStar}>*</span>
              </label>
            </div>
            <textarea
              id="adjust-reason"
              rows={3}
              maxLength={250}
              className={styles.textareaInput}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Nhập lý do kiểm kê..."
              disabled={isSubmitting}
            />
            <div className={styles.textareaFooter}>
              <span className={isReasonValid ? styles.validationPassed : styles.validationWarning}>
                {isReasonValid
                  ? 'Đầy đủ thông tin kiểm toán ca làm việc'
                  : `Cần thêm ít nhất ${Math.max(0, 10 - trimmedReason.length)} ký tự`}
              </span>
              <span className={styles.charCount}>{trimmedReason.length} / 250 ký tự</span>
            </div>
          </div>

          {/* Hộp Thông tin kiểm toán & Dự kiến hệ thống */}
          <div className={styles.auditBox}>
            <div className={styles.auditRow}>
              <span className={styles.auditLabel}>Người thực hiện:</span>
              <span className={styles.auditValue}>{actorDisplay}</span>
            </div>
            <div className={styles.auditRow}>
              <span className={styles.auditLabel}>Thời điểm ghi nhận:</span>
              <span className={styles.auditValue}>{capturedTime}</span>
            </div>
            <div className={styles.auditRow}>
              <span className={styles.auditLabel}>Hành động hệ thống dự kiến:</span>
              <span className={styles.auditValueExpected}>{expectedMovementText}</span>
            </div>
          </div>

          {/* Footer nút bấm */}
          <div className={styles.footerRow}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={onClose}
              disabled={isSubmitting}
            >
              Hủy bỏ
            </button>

            <button
              type="submit"
              className={styles.submitBtn}
              disabled={!canSubmit}
            >
              {isSubmitting ? 'Đang lưu...' : 'Lưu thay đổi'}
            </button>
          </div>

          
        </form>
      </div>
    </div>
  );
}

