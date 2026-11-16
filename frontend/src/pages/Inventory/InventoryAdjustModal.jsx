import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import { MAX_STOCK_QUANTITY } from '../../api/inventoryApi';
import {
  ADJUST_MODAL_STATES,
  canSubmitAdjustment,
  classifyAdjustError,
  executeAdjustmentReload,
  executeAdjustmentSubmit,
} from '../../utils/inventoryAdjustController';
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
  const [modalState, setModalState] = useState(ADJUST_MODAL_STATES.IDLE);
  const [errorMessage, setErrorMessage] = useState('');
  const [conflictData, setConflictData] = useState(null);
  const [savedIntent, setSavedIntent] = useState(null);
  const [reconciledNotice, setReconciledNotice] = useState('');

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
        setSavedIntent(null);
        setReconciledNotice('');
        setModalState(ADJUST_MODAL_STATES.IDLE);
      }
    } else if (!isOpen) {
      lastOpenedProductIdRef.current = null;
      setConflictData(null);
      setErrorMessage('');
      setSavedIntent(null);
      setReconciledNotice('');
      setModalState(ADJUST_MODAL_STATES.IDLE);
    }
  }, [isOpen, product]);

  const isSubmitting = modalState === ADJUST_MODAL_STATES.SUBMITTING;
  const isReloading = modalState === ADJUST_MODAL_STATES.RECONCILING;
  const isAmbiguous = modalState === ADJUST_MODAL_STATES.AMBIGUOUS;

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
  const isNoOp = isValidCounted && delta === 0;

  // Khóa nút submit nếu không đủ điều kiện hoặc đang ở trạng thái AMBIGUOUS/STALE_VERSION/SUBMITTING/RECONCILING
  const canSubmit = canSubmitAdjustment({
    modalState,
    isValidCounted,
    isReasonValid,
    isNoOp,
  });

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (isSubmittingSyncRef.current) return;

    if (isNoOp) {
      toast.info('Số đếm trùng với tồn kho đang hiển thị. Không có yêu cầu điều chỉnh nào được gửi.');
      onClose();
      return;
    }

    if (!canSubmit) return;

    isSubmittingSyncRef.current = true;
    setModalState(ADJUST_MODAL_STATES.SUBMITTING);
    setErrorMessage('');
    setReconciledNotice('');

    try {
      const outcome = await executeAdjustmentSubmit({
        product,
        countedQty,
        reason,
        modalState: ADJUST_MODAL_STATES.IDLE, // Đã kiểm tra canSubmit ở trên
        savedIntent,
        onSuccess: (res) => {
          if (onSuccess) onSuccess(res);
          onClose();
        },
      });

      if (!outcome.executed) {
        setModalState(ADJUST_MODAL_STATES.IDLE);
        return;
      }

      if (outcome.success) {
        // onSuccess đã gọi và đóng modal
        return;
      }

      // Xử lý các nhánh lỗi có phân loại
      setModalState(outcome.nextState);
      const errCode = outcome.errorClassification?.code;
      if (outcome.nextState === ADJUST_MODAL_STATES.STALE_VERSION || errCode === 'STALE_STOCK_VERSION') {
        setConflictData(outcome.conflictData);
        setErrorMessage('');
      } else if (outcome.nextState === ADJUST_MODAL_STATES.AMBIGUOUS) {
        setConflictData(null);
        setSavedIntent(outcome.savedIntent);
        setErrorMessage(outcome.errorMessage);
      } else {
        setConflictData(null);
        setErrorMessage(outcome.errorMessage);
      }
    } catch (unexpectedErr) {
      const classified = classifyAdjustError(unexpectedErr);
      setModalState(classified.type === 'AMBIGUOUS' ? ADJUST_MODAL_STATES.AMBIGUOUS : ADJUST_MODAL_STATES.IDLE);
      setErrorMessage(classified.message);
    } finally {
      isSubmittingSyncRef.current = false;
    }
  };

  // Handler tải lại dữ liệu từ máy chủ để đối soát (hỗ trợ cả STALE_VERSION và AMBIGUOUS)
  const handleReloadLatest = async () => {
    if (isReloading || isSubmitting) return;

    setModalState(ADJUST_MODAL_STATES.RECONCILING);
    setErrorMessage('');
    setReconciledNotice('');

    try {
      const latest = await executeAdjustmentReload({
        productId: product.product_id,
        onReloadLatest,
      });

      if (latest) {
        setConflictData(null);
        if (isAmbiguous) {
          setReconciledNotice(
            `Đã tải lại số liệu mới nhất từ máy chủ (v${latest.stock_version}, tồn hiện tại: ${latest.quantity} cái). ` +
            'Vui lòng đối chiếu kỹ số đếm thực tế với số tồn vừa tải trước khi xác nhận tiếp tục.'
          );
        }
      }
    } catch (reloadErr) {
      // Reload thất bại: GIỮ NGUYÊN trạng thái (AMBIGUOUS hoặc STALE_VERSION), GIỮ DRAFT, tiếp tục khóa submit
      const msg = reloadErr?.message || 'Không thể tải lại dữ liệu mới nhất từ máy chủ.';
      setErrorMessage(msg);
      // Giữ nguyên modalState nếu trước đó là AMBIGUOUS
      if (isAmbiguous) {
        setModalState(ADJUST_MODAL_STATES.AMBIGUOUS);
      } else {
        setModalState(ADJUST_MODAL_STATES.STALE_VERSION);
      }
      return;
    }

    // Reload thành công: chuyển sang IDLE để cho phép đối chiếu và xác nhận ý định mới
    setModalState(ADJUST_MODAL_STATES.IDLE);
    setSavedIntent(null);
  };

  return (
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting && !isReloading) onClose();
      }}
    >
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
              Dữ liệu tồn kho của sản phẩm này vừa được cập nhật trên máy chủ (Phiên bản gửi lên:{' '}
              <span className={styles.versionChip}>v{conflictData.expectedVersion}</span>, Phiên bản thực tế trên máy chủ:{' '}
              <span className={styles.versionChipHighlight}>v{conflictData.actualVersion}</span>). Vui lòng nhấn &quot;Tải lại dữ liệu mới nhất&quot; để đối soát lại tồn kho trước khi gửi.
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

        {/* Khối Cảnh báo Kết quả chưa xác minh do mất kết nối/timeout (P1: AMBIGUOUS OUTCOME) */}
        {isAmbiguous && (
          <div className={styles.ambiguousCard}>
            <div className={styles.ambiguousHeaderRow}>
              <div className={styles.ambiguousTitleBlock}>
                <span className={styles.ambiguousTitle}>Kết quả giao dịch chưa thể xác minh</span>
                <span className={styles.ambiguousSubtitle}>AMBIGUOUS OUTCOME • Idempotency Protection</span>
              </div>
              <span className={styles.ambiguousBadge}>MẤT KẾT NỐI</span>
            </div>

            <p className={styles.ambiguousDesc}>
              Yêu cầu kiểm kê đã được gửi đi nhưng kết nối mạng bị gián đoạn hoặc quá thời gian phản hồi.
              Máy chủ có thể đã ghi nhận hoặc chưa hoàn tất giao dịch này.
              <strong> Chức năng gửi giao dịch mới tạm thời bị khóa</strong> để tránh nhân đôi biến động kho.
            </p>

            <div className={styles.ambiguousDetailsBox}>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel}>Số đếm dự kiến:</span>
                <span className={styles.conflictDetailValue}>{savedIntent?.countedQuantity ?? parsedCounted} cái</span>
              </div>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel}>Phiên bản kiểm kê:</span>
                <span className={styles.conflictDetailValue}>v{savedIntent?.expectedStockVersion ?? currentVersion}</span>
              </div>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel}>Khóa giao dịch:</span>
                <span className={styles.ambiguousKeySnippet}>{savedIntent?.idempotencyKey || 'Đang bảo lưu'}</span>
              </div>
            </div>

            <button
              type="button"
              className={styles.ambiguousReloadBtn}
              onClick={handleReloadLatest}
              disabled={isReloading}
            >
              {isReloading ? 'Đang tải lại dữ liệu từ máy chủ...' : 'Tải lại tồn kho từ máy chủ để đối soát'}
            </button>
          </div>
        )}

        {/* Thông báo đã tải lại đối soát thành công */}
        {reconciledNotice && (
          <div className={styles.reconciledAlert}>
            <div className={styles.reconciledText}>{reconciledNotice}</div>
          </div>
        )}

        {/* Thông báo lỗi thông thường (khi không ở khối conflict hoặc ambiguous) */}
        {errorMessage && !conflictData && !isAmbiguous && (
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
                disabled={isSubmitting || isReloading || isAmbiguous}
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
              disabled={isSubmitting || isReloading || isAmbiguous}
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
              {isSubmitting
                ? 'Đang lưu...'
                : isAmbiguous
                ? 'Yêu cầu đối soát trước khi gửi'
                : 'Lưu thay đổi'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
