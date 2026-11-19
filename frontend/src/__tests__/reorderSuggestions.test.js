import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  MAX_SQL_INT,
  buildDraftReceiptPayload,
  buildPrefillDraftState,
  buildReorderSuggestions,
  validateSelectedReorderLines,
} from '../utils/reorderSuggestions.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

describe('T3C9F16 — Reorder Suggestions & Draft Receipt Payload Suite', () => {
  test('P1: distinguishes verified zero sales, verified positive sales, and unknown sales (outside Top 20)', () => {
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
        product_id: 103,
        sku: 'SKU-103',
        name: 'Mì Hảo Hảo Tôm Chua Cay',
        sold_units: 0,
        revenue_vnd: 0,
      },
    ];

    const rows = buildReorderSuggestions(lowStockItems, topProductItems);
    assert.equal(rows.length, 3);

    // Row 1 (101): Out of stock (0/5), NOT in topProductItems -> UNKNOWN sales (sold_units: null, NOT 0)
    assert.deepEqual(rows[0], {
      product_id: 101,
      sku: 'SKU-101',
      name: 'Nước khoáng Lavie 500ml',
      quantity: 0,
      threshold: 5,
      sold_units: null,
      sales_status: 'UNKNOWN',
      suggested_quantity: 10,
      unit_cost_vnd: 0,
      reason: 'Hết hàng (0/5) · Chưa có dữ liệu bán hàng đầy đủ',
    });

    // Row 2 (102): Low stock (2/5), in Top 20 with sold_units=25 -> VERIFIED (max(8, 13, 5) = 13)
    assert.deepEqual(rows[1], {
      product_id: 102,
      sku: 'SKU-102',
      name: 'Coca Cola 330ml',
      quantity: 2,
      threshold: 5,
      sold_units: 25,
      sales_status: 'VERIFIED',
      suggested_quantity: 13,
      unit_cost_vnd: 0,
      reason: 'Tồn thấp (2/5) · Bán 25 SP/30 ngày',
    });

    // Row 3 (103): Low stock (4/5), explicitly verified sold_units=0 -> VERIFIED zero
    assert.deepEqual(rows[2], {
      product_id: 103,
      sku: 'SKU-103',
      name: 'Mì Hảo Hảo Tôm Chua Cay',
      quantity: 4,
      threshold: 5,
      sold_units: 0,
      sales_status: 'VERIFIED',
      suggested_quantity: 6,
      unit_cost_vnd: 0,
      reason: 'Tồn thấp (4/5) · Đã xác minh bán 0 SP/30 ngày',
    });
  });

  test('P1: handles malformed items, duplicate IDs, and missing Top Products safely', () => {
    assert.deepEqual(buildReorderSuggestions([], []), []);
    assert.deepEqual(buildReorderSuggestions(null, undefined), []);

    const rows = buildReorderSuggestions(
      [
        { product_id: 10, sku: 'SKU-10', name: 'SP 10', quantity: 1, threshold: 5 },
        { product_id: 10, sku: 'SKU-10-DUP', name: 'SP 10 dup', quantity: 2, threshold: 5 },
        { product_id: -1, sku: 'BAD-ID', name: 'Bad ID', quantity: 0, threshold: 5 },
        { product_id: 'abc', sku: 'NAN-ID', name: 'NaN ID', quantity: 0, threshold: 5 },
        { product_id: 11, sku: 'BAD-QTY', name: 'Negative qty', quantity: -2, threshold: 5 },
        { product_id: 12, sku: 'FLOAT-QTY', name: 'Float qty', quantity: 1.5, threshold: 5 },
      ],
      null
    );

    assert.equal(rows.length, 1);
    assert.equal(rows[0].product_id, 10);
    assert.equal(rows[0].sold_units, null);
    assert.equal(rows[0].sales_status, 'UNKNOWN');
    assert.match(rows[0].reason, /Chưa có dữ liệu bán hàng đầy đủ/);
  });

  test('P2: buildDraftReceiptPayload and buildPrefillDraftState enforce identical strict validation and never coerce invalid inputs', () => {
    const validRows = [
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

    const directRes = buildDraftReceiptPayload({
      supplierId: '3',
      rows: validRows,
      selectedIds: [101, 102],
    });
    assert.equal(directRes.error, null);
    assert.deepEqual(directRes.payload, {
      supplier_id: 3,
      items: [
        { product_id: 101, quantity: 12, unit_cost_vnd: 4500 },
        { product_id: 102, quantity: 20, unit_cost_vnd: 0 },
      ],
    });

    const prefillRes = buildPrefillDraftState({
      supplierId: '3',
      rows: validRows,
      selectedIds: [101, 102],
    });
    assert.equal(prefillRes.error, null);
    assert.deepEqual(prefillRes.prefillDraft, {
      supplier_id: 3,
      items: [
        {
          product_id: 101,
          sku: 'SKU-101',
          name: 'Lavie 500ml',
          quantity: 12,
          unit_cost_vnd: 4500,
        },
        {
          product_id: 102,
          sku: 'SKU-102',
          name: 'Coca Cola 330ml',
          quantity: 20,
          unit_cost_vnd: 0,
        },
      ],
    });

    // Invalid quantity (0, negative, float, empty, > MAX_SQL_INT) rejected by BOTH
    for (const badQty of [0, -5, 2.5, '', MAX_SQL_INT + 1]) {
      const badRows = [
        { product_id: 101, sku: 'SKU-101', suggested_quantity: badQty, unit_cost_vnd: 5000 },
      ];
      const d = buildDraftReceiptPayload({ supplierId: 1, rows: badRows, selectedIds: [101] });
      const p = buildPrefillDraftState({ supplierId: 1, rows: badRows, selectedIds: [101] });
      assert.equal(d.payload, null);
      assert.equal(p.prefillDraft, null);
      assert.match(d.error, /Số lượng nhập/i);
      assert.equal(d.error, p.error);
    }

    // Invalid unit_cost_vnd (< 0, float, empty) rejected by BOTH
    for (const badCost of [-1, -1000, 12.5, '']) {
      const badRows = [
        { product_id: 101, sku: 'SKU-101', suggested_quantity: 5, unit_cost_vnd: badCost },
      ];
      const d = buildDraftReceiptPayload({ supplierId: 1, rows: badRows, selectedIds: [101] });
      const p = buildPrefillDraftState({ supplierId: 1, rows: badRows, selectedIds: [101] });
      assert.equal(d.payload, null);
      assert.equal(p.prefillDraft, null);
      assert.match(d.error, /Đơn giá nhập/i);
      assert.equal(d.error, p.error);
    }

    // Duplicate product_id in rows rejected by BOTH
    const dupRows = [
      { product_id: 101, sku: 'SKU-101', suggested_quantity: 5, unit_cost_vnd: 1000 },
      { product_id: 101, sku: 'SKU-101', suggested_quantity: 8, unit_cost_vnd: 1000 },
    ];
    const dupCheck = validateSelectedReorderLines({ rows: dupRows, selectedIds: [101] });
    assert.equal(dupCheck.items, null);
    assert.match(dupCheck.error, /trùng lặp/i);

    // SQL BIGINT line total overflow rejected
    const overflowRows = [
      {
        product_id: 101,
        sku: 'SKU-101',
        suggested_quantity: MAX_SQL_INT,
        unit_cost_vnd: Number.MAX_SAFE_INTEGER,
      },
    ];
    const overflowRes = buildDraftReceiptPayload({
      supplierId: 1,
      rows: overflowRows,
      selectedIds: [101],
    });
    assert.equal(overflowRes.payload, null);
    assert.match(overflowRes.error, /vượt quá giới hạn/i);
  });

  test('AiAssistant.jsx and PurchaseList.jsx integrate DRAFT-only AI reorder workflow without auto-confirming', () => {
    const aiPageSource = fs.readFileSync(
      path.resolve(__dirname, '../pages/AiAssistant/AiAssistant.jsx'),
      'utf8'
    );
    assert.match(aiPageSource, /Bảng gợi ý nhập hàng thông minh/);
    assert.match(aiPageSource, /receiptsApi\.createDraft/);
    assert.match(aiPageSource, /buildPrefillDraftState/);
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
    assert.match(purchasePageSource, /buildPrefillDraftState/);
    assert.match(purchasePageSource, /replace:\s*true,\s*state:\s*null/);
  });
});
