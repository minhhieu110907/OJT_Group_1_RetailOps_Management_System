import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import axiosClient from '../api/axiosClient.js';
import { inventoryApi } from '../api/inventoryApi.js';
import { receiptsApi } from '../api/receiptsApi.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcRoot = path.resolve(__dirname, '..');

describe('POS Printable Receipt, Keyboard Shortcuts & Email Alert Enhancements', () => {
  it('PrintableReceipt.jsx renders thermal receipt fields and print-only testid', () => {
    const source = fs.readFileSync(
      path.join(srcRoot, 'components/pos/PrintableReceipt.jsx'),
      'utf8'
    );
    assert.match(source, /RETAILOPS STORE/);
    assert.match(source, /HÓA ĐƠN BÁN LẺ/);
    assert.match(source, /data-testid="printable-receipt"/);
    assert.match(source, /#HD-\{order\.id\}/);
    assert.match(source, /TỔNG THANH TOÁN:/);
  });

  it('PosPage.jsx wires F2, F9, Ctrl+Enter, Escape shortcuts and print receipt button', () => {
    const posSource = fs.readFileSync(
      path.join(srcRoot, 'pages/Pos/PosPage.jsx'),
      'utf8'
    );
    assert.match(posSource, /event\.key === 'F2'/);
    assert.match(posSource, /event\.key === 'F9'/);
    assert.match(posSource, /event\.key === 'Enter'/);
    assert.match(posSource, /event\.key === 'Escape'/);
    assert.match(posSource, /data-testid="pos-print-receipt-btn"/);
    assert.match(posSource, /<PrintableReceipt/);
  });

  it('OrderDetailModal.jsx wires print receipt button and PrintableReceipt', () => {
    const detailSource = fs.readFileSync(
      path.join(srcRoot, 'pages/Orders/OrderDetailModal.jsx'),
      'utf8'
    );
    assert.match(detailSource, /data-testid="order-detail-print-btn"/);
    assert.match(detailSource, /<PrintableReceipt/);
  });

  it('inventoryApi.notifyLowStockAlert posts to /inventory/low-stock/notify', async () => {
    let calledUrl = null;
    const origPost = axiosClient.post;
    axiosClient.post = async (url) => {
      calledUrl = url;
      return { data: { queued: true, low_stock_count: 3 } };
    };
    try {
      const res = await inventoryApi.notifyLowStockAlert();
      assert.strictEqual(calledUrl, '/inventory/low-stock/notify');
      assert.strictEqual(res.queued, true);
      assert.strictEqual(res.low_stock_count, 3);
    } finally {
      axiosClient.post = origPost;
    }
  });

  it('receiptsApi.confirm forwards notify_email=true query param when notifyEmail is enabled', async () => {
    let capturedConfig = null;
    const origPost = axiosClient.post;
    axiosClient.post = async (_url, _body, config) => {
      capturedConfig = config;
      return {
        data: {
          id: 10,
          supplier_id: 1,
          supplier_name_snapshot: 'NCC A',
          status: 'CONFIRMED',
          draft_version: 2,
          total_vnd: 100000,
          created_by: 1,
          closed_by: 1,
          created_at: '2026-11-23T09:00:00Z',
          updated_at: '2026-11-23T09:00:00Z',
          closed_at: '2026-11-23T09:00:00Z',
          items: [],
        },
      };
    };
    try {
      await receiptsApi.confirm(10, {
        expected_draft_version: 1,
        idempotencyKey: 'test-confirm-key-123456',
        notifyEmail: true,
      });
      assert.deepStrictEqual(capturedConfig.params, { notify_email: true });
    } finally {
      axiosClient.post = origPost;
    }
  });

  it('PosPage.jsx includes cash received & change calculator and passes cash meta to PrintableReceipt', () => {
    const posSource = fs.readFileSync(
      path.join(srcRoot, 'pages/Pos/PosPage.jsx'),
      'utf8'
    );
    assert.match(posSource, /data-testid="pos-cash-calculator"/);
    assert.match(posSource, /data-testid="pos-cash-undo-btn"/);
    assert.match(posSource, /placeholder="Nhập số tiền"/);
    assert.match(posSource, /Tiền khách đưa \(VNĐ\)/);
    assert.match(posSource, /Tiền thừa trả khách/);
    assert.match(posSource, /cashReceivedVnd=/);
    assert.match(posSource, /changeDueVnd=/);
  });

  it('PrintablePurchaseReceipt.jsx and PurchaseList.jsx wire purchase receipt printing cleanly', () => {
    const voucherSource = fs.readFileSync(
      path.join(srcRoot, 'components/purchases/PrintablePurchaseReceipt.jsx'),
      'utf8'
    );
    assert.match(voucherSource, /PHIẾU NHẬP KHO/);
    assert.match(voucherSource, /data-testid="printable-purchase-receipt"/);
    assert.match(voucherSource, /#PN-\{receipt\.id\}/);
    assert.match(voucherSource, /TỔNG GIÁ TRỊ PHIẾU NHẬP:/);

    const purchaseSource = fs.readFileSync(
      path.join(srcRoot, 'pages/Purchases/PurchaseList.jsx'),
      'utf8'
    );
    assert.match(purchaseSource, /data-testid="purchase-print-btn"/);
    assert.match(purchaseSource, /<PrintablePurchaseReceipt/);
  });

  it('PrintableReceipt uses Tiền trả lại, PosPage persists cart, and Purchases/Movements expose Xuất Excel', async () => {
    const receiptSource = fs.readFileSync(
      path.join(srcRoot, 'components/pos/PrintableReceipt.jsx'),
      'utf8'
    );
    assert.match(receiptSource, /Tiền khách đưa:/);
    assert.match(receiptSource, /Tiền trả lại:/);
    assert.doesNotMatch(receiptSource, /Tiền thối/);

    const { loadPosCart, savePosCart } = await import('../utils/posUtils.js');
    const store = new Map();
    const mockStorage = {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    };
    const sampleCart = [{ product_id: 1, name: 'Test', quantity: 2, price_vnd: 10000 }];
    assert.strictEqual(savePosCart(mockStorage, 'api:7', sampleCart), true);
    assert.deepStrictEqual(loadPosCart(mockStorage, 'api:7'), sampleCart);
    assert.deepStrictEqual(loadPosCart(mockStorage, 'api:8'), []);
    savePosCart(mockStorage, 'api:7', []);
    assert.deepStrictEqual(loadPosCart(mockStorage, 'api:7'), []);

    const purchaseSource = fs.readFileSync(
      path.join(srcRoot, 'pages/Purchases/PurchaseList.jsx'),
      'utf8'
    );
    const movementSource = fs.readFileSync(
      path.join(srcRoot, 'pages/Inventory/StockMovementList.jsx'),
      'utf8'
    );
    assert.match(purchaseSource, /Xuất Excel/);
    assert.match(movementSource, /Xuất Excel/);
    assert.doesNotMatch(purchaseSource, /Xuất CSV/);
    assert.doesNotMatch(movementSource, /Xuất CSV/);
  });
});
