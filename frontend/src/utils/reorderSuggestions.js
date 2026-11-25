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
 * Ghép dữ liệu từ GET /api/v1/inventory/low-stock, GET /api/v1/analytics/products/top
 * và GET /api/v1/analytics/products/slow theo product_id để sinh danh sách gợi ý
 * nhập hàng có dẫn chứng (AI-03).
 *
 * Quan trọng (P1):
 * - Nếu sản phẩm xuất hiện trong topProductItems (hoặc lowItem có sold_units hợp lệ) ->
 *   sales_status = 'VERIFIED', sold_units = số nguyên >= 0.
 * - Nếu sản phẩm KHÔNG nằm trong topProductItems ->
 *   sales_status = 'UNKNOWN', sold_units = null (tuyệt đối không giả định sold_units = 0).
 * - Nếu sản phẩm xuất hiện trong slowProductItems ->
 *   is_slow_moving = true, classification = 'SLOW_MOVING_HOLD' để cảnh báo Admin cân nhắc giữ.
 *
 * @param {Array<Object>} lowStockItems
 * @param {Array<Object>|null} topProductItems
 * @param {Array<Object>|null} [slowProductItems]
 * @returns {Array<{
 *   product_id: number,
 *   sku: string,
 *   name: string,
 *   quantity: number,
 *   threshold: number,
 *   sold_units: number | null,
 *   sales_status: 'VERIFIED' | 'UNKNOWN',
 *   is_slow_moving: boolean,
 *   classification: 'PRIORITY_RESTOCK' | 'SLOW_MOVING_HOLD' | 'CHECK_DEMAND',
 *   suggested_quantity: number,
 *   unit_cost_vnd: number,
 *   reason: string
 * }>}
 */
export function buildReorderSuggestions(
  lowStockItems = [],
  topProductItems = [],
  slowProductItems = []
) {
  const safeLowStock = Array.isArray(lowStockItems) ? lowStockItems : [];
  const hasTopArray = Array.isArray(topProductItems);
  const safeTopProducts = hasTopArray ? topProductItems : [];
  const safeSlowProducts = Array.isArray(slowProductItems) ? slowProductItems : [];

  const topByProductId = new Map();
  for (const item of safeTopProducts) {
    const pid = parseStrictInteger(item?.product_id);
    if (pid !== null && pid > 0 && !topByProductId.has(pid)) {
      topByProductId.set(pid, item);
    }
  }

  const slowByProductId = new Map();
  for (const item of safeSlowProducts) {
    const pid = parseStrictInteger(item?.product_id);
    if (pid !== null && pid > 0 && !slowByProductId.has(pid)) {
      slowByProductId.set(pid, item);
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
    const slowMatch = slowByProductId.get(productId);
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
        : slowMatch !== undefined
        ? parseStrictInteger(slowMatch?.sold_units)
        : parseStrictInteger(lowItem?.sold_units);

    const hasVerifiedSales = matchedSold !== null && matchedSold >= 0;
    const soldUnits = hasVerifiedSales ? matchedSold : null;
    const salesStatus = hasVerifiedSales ? 'VERIFIED' : 'UNKNOWN';

    const isSlowMoving = slowMatch !== undefined && (soldUnits === null || soldUnits <= 2);
    const classification = isSlowMoving
      ? 'SLOW_MOVING_HOLD'
      : hasVerifiedSales && soldUnits > 0
      ? 'PRIORITY_RESTOCK'
      : 'CHECK_DEMAND';

    const stockDeficitTarget = Math.max(1, threshold * 2 - quantity, 5);
    const suggestedQuantity = hasVerifiedSales
      ? Math.min(MAX_SQL_INT, Math.max(stockDeficitTarget, Math.ceil(soldUnits / 2)))
      : Math.min(MAX_SQL_INT, stockDeficitTarget);

    const stockLabel =
      quantity === 0
        ? `Hết hàng (0/${threshold})`
        : `Tồn thấp (${quantity}/${threshold})`;

    let reason;
    if (isSlowMoving) {
      const slowCountLabel = soldUnits !== null ? `${soldUnits} SP/30 ngày` : '<= 2 SP/30 ngày';
      reason = `${stockLabel} · Bán chậm (${slowCountLabel}) — Cân nhắc trước khi nhập thêm`;
    } else if (hasVerifiedSales) {
      reason =
        soldUnits > 0
          ? `${stockLabel} · Bán ${soldUnits} SP/30 ngày`
          : `${stockLabel} · Đã xác minh bán 0 SP/30 ngày`;
    } else {
      reason = `${stockLabel} · Chưa có dữ liệu bán hàng đầy đủ`;
    }

    const categoryId = parseStrictInteger(lowItem?.category_id);

    results.push({
      product_id: productId,
      ...(categoryId !== null && categoryId > 0 ? { category_id: categoryId } : {}),
      sku: rawSku,
      name: rawName,
      quantity,
      threshold,
      sold_units: soldUnits,
      sales_status: salesStatus,
      is_slow_moving: isSlowMoving,
      classification,
      suggested_quantity: suggestedQuantity,
      unit_cost_vnd: 0,
      reason,
    });
  }

  return results;
}

/**
 * Lấy đơn giá nhập gần nhất của từng sản phẩm từ các phiếu CONFIRMED
 * (danh sách đã sắp xếp mới nhất trước). Chỉ nhận số nguyên >= 0 hợp lệ.
 */
export function buildLastCostMap(receipts = []) {
  const map = new Map();
  for (const receipt of Array.isArray(receipts) ? receipts : []) {
    if (receipt?.status !== 'CONFIRMED') continue;
    for (const item of Array.isArray(receipt?.items) ? receipt.items : []) {
      const pid = parseStrictInteger(item?.product_id);
      const cost = parseStrictInteger(item?.unit_cost_vnd);
      if (pid !== null && pid > 0 && cost !== null && cost > 0 && !map.has(pid)) {
        map.set(pid, cost);
      }
    }
  }
  return map;
}

/** Điền sẵn đơn giá dự kiến và NCC gần nhất từ lịch sử phiếu CONFIRMED; không ghi đè giá Admin đã sửa. */
export function buildLastSupplierMap(receipts = []) {
  const map = new Map();
  for (const receipt of Array.isArray(receipts) ? receipts : []) {
    if (receipt?.status !== 'CONFIRMED') continue;
    const supId = parseStrictInteger(receipt?.supplier_id);
    const supName =
      typeof receipt?.supplier_name_snapshot === 'string' &&
      receipt.supplier_name_snapshot.trim()
        ? receipt.supplier_name_snapshot.trim()
        : null;
    if (supId === null || supId <= 0) continue;
    for (const item of Array.isArray(receipt?.items) ? receipt.items : []) {
      const pid = parseStrictInteger(item?.product_id);
      if (pid !== null && pid > 0 && !map.has(pid)) {
        map.set(pid, { supplier_id: supId, supplier_name: supName });
      }
    }
  }
  return map;
}

export function applyLastUnitCosts(rows = [], costMap = new Map(), supplierMap = new Map()) {
  return (Array.isArray(rows) ? rows : []).map((row) => {
    const lastCost = costMap.get(row.product_id);
    const lastSup = supplierMap instanceof Map ? supplierMap.get(row.product_id) : undefined;
    const next = { ...row };
    if (lastCost !== undefined && parseStrictInteger(row.unit_cost_vnd) === 0) {
      next.unit_cost_vnd = lastCost;
      next.cost_source = 'LAST_RECEIPT';
    }
    if (lastSup) {
      next.last_supplier_id = lastSup.supplier_id;
      next.last_supplier_name = lastSup.supplier_name;
    }
    return next;
  });
}

/**
 * Tìm danh sách product_id phù hợp với nhà cung cấp đang chọn
 * (dựa trên danh mục category_ids của NCC hoặc lịch sử lần nhập gần nhất).
 */
export function getMatchingProductIdsForSupplier(rows = [], supplier = null) {
  if (!supplier || typeof supplier !== 'object') return [];
  const supId = parseStrictInteger(supplier.id);
  const catSet = new Set(
    Array.isArray(supplier.category_ids)
      ? supplier.category_ids.map((c) => parseStrictInteger(c)).filter((c) => c !== null && c > 0)
      : []
  );
  const matched = [];
  for (const row of Array.isArray(rows) ? rows : []) {
    const pid = parseStrictInteger(row?.product_id);
    if (pid === null || pid <= 0) continue;
    const rowCat = parseStrictInteger(row?.category_id);
    const matchesCategory = rowCat !== null && catSet.has(rowCat);
    const matchesHistory = supId !== null && row?.last_supplier_id === supId;
    if (matchesCategory || matchesHistory) {
      matched.push(pid);
    }
  }
  return matched;
}

/**
 * Lọc danh sách gợi ý nhập hàng theo danh mục của Nhà cung cấp đang chọn
 * (hoặc lịch sử nhập gần nhất), luôn giữ lại các sản phẩm đã tick chọn.
 */
export function filterReorderRowsBySupplier(
  rows = [],
  { supplier = null, selectedIds = [], showAll = false } = {}
) {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (showAll || !supplier || typeof supplier !== 'object') {
    return safeRows;
  }
  const hasLinkedCategories =
    Array.isArray(supplier.category_ids) && supplier.category_ids.length > 0;
  if (!hasLinkedCategories) {
    return safeRows;
  }
  const matchedSet = new Set(getMatchingProductIdsForSupplier(safeRows, supplier));
  const selectedSet = new Set(
    (Array.isArray(selectedIds) ? selectedIds : [])
      .map((id) => parseStrictInteger(id))
      .filter((id) => id !== null && id > 0)
  );
  return safeRows.filter((row) => {
    const pid = parseStrictInteger(row?.product_id);
    return pid !== null && (matchedSet.has(pid) || selectedSet.has(pid));
  });
}

/** Phân trang danh sách gợi ý nhập hàng ở phía client một cách an toàn. */
export function paginateReorderRows(rows = [], { page = 1, pageSize = 10 } = {}) {
  const safe = Array.isArray(rows) ? rows : [];
  const size = Math.max(1, parseStrictInteger(pageSize) || 10);
  const totalItems = safe.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / size));
  const currentPage = Math.min(Math.max(1, parseStrictInteger(page) || 1), totalPages);
  const start = (currentPage - 1) * size;
  return {
    items: safe.slice(start, start + size),
    page: currentPage,
    pageSize: size,
    totalItems,
    totalPages,
  };
}

export const REORDER_CLASSIFICATION_FILTERS = [
  { key: 'ALL', label: 'Tất cả' },
  { key: 'PRIORITY_RESTOCK', label: 'Ưu tiên nhập' },
  { key: 'CHECK_DEMAND', label: 'Cần kiểm tra nhu cầu' },
  { key: 'SLOW_MOVING_HOLD', label: 'Bán chậm' },
];

const CLASSIFICATION_RANK = {
  PRIORITY_RESTOCK: 0,
  CHECK_DEMAND: 1,
  SLOW_MOVING_HOLD: 2,
};

/** Lọc theo phân loại và sắp xếp (ổn định) cho bảng gợi ý. */
export function filterAndSortReorderRows(rows = [], { filter = 'ALL', sort = 'PRIORITY' } = {}) {
  const safe = Array.isArray(rows) ? rows : [];
  const filtered =
    filter === 'ALL' ? safe : safe.filter((row) => row.classification === filter);
  const indexed = filtered.map((row, index) => ({ row, index }));
  indexed.sort((a, b) => {
    let diff = 0;
    if (sort === 'STOCK_ASC') {
      diff = a.row.quantity - b.row.quantity;
    } else if (sort === 'SOLD_DESC') {
      diff = (b.row.sold_units ?? -1) - (a.row.sold_units ?? -1);
    } else {
      diff =
        (CLASSIFICATION_RANK[a.row.classification] ?? 9) -
        (CLASSIFICATION_RANK[b.row.classification] ?? 9);
    }
    return diff !== 0 ? diff : a.index - b.index;
  });
  return indexed.map((entry) => entry.row);
}

/**
 * Sinh thông điệp hướng dẫn trạng thái nút "Tạo phiếu nháp" & "Mở form tạo phiếu"
 * để Admin biết rõ điều kiện mở khóa nút (chọn sản phẩm + chọn nhà cung cấp).
 */
export function getDraftActionGuidance({
  selectedCount = 0,
  supplierId = '',
  suppliersCount = 0,
  suppliersFailed = false,
  isCreatingDraft = false,
  zeroCostSelectedCount = 0,
} = {}) {
  const hasSelection = Number(selectedCount) > 0;
  const hasSupplier = supplierId !== '' && supplierId !== null && supplierId !== undefined;

  if (isCreatingDraft) {
    return {
      tone: 'info',
      message: 'Đang tạo phiếu nhập nháp (DRAFT)...',
      createDraftTooltip: 'Đang gửi yêu cầu tạo phiếu nhập nháp...',
      openFormTooltip: 'Đang xử lý yêu cầu tạo phiếu nhập nháp...',
    };
  }

  if (!suppliersFailed && Number(suppliersCount) === 0) {
    return {
      tone: 'warning',
      message:
        'Chưa có Nhà cung cấp nào đang hoạt động (ACTIVE) để tạo phiếu nháp trực tiếp. Vui lòng tạo/kích hoạt nhà cung cấp tại mục Nhà cung cấp hoặc bấm "Mở form tạo phiếu".',
      createDraftTooltip: 'Cần có ít nhất 1 Nhà cung cấp đang hoạt động (ACTIVE).',
      openFormTooltip: hasSelection
        ? 'Mở form tạo phiếu nhập với các sản phẩm đã chọn.'
        : 'Vui lòng tick chọn ít nhất 1 sản phẩm trong bảng.',
    };
  }

  if (!hasSelection && !hasSupplier) {
    return {
      tone: 'info',
      message:
        'Để tạo phiếu nháp: (1) Tick chọn ít nhất 1 sản phẩm trong bảng và (2) Chọn Nhà cung cấp dự kiến ở trên.',
      createDraftTooltip: 'Vui lòng tick chọn ít nhất 1 sản phẩm và chọn Nhà cung cấp dự kiến.',
      openFormTooltip: 'Vui lòng tick chọn ít nhất 1 sản phẩm trong bảng.',
    };
  }

  if (!hasSelection && hasSupplier) {
    return {
      tone: 'info',
      message:
        'Đã chọn Nhà cung cấp — vui lòng tick chọn ít nhất 1 sản phẩm trong bảng để mở khóa nút Tạo phiếu nháp.',
      createDraftTooltip: 'Vui lòng tick chọn ít nhất 1 sản phẩm trong bảng.',
      openFormTooltip: 'Vui lòng tick chọn ít nhất 1 sản phẩm trong bảng.',
    };
  }

  if (hasSelection && !hasSupplier) {
    return {
      tone: 'info',
      message: `Đã chọn ${selectedCount} sản phẩm — vui lòng chọn Nhà cung cấp dự kiến để mở khóa nút "Tạo phiếu nháp" (hoặc bấm "Mở form tạo phiếu").`,
      createDraftTooltip: 'Vui lòng chọn Nhà cung cấp dự kiến trước khi tạo phiếu nháp.',
      openFormTooltip: 'Mở form tạo phiếu nhập với các sản phẩm đã chọn.',
    };
  }

  const zeroCostNote =
    Number(zeroCostSelectedCount) > 0
      ? ` Lưu ý: ${zeroCostSelectedCount} sản phẩm đang để đơn giá dự kiến = 0 VND (có thể cập nhật lại trước khi xác nhận phiếu).`
      : '';

  return {
    tone: Number(zeroCostSelectedCount) > 0 ? 'warning' : 'ready',
    message: `Sẵn sàng tạo phiếu nhập nháp (DRAFT) cho ${selectedCount} sản phẩm đã chọn.${zeroCostNote}`,
    createDraftTooltip: `Tạo phiếu nhập nháp (DRAFT) cho ${selectedCount} sản phẩm đã chọn.`,
    openFormTooltip: 'Mở form tạo phiếu nhập với các sản phẩm và nhà cung cấp đã chọn.',
  };
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
