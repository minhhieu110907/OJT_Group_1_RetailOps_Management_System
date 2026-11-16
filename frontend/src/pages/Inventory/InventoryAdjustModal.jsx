import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import {
  MAX_STOCK_QUANTITY,
  generateSecureIdempotencyKey,
  inventoryApi,
} from '../../api/inventoryApi';
import { getApiErrorMessage } from '../../api/axiosClient';
import styles from './InventoryAdjustModal.module.css';

/**
 * Format số lượng: ví dụ 11 -> "11"
 */
function formatNumber(num) {
  if (num === null || num === undefined || Number.isNaN(Number(num))) return '0';
  return Number(num).toLocaleString('vi-VN');
}

export default function InventoryAdjustModal({
  isOpen,
  product,
  categoryName,
  onClose,
  onSuccess,
  onReloadLatest,
}) {
  const { user } = useAuth();
  const toast = useToast();

  const [countedQty, setCountedQty] = useState('');
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [conflictData, setConflictData] = useState(null);

  // Track product identity to only reset when switching to a completely different product or first open
  const lastOpenedProductIdRef = useRef(null);
  const isSubmittingSyncRef = useRef(false);

  // Synchronize draft when opening modal for a new product
  useEffect(() => {
    if (isOpen && product) {
      if (lastOpenedProductIdRef.current !== product.product_id) {
        lastOpenedProductIdRef.current = product.product_id;
        setCountedQty(
          product.quantity !== undefined && product.quantity !== null
            ? String(product.quantity)
            : '0'
        );
        setReason('');
        setErrorMessage('');
        setConflictData(null);
      }
    } else if (!isOpen) {
      lastOpenedProductIdRef.current = null;
      setConflictData(null);
      setErrorMessage('');
    }
  }, [isOpen, product]);

  // Lắng nghe phím Esc để đóng modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !isSubmitting && !isReloading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isSubmitting, isReloading, onClose]);

  if (!isOpen || !product) return null;

  const currentQty = Number(product.quantity) || 0;
  const currentVersion = Number(product.stock_version) || 0;

  // Tính toán Delta và Tỷ lệ %
  const trimmedQty = countedQty.trim();
  const parsedCounted = trimmedQty === '' ? NaN : Number(trimmedQty);
  const isValidCounted =
    !Number.isNaN(parsedCounted) &&
    Number.isInteger(parsedCounted) &&
    parsedCounted >= 0 &&
    parsedCounted <= MAX_STOCK_QUANTITY;

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

  // Thông tin người thực hiện từ AuthContext đã xác thực
  const actorDisplay = user
    ? `${user.name || user.email || 'Admin'} (ID #${user.id})`
    : 'Chưa xác thực';

  // Dự kiến bản ghi Stock Movement
  let expectedMovementText = 'Số đếm trùng tồn kho ghi nhận • Không phát sinh biến động';
  if (delta > 0) {
    expectedMovementText = `Tạo bản ghi Stock Movement (IN) +${delta} • Tăng tồn kho hệ thống`;
  } else if (delta < 0) {
    expectedMovementText = `Tạo bản ghi Stock Movement (OUT) ${delta} • Giảm tồn kho hệ thống`;
  }

  // Validation
  const trimmedReason = reason.trim();
  const isReasonValid = trimmedReason.length >= 10 && trimmedReason.length <= 250;
  // Cho phép submit nếu delta === 0 (để kích hoạt No-op toast & close mà không bắt nhập lý do 10 ký tự)
  // hoặc nếu delta !== 0 thì bắt buộc isValidCounted & isReasonValid
  const isNoOp = isValidCounted && delta === 0;
  const canSubmit = (isNoOp || (isValidCounted && isReasonValid)) && !isSubmitting && !isReloading;

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (isSubmittingSyncRef.current) return;

    // F05: No-Op Semantics - Số lượng đếm trùng với tồn kho đang hiển thị
    // Không yêu cầu lý do 10 ký tự cho thao tác No-Op
    if (isValidCounted && delta === 0) {
      toast.info('Số đếm trùng với tồn kho đang hiển thị. Không có yêu cầu điều chỉnh nào được gửi.');
      onClose();
      return;
    }

    if (!canSubmit) return;

    isSubmittingSyncRef.current = true;
    setIsSubmitting(true);
    setErrorMessage('');

    // F06: Generate a cryptographically secure idempotency key per adjustment intent
    let intentKey;
    try {
      intentKey = generateSecureIdempotencyKey();
    } catch (keyErr) {
      setErrorMessage(keyErr.message || 'Không thể tạo khóa bảo mật giao dịch.');
      setIsSubmitting(false);
      isSubmittingSyncRef.current = false;
      return;
    }

    try {
      const response = await inventoryApi.adjustInventory({
        productId: product.product_id,
        countedQuantity: parsedCounted,
        expectedStockVersion: currentVersion,
        reason: trimmedReason,
        idempotencyKey: intentKey,
      });

      if (onSuccess) {
        onSuccess(response);
      }
      onClose();
    } catch (err) {
      const msg = getApiErrorMessage(err, 'Không thể điều chỉnh tồn kho.');
      const errStatus = err?.response?.status;
      const errCode = err?.response?.data?.code;

      // F03: Chỉ hiện khối stale-version conflict khi đúng mã STALE_STOCK_VERSION
      if (errStatus === 409 && errCode === 'STALE_STOCK_VERSION') {
        const errorDetails = err?.response?.data?.details || {};
        const serverVersion = errorDetails.current_stock_version;
        setConflictData({
          expectedVersion: errorDetails.expected_stock_version ?? currentVersion,
          actualVersion: serverVersion !== undefined ? serverVersion : 'Chưa xác định',
          detailsMsg: err?.response?.data?.message || 'Phiên bản tồn kho đã thay đổi trên máy chủ.',
        });
      } else if (!err?.response || err?.code === 'ECONNABORTED') {
        // Ambiguous network failure: Timeout hoặc mất kết nối mạng sau khi đã gửi request
        setConflictData(null);
        setErrorMessage(
          'Kết nối máy chủ bị gián đoạn hoặc quá thời gian phản hồi. Kết quả điều chỉnh chưa thể xác minh. Vui lòng bấm "Tải lại dữ liệu mới nhất" để kiểm tra số tồn trên máy chủ trước khi gửi lại giao dịch.'
        );
      } else {
        setConflictData(null);
        setErrorMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
      isSubmittingSyncRef.current = false;
    }
  };

  // F04: Handler tải lại dữ liệu mới nhất mà vẫn giữ draft (countedQty & reason)
  const handleReloadLatest = async () => {
    if (isReloading || isSubmitting) return;
    setIsReloading(true);
    setErrorMessage('');
    try {
      if (onReloadLatest) {
        const latest = await onReloadLatest(product.product_id);
        // Chỉ xóa conflict banner khi dữ liệu mới thực sự đã được tải về thành công
        if (latest) {
          setConflictData(null);
        }
      }
    } catch (reloadErr) {
      // Giữ nguyên conflictData, không xóa banner khi reload thất bại
      setErrorMessage(getApiErrorMessage(reloadErr, 'Không thể tải lại dữ liệu mới nhất từ máy chủ.'));
    } finally {
      setIsReloading(false);
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
              <span>Danh mục: {categoryName || 'Mặc định'}</span>
            </div>
          </div>

          <div className={styles.versionBadgeContainer}>
            <div className={styles.versionBadge}>
              <span className={styles.versionLabel}>stock_version:</span>
              <span className={styles.versionValue}>{currentVersion}</span>
            </div>
            <span className={styles.versionSubtext}>Phiên bản tồn kho hiện tại</span>
          </div>
        </div>

        {/* Khối Cảnh báo Xung đột phiên bản dữ liệu (HTTP 409 - STALE_STOCK_VERSION) */}
        {conflictData && (
          <div className={styles.conflictCard}>
            <div className={styles.conflictHeaderRow}>
              <div className={styles.conflictTitleBlock}>
                <span className={styles.conflictTitle}>Xung đột phiên bản dữ liệu</span>
                <span className={styles.conflictSubtitle}>STALE_STOCK_VERSION • Optimistic Lock</span>
              </div>
              <span className={styles.httpBadge}>HTTP 409</span>
            </div>

            <p className={styles.conflictDesc}>
              Dữ liệu tồn kho của sản phẩm này vừa được cập nhật trên máy chủ (Phiên bản gửi lên: <span className={styles.versionChip}>v{conflictData.expectedVersion}</span>, Phiên bản thực tế trên máy chủ: <span className={styles.versionChipHighlight}>v{conflictData.actualVersion}</span>). Vui lòng nhấn &quot;Tải lại dữ liệu mới nhất&quot; để đối soát lại tồn kho trước khi gửi.
            </p>

            <div className={styles.conflictDetailsBox}>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel}>Thông báo máy chủ:</span>
                <span className={styles.conflictDetailValue}>{conflictData.detailsMsg}</span>
              </div>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel}>Hành vi bảo vệ:</span>
                <span className={styles.conflictActionProtect}>Hủy bỏ commit để bảo đảm tính toàn vẹn tồn kho</span>
              </div>
            </div>

            <button
              type="button"
              className={styles.conflictReloadBtn}
              onClick={handleReloadLatest}
              disabled={isReloading}
            >
              {isReloading ? 'Đang tải dữ liệu...' : 'Tải lại dữ liệu mới nhất (Giữ nguyên số đếm & lý do)'}
            </button>
          </div>
        )}

        {errorMessage && !conflictData && (
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
            <span className={styles.statCardTitle}>CHÊNH LỆCH</span>
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
                max={MAX_STOCK_QUANTITY}
                step="1"
                className={styles.textInput}
                value={countedQty}
                onChange={(e) => setCountedQty(e.target.value)}
                placeholder="Nhập số lượng đếm được..."
                disabled={isSubmitting || isReloading}
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
              <span className={styles.helperLabel}>Từ 10 đến 250 ký tự</span>
            </div>
            <textarea
              id="adjust-reason"
              rows={3}
              maxLength={250}
              className={styles.textareaInput}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Nhập lý do kiểm kê thực tế..."
              disabled={isSubmitting || isReloading}
            />
            <div className={styles.textareaFooter}>
              <span className={isReasonValid ? styles.validationPassed : styles.validationWarning}>
                {isReasonValid
                  ? 'Độ dài lý do hợp lệ'
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
              disabled={isSubmitting || isReloading}
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

