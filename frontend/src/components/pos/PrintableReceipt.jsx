import { createPortal } from 'react-dom';
import { formatOrderDateTimeVN } from '../../utils/orderUtils';
import { formatVnd } from '../../utils/posUtils';
import styles from './PrintableReceipt.module.css';

/**
 * Printable retail receipt (80mm thermal / A5 friendly).
 * Hidden on screen; becomes the sole visible content when `window.print()` runs.
 */
export default function PrintableReceipt({
  order,
  actorLabel = '',
  cashReceivedVnd = null,
  changeDueVnd = null,
}) {
  if (!order || typeof document === 'undefined' || !document.body) {
    return null;
  }

  const items = Array.isArray(order.items) ? order.items : [];
  const totalUnits = items.reduce((sum, it) => sum + (Number(it.quantity) || 0), 0);

  const content = (
    <div className={styles.printOnlyWrapper} data-testid="printable-receipt">
      <div className={styles.receiptPaper}>
        <header className={styles.receiptHeader}>
          <h1 className={styles.storeName}>RETAILOPS STORE</h1>
          <p className={styles.storeTagline}>Hệ thống bán lẻ thông minh</p>
          <div className={styles.dividerDashed} />
          <h2 className={styles.receiptTitle}>HÓA ĐƠN BÁN LẺ</h2>
        </header>

        <section className={styles.metaSection}>
          <div className={styles.metaRow}>
            <span>Mã đơn:</span>
            <strong>#HD-{order.id}</strong>
          </div>
          <div className={styles.metaRow}>
            <span>Ngày bán:</span>
            <span>{formatOrderDateTimeVN(order.sold_at)}</span>
          </div>
          <div className={styles.metaRow}>
            <span>Trạng thái:</span>
            <span>{order.status === 'CANCELLED' ? 'Đã hủy' : 'Hoàn tất'}</span>
          </div>
          {actorLabel && (
            <div className={styles.metaRow}>
              <span>Thu ngân:</span>
              <span>{actorLabel}</span>
            </div>
          )}
        </section>

        <div className={styles.dividerDashed} />

        <table className={styles.itemsTable}>
          <thead>
            <tr>
              <th>Sản phẩm</th>
              <th className={styles.right}>SL</th>
              <th className={styles.right}>Thành tiền</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={`${item.product_id || idx}-${item.sku_snapshot || idx}`}>
                <td>
                  <div className={styles.itemName}>{item.product_name_snapshot}</div>
                  <div className={styles.itemMeta}>
                    {item.sku_snapshot} · {formatVnd(item.unit_price_vnd)}
                  </div>
                </td>
                <td className={styles.right}>{item.quantity}</td>
                <td className={styles.right}>{formatVnd(item.line_total_vnd)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className={styles.dividerDashed} />

        <section className={styles.totalSection}>
          <div className={styles.metaRow}>
            <span>Tổng số lượng:</span>
            <span>{totalUnits} sản phẩm</span>
          </div>
          <div className={styles.grandTotalRow}>
            <span>TỔNG THANH TOÁN:</span>
            <strong>{formatVnd(order.total_vnd)}</strong>
          </div>
          {typeof cashReceivedVnd === 'number' && cashReceivedVnd > 0 && (
            <>
              <div className={styles.metaRow}>
                <span>Tiền khách đưa:</span>
                <span>{formatVnd(cashReceivedVnd)}</span>
              </div>
              <div className={styles.metaRow}>
                <span>Tiền trả lại:</span>
                <strong>{formatVnd(Math.max(0, changeDueVnd || 0))}</strong>
              </div>
            </>
          )}
        </section>

        <div className={styles.dividerDashed} />

        <footer className={styles.receiptFooter}>
          <p>Cảm ơn quý khách đã mua hàng!</p>
          <p>Hẹn gặp lại quý khách.</p>
        </footer>
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
