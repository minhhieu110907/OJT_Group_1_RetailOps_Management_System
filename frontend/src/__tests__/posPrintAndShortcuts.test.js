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
    assert.match(posSource, /evaluatePosCashInput/);
    assert.match(posSource, /cashReceivedVnd=/);
    assert.match(posSource, /changeDueVnd=/);

    const receiptSource = fs.readFileSync(
      path.join(srcRoot, 'components/pos/PrintableReceipt.jsx'),
      'utf8'
    );
    assert.doesNotMatch(receiptSource, /Math\.max\(0,\s*changeDueVnd/);
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

  it('Finding P1: evaluatePosCashInput enforces optional cash >= total and rejects invalid/underpaid inputs', async () => {
    const { evaluatePosCashInput } = await import('../utils/posUtils.js');

    // 1. Optional (empty) -> allowed
    const emptyRes = evaluatePosCashInput('', 100000);
    assert.strictEqual(emptyRes.hasInput, false);
    assert.strictEqual(emptyRes.canCheckout, true);

    // 2. Underpaid -> blocked with exact short amount
    const shortRes = evaluatePosCashInput('50000', 100000);
    assert.strictEqual(shortRes.hasInput, true);
    assert.strictEqual(shortRes.isValid, true);
    assert.strictEqual(shortRes.canCheckout, false);
    assert.strictEqual(shortRes.shortAmountVnd, 50000);

    // 3. Exact -> allowed with 0 change
    const exactRes = evaluatePosCashInput('100000', 100000);
    assert.strictEqual(exactRes.canCheckout, true);
    assert.strictEqual(exactRes.changeDueVnd, 0);

    // 4. Overpaid -> allowed with exact change
    const overRes = evaluatePosCashInput('150000', 100000);
    assert.strictEqual(overRes.canCheckout, true);
    assert.strictEqual(overRes.changeDueVnd, 50000);

    // 5. Negative, decimal, non-numeric, unsafe -> blocked
    for (const bad of [-5000, '-5000', '12.5', 'abc', Number.MAX_SAFE_INTEGER + 1]) {
      const badRes = evaluatePosCashInput(bad, 100000);
      assert.strictEqual(badRes.isValid, false);
      assert.strictEqual(badRes.canCheckout, false);
    }
  });

  it('Finding P2: POS cart persistence round-trips addProductToCart items and isolates users/corrupt storage', async () => {
    const { addProductToCart, loadPosCart, savePosCart } = await import('../utils/posUtils.js');
    const store = new Map();
    const mockStorage = {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    };

    const p1 = { id: 11, sku: 'SKU-11', name: 'Sản phẩm A', sale_price_vnd: 25000, quantity: 10 };
    const p2 = { id: 22, sku: 'SKU-22', name: 'Sản phẩm B', sale_price_vnd: 40000, quantity: 5 };

    let { nextCart } = addProductToCart([], p1);
    ({ nextCart } = addProductToCart(nextCart, p1));
    ({ nextCart } = addProductToCart(nextCart, p2));

    assert.strictEqual(savePosCart(mockStorage, 'api:7', nextCart), true);
    assert.deepStrictEqual(loadPosCart(mockStorage, 'api:7'), nextCart);
    assert.deepStrictEqual(loadPosCart(mockStorage, 'api:8'), []);

    // Corrupt JSON
    mockStorage.setItem('retailops_pos_cart_v1:api:7', '{not-json');
    assert.deepStrictEqual(loadPosCart(mockStorage, 'api:7'), []);

    // Legacy/wrong schema & invalid quantity/productId
    mockStorage.setItem(
      'retailops_pos_cart_v1:api:7',
      JSON.stringify([
        { product_id: 1, name: 'Legacy', quantity: 2 },
        { productId: 0, sku: 'X', name: 'BadId', unitPriceVnd: 1000, quantity: 1, availableStock: 5 },
        { productId: 3, sku: 'Y', name: 'BadQty', unitPriceVnd: 1000, quantity: 0, availableStock: 5 },
      ])
    );
    assert.deepStrictEqual(loadPosCart(mockStorage, 'api:7'), []);

    // Storage throwing exception
    const throwingStorage = {
      getItem: () => {
        throw new Error('QuotaExceeded');
      },
      setItem: () => {
        throw new Error('QuotaExceeded');
      },
      removeItem: () => {
        throw new Error('QuotaExceeded');
      },
    };
    assert.strictEqual(savePosCart(throwingStorage, 'api:7', nextCart), false);
    assert.deepStrictEqual(loadPosCart(throwingStorage, 'api:7'), []);
  });

  it('Finding P2: Purchase Receipt export uses supplier_name_snapshot, paginates, deduplicates, and fails cleanly', async () => {
    const {
      buildPurchaseReceiptExportRows,
      collectPurchaseReceiptsForExport,
    } = await import('../utils/exportReportHelpers.js');

    const calls = [];
    const mockReceiptsApi = {
      async list(params) {
        calls.push(params);
        if (params.page === 1) {
          return {
            items: [
              { id: 10, supplier_id: 2, supplier_name_snapshot: 'NCC Miền Bắc', items: [{}], created_at: '2026-11-20T10:00:00Z', total_vnd: 500000, status: 'CONFIRMED' },
              { id: 9, supplier_id: 3, supplier_name_snapshot: 'NCC Miền Nam', items: [{}, {}], created_at: '2026-11-20T09:00:00Z', total_vnd: 300000, status: 'DRAFT', draft_version: 2 },
            ],
            total: 3,
            total_pages: 2,
          };
        }
        return {
          items: [
            { id: 9, supplier_id: 3, supplier_name_snapshot: 'NCC Miền Nam', items: [{}, {}], created_at: '2026-11-20T09:00:00Z', total_vnd: 300000, status: 'DRAFT', draft_version: 2 },
            { id: 8, supplier_id: 4, supplier_name_snapshot: 'NCC Trung Bộ', items: [{}], created_at: '2026-11-20T08:00:00Z', total_vnd: 200000, status: 'CANCELLED' },
          ],
          total: 3,
          total_pages: 2,
        };
      },
    };

    const res = await collectPurchaseReceiptsForExport({
      topTab: 'RECEIPTS',
      activeTab: 'ALL',
      supplierFilter: '2',
      fromDateFilter: '2026-11-01',
      toDateFilter: '2026-11-23',
      receiptsApi: mockReceiptsApi,
    });
    assert.strictEqual(res.items.length, 3);
    assert.deepStrictEqual(res.items.map((r) => r.id), [10, 9, 8]);
    assert.strictEqual(calls[0].supplierId, 2);
    assert.strictEqual(calls[1].supplierId, 2);

    const rows = buildPurchaseReceiptExportRows(res.items, (d) => d);
    assert.strictEqual(rows[1][1], 'NCC Miền Bắc');

    // Empty result
    const emptyRes = await collectPurchaseReceiptsForExport({
      topTab: 'RECEIPTS',
      activeTab: 'DRAFT',
      receiptsApi: { async list() { return { items: [], total: 0, total_pages: 1 }; } },
    });
    assert.strictEqual(emptyRes.items.length, 0);

    // Mid-export failure rejects cleanly
    await assert.rejects(
      () =>
        collectPurchaseReceiptsForExport({
          topTab: 'RECEIPTS',
          activeTab: 'ALL',
          receiptsApi: {
            async list({ page }) {
              if (page === 1) return { items: [{ id: 1 }], total: 2, total_pages: 2 };
              throw new Error('Network failure');
            },
          },
        }),
      /Network failure/
    );
  });

  it('Finding P2: Stock Movement export caps cleanly with partial flag, resolves product names in batch, and enforces RBAC', async () => {
    const {
      buildStockMovementExportRows,
      collectStockMovementsForExport,
    } = await import('../utils/exportReportHelpers.js');

    let invCalls = 0;
    const mockInventoryApi = {
      async getStockMovements({ page, kind }) {
        assert.strictEqual(kind, 'ADJUSTMENT');
        if (page === 1) {
          return {
            items: Array.from({ length: 100 }, (_, i) => ({
              id: i + 1,
              product_id: 500 + (i % 2),
              sku: `SKU-${i}`,
              kind: 'ADJUSTMENT',
              quantity_before: 10,
              quantity_after: 12,
              occurred_at: '2026-11-20T10:00:00Z',
              reference_id: null,
              actor_id: 1,
              adjustment_reason: 'Kiểm kê',
            })),
            total: 125,
          };
        }
        return {
          items: Array.from({ length: 25 }, (_, i) => ({
            id: 101 + i,
            product_id: 500 + (i % 2),
            sku: `SKU-${100 + i}`,
            kind: 'ADJUSTMENT',
            quantity_before: 10,
            quantity_after: 8,
            occurred_at: '2026-11-20T09:00:00Z',
            reference_id: null,
            actor_id: 1,
            adjustment_reason: 'Hư hỏng',
          })),
          total: 125,
        };
      },
      async getInventory() {
        invCalls += 1;
        return {
          items: [
            { product_id: 500, name: 'Sản phẩm Batch A' },
            { product_id: 501, name: 'Sản phẩm Batch B' },
          ],
          total: 2,
        };
      },
    };

    const capped = await collectStockMovementsForExport({
      selectedKind: 'ADJUSTMENT',
      inventoryApi: mockInventoryApi,
      maxRows: 100,
    });
    assert.strictEqual(capped.items.length, 100);
    assert.strictEqual(capped.isTruncated, true);
    assert.strictEqual(capped.remainingCount, 25);
    assert.strictEqual(invCalls, 1);

    const staffRows = buildStockMovementExportRows(capped.items.slice(0, 1), {
      isAdmin: false,
      productMap: capped.productMap,
      formatDateTimeFn: (d) => d,
      formatReferenceCodeFn: () => '-',
      movementKindLabels: { ADJUSTMENT: { label: 'Điều chỉnh kho' } },
    });
    assert.strictEqual(staffRows[0].includes('Người thực hiện'), false);
    assert.strictEqual(staffRows[1][1], 'Sản phẩm Batch A');

    const adminRows = buildStockMovementExportRows(capped.items.slice(0, 1), {
      isAdmin: true,
      productMap: capped.productMap,
      formatDateTimeFn: (d) => d,
      formatReferenceCodeFn: () => '-',
      movementKindLabels: { ADJUSTMENT: { label: 'Điều chỉnh kho' } },
    });
    assert.strictEqual(adminRows[0].includes('Người thực hiện'), true);
    assert.strictEqual(adminRows[1][7], 'Kiểm kê');
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
