import { createPortal } from 'react-dom';
import { formatOrderDateTimeVN } from '../../utils/orderUtils';
import { formatVnd } from '../../utils/posUtils';
import styles from './PrintablePurchaseReceipt.module.css';

const RECEIPT_STATUS_VN = {
  DRAFT: 'Bản nháp (Chưa nhập kho)',
  CONFIRMED: 'Đã xác nhận nhập kho',
  CANCELLED: 'Đã hủy',
};

/**
 * Printable A5/A4 purchase receipt voucher for warehouse & accounting check-in.
 * Hidden on screen; becomes the sole visible content when `window.print()` runs.
 */
export default function PrintablePurchaseReceipt({ receipt }) {
  if (!receipt || typeof document === 'undefined' || !document.body) {
    return null;
  }

  const items = Array.isArray(receipt.items) ? receipt.items : [];
  const totalQty = items.reduce((sum, it) => sum + (Number(it.quantity) || 0), 0);

  const content = (
    <div className={styles.printOnlyWrapper} data-testid="printable-purchase-receipt">
      <div className={styles.voucherPaper}>
        <header className={styles.voucherHeader}>
          <div>
            <h1 className={styles.storeName}>RETAILOPS STORE</h1>
            <p className={styles.storeSub}>Hệ thống quản lý kho &amp; bán lẻ</p>
          </div>
          <div className={styles.voucherCodeBox}>
            <h2 className={styles.voucherTitle}>PHIẾU NHẬP KHO</h2>
            <p className={styles.voucherNumber}>Mã phiếu: #PN-{receipt.id}</p>
          </div>
        </header>

        <section className={styles.metaGrid}>
          <div className={styles.metaRow}>
            <span>Nhà cung cấp:</span>
            <strong>{receipt.supplier_name_snapshot || `NCC #${receipt.supplier_id}`}</strong>
          </div>
          <div className={styles.metaRow}>
            <span>Trạng thái:</span>
            <strong>{RECEIPT_STATUS_VN[receipt.status] || receipt.status}</strong>
          </div>
          <div className={styles.metaRow}>
            <span>Ngày tạo phiếu:</span>
            <span>{formatOrderDateTimeVN(receipt.created_at)}</span>
          </div>
          {receipt.closed_at && (
            <div className={styles.metaRow}>
              <span>{receipt.status === 'CONFIRMED' ? 'Ngày nhập kho:' : 'Ngày đóng phiếu:'}</span>
              <span>{formatOrderDateTimeVN(receipt.closed_at)}</span>
            </div>
          )}
        </section>

        <table className={styles.itemsTable}>
          <thead>
            <tr>
              <th>STT</th>
              <th>Mã SKU</th>
              <th>Tên sản phẩm</th>
              <th className={styles.right}>Số lượng</th>
              <th className={styles.right}>Đơn giá nhập</th>
              <th className={styles.right}>Thành tiền</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={`${item.product_id || idx}-${idx}`}>
                <td>{idx + 1}</td>
                <td>{item.sku_snapshot}</td>
                <td>{item.product_name_snapshot}</td>
                <td className={styles.right}>{Number(item.quantity || 0).toLocaleString('vi-VN')}</td>
                <td className={styles.right}>{formatVnd(item.unit_cost_vnd)}</td>
                <td className={styles.right}>
                  <strong>{formatVnd(item.line_total_vnd)}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <section className={styles.summaryBox}>
          <div className={styles.summaryRow}>
            <span>Tổng số lượng nhập:</span>
            <strong>{totalQty.toLocaleString('vi-VN')} sản phẩm</strong>
          </div>
          <div className={styles.grandTotalRow}>
            <span>TỔNG GIÁ TRỊ PHIẾU NHẬP:</span>
            <strong>{formatVnd(receipt.total_vnd)}</strong>
          </div>
        </section>

        <footer className={styles.signatureGrid}>
          <div className={styles.sigCol}>
            <strong>Người lập phiếu</strong>
            <span>(Ký, ghi rõ họ tên)</span>
          </div>
          <div className={styles.sigCol}>
            <strong>Thủ kho</strong>
            <span>(Ký, ghi rõ họ tên)</span>
          </div>
          <div className={styles.sigCol}>
            <strong>Đại diện Nhà cung cấp</strong>
            <span>(Ký, ghi rõ họ tên)</span>
          </div>
        </footer>
      </div>
    </div>
  );

  return createPortal(content, document.body);
}
