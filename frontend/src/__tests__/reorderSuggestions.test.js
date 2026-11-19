import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildDraftReceiptPayload,
  buildReorderSuggestions,
} from '../utils/reorderSuggestions.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

describe('T3C9F16 — Reorder Suggestions & Draft Receipt Payload Suite', () => {
  test('buildReorderSuggestions merges low-stock and 30-day top-products with evidence reasons', () => {
    const lowStockItems = [
      {
        product_id: 101,
        sku: 'SKU-101',
        name: 'Nước khoáng Lavie 500ml',
        quantity: 0,
        threshold: 5,
      },
      {
        product_id: 102,
        sku: 'SKU-102',
        name: 'Coca Cola 330ml',
        quantity: 2,
        threshold: 5,
      },
      {
        product_id: 103,
        sku: 'SKU-103',
        name: 'Mì Hảo Hảo Tôm Chua Cay',
        quantity: 4,
        threshold: 5,
      },
    ];

    const topProductItems = [
      {
        product_id: 102,
        sku: 'SKU-102',
        name: 'Coca Cola 330ml',
        sold_units: 25,
        revenue_vnd: 250000,
      },
      {
        product_id: 999,
        sku: 'SKU-999',
        name: 'Sản phẩm còn nhiều tồn',
        sold_units: 50,
        revenue_vnd: 500000,
      },
    ];

    const rows = buildReorderSuggestions(lowStockItems, topProductItems);
    assert.equal(rows.length, 3);

    // Row 1: Out of stock (0/5), no top-products match -> suggested = max(10 - 0, 0, 5) = 10
    assert.deepEqual(rows[0], {
      product_id: 101,
      sku: 'SKU-101',
      name: 'Nước khoáng Lavie 500ml',
      quantity: 0,
      threshold: 5,
      sold_units: 0,
      suggested_quantity: 10,
      unit_cost_vnd: 0,
      reason: 'Hết hàng (0/5)',
    });

    // Row 2: Low stock (2/5), sold 25 in 30d -> suggested = max(10 - 2, ceil(25/2)=13, 5) = 13
    assert.deepEqual(rows[1], {
      product_id: 102,
      sku: 'SKU-102',
      name: 'Coca Cola 330ml',
      quantity: 2,
      threshold: 5,
      sold_units: 25,
      suggested_quantity: 13,
      unit_cost_vnd: 0,
      reason: 'Tồn thấp (2/5) · Bán 25 SP/30 ngày',
    });

    // Row 3: Low stock (4/5), sold 0 -> suggested = max(10 - 4=6, 0, 5) = 6
    assert.deepEqual(rows[2], {
      product_id: 103,
      sku: 'SKU-103',
      name: 'Mì Hảo Hảo Tôm Chua Cay',
      quantity: 4,
      threshold: 5,
      sold_units: 0,
      suggested_quantity: 6,
      unit_cost_vnd: 0,
      reason: 'Tồn thấp (4/5)',
    });
  });

  test('buildReorderSuggestions handles empty, null, and duplicate product_id safely', () => {
    assert.deepEqual(buildReorderSuggestions([], []), []);
    assert.deepEqual(buildReorderSuggestions(null, undefined), []);

    const duplicated = buildReorderSuggestions(
      [
        { product_id: 10, sku: 'SKU-10', name: 'SP 10', quantity: 1, threshold: 5 },
        { product_id: 10, sku: 'SKU-10', name: 'SP 10 dup', quantity: 1, threshold: 5 },
        { product_id: -1, sku: 'BAD', name: 'Bad ID', quantity: 0, threshold: 5 },
      ],
      []
    );
    assert.equal(duplicated.length, 1);
    assert.equal(duplicated[0].product_id, 10);
  });

  test('buildDraftReceiptPayload builds valid DRAFT payload for selected rows', () => {
    const rows = [
      {
        product_id: 101,
        sku: 'SKU-101',
        name: 'Lavie 500ml',
        quantity: 0,
        suggested_quantity: 12,
        unit_cost_vnd: 4500,
      },
      {
        product_id: 102,
        sku: 'SKU-102',
        name: 'Coca Cola 330ml',
        quantity: 2,
        suggested_quantity: 20,
        unit_cost_vnd: 0,
      },
    ];

    const res = buildDraftReceiptPayload({
      supplierId: '3',
      rows,
      selectedIds: [101, 102],
    });

    assert.equal(res.error, null);
    assert.deepEqual(res.payload, {
      supplier_id: 3,
      items: [
        { product_id: 101, quantity: 12, unit_cost_vnd: 4500 },
        { product_id: 102, quantity: 20, unit_cost_vnd: 0 },
      ],
    });
  });

  test('buildDraftReceiptPayload rejects missing supplier, empty selection, non-positive quantity, and negative cost', () => {
    const baseRows = [
      {
        product_id: 101,
        sku: 'SKU-101',
        suggested_quantity: 10,
        unit_cost_vnd: 5000,
      },
    ];

    // 1. Missing supplier
    const noSupplier = buildDraftReceiptPayload({
      supplierId: '',
      rows: baseRows,
      selectedIds: [101],
    });
    assert.equal(noSupplier.payload, null);
    assert.match(noSupplier.error, /nhà cung cấp/i);

    // 2. Empty selection
    const noSelection = buildDraftReceiptPayload({
      supplierId: 2,
      rows: baseRows,
      selectedIds: [],
    });
    assert.equal(noSelection.payload, null);
    assert.match(noSelection.error, /ít nhất 1 sản phẩm/i);

    // 3. Invalid quantity (<= 0)
    const zeroQty = buildDraftReceiptPayload({
      supplierId: 2,
      rows: [{ product_id: 101, sku: 'SKU-101', suggested_quantity: 0, unit_cost_vnd: 5000 }],
      selectedIds: [101],
    });
    assert.equal(zeroQty.payload, null);
    assert.match(zeroQty.error, /Số lượng nhập/i);

    const negQtyPlainRow = buildDraftReceiptPayload({
      supplierId: 2,
      rows: [{ product_id: 101, sku: 'SKU-101', quantity: -5, unit_cost_vnd: 5000 }],
      selectedIds: [101],
    });
    assert.equal(negQtyPlainRow.payload, null);
    assert.match(negQtyPlainRow.error, /Số lượng nhập/i);

    // 4. Negative unit cost (< 0)
    const negCost = buildDraftReceiptPayload({
      supplierId: 2,
      rows: [{ product_id: 101, sku: 'SKU-101', suggested_quantity: 5, unit_cost_vnd: -1000 }],
      selectedIds: [101],
    });
    assert.equal(negCost.payload, null);
    assert.match(negCost.error, /Đơn giá nhập/i);
  });

  test('AiAssistant.jsx and PurchaseList.jsx integrate DRAFT-only AI reorder workflow without auto-confirming', () => {
    const aiPageSource = fs.readFileSync(
      path.resolve(__dirname, '../pages/AiAssistant/AiAssistant.jsx'),
      'utf8'
    );
    assert.match(aiPageSource, /Bảng gợi ý nhập hàng thông minh/);
    assert.match(aiPageSource, /receiptsApi\.createDraft/);
    assert.doesNotMatch(
      aiPageSource,
      /receiptsApi\.confirm/,
      'AiAssistant must ONLY create DRAFT receipts and NEVER auto-confirm'
    );

    const purchasePageSource = fs.readFileSync(
      path.resolve(__dirname, '../pages/Purchases/PurchaseList.jsx'),
      'utf8'
    );
    assert.match(purchasePageSource, /prefillDraft/);
    assert.match(purchasePageSource, /openReceiptId/);
    assert.match(purchasePageSource, /replace:\s*true,\s*state:\s*null/);
  });
});
