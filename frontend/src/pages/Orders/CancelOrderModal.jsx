import { useRef, useState } from 'react';
import {
  generateCheckoutIdempotencyKey,
  ordersApi,
} from '../../api/ordersApi';
import { formatVnd } from '../../utils/posUtils';
import {
  classifyCancelOrderError,
  formatOrderActorLabel,
  formatOrderDateTimeVN,
  formatOrderTimeShortVN,
  isCancelReasonLocked,
  reconcileCancelIntentWithAuthoritativeOrder,
  resolveCancelIntentForOrder,
} from '../../utils/orderUtils';
import styles from './Orders.module.css';

export default function CancelOrderModal({
  order,
  user,
  isMockMode,
  remainingMinutes,
  cancelIntent,
  onUpdateCancelIntent,
  onClose,
  onCancelled,
  onReloadOrder,
  toast,
}) {
  const [localIntent, setLocalIntent] = useState(() =>
    resolveCancelIntentForOrder({
      existingIntent: cancelIntent,
      orderId: order?.id,
      generateKeyFn: generateCheckoutIdempotencyKey,
    })
  );

  const activeIntent =
    cancelIntent && cancelIntent.orderId === order?.id
      ? cancelIntent
      : localIntent;

  const commitIntent = (nextIntent) => {
    setLocalIntent(nextIntent);
    if (typeof onUpdateCancelIntent === 'function' && order?.id) {
      onUpdateCancelIntent(order.id, nextIntent);
    }
  };

  const [phase, setPhase] = useState('CONFIRM'); // 'CONFIRM' | 'INELIGIBLE' | 'DATA_CHANGED'
  const [reasonError, setReasonError] = useState('');
  const [serverErrorMessage, setServerErrorMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isSubmittingRef = useRef(false);

  if (!order) return null;

  const reason = activeIntent.reason || '';
  const reasonLocked = isCancelReasonLocked(activeIntent);
  const ambiguousMessage = activeIntent.ambiguousMessage || '';

  const totalUnits = Array.isArray(order.items)
    ? order.items.reduce((sum, item) => sum + (item.quantity || 0), 0)
    : 0;
  const itemsPreview = Array.isArray(order.items)
    ? order.items
        .slice(0, 3)
        .map((item) => `${item.quantity} ${item.product_name_snapshot}`)
        .join(', ')
    : '';
  const hasMoreItems = Array.isArray(order.items) && order.items.length > 3;

  const handleReasonChange = (value) => {
    if (reasonLocked) return;
    if (reasonError) setReasonError('');

    const shouldRotateKey = activeIntent.outcome === 'definite_failure';
    commitIntent({
      ...activeIntent,
      orderId: order.id,
      reason: value,
      normalizedReason: value.trim(),
      outcome: 'idle',
      ambiguousMessage: '',
      idempotencyKey: shouldRotateKey
        ? generateCheckoutIdempotencyKey()
        : activeIntent.idempotencyKey,
    });
  };

  const handleConfirmCancel = async () => {
    if (isSubmittingRef.current) return;
    const trimmed = reason.trim();
    if (!trimmed) {
      setReasonError('Vui lòng nhập lý do hủy đơn hàng.');
      return;
    }
    if (trimmed.length > 500) {
      setReasonError('Lý do hủy đơn không được vượt quá 500 ký tự.');
      return;
    }

    const pendingIntent = {
      ...activeIntent,
      orderId: order.id,
      reason,
      normalizedReason: trimmed,
      outcome: 'pending',
    };
    commitIntent(pendingIntent);

    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      const updatedOrder = await ordersApi.cancelOrder({
        isMockMode,
        orderId: order.id,
        reason: trimmed,
        idempotencyKey: pendingIntent.idempotencyKey,
      });

      commitIntent({
        ...pendingIntent,
        outcome: 'confirmed',
        ambiguousMessage: '',
      });
      toast.success(`Đã hủy đơn hàng #${updatedOrder.id} và hoàn tồn kho thành công.`);
      onCancelled(updatedOrder);
    } catch (err) {
      const classified = classifyCancelOrderError(err, {
        actorRole: user?.role,
      });
      if (classified.outcome === 'INELIGIBLE') {
        commitIntent({
          ...pendingIntent,
          outcome: 'definite_failure',
          ambiguousMessage: '',
        });
        setServerErrorMessage(classified.message);
        setPhase('INELIGIBLE');
      } else if (classified.outcome === 'DATA_CHANGED') {
        commitIntent({
          ...pendingIntent,
          outcome: 'definite_failure',
          ambiguousMessage: '',
        });
        setServerErrorMessage(classified.message);
        setPhase('DATA_CHANGED');
      } else if (classified.outcome === 'AMBIGUOUS') {
        commitIntent({
          ...pendingIntent,
          outcome: 'ambiguous',
          ambiguousMessage: classified.message,
        });
        toast.warning(classified.message);
      } else {
        commitIntent({
          ...pendingIntent,
          outcome: 'definite_failure',
          ambiguousMessage: '',
        });
        toast.error(classified.message);
      }
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  const handleReconcileOrderState = async () => {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      const latest = await ordersApi.getOrderById({
        isMockMode,
        orderId: order.id,
      });
      const reconciled = reconcileCancelIntentWithAuthoritativeOrder({
        intent: activeIntent,
        authoritativeOrder: latest,
      });
      commitIntent(reconciled.nextIntent);

      if (reconciled.status === 'ALREADY_CANCELLED') {
        toast.info(reconciled.message);
        onReloadOrder(latest);
        onClose();
        return;
      }

      if (reconciled.status === 'STILL_COMPLETED') {
        toast.warning(reconciled.message);
      } else {
        toast.error(reconciled.message);
      }
    } catch (err) {
      const classified = classifyCancelOrderError(err, {
        actorRole: user?.role,
      });
      toast.error(classified.message);
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  const handleReloadOrderState = async () => {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      const latest = await ordersApi.getOrderById({
        isMockMode,
        orderId: order.id,
      });
      commitIntent({
        ...activeIntent,
        outcome: 'confirmed',
        ambiguousMessage: '',
      });
      onReloadOrder(latest);
      onClose();
    } catch (err) {
      const classified = classifyCancelOrderError(err, {
        actorRole: user?.role,
      });
      toast.error(classified.message);
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className={styles.modalOverlay}
      role="dialog"
      aria-modal="true"
      aria-labelledby="cancel-order-modal-title"
    >
      <div className={styles.modalCard}>
        {phase === 'CONFIRM' && (
          <>
            <div className={styles.modalHeader}>
              <div className={styles.modalTitleRow}>
                <span className={styles.modalIconDanger} aria-hidden="true">
                  ⚠
                </span>
                <div>
                  <h2 id="cancel-order-modal-title" className={styles.modalTitle}>
                    Xác nhận hủy đơn hàng #{order.id}
                  </h2>
                  <p className={styles.modalSubtitle}>Quy trình hủy đơn hàng tiêu chuẩn</p>
                </div>
              </div>
              <button
                type="button"
                className={styles.modalCloseBtn}
                onClick={onClose}
                disabled={isSubmitting}
                aria-label="Đóng hộp thoại hủy đơn"
              >
                ✕
              </button>
            </div>

            <div className={styles.modalBody}>
              <div className={styles.summaryCard}>
                <div className={styles.summaryTopRow}>
                  <span className={styles.creatorLabel}>
                    Người tạo đơn:{' '}
                    <strong>
                      {order.created_by_name ||
                        formatOrderActorLabel(order.created_by, user)}
                    </strong>
                  </span>
                  <span className={styles.windowBadgeAmber}>
                    Tạo lúc {formatOrderTimeShortVN(order.sold_at)}
                    {typeof remainingMinutes === 'number'
                      ? ` (Còn ${remainingMinutes} phút hợp lệ)`
                      : ''}
                  </span>
                </div>

                <div className={styles.summaryBottomRow}>
                  <div className={styles.summaryItemsText}>
                    <div>
                      Sản phẩm trong đơn: <strong>{totalUnits} sản phẩm</strong>
                    </div>
                    {itemsPreview && (
                      <div className={styles.summaryItemsDetail}>
                        ({itemsPreview}
                        {hasMoreItems ? ', ...' : ''})
                      </div>
                    )}
                  </div>
                  <div className={styles.summaryTotalBox}>
                    <span>Tổng tiền đơn hàng:</span>
                    <strong>{formatVnd(order.total_vnd)}</strong>
                  </div>
                </div>
              </div>

              <div className={styles.warningListBox}>
                <strong>Hành động này không thể hoàn tác. Khi xác nhận hủy đơn:</strong>
                <ul>
                  <li>Đơn hàng sẽ chuyển sang trạng thái Đã hủy.</li>
                  <li>
                    Hoàn trả tồn kho tự động đúng 1 lần duy nhất vào kho hàng (+
                    {totalUnits} sản phẩm).
                  </li>
                  <li>
                    Ghi nhận người thực hiện, thời điểm và lý do hủy vào nhật ký hệ
                    thống.
                  </li>
                </ul>
              </div>

              {ambiguousMessage && (
                <div className={styles.alertBoxAmber} role="alert">
                  <strong>Chưa xác định được kết quả hủy đơn</strong>
                  <p>
                    {ambiguousMessage} Bạn có thể bấm &quot;Kiểm tra trạng thái đơn&quot; để
                    đối soát hoặc bấm &quot;Xác nhận hủy đơn&quot; để thử lại với cùng mã giao dịch.
                  </p>
                  <div style={{ marginTop: '10px' }}>
                    <button
                      type="button"
                      className={styles.compactSecondaryBtn}
                      onClick={handleReconcileOrderState}
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? 'Đang kiểm tra...' : 'Kiểm tra trạng thái đơn'}
                    </button>
                  </div>
                </div>
              )}

              <div className={styles.reasonGroup}>
                <div className={styles.reasonHeader}>
                  <label htmlFor="cancel-order-reason">Lý do hủy đơn hàng *</label>
                  <span className={styles.reasonCounter}>
                    {reason.trim().length} / 500
                  </span>
                </div>
                <textarea
                  id="cancel-order-reason"
                  className={styles.reasonTextarea}
                  placeholder="Nhập lý do hủy đơn (ví dụ: Khách hàng yêu cầu hủy đơn hàng)..."
                  maxLength={500}
                  value={reason}
                  onChange={(e) => handleReasonChange(e.target.value)}
                  disabled={isSubmitting || reasonLocked}
                  readOnly={reasonLocked}
                />
                {reasonError ? (
                  <span className={styles.reasonError}>{reasonError}</span>
                ) : reasonLocked ? (
                  <span className={styles.reasonHint}>
                    Đang khóa lý do để giữ nguyên mã giao dịch đối soát cho yêu cầu hủy trước đó.
                  </span>
                ) : (
                  <span className={styles.reasonHint}>
                    Lý do hủy được lưu cùng thông tin người thực hiện
                  </span>
                )}
              </div>
            </div>

            <div className={styles.modalFooterRight}>
              <button
                type="button"
                className={styles.compactSecondaryBtn}
                onClick={onClose}
                disabled={isSubmitting}
              >
                Quay lại
              </button>
              <button
                type="button"
                className={styles.compactDangerBtn}
                onClick={handleConfirmCancel}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Đang hủy đơn...' : 'Xác nhận hủy đơn'}
              </button>
            </div>
          </>
        )}

        {phase === 'INELIGIBLE' && (
          <>
            <div className={styles.modalHeader}>
              <div className={styles.modalTitleRow}>
                <span className={styles.modalIconDanger} aria-hidden="true">
                  ⏳
                </span>
                <div>
                  <h2 id="cancel-order-modal-title" className={styles.modalTitle}>
                    Không đủ điều kiện hủy đơn
                  </h2>
                  <p className={styles.modalSubtitle}>
                    {user?.role === 'ADMIN'
                      ? 'Chỉ được hủy đơn hoàn tất trong cùng ngày kinh doanh'
                      : 'Ngoài thời hạn 15 phút, khác người tạo hoặc khác ngày kinh doanh'}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className={styles.modalCloseBtn}
                onClick={onClose}
                aria-label="Đóng thông báo lỗi"
              >
                ✕
              </button>
            </div>

            <div className={styles.modalBody}>
              <div className={styles.kvBox}>
                <div className={styles.kvRow}>
                  <span className={styles.kvLabel}>Mã đơn hàng:</span>
                  <span className={styles.kvValue}>#{order.id}</span>
                </div>
                <div className={styles.kvRow}>
                  <span className={styles.kvLabel}>Thời gian tạo:</span>
                  <span className={styles.kvValue}>
                    {formatOrderDateTimeVN(order.sold_at)}
                  </span>
                </div>
                <div className={styles.kvRow}>
                  <span className={styles.kvLabel}>Trạng thái quyền:</span>
                  <span className={styles.kvValueDanger}>
                    {user?.role === 'ADMIN' ? 'Tài khoản quản trị' : 'Tài khoản nhân viên'}
                  </span>
                </div>
              </div>

              <div className={styles.alertBoxRose} role="alert">
                <strong>Không đủ điều kiện hủy đơn này</strong>
                <p>{serverErrorMessage}</p>
              </div>
            </div>

            <div className={styles.modalFooterRight}>
              <button
                type="button"
                className={styles.compactSecondaryBtn}
                onClick={onClose}
              >
                Đóng
              </button>
            </div>
          </>
        )}

        {phase === 'DATA_CHANGED' && (
          <>
            <div className={styles.modalHeader}>
              <div className={styles.modalTitleRow}>
                <span className={styles.modalIconAmber} aria-hidden="true">
                  ↻
                </span>
                <div>
                  <h2 id="cancel-order-modal-title" className={styles.modalTitle}>
                    Dữ liệu đơn hàng bị thay đổi
                  </h2>
                  <p className={styles.modalSubtitle}>
                    Trạng thái đơn hàng trên máy chủ đã thay đổi so với lúc mở màn hình
                  </p>
                </div>
              </div>
              <button
                type="button"
                className={styles.modalCloseBtn}
                onClick={onClose}
                disabled={isSubmitting}
                aria-label="Đóng thông báo xung đột"
              >
                ✕
              </button>
            </div>

            <div className={styles.modalBody}>
              <div className={styles.kvBox}>
                <div className={styles.kvRow}>
                  <span className={styles.kvLabel}>Mã đơn hàng:</span>
                  <span className={styles.kvValue}>#{order.id}</span>
                </div>
                <div className={styles.kvRow}>
                  <span className={styles.kvLabel}>Trạng thái hiện tại:</span>
                  <span className={styles.kvValueDanger}>Đã thay đổi trên máy chủ</span>
                </div>
                <div className={styles.kvRow}>
                  <span className={styles.kvLabel}>Xác minh dữ liệu:</span>
                  <span className={styles.kvValue}>Cần tải lại trạng thái mới nhất</span>
                </div>
              </div>

              <div className={styles.alertBoxAmber} role="alert">
                <strong>Trạng thái đơn hàng đã thay đổi trên máy chủ</strong>
                <p>{serverErrorMessage}</p>
              </div>
            </div>

            <div className={styles.modalFooterRight}>
              <button
                type="button"
                className={styles.compactSecondaryBtn}
                onClick={onClose}
                disabled={isSubmitting}
              >
                Đóng
              </button>
              <button
                type="button"
                className={styles.compactPrimaryBtn}
                onClick={handleReloadOrderState}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Đang tải lại...' : 'Tải lại trạng thái đơn'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
