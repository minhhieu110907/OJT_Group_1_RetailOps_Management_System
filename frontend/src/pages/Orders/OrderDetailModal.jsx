import { useEffect } from 'react';
import { formatVnd } from '../../utils/posUtils';
import {
  evaluateCancelOrderEligibility,
  formatOrderActorLabel,
  formatOrderDateTimeVN,
} from '../../utils/orderUtils';
import styles from './Orders.module.css';

function renderWindowBadge(order, eligibility, detailStatus) {
  if (detailStatus === 'loading') {
    return <span className={styles.windowBadgeMuted}>Đang xác minh trạng thái...</span>;
  }
  if (detailStatus === 'error') {
    return <span className={styles.windowBadgeMuted}>Chưa xác minh được trạng thái</span>;
  }
  if (order.status === 'CANCELLED') {
    return <span className={styles.windowBadgeMuted}>Đã hoàn trả tồn kho</span>;
  }

  if (eligibility.canCancel) {
    return (
      <span className={styles.windowBadgeAmber}>
        {typeof eligibility.remainingMinutes === 'number'
          ? `Còn ${eligibility.remainingMinutes} phút hợp lệ để hủy`
          : 'Hợp lệ hủy trong ngày (Quản trị viên)'}
      </span>
    );
  }

  if (eligibility.reason === 'WINDOW_EXPIRED') {
    return <span className={styles.windowBadgeMuted}>Đã quá hạn 15 phút để hủy</span>;
  }
  if (eligibility.reason === 'NOT_OWNER') {
    return <span className={styles.windowBadgeMuted}>Đơn của tài khoản khác</span>;
  }
  return <span className={styles.windowBadgeMuted}>Đã qua ngày bán hàng</span>;
}

export default function OrderDetailModal({
  order,
  detailStatus = 'verified',
  detailError = '',
  onRetryDetail,
  user,
  nowMs,
  onClose,
  onOpenCancelModal,
  hideTimezone = false,
  compactAdminLabel = false,
}) {
  const isOpen = Boolean(order);

  useEffect(() => {
    if (!isOpen) return undefined;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && typeof onClose === 'function') {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = originalOverflow;
    };
  }, [isOpen, onClose]);

  if (!order) return null;

  const formatActor = (actorId, actorName) => {
    const label = formatOrderActorLabel(actorId, user, actorName);
    if (compactAdminLabel && /^Admin #\d+$/.test(label)) {
      return 'Admin';
    }
    return label;
  };

  const isVerified = detailStatus === 'verified';
  const eligibility = evaluateCancelOrderEligibility({
    order,
    user,
    nowMs,
  });
  const canOpenCancel =
    isVerified && order.status === 'COMPLETED' && eligibility.canCancel;

  const totalUnits = Array.isArray(order.items)
    ? order.items.reduce((sum, item) => sum + (item.quantity || 0), 0)
    : 0;

  return (
    <div
      className={styles.modalOverlay}
      role="dialog"
      aria-modal="true"
      aria-labelledby="order-detail-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && typeof onClose === 'function') {
          onClose();
        }
      }}
    >
      <div className={styles.detailModalCard}>
        <div className={styles.modalHeader}>
          <div className={styles.detailHeaderTitleGroup}>
            <h2 id="order-detail-modal-title" className={styles.detailModalTitle}>
              Chi tiết đơn hàng #{order.id}
            </h2>
            {order.status === 'COMPLETED' ? (
              <span className={styles.statusCompleted}>Đã hoàn tất</span>
            ) : (
              <span className={styles.statusCancelled}>Đã hủy</span>
            )}
          </div>
          <button
            type="button"
            className={styles.modalCloseBtn}
            onClick={onClose}
            aria-label="Đóng chi tiết đơn hàng"
          >
            ✕
          </button>
        </div>

        <div className={styles.modalBody}>
          {detailStatus === 'error' && (
            <div className={styles.alertBoxRose} role="alert">
              <strong>Không thể xác minh chi tiết đơn hàng</strong>
              <p>{detailError || 'Vui lòng thử lại trước khi thực hiện thao tác hủy đơn.'}</p>
              {typeof onRetryDetail === 'function' && (
                <div style={{ marginTop: '10px' }}>
                  <button
                    type="button"
                    className={styles.compactSecondaryBtn}
                    onClick={() => onRetryDetail(order)}
                  >
                    Thử lại
                  </button>
                </div>
              )}
            </div>
          )}

          <div className={styles.detailMetaBox}>
            <div className={styles.detailMetaLeft}>
              <p className={styles.detailMetaLine}>
                Người tạo đơn:{' '}
                <strong>{formatActor(order.created_by, order.created_by_name)}</strong>
              </p>
              <p className={styles.detailMetaLine}>
                Thời gian tạo:{' '}
                <strong>
                  {formatOrderDateTimeVN(order.sold_at)}
                </strong>
              </p>
              {order.status === 'CANCELLED' && (
                <>
                  <p className={styles.detailMetaLine}>
                    Thời gian hủy:{' '}
                    <strong>
                      {formatOrderDateTimeVN(order.cancelled_at)}
                    </strong>
                  </p>
                  <p className={styles.detailMetaLine}>
                    Lý do hủy: <strong>{order.cancel_reason || '—'}</strong>
                    {order.cancelled_by
                      ? ` (Người thực hiện: ${formatActor(
                          order.cancelled_by,
                          order.cancelled_by_name
                        )})`
                      : ''}
                  </p>
                </>
              )}
            </div>
            {renderWindowBadge(order, eligibility, detailStatus)}
          </div>

          <h3 className={styles.detailSectionTitle}>
            Danh sách sản phẩm trong đơn ({totalUnits} sản phẩm)
          </h3>

          <div className={styles.detailTableWrap}>
            <table className={styles.detailTable}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left' }}>MÃ SKU</th>
                  <th style={{ textAlign: 'left' }}>TÊN SẢN PHẨM</th>
                  <th style={{ textAlign: 'center' }}>SL</th>
                  <th style={{ textAlign: 'right' }}>ĐƠN GIÁ</th>
                  <th style={{ textAlign: 'right' }}>THÀNH TIỀN</th>
                </tr>
              </thead>
              <tbody>
                {Array.isArray(order.items) &&
                  order.items.map((item, idx) => (
                    <tr key={`${item.product_id}-${idx}`}>
                      <td>{item.sku_snapshot}</td>
                      <td>{item.product_name_snapshot}</td>
                      <td style={{ textAlign: 'center' }}>{item.quantity}</td>
                      <td style={{ textAlign: 'right' }}>
                        {formatVnd(item.unit_price_vnd)}
                      </td>
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>
                        {formatVnd(item.line_total_vnd)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          <div className={styles.detailTotalRow}>
            <span>Tổng tiền đơn hàng:</span>
            <span>{formatVnd(order.total_vnd)}</span>
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
          {canOpenCancel && typeof onOpenCancelModal === 'function' && (
            <button
              type="button"
              className={styles.compactDangerBtn}
              onClick={() => onOpenCancelModal(order, eligibility.remainingMinutes)}
            >
              Hủy đơn hàng
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
