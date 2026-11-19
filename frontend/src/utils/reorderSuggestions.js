import { DEFAULT_LOW_STOCK_THRESHOLD } from '../api/inventoryApi.js';

/**
 * Ghép dữ liệu từ GET /api/v1/inventory/low-stock và GET /api/v1/analytics/products/top
 * theo product_id để sinh danh sách gợi ý nhập hàng có dẫn chứng (AI-03).
 *
 * @param {Array<Object>} lowStockItems
 * @param {Array<Object>} topProductItems
 * @returns {Array<{
 *   product_id: number,
 *   sku: string,
 *   name: string,
 *   quantity: number,
 *   threshold: number,
 *   sold_units: number,
 *   suggested_quantity: number,
 *   unit_cost_vnd: number,
 *   reason: string
 * }>}
 */
export function buildReorderSuggestions(lowStockItems = [], topProductItems = []) {
  const safeLowStock = Array.isArray(lowStockItems) ? lowStockItems : [];
  const safeTopProducts = Array.isArray(topProductItems) ? topProductItems : [];

  const topByProductId = new Map();
  for (const item of safeTopProducts) {
    const pid = Number(item?.product_id);
    if (Number.isInteger(pid) && pid > 0) {
      topByProductId.set(pid, item);
    }
  }

  const results = [];
  const seenIds = new Set();

  for (const lowItem of safeLowStock) {
    const productId = Number(lowItem?.product_id ?? lowItem?.id);
    if (!Number.isInteger(productId) || productId <= 0 || seenIds.has(productId)) {
      continue;
    }
    seenIds.add(productId);

    const topMatch = topByProductId.get(productId);
    const sku = String(lowItem?.sku || topMatch?.sku || `SP-${productId}`).trim();
    const name = String(lowItem?.name || topMatch?.name || `Sản phẩm #${productId}`).trim();

    const rawQty = Number(lowItem?.quantity);
    const quantity = Number.isInteger(rawQty) && rawQty >= 0 ? rawQty : 0;

    const rawThreshold = Number(lowItem?.threshold);
    const threshold =
      Number.isInteger(rawThreshold) && rawThreshold > 0
        ? rawThreshold
        : DEFAULT_LOW_STOCK_THRESHOLD;

    const rawSold = Number(topMatch?.sold_units ?? lowItem?.sold_units);
    const soldUnits = Number.isInteger(rawSold) && rawSold >= 0 ? rawSold : 0;

    const suggestedQuantity = Math.max(
      1,
      threshold * 2 - quantity,
      Math.ceil(soldUnits / 2),
      5
    );

    const stockLabel =
      quantity === 0
        ? `Hết hàng (0/${threshold})`
        : `Tồn thấp (${quantity}/${threshold})`;

    const reason =
      soldUnits > 0
        ? `${stockLabel} · Bán ${soldUnits} SP/30 ngày`
        : stockLabel;

    results.push({
      product_id: productId,
      sku,
      name,
      quantity,
      threshold,
      sold_units: soldUnits,
      suggested_quantity: suggestedQuantity,
      unit_cost_vnd: 0,
      reason,
    });
  }

  return results;
}

/**
 * Kiểm tra và tạo payload chuẩn cho POST /api/v1/purchase-receipts (trạng thái DRAFT).
 *
 * @param {Object} params
 * @param {number|string} params.supplierId
 * @param {Array<Object>} params.rows
 * @param {Array<number|string>|Set<number|string>} params.selectedIds
 * @returns {{
 *   payload: { supplier_id: number, items: Array<{ product_id: number, quantity: number, unit_cost_vnd: number }> } | null,
 *   error: string | null
 * }}
 */
export function buildDraftReceiptPayload({ supplierId, rows = [], selectedIds = [] } = {}) {
  const parsedSupplierId = Number(supplierId);
  if (!Number.isInteger(parsedSupplierId) || parsedSupplierId <= 0) {
    return {
      payload: null,
      error: 'Vui lòng chọn nhà cung cấp hợp lệ trước khi tạo phiếu nhập nháp.',
    };
  }

  const safeRows = Array.isArray(rows) ? rows : [];
  const rawSelected =
    selectedIds instanceof Set
      ? Array.from(selectedIds)
      : Array.isArray(selectedIds)
      ? selectedIds
      : [];

  const selectedSet = new Set(
    rawSelected
      .map((id) => Number(id))
      .filter((id) => Number.isInteger(id) && id > 0)
  );

  const chosenRows = safeRows.filter((row) =>
    selectedSet.has(Number(row?.product_id))
  );

  if (chosenRows.length === 0) {
    return {
      payload: null,
      error: 'Vui lòng chọn ít nhất 1 sản phẩm gợi ý để tạo phiếu nhập nháp.',
    };
  }

  const items = [];
  for (const row of chosenRows) {
    const productId = Number(row?.product_id);
    if (!Number.isInteger(productId) || productId <= 0) {
      return {
        payload: null,
        error: 'Mã sản phẩm trong danh sách gợi ý không hợp lệ.',
      };
    }

    const rawOrderQty =
      row?.order_quantity !== undefined
        ? row.order_quantity
        : row?.suggested_quantity !== undefined
        ? row.suggested_quantity
        : row?.quantity;
    const orderQty = Number(rawOrderQty);

    if (!Number.isInteger(orderQty) || orderQty < 1) {
      return {
        payload: null,
        error: `Số lượng nhập của sản phẩm ${row?.sku || `#${productId}`} phải là số nguyên lớn hơn hoặc bằng 1.`,
      };
    }

    const rawUnitCost =
      row?.unit_cost_vnd !== undefined && row?.unit_cost_vnd !== ''
        ? row.unit_cost_vnd
        : 0;
    const unitCostVnd = Number(rawUnitCost);

    if (!Number.isInteger(unitCostVnd) || unitCostVnd < 0) {
      return {
        payload: null,
        error: `Đơn giá nhập của sản phẩm ${row?.sku || `#${productId}`} phải là số nguyên không âm (>= 0 VND).`,
      };
    }

    items.push({
      product_id: productId,
      quantity: orderQty,
      unit_cost_vnd: unitCostVnd,
    });
  }

  return {
    payload: {
      supplier_id: parsedSupplierId,
      items,
    },
    error: null,
  };
}
