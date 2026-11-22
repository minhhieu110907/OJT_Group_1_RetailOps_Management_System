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
  getDraftActionGuidance,
  parseStrictInteger,
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
      is_slow_moving: false,
      classification: 'CHECK_DEMAND',
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
      is_slow_moving: false,
      classification: 'PRIORITY_RESTOCK',
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
      is_slow_moving: false,
      classification: 'CHECK_DEMAND',
      suggested_quantity: 6,
      unit_cost_vnd: 0,
      reason: 'Tồn thấp (4/5) · Đã xác minh bán 0 SP/30 ngày',
    });
  });

  test('classifies slow-moving products as SLOW_MOVING_HOLD and provides clear draft action guidance', () => {
    const rows = buildReorderSuggestions(
      [
        { product_id: 201, sku: 'SKU-201', name: 'Sản phẩm bán chậm', quantity: 2, threshold: 5 },
      ],
      [],
      [
        { product_id: 201, sku: 'SKU-201', name: 'Sản phẩm bán chậm', sold_units: 1, revenue_vnd: 10000 },
      ]
    );
    assert.equal(rows.length, 1);
    assert.equal(rows[0].is_slow_moving, true);
    assert.equal(rows[0].classification, 'SLOW_MOVING_HOLD');
    assert.equal(rows[0].sold_units, 1);
    assert.match(rows[0].reason, /Bán chậm \(1 SP\/30 ngày\)/);

    const noSup = getDraftActionGuidance({ selectedCount: 0, supplierId: '', suppliersCount: 0 });
    assert.equal(noSup.tone, 'warning');
    assert.match(noSup.message, /Chưa có Nhà cung cấp/);

    const missingBoth = getDraftActionGuidance({ selectedCount: 0, supplierId: '', suppliersCount: 2 });
    assert.equal(missingBoth.tone, 'info');
    assert.match(missingBoth.message, /Tick chọn ít nhất 1 sản phẩm.*Chọn Nhà cung cấp/i);

    const missingSup = getDraftActionGuidance({ selectedCount: 2, supplierId: '', suppliersCount: 2 });
    assert.match(missingSup.message, /Đã chọn 2 sản phẩm.*chọn Nhà cung cấp/i);

    const readyZeroCost = getDraftActionGuidance({
      selectedCount: 1,
      supplierId: '7',
      suppliersCount: 2,
      zeroCostSelectedCount: 1,
    });
    assert.equal(readyZeroCost.tone, 'warning');
    assert.match(readyZeroCost.message, /đơn giá dự kiến = 0 VND/);

    const readyClean = getDraftActionGuidance({
      selectedCount: 1,
      supplierId: '7',
      suppliersCount: 2,
      zeroCostSelectedCount: 0,
    });
    assert.equal(readyClean.tone, 'ready');
    assert.match(readyClean.message, /Sẵn sàng tạo phiếu nhập nháp/);
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

  test('P1: rejects unsafe integers (Number.MAX_SAFE_INTEGER + 1, "9007199254740993"), NaN, Infinity, decimals, and receipt BIGINT total overflow', () => {
    // 1. Number.MAX_SAFE_INTEGER is accepted for unit_cost_vnd (with quantity 1), supplier_id, product_id, but rejected for quantity (> MAX_SQL_INT)
    assert.equal(parseStrictInteger(Number.MAX_SAFE_INTEGER), Number.MAX_SAFE_INTEGER);
    assert.equal(parseStrictInteger(String(Number.MAX_SAFE_INTEGER)), Number.MAX_SAFE_INTEGER);

    const maxSafeCostRes = buildDraftReceiptPayload({
      supplierId: Number.MAX_SAFE_INTEGER,
      rows: [
        {
          product_id: Number.MAX_SAFE_INTEGER,
          sku: 'SKU-SAFE-MAX',
          suggested_quantity: 1,
          unit_cost_vnd: String(Number.MAX_SAFE_INTEGER),
        },
      ],
      selectedIds: [Number.MAX_SAFE_INTEGER],
    });
    assert.equal(maxSafeCostRes.error, null);
    assert.equal(maxSafeCostRes.payload.supplier_id, Number.MAX_SAFE_INTEGER);
    assert.equal(maxSafeCostRes.payload.items[0].product_id, Number.MAX_SAFE_INTEGER);
    assert.equal(maxSafeCostRes.payload.items[0].unit_cost_vnd, Number.MAX_SAFE_INTEGER);

    const maxSafeQtyRes = buildDraftReceiptPayload({
      supplierId: 1,
      rows: [
        {
          product_id: 101,
          sku: 'SKU-101',
          suggested_quantity: Number.MAX_SAFE_INTEGER,
          unit_cost_vnd: 0,
        },
      ],
      selectedIds: [101],
    });
    assert.equal(maxSafeQtyRes.payload, null);
    assert.match(maxSafeQtyRes.error, /Số lượng nhập/i);

    // 2. Number.MAX_SAFE_INTEGER + 1 (9007199254740992) and string "9007199254740993" MUST be rejected without rounding
    const unsafeNum = Number.MAX_SAFE_INTEGER + 1;
    const unsafeStr = '9007199254740993';
    for (const unsafeVal of [
      unsafeNum,
      String(unsafeNum),
      unsafeStr,
      '-9007199254740993',
      NaN,
      Infinity,
      -Infinity,
      1.5,
      '1.5',
      '',
      '   ',
    ]) {
      assert.equal(parseStrictInteger(unsafeVal), null, `Expected null for ${String(unsafeVal)}`);

      // Rejected for unit_cost_vnd in both Direct Create and Pre-fill
      const badCostRows = [
        {
          product_id: 101,
          sku: 'SKU-101',
          suggested_quantity: 1,
          unit_cost_vnd: unsafeVal,
        },
      ];
      const dCost = buildDraftReceiptPayload({
        supplierId: 1,
        rows: badCostRows,
        selectedIds: [101],
      });
      const pCost = buildPrefillDraftState({
        supplierId: 1,
        rows: badCostRows,
        selectedIds: [101],
      });
      assert.equal(dCost.payload, null);
      assert.equal(pCost.prefillDraft, null);
      assert.equal(dCost.error, pCost.error);

      // Rejected for quantity in both Direct Create and Pre-fill
      const badQtyRows = [
        {
          product_id: 101,
          sku: 'SKU-101',
          suggested_quantity: unsafeVal,
          unit_cost_vnd: 1000,
        },
      ];
      const dQty = buildDraftReceiptPayload({
        supplierId: 1,
        rows: badQtyRows,
        selectedIds: [101],
      });
      const pQty = buildPrefillDraftState({
        supplierId: 1,
        rows: badQtyRows,
        selectedIds: [101],
      });
      assert.equal(dQty.payload, null);
      assert.equal(pQty.prefillDraft, null);
      assert.equal(dQty.error, pQty.error);

      // Rejected for supplierId in Direct Create (and Pre-fill when non-empty)
      const dSup = buildDraftReceiptPayload({
        supplierId: unsafeVal,
        rows: [{ product_id: 101, sku: 'SKU-101', suggested_quantity: 1, unit_cost_vnd: 1000 }],
        selectedIds: [101],
      });
      assert.equal(dSup.payload, null);
      if (unsafeVal !== '' && unsafeVal !== null && unsafeVal !== undefined) {
        const pSup = buildPrefillDraftState({
          supplierId: unsafeVal,
          rows: [{ product_id: 101, sku: 'SKU-101', suggested_quantity: 1, unit_cost_vnd: 1000 }],
          selectedIds: [101],
        });
        assert.equal(pSup.prefillDraft, null);
      }

      // Rejected for product_id in both Direct Create and Pre-fill
      const dProd = buildDraftReceiptPayload({
        supplierId: 1,
        rows: [
          {
            product_id: unsafeVal,
            sku: 'SKU-UNSAFE',
            suggested_quantity: 1,
            unit_cost_vnd: 1000,
          },
        ],
        selectedIds: [unsafeVal],
      });
      const pProd = buildPrefillDraftState({
        supplierId: 1,
        rows: [
          {
            product_id: unsafeVal,
            sku: 'SKU-UNSAFE',
            suggested_quantity: 1,
            unit_cost_vnd: 1000,
          },
        ],
        selectedIds: [unsafeVal],
      });
      assert.equal(dProd.payload, null);
      assert.equal(pProd.prefillDraft, null);
    }

    // 3. Receipt-wide SQL BIGINT total overflow across multiple valid lines rejected by both
    const multiLineOverflowRows = [
      {
        product_id: 101,
        sku: 'SKU-101',
        suggested_quantity: 600,
        unit_cost_vnd: Number.MAX_SAFE_INTEGER,
      },
      {
        product_id: 102,
        sku: 'SKU-102',
        suggested_quantity: 600,
        unit_cost_vnd: Number.MAX_SAFE_INTEGER,
      },
    ];
    const dTotalOverflow = buildDraftReceiptPayload({
      supplierId: 1,
      rows: multiLineOverflowRows,
      selectedIds: [101, 102],
    });
    const pTotalOverflow = buildPrefillDraftState({
      supplierId: 1,
      rows: multiLineOverflowRows,
      selectedIds: [101, 102],
    });
    assert.equal(dTotalOverflow.payload, null);
    assert.equal(pTotalOverflow.prefillDraft, null);
    assert.match(dTotalOverflow.error, /Tổng tiền phiếu nhập vượt quá giới hạn BIGINT/i);
    assert.equal(dTotalOverflow.error, pTotalOverflow.error);
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

import {
  applyLastUnitCosts as _applyLastUnitCosts,
  buildLastCostMap as _buildLastCostMap,
  buildLastSupplierMap as _buildLastSupplierMap,
  filterAndSortReorderRows as _filterAndSortReorderRows,
  getMatchingProductIdsForSupplier as _getMatchingProductIdsForSupplier,
  paginateReorderRows as _paginateReorderRows,
} from '../utils/reorderSuggestions.js';

test('last receipt cost map uses newest CONFIRMED price and never overrides edited cost', () => {
  const receipts = [
    { status: 'DRAFT', supplier_id: 99, items: [{ product_id: 1, unit_cost_vnd: 1 }] },
    {
      status: 'CONFIRMED',
      supplier_id: 10,
      supplier_name_snapshot: 'NCC A',
      items: [{ product_id: 1, unit_cost_vnd: 12000 }],
    },
    {
      status: 'CONFIRMED',
      supplier_id: 20,
      supplier_name_snapshot: 'NCC B',
      items: [
        { product_id: 1, unit_cost_vnd: 9000 },
        { product_id: 2, unit_cost_vnd: 0 },
      ],
    },
  ];
  const map = _buildLastCostMap(receipts);
  const supMap = _buildLastSupplierMap(receipts);
  assert.equal(map.get(1), 12000);
  assert.equal(map.has(2), false);
  assert.deepEqual(supMap.get(1), { supplier_id: 10, supplier_name: 'NCC A' });

  const rows = _applyLastUnitCosts(
    [
      { product_id: 1, unit_cost_vnd: 0, category_id: 5 },
      { product_id: 1, unit_cost_vnd: 5000 },
      { product_id: 3, unit_cost_vnd: 0, category_id: 5 },
    ],
    map,
    supMap
  );
  assert.equal(rows[0].unit_cost_vnd, 12000);
  assert.equal(rows[0].cost_source, 'LAST_RECEIPT');
  assert.equal(rows[0].last_supplier_id, 10);
  assert.equal(rows[0].last_supplier_name, 'NCC A');
  assert.equal(rows[1].unit_cost_vnd, 5000);

  const matched = _getMatchingProductIdsForSupplier(rows, { id: 10, category_ids: [5] });
  assert.deepEqual(matched, [1, 1, 3]);
});

test('filterAndSortReorderRows and paginateReorderRows filter, sort, and paginate stably', () => {
  const rows = [
    { product_id: 1, classification: 'SLOW_MOVING_HOLD', quantity: 1, sold_units: 0 },
    { product_id: 2, classification: 'PRIORITY_RESTOCK', quantity: 3, sold_units: 9 },
    { product_id: 3, classification: 'PRIORITY_RESTOCK', quantity: 0, sold_units: 20 },
  ];
  assert.deepEqual(
    _filterAndSortReorderRows(rows, { sort: 'PRIORITY' }).map((r) => r.product_id),
    [2, 3, 1]
  );
  assert.deepEqual(
    _filterAndSortReorderRows(rows, { filter: 'PRIORITY_RESTOCK', sort: 'STOCK_ASC' }).map((r) => r.product_id),
    [3, 2]
  );
  assert.deepEqual(
    _filterAndSortReorderRows(rows, { sort: 'SOLD_DESC' }).map((r) => r.product_id),
    [3, 2, 1]
  );
  const page1 = _paginateReorderRows(rows, { page: 1, pageSize: 2 });
  assert.equal(page1.totalPages, 2);
  assert.equal(page1.items.length, 2);
  const page2 = _paginateReorderRows(rows, { page: 2, pageSize: 2 });
  assert.equal(page2.items.length, 1);
});
