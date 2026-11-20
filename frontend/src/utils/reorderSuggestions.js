import { DEFAULT_LOW_STOCK_THRESHOLD } from '../api/inventoryApi.js';

export const MAX_SQL_INT = 2_147_483_647;
export const MAX_SAFE_JS_INT = Number.MAX_SAFE_INTEGER;
export const MAX_SAFE_JS_BIGINT = BigInt(Number.MAX_SAFE_INTEGER);
export const MAX_SQL_BIGINT = 9_223_372_036_854_775_807n;

/**
 * Kiểm tra giá trị có phải là số nguyên an toàn tuyệt đối (Number.isSafeInteger).
 * - Với number: chỉ chấp nhận Number.isSafeInteger(raw).
 * - Với string: kiểm tra cú pháp /^-?\d+$/, đối chiếu qua BigInt trong phạm vi
 *   [-Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER] trước khi chuyển sang Number
 *   để ngăn chặn triệt để hiện tượng làm tròn IEEE-754 (VD: "9007199254740993").
 * - Từ chối chuỗi rỗng, boolean, NaN, Infinity, số thập phân và số vượt MAX_SAFE_INTEGER.
 */
export function parseStrictInteger(raw) {
  if (raw === '' || raw === null || raw === undefined || typeof raw === 'boolean') {
    return null;
  }
  if (typeof raw === 'number') {
    return Number.isSafeInteger(raw) ? raw : null;
  }
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (!/^-?\d+$/.test(trimmed)) {
      return null;
    }
    try {
      const big = BigInt(trimmed);
      if (big < -MAX_SAFE_JS_BIGINT || big > MAX_SAFE_JS_BIGINT) {
        return null;
      }
      const num = Number(trimmed);
      return Number.isSafeInteger(num) && BigInt(num) === big ? num : null;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Ghép dữ liệu từ GET /api/v1/inventory/low-stock và GET /api/v1/analytics/products/top
 * theo product_id để sinh danh sách gợi ý nhập hàng có dẫn chứng (AI-03).
 *
 * Quan trọng (P1):
 * - Nếu sản phẩm xuất hiện trong topProductItems (hoặc lowItem có sold_units hợp lệ) ->
 *   sales_status = 'VERIFIED', sold_units = số nguyên >= 0.
 * - Nếu sản phẩm KHÔNG nằm trong topProductItems ->
 *   sales_status = 'UNKNOWN', sold_units = null (tuyệt đối không giả định sold_units = 0).
 *
 * @param {Array<Object>} lowStockItems
 * @param {Array<Object>|null} topProductItems
 * @returns {Array<{
 *   product_id: number,
 *   sku: string,
 *   name: string,
 *   quantity: number,
 *   threshold: number,
 *   sold_units: number | null,
 *   sales_status: 'VERIFIED' | 'UNKNOWN',
 *   suggested_quantity: number,
 *   unit_cost_vnd: number,
 *   reason: string
 * }>}
 */
export function buildReorderSuggestions(lowStockItems = [], topProductItems = []) {
  const safeLowStock = Array.isArray(lowStockItems) ? lowStockItems : [];
  const hasTopArray = Array.isArray(topProductItems);
  const safeTopProducts = hasTopArray ? topProductItems : [];

  const topByProductId = new Map();
  for (const item of safeTopProducts) {
    const pid = parseStrictInteger(item?.product_id);
    if (pid !== null && pid > 0 && !topByProductId.has(pid)) {
      topByProductId.set(pid, item);
    }
  }

  const results = [];
  const seenIds = new Set();

  for (const lowItem of safeLowStock) {
    const productId = parseStrictInteger(lowItem?.product_id ?? lowItem?.id);
    if (productId === null || productId <= 0 || seenIds.has(productId)) {
      continue;
    }

    const parsedQty = parseStrictInteger(lowItem?.quantity);
    if (parsedQty === null || parsedQty < 0 || parsedQty > MAX_SQL_INT) {
      continue;
    }
    const quantity = parsedQty;

    seenIds.add(productId);

    const topMatch = topByProductId.get(productId);
    const rawSku = typeof lowItem?.sku === 'string' && lowItem.sku.trim()
      ? lowItem.sku.trim()
      : typeof topMatch?.sku === 'string' && topMatch.sku.trim()
      ? topMatch.sku.trim()
      : `SP-${productId}`;
    const rawName = typeof lowItem?.name === 'string' && lowItem.name.trim()
      ? lowItem.name.trim()
      : typeof topMatch?.name === 'string' && topMatch.name.trim()
      ? topMatch.name.trim()
      : `Sản phẩm #${productId}`;

    const parsedThreshold = parseStrictInteger(lowItem?.threshold);
    const threshold =
      parsedThreshold !== null && parsedThreshold > 0 && parsedThreshold <= MAX_SQL_INT
        ? parsedThreshold
        : DEFAULT_LOW_STOCK_THRESHOLD;

    const matchedSold =
      topMatch !== undefined
        ? parseStrictInteger(topMatch?.sold_units)
        : parseStrictInteger(lowItem?.sold_units);

    const hasVerifiedSales = matchedSold !== null && matchedSold >= 0;
    const soldUnits = hasVerifiedSales ? matchedSold : null;
    const salesStatus = hasVerifiedSales ? 'VERIFIED' : 'UNKNOWN';

    const stockDeficitTarget = Math.max(1, threshold * 2 - quantity, 5);
    const suggestedQuantity = hasVerifiedSales
      ? Math.min(MAX_SQL_INT, Math.max(stockDeficitTarget, Math.ceil(soldUnits / 2)))
      : Math.min(MAX_SQL_INT, stockDeficitTarget);

    const stockLabel =
      quantity === 0
        ? `Hết hàng (0/${threshold})`
        : `Tồn thấp (${quantity}/${threshold})`;

    let reason;
    if (hasVerifiedSales) {
      reason =
        soldUnits > 0
          ? `${stockLabel} · Bán ${soldUnits} SP/30 ngày`
          : `${stockLabel} · Đã xác minh bán 0 SP/30 ngày`;
    } else {
      reason = `${stockLabel} · Chưa có dữ liệu bán hàng đầy đủ`;
    }

    results.push({
      product_id: productId,
      sku: rawSku,
      name: rawName,
      quantity,
      threshold,
      sold_units: soldUnits,
      sales_status: salesStatus,
      suggested_quantity: suggestedQuantity,
      unit_cost_vnd: 0,
      reason,
    });
  }

  return results;
}

/**
 * Kiểm tra danh sách dòng sản phẩm được chọn cho cả hai luồng:
 * 1) Tạo phiếu nhập DRAFT trực tiếp (buildDraftReceiptPayload)
 * 2) Mở form tạo phiếu nhập có điền sẵn (buildPrefillDraftState)
 *
 * Tuyệt đối không âm thầm ép giá trị sai về 1 hoặc 0; không cho phép trùng product_id.
 */
export function validateSelectedReorderLines({ rows = [], selectedIds = [] } = {}) {
  const safeRows = Array.isArray(rows) ? rows : [];
  const rawSelected =
    selectedIds instanceof Set
      ? Array.from(selectedIds)
      : Array.isArray(selectedIds)
      ? selectedIds
      : [];

  if (rawSelected.length === 0) {
    return {
      items: null,
      richItems: null,
      error: 'Vui lòng chọn ít nhất 1 sản phẩm gợi ý để tạo phiếu nhập nháp.',
    };
  }

  const selectedSet = new Set();
  for (const rawId of rawSelected) {
    const pid = parseStrictInteger(rawId);
    if (pid === null || pid <= 0) {
      return {
        items: null,
        richItems: null,
        error: 'Mã sản phẩm trong danh sách gợi ý không hợp lệ.',
      };
    }
    selectedSet.add(pid);
  }

  const chosenRows = safeRows.filter((row) => {
    const pid = parseStrictInteger(row?.product_id);
    return pid !== null && selectedSet.has(pid);
  });

  if (chosenRows.length === 0) {
    return {
      items: null,
      richItems: null,
      error: 'Vui lòng chọn ít nhất 1 sản phẩm gợi ý để tạo phiếu nhập nháp.',
    };
  }

  const seenProductIds = new Set();
  const items = [];
  const richItems = [];
  let receiptTotalBigInt = 0n;

  for (const row of chosenRows) {
    const productId = parseStrictInteger(row?.product_id);
    if (productId === null || productId <= 0) {
      return {
        items: null,
        richItems: null,
        error: 'Mã sản phẩm trong danh sách gợi ý không hợp lệ.',
      };
    }

    if (seenProductIds.has(productId)) {
      return {
        items: null,
        richItems: null,
        error: `Sản phẩm ${row?.sku || `#${productId}`} bị trùng lặp trong danh sách chọn.`,
      };
    }
    seenProductIds.add(productId);

    const rawOrderQty =
      row?.order_quantity !== undefined
        ? row.order_quantity
        : row?.suggested_quantity !== undefined
        ? row.suggested_quantity
        : row?.quantity;

    const orderQty = parseStrictInteger(rawOrderQty);
    if (orderQty === null || orderQty < 1 || orderQty > MAX_SQL_INT) {
      return {
        items: null,
        richItems: null,
        error: `Số lượng nhập của sản phẩm ${row?.sku || `#${productId}`} phải là số nguyên từ 1 đến ${MAX_SQL_INT.toLocaleString('vi-VN')}.`,
      };
    }

    const rawUnitCost =
      row?.unit_cost_vnd !== undefined ? row.unit_cost_vnd : 0;
    const unitCostVnd = parseStrictInteger(rawUnitCost);

    if (unitCostVnd === null || unitCostVnd < 0) {
      return {
        items: null,
        richItems: null,
        error: `Đơn giá nhập của sản phẩm ${row?.sku || `#${productId}`} phải là số nguyên không âm (>= 0 VND).`,
      };
    }

    const lineTotalBigInt = BigInt(orderQty) * BigInt(unitCostVnd);
    if (lineTotalBigInt > MAX_SQL_BIGINT) {
      return {
        items: null,
        richItems: null,
        error: `Thành tiền của sản phẩm ${row?.sku || `#${productId}`} vượt quá giới hạn cho phép.`,
      };
    }

    receiptTotalBigInt += lineTotalBigInt;
    if (receiptTotalBigInt > MAX_SQL_BIGINT) {
      return {
        items: null,
        richItems: null,
        error: 'Tổng tiền phiếu nhập vượt quá giới hạn BIGINT cho phép.',
      };
    }

    items.push({
      product_id: productId,
      quantity: orderQty,
      unit_cost_vnd: unitCostVnd,
    });

    richItems.push({
      product_id: productId,
      sku: typeof row?.sku === 'string' && row.sku.trim() ? row.sku.trim() : `SP-${productId}`,
      name: typeof row?.name === 'string' && row.name.trim() ? row.name.trim() : `Sản phẩm #${productId}`,
      quantity: orderQty,
      unit_cost_vnd: unitCostVnd,
    });
  }

  return {
    items,
    richItems,
    error: null,
  };
}

/**
 * Kiểm tra và tạo payload chuẩn cho POST /api/v1/purchase-receipts (trạng thái DRAFT).
 */
export function buildDraftReceiptPayload({ supplierId, rows = [], selectedIds = [] } = {}) {
  const parsedSupplierId = parseStrictInteger(supplierId);
  if (parsedSupplierId === null || parsedSupplierId <= 0) {
    return {
      payload: null,
      error: 'Vui lòng chọn nhà cung cấp hợp lệ trước khi tạo phiếu nhập nháp.',
    };
  }

  const lineCheck = validateSelectedReorderLines({ rows, selectedIds });
  if (lineCheck.error || !lineCheck.items) {
    return {
      payload: null,
      error: lineCheck.error,
    };
  }

  return {
    payload: {
      supplier_id: parsedSupplierId,
      items: lineCheck.items,
    },
    error: null,
  };
}

/**
 * Kiểm tra và tạo state prefillDraft cho luồng "Mở form tạo phiếu" sang /purchases.
 * Dùng chung bộ kiểm tra dòng sản phẩm với buildDraftReceiptPayload (không tự ép giá trị lỗi về 1 hoặc 0).
 */
export function buildPrefillDraftState({ supplierId = '', rows = [], selectedIds = [] } = {}) {
  let normalizedSupplierId = '';
  if (supplierId !== '' && supplierId !== null && supplierId !== undefined) {
    const parsedSupplierId = parseStrictInteger(supplierId);
    if (parsedSupplierId === null || parsedSupplierId <= 0) {
      return {
        prefillDraft: null,
        error: 'Nhà cung cấp đã chọn không hợp lệ.',
      };
    }
    normalizedSupplierId = parsedSupplierId;
  }

  const lineCheck = validateSelectedReorderLines({ rows, selectedIds });
  if (lineCheck.error || !lineCheck.richItems) {
    return {
      prefillDraft: null,
      error: lineCheck.error,
    };
  }

  return {
    prefillDraft: {
      supplier_id: normalizedSupplierId,
      items: lineCheck.richItems,
    },
    error: null,
  };
}
