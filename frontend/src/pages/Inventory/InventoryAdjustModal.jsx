import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import {
  MAX_STOCK_QUANTITY,
  generateSecureIdempotencyKey,
  inventoryApi,
} from '../../api/inventoryApi';
import { getApiErrorMessage } from '../../api/axiosClient';
import { acquireModalScrollLock } from '../../utils/modalScrollLock';
import {
  ADJUSTMENT_STATUS,
  canCloseAdjustmentModal,
  canSubmitAdjustment,
  classifyAdjustmentError,
  createInitialAdjustmentState,
  hasUnresolvedAdjustmentIntent,
  isValidAuthoritativeInventory,
  reduceAdjustmentState,
} from './inventoryAdjustmentController';
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
  initialDraft,
  onClose,
  onSuccess,
  onReloadLatest,
  onAmbiguousStateChange,
}) {
  const { user } = useAuth();
  const toast = useToast();

  const [countedQty, setCountedQty] = useState(() => {
    if (initialDraft?.draft?.countedQty !== undefined) {
      return initialDraft.draft.countedQty;
    }
    return product?.quantity !== undefined && product?.quantity !== null
      ? String(product.quantity)
      : '0';
  });
  const [reason, setReason] = useState(() => initialDraft?.draft?.reason ?? '');

  // Production state managed by pure production reducer, initialized directly with initialDraft if present
  const [state, dispatch] = useReducer(
    reduceAdjustmentState,
    initialDraft,
    createInitialAdjustmentState
  );
  const { status: modalStatus, errorMessage, conflictData, ambiguousIntent, reconciledResult } = state;

  // Sync ambiguous state and full intent snapshot to parent for safe unmount/tab/product/navigation protection
  useEffect(() => {
    if (!isOpen || !product) return;

    const isUnresolved = hasUnresolvedAdjustmentIntent(modalStatus, ambiguousIntent);
    if (isUnresolved) {
      if (onAmbiguousStateChange) {
        onAmbiguousStateChange({
          product,
          state: {
            status: modalStatus,
            ambiguousIntent,
            reconciledResult,
            errorMessage,
          },
          draft: {
            countedQty,
            reason,
          },
        });
      }
    } else {
      // Chỉ khi modal đã resolved và đang ở IDLE (hoặc sau explicit acknowledgement)
      // thì mới thông báo null để parent clear session đã giải quyết
      if (modalStatus === ADJUSTMENT_STATUS.IDLE && onAmbiguousStateChange) {
        onAmbiguousStateChange(null);
      }
    }
  }, [
    isOpen,
    modalStatus,
    ambiguousIntent,
    reconciledResult,
    errorMessage,
    product,
    countedQty,
    reason,
    onAmbiguousStateChange,
  ]);

  // Track product identity to only reset when switching to a completely different product or first open
  const lastOpenedProductIdRef = useRef(null);
  const isSubmittingSyncRef = useRef(false);
  const backdropMouseDownRef = useRef(false);

  // Khóa cuộn và thao tác trang nền khi Modal đang mở
  useEffect(() => {
    if (!isOpen || !product) return undefined;
    return acquireModalScrollLock();
  }, [isOpen, product]);

  // Derived loading state flags
  const isSubmitting = modalStatus === ADJUSTMENT_STATUS.SUBMITTING;
  const isReloading = modalStatus === ADJUSTMENT_STATUS.RECONCILING;

  // Synchronize draft when opening modal for a product, restoring lifted ambiguous session if present
  useEffect(() => {
    if (isOpen && product) {
      if (lastOpenedProductIdRef.current !== product.product_id) {
        lastOpenedProductIdRef.current = product.product_id;

        // If restoring a lifted ambiguous session for the same product
        if (initialDraft && initialDraft.state && initialDraft.product?.product_id === product.product_id) {
          setCountedQty(initialDraft.draft?.countedQty ?? String(product.quantity ?? '0'));
          setReason(initialDraft.draft?.reason ?? '');
          // State was already initialized by createInitialAdjustmentState(initialDraft) in useReducer
        } else {
          setCountedQty(
            product.quantity !== undefined && product.quantity !== null
              ? String(product.quantity)
              : '0'
          );
          setReason('');
          dispatch({ type: 'RESET_PRODUCT' });
        }
      }
    } else if (!isOpen) {
      lastOpenedProductIdRef.current = null;
      dispatch({ type: 'RESET_PRODUCT' });
    }
  }, [isOpen, product, initialDraft]);

  // Centralized close request handler
  const handleRequestClose = useCallback(() => {
    if (!canCloseAdjustmentModal(modalStatus, ambiguousIntent)) {
      return;
    }
    if (onClose) {
      onClose();
    }
  }, [modalStatus, ambiguousIntent, onClose]);

  // Lắng nghe phím Esc để đóng modal có kiểm tra guard an toàn
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        handleRequestClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, handleRequestClose]);

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
        deltaPercentText = `Tăng tồn kho (+${delta})`;
      }
    } else {
      if (currentQty > 0) {
        const pct = Math.abs((delta / currentQty) * 100).toFixed(1).replace(/\.0$/, '');
        deltaPercentText = `Giảm tồn kho (-${pct}%)`;
      } else {
        deltaPercentText = `Giảm tồn kho (${delta})`;
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
  const canSubmit = canSubmitAdjustment({
    status: modalStatus,
    isValidCounted,
    isReasonValid,
    delta,
  });

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (isSubmittingSyncRef.current) return;

    // ROOT CAUSE C FIX: Kiểm tra trạng thái khóa TRƯỚC mọi nhánh no-op!
    // Tuyệt đối không cho phép No-Op bypass khi đang ở AMBIGUOUS, RECONCILING, STALE_VERSION, hay AWAITING_ACKNOWLEDGEMENT
    if (!canSubmit) return;

    // F05: No-Op Semantics - Chỉ chạy khi canSubmit=true (ở trạng thái IDLE)
    if (isValidCounted && delta === 0) {
      toast.info('Số đếm trùng với tồn kho đang hiển thị. Không có yêu cầu điều chỉnh nào được gửi.');
      handleRequestClose();
      return;
    }

    isSubmittingSyncRef.current = true;
    dispatch({ type: 'START_SUBMIT' });

    // F06: Generate a cryptographically secure idempotency key per adjustment intent
    let intentKey;
    try {
      intentKey = generateSecureIdempotencyKey();
    } catch (keyErr) {
      dispatch({
        type: 'SUBMIT_CONFIRMED_ERROR',
        payload: { message: keyErr.message || 'Không thể tạo khóa bảo mật giao dịch.' },
      });
      isSubmittingSyncRef.current = false;
      return;
    }

    const payloadSnapshot = {
      productId: product.product_id,
      countedQuantity: parsedCounted,
      expectedStockVersion: currentVersion,
      reason: trimmedReason,
      idempotencyKey: intentKey,
    };

    try {
      const response = await inventoryApi.adjustInventory(payloadSnapshot);

      if (onSuccess) {
        onSuccess(response);
      }
      if (onClose) {
        onClose();
      }
    } catch (err) {
      const classified = classifyAdjustmentError(err);

      if (classified.type === ADJUSTMENT_STATUS.STALE_VERSION) {
        const errorDetails = classified.details;
        const serverVersion = errorDetails.current_stock_version;
        dispatch({
          type: 'SUBMIT_STALE_VERSION',
          payload: {
            expectedVersion: errorDetails.expected_stock_version ?? currentVersion,
            actualVersion: serverVersion !== undefined ? serverVersion : 'Chưa xác định',
            detailsMsg: classified.message,
          },
        });
      } else if (classified.type === ADJUSTMENT_STATUS.AMBIGUOUS) {
        dispatch({
          type: 'SUBMIT_AMBIGUOUS',
          payload: {
            message: classified.message,
            intent: {
              key: intentKey,
              payload: payloadSnapshot,
            },
          },
        });
      } else {
        dispatch({
          type: 'SUBMIT_CONFIRMED_ERROR',
          payload: {
            message: classified.message || getApiErrorMessage(err, 'Không thể điều chỉnh tồn kho.'),
          },
        });
      }
    } finally {
      isSubmittingSyncRef.current = false;
    }
  };

  // Handler tải lại dữ liệu mới nhất mà vẫn giữ draft (countedQty & reason)
  const handleReloadLatest = async () => {
    if (isReloading || isSubmitting) return;
    const previousStatus = modalStatus;
    dispatch({ type: 'START_RELOAD' });

    try {
      if (onReloadLatest) {
        const latest = await onReloadLatest(product.product_id);

        // Fail-closed validation cho authoritative response
        if (!isValidAuthoritativeInventory(latest, product.product_id)) {
          dispatch({
            type: 'RELOAD_FAILURE',
            payload: {
              previousStatus,
              errorMessage: 'Dữ liệu nhận từ máy chủ không hợp lệ hoặc không đúng sản phẩm.',
            },
          });
          return;
        }

        // Tải hợp lệ: dispatch RELOAD_SUCCESS
        // Reducer sẽ chuyển sang AWAITING_ACKNOWLEDGEMENT nếu đến từ AMBIGUOUS
        dispatch({
          type: 'RELOAD_SUCCESS',
          payload: {
            previousStatus,
            reconciledResult: {
              previousVersion: currentVersion,
              latestVersion: latest.stock_version,
              latestQuantity: latest.quantity,
            },
          },
        });
      } else {
        dispatch({
          type: 'RELOAD_FAILURE',
          payload: {
            previousStatus,
            errorMessage: 'Không tìm thấy hàm tải lại dữ liệu.',
          },
        });
      }
    } catch (reloadErr) {
      dispatch({
        type: 'RELOAD_FAILURE',
        payload: {
          previousStatus,
          errorMessage: getApiErrorMessage(reloadErr, 'Không thể tải lại dữ liệu mới nhất từ máy chủ.'),
        },
      });
    }
  };

  // Khi người dùng bấm xác nhận chủ động sau khi đã xem snapshot tồn kho mới nhất
  const handleAcknowledgeReconciliation = () => {
    dispatch({ type: 'ACKNOWLEDGE_RECONCILIATION' });
  };

  const isModalCloseAllowed = canCloseAdjustmentModal(modalStatus, ambiguousIntent);

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      onMouseDown={(e) => {
        backdropMouseDownRef.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        const startedOnBackdrop = backdropMouseDownRef.current;
        backdropMouseDownRef.current = false;
        if (startedOnBackdrop && e.target === e.currentTarget && isModalCloseAllowed) {
          handleRequestClose();
        }
      }}
    >
      <div className={styles.modalBox}>
        {/* Header với Category, Tên sản phẩm, Phiên bản */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            {categoryName && (
              <div className={styles.badgeRow}>
                <span className={styles.categoryBadge}>{categoryName.toUpperCase()}</span>
              </div>
            )}
            <h2 className={styles.productName}>{product.name}</h2>
            <div className={styles.subInfo}>
              <span>Danh mục: {categoryName || 'Mặc định'}</span>
            </div>
          </div>

          <div className={styles.versionBadgeContainer}>
            <div className={styles.versionBadge}>
              <span className={styles.versionLabel}>Phiên bản:</span>
              <span className={styles.versionValue}>{currentVersion}</span>
            </div>
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

        {/* Khối Cảnh báo Giao dịch chưa thể xác minh (P1 - AMBIGUOUS OUTCOME) */}
        {(modalStatus === ADJUSTMENT_STATUS.AMBIGUOUS || (modalStatus === ADJUSTMENT_STATUS.RECONCILING && ambiguousIntent)) && (
          <div className={styles.conflictCard} style={{ backgroundColor: '#fff7ed', borderColor: '#fed7aa' }}>
            <div className={styles.conflictHeaderRow}>
              <div className={styles.conflictTitleBlock}>
                <span className={styles.conflictTitle} style={{ color: '#c2410c' }}>
                  Kết quả điều chỉnh chưa thể xác minh
                </span>
                <span className={styles.conflictSubtitle} style={{ color: '#ea580c' }}>
                  Mất kết nối mạng / Quá thời gian phản hồi • Bảo vệ tính toàn vẹn
                </span>
              </div>
              <span className={styles.httpBadge} style={{ backgroundColor: '#ffedd5', borderColor: '#fdba74', color: '#c2410c' }}>
                CHƯA RÕ KẾT QUẢ
              </span>
            </div>

            <p className={styles.conflictDesc} style={{ color: '#9a3412' }}>
              Yêu cầu điều chỉnh đã được gửi đi nhưng kết nối mạng bị gián đoạn hoặc máy chủ chưa phản hồi kịp thời. Hệ thống tạm khóa việc gửi giao dịch mới để tránh tạo bản ghi trùng lặp. Vui lòng bấm <strong>&quot;Tải lại tồn kho từ máy chủ&quot;</strong> để đối soát số liệu thực tế trước khi tiếp tục.
            </p>

            <div className={styles.conflictDetailsBox} style={{ borderColor: '#fed7aa' }}>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel} style={{ color: '#c2410c' }}>Mã giao dịch (Idempotency Key):</span>
                <span className={styles.conflictDetailValue} style={{ fontSize: '11px', fontFamily: 'monospace' }}>
                  {ambiguousIntent?.key}
                </span>
              </div>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel} style={{ color: '#c2410c' }}>Số lượng đã yêu cầu:</span>
                <span className={styles.conflictDetailValue}>
                  {ambiguousIntent?.payload?.countedQuantity} cái
                </span>
              </div>
              <div className={styles.conflictDetailRow}>
                <span className={styles.conflictDetailLabel} style={{ color: '#c2410c' }}>Hành vi bảo vệ:</span>
                <span className={styles.conflictActionProtect}>Khóa đóng modal &amp; khóa giao dịch mới cho đến khi hoàn tất đối soát</span>
              </div>
            </div>

            <button
              type="button"
              className={styles.conflictReloadBtn}
              style={{ borderColor: '#ea580c', color: '#c2410c' }}
              onClick={handleReloadLatest}
              disabled={isReloading}
            >
              {isReloading ? 'Đang đối soát dữ liệu từ máy chủ...' : 'Tải lại tồn kho từ máy chủ để đối soát'}
            </button>
          </div>
        )}

        {/* Khối Cổng xác nhận chủ động sau khi tải lại authoritative snapshot (P1 - ACKNOWLEDGEMENT GATE) */}
        {modalStatus === ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT && reconciledResult && (
          <div className={styles.conflictCard} style={{ backgroundColor: '#f0fdf4', borderColor: '#bbf7d0' }}>
            <div className={styles.conflictHeaderRow}>
              <div className={styles.conflictTitleBlock}>
                <span className={styles.conflictTitle} style={{ color: '#15803d' }}>
                  Đã tải dữ liệu tồn kho authoritative mới nhất
                </span>
                <span className={styles.conflictSubtitle} style={{ color: '#16a34a' }}>
                  Kiểm tra đối soát số liệu hệ thống
                </span>
              </div>
            </div>

            <p className={styles.conflictDesc} style={{ color: '#166534' }}>
              Đã tải tồn kho mới nhất: hiện tại là <strong>{reconciledResult.latestQuantity} cái</strong> (Phiên bản: <strong>v{reconciledResult.latestVersion}</strong>). Vui lòng kiểm tra kết quả và xác nhận trước khi thực hiện điều chỉnh mới.
            </p>

            <button
              type="button"
              className={styles.conflictReloadBtn}
              style={{ borderColor: '#16a34a', color: '#15803d', fontWeight: 600 }}
              onClick={handleAcknowledgeReconciliation}
            >
              Đã kiểm tra đối soát • Tiếp tục thao tác
            </button>
          </div>
        )}

        {errorMessage && !conflictData && modalStatus !== ADJUSTMENT_STATUS.AMBIGUOUS && (
          <div className={styles.errorAlert}>
            {errorMessage}
          </div>
        )}

        {/* 3 Thẻ thống kê: HIỆN TẠI, THỰC TẾ, CHÊNH LỆCH */}
        <div className={styles.statsCardsRow}>
          <div className={styles.statCard}>
            <span className={styles.statCardTitle}>HIỆN TẠI</span>
            <div className={styles.statCardMain}>
              <span className={styles.statCardNumber}>{formatNumber(currentQty)}</span>
              <span className={styles.statCardUnit}>cái</span>
            </div>
            <span className={styles.statCardSub}>Dữ liệu từ máy chủ (v{currentVersion})</span>
          </div>

          <div className={styles.statCard}>
            <span className={styles.statCardTitle}>THỰC TẾ</span>
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
                onWheel={(e) => e.currentTarget.blur()}
                placeholder="Nhập số lượng đếm được..."
                disabled={isSubmitting || isReloading || modalStatus === ADJUSTMENT_STATUS.AMBIGUOUS || modalStatus === ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT}
                autoFocus
              />
              <span className={styles.inputUnit}>cái</span>
            </div>
          </div>

          {/* Ô nhập Lý do điều chỉnh kiểm kê */}
          <div className={styles.formGroup}>
            <div className={styles.labelRow}>
              <label htmlFor="adjust-reason" className={styles.fieldLabel}>
                Lý do điều chỉnh kiểm kê <span className={styles.requiredStar}>*</span>
              </label>
              <span className={styles.helperLabel}>Tối thiểu 10 ký tự</span>
            </div>
            <textarea
              id="adjust-reason"
              rows={3}
              className={styles.textareaInput}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Nhập lý do kiểm kê thực tế..."
              disabled={isSubmitting || isReloading || modalStatus === ADJUSTMENT_STATUS.AMBIGUOUS || modalStatus === ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT}
            />
            <div className={styles.textareaFooter}>
              <span className={styles.charCount} style={{ marginLeft: 'auto' }}>
                {trimmedReason.length} / 250 ký tự
              </span>
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
              onClick={handleRequestClose}
              disabled={!isModalCloseAllowed}
            >
              Hủy bỏ
            </button>

            <button
              type="submit"
              className={styles.submitBtn}
              disabled={!canSubmit}
            >
              {isSubmitting ? 'Đang lưu...' : isReloading ? 'Đang đối soát...' : 'Lưu thay đổi'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
