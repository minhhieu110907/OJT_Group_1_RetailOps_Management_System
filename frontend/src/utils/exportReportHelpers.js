import { parseReceiptSearchInput } from '../api/receiptsApi.js';

export const MAX_EXPORT_ROWS = 1000;
const EXPORT_PAGE_SIZE = 100;

/**
 * Collect all filtered purchase receipts across pages (up to maxRows)
 * without N+1 calls, preserving filter parameters and deduplicating by id.
 */
export async function collectPurchaseReceiptsForExport({
  topTab,
  activeTab,
  supplierFilter = '',
  debouncedSearchQuery = '',
  fromDateFilter = '',
  toDateFilter = '',
  receiptsApi,
  maxRows = MAX_EXPORT_ROWS,
}) {
  const resolvedSupplierId = supplierFilter ? Number(supplierFilter) : null;
  const parsedSearch = parseReceiptSearchInput(debouncedSearchQuery);

  if (parsedSearch.mode === 'UNSUPPORTED_QUERY' || parsedSearch.mode === 'INVALID_ID') {
    return {
      items: [],
      total: 0,
      effectiveTotal: 0,
      exportedCount: 0,
      totalAvailable: 0,
      isHistoryWindowCapped: false,
      unexportedByHistoryWindow: 0,
      unexportedByExportCap: 0,
      isTruncated: false,
      remainingCount: 0,
      validationError: parsedSearch.error || '',
    };
  }

  if (parsedSearch.mode === 'EXACT_ID') {
    const exactRes = await receiptsApi.findByExactId(parsedSearch.receiptId, {
      pageSize: EXPORT_PAGE_SIZE,
      topTab,
      activeTab,
      supplierId: resolvedSupplierId,
      fromDate: fromDateFilter,
      toDate: toDateFilter,
    });
    const items = Array.isArray(exactRes?.items) ? exactRes.items : [];
    const total = Number(exactRes?.total) || items.length;
    return {
      items,
      total,
      effectiveTotal: total,
      exportedCount: items.length,
      totalAvailable: total,
      isHistoryWindowCapped: false,
      unexportedByHistoryWindow: 0,
      unexportedByExportCap: Math.max(0, total - items.length),
      isTruncated: false,
      remainingCount: 0,
      validationError: '',
    };
  }

  const seenIds = new Set();
  const collected = [];
  let currentPage = 1;
  let total = 0;
  let effectiveTotal = 0;
  let isHistoryWindowCapped = false;

  const isAllHistory = topTab === 'HISTORY' && activeTab === 'ALL_HISTORY';
  const statusParam =
    activeTab === 'DRAFT' || activeTab === 'CONFIRMED' || activeTab === 'CANCELLED'
      ? activeTab
      : '';

  while (collected.length < maxRows) {
    const res = isAllHistory
      ? await receiptsApi.listHistory({
          page: currentPage,
          pageSize: EXPORT_PAGE_SIZE,
          supplierId: resolvedSupplierId,
          fromDate: fromDateFilter,
          toDate: toDateFilter,
        })
      : await receiptsApi.list({
          page: currentPage,
          pageSize: EXPORT_PAGE_SIZE,
          status: statusParam,
          supplierId: resolvedSupplierId,
          fromDate: fromDateFilter,
          toDate: toDateFilter,
        });

    const pageItems = Array.isArray(res?.items) ? res.items : [];
    total = Number(res?.total ?? 0);
    effectiveTotal = isAllHistory
      ? Number(res?.effective_total ?? total)
      : total;
    if (res?.is_window_capped || (isAllHistory && total > effectiveTotal)) {
      isHistoryWindowCapped = true;
    }

    for (const item of pageItems) {
      if (!item || seenIds.has(item.id)) continue;
      seenIds.add(item.id);
      collected.push(item);
      if (collected.length >= maxRows) break;
    }

    const totalPages = Number(res?.total_pages) || 1;
    if (
      pageItems.length === 0 ||
      currentPage >= totalPages ||
      collected.length >= effectiveTotal ||
      collected.length >= maxRows
    ) {
      break;
    }
    currentPage += 1;
  }

  const exportedCount = collected.length;
  const unexportedByHistoryWindow = isAllHistory
    ? Math.max(0, total - effectiveTotal)
    : 0;
  const unexportedByExportCap = Math.max(0, effectiveTotal - exportedCount);
  const remainingCount = Math.max(0, total - exportedCount);

  return {
    items: collected,
    total,
    effectiveTotal,
    exportedCount,
    totalAvailable: total,
    isHistoryWindowCapped,
    unexportedByHistoryWindow,
    unexportedByExportCap,
    isTruncated: remainingCount > 0 || isHistoryWindowCapped,
    remainingCount,
    validationError: '',
  };
}

/**
 * Format accurate user-facing export result toast distinguishing
 * ALL_HISTORY window truncation (500) from export row cap (1000).
 */
export function formatPurchaseExportMessage(exportResult, maxRows = MAX_EXPORT_ROWS) {
  const {
    total = 0,
    effectiveTotal = 0,
    exportedCount = 0,
    isHistoryWindowCapped = false,
    unexportedByHistoryWindow = 0,
    unexportedByExportCap = 0,
    isTruncated = false,
  } = exportResult || {};

  if (!isTruncated) {
    return {
      severity: 'success',
      message: `Xuất Excel thành công (${exportedCount} phiếu nhập)!`,
    };
  }

  if (unexportedByHistoryWindow > 0 && unexportedByExportCap > 0) {
    return {
      severity: 'warning',
      message: `Đã xuất ${exportedCount}/${total} phiếu nhập (${unexportedByHistoryWindow} phiếu nằm ngoài cửa sổ lịch sử ${effectiveTotal} phiếu gần nhất và ${unexportedByExportCap} phiếu vượt giới hạn xuất ${maxRows} bản ghi).`,
    };
  }

  if (unexportedByHistoryWindow > 0 || isHistoryWindowCapped) {
    return {
      severity: 'warning',
      message: `Đã xuất ${exportedCount}/${total} phiếu nhập (chỉ truy xuất tối đa ${effectiveTotal} phiếu gần nhất trong cửa sổ lịch sử; còn ${unexportedByHistoryWindow} phiếu ngoài cửa sổ chưa thể xuất).`,
    };
  }

  return {
    severity: 'warning',
    message: `Đã xuất ${exportedCount}/${total} phiếu nhập (còn ${unexportedByExportCap} phiếu chưa xuất do giới hạn xuất ${maxRows} bản ghi).`,
  };
}

/**
 * Build 2D worksheet rows for Purchase Receipts using canonical supplier_name_snapshot.
 */
export function buildPurchaseReceiptExportRows(receipts, formatDateFn) {
  const headers = [
    'Mã phiếu nhập',
    'Nhà cung cấp',
    'Số mặt hàng',
    'Thời gian tạo',
    'Tổng tiền (VNĐ)',
    'Trạng thái',
  ];

  const rows = (Array.isArray(receipts) ? receipts : []).map((row) => {
    const count = Array.isArray(row.items) ? row.items.length : 0;
    const statusText =
      row.status === 'CONFIRMED'
        ? 'Đã nhập'
        : row.status === 'CANCELLED'
        ? 'Đã hủy'
        : `Bản nháp (${row.draft_version ?? 1})`;
    const supplierLabel =
      row.supplier_name_snapshot ||
      (row.supplier_id ? `NCC #${row.supplier_id}` : '—');
    return [
      `#PN-${row.id}`,
      supplierLabel,
      count,
      formatDateFn(row.created_at),
      Number(row.total_vnd) || 0,
      statusText,
    ];
  });

  return [headers, ...rows];
}

/**
 * Collect stock movements across pages (up to maxRows) and batch-resolve product names
 * via inventoryApi.getInventory without N+1 requests.
 */
export async function collectStockMovementsForExport({
  selectedKind = '',
  inventoryApi,
  existingProductMap = new Map(),
  maxRows = MAX_EXPORT_ROWS,
}) {
  const seenIds = new Set();
  const collected = [];
  let currentPage = 1;
  let totalAvailable = 0;

  while (collected.length < maxRows) {
    const res = await inventoryApi.getStockMovements({
      page: currentPage,
      pageSize: EXPORT_PAGE_SIZE,
      kind: selectedKind || null,
    });
    const pageItems = Array.isArray(res?.items) ? res.items : [];
    totalAvailable = Number(res?.total) || 0;

    for (const item of pageItems) {
      if (!item || seenIds.has(item.id)) continue;
      seenIds.add(item.id);
      collected.push(item);
      if (collected.length >= maxRows) break;
    }

    if (
      pageItems.length < EXPORT_PAGE_SIZE ||
      collected.length >= totalAvailable ||
      collected.length >= maxRows
    ) {
      break;
    }
    currentPage += 1;
  }

  const resolvedProductMap = new Map(existingProductMap);
  if (collected.length > 0 && typeof inventoryApi.getInventory === 'function') {
    const neededIds = new Set(
      collected.map((m) => m.product_id).filter((pid) => pid && !resolvedProductMap.has(pid))
    );
    if (neededIds.size > 0) {
      try {
        let invPage = 1;
        const maxInvPages = 10;
        while (invPage <= maxInvPages && neededIds.size > 0) {
          const invRes = await inventoryApi.getInventory({
            page: invPage,
            pageSize: EXPORT_PAGE_SIZE,
          });
          const invItems = Array.isArray(invRes?.items) ? invRes.items : [];
          for (const inv of invItems) {
            if (inv?.product_id && inv?.name) {
              resolvedProductMap.set(inv.product_id, inv.name);
              neededIds.delete(inv.product_id);
            }
          }
          const invTotal = Number(invRes?.total) || 0;
          if (invItems.length < EXPORT_PAGE_SIZE || invPage * EXPORT_PAGE_SIZE >= invTotal) {
            break;
          }
          invPage += 1;
        }
      } catch {
        // Fallback to Product ID label if batch inventory lookup fails
      }
    }
  }

  const remainingCount = Math.max(0, totalAvailable - collected.length);
  return {
    items: collected,
    totalAvailable,
    isTruncated: remainingCount > 0,
    remainingCount,
    productMap: resolvedProductMap,
  };
}

/**
 * Build 2D worksheet rows for Stock Movements while enforcing ADMIN-only columns.
 */
export function buildStockMovementExportRows(
  movements,
  {
    isAdmin,
    productMap,
    formatDateTimeFn,
    formatReferenceCodeFn,
    movementKindLabels,
  }
) {
  const headers = [
    'Mã SKU',
    'Tên sản phẩm',
    'Loại biến động',
    'Số lượng thay đổi',
    'Thời điểm ghi nhận',
    'Mã chứng từ tham chiếu',
    ...(isAdmin ? ['Người thực hiện', 'Lý do điều chỉnh'] : []),
  ];

  const rows = (Array.isArray(movements) ? movements : []).map((row) => {
    const delta = (Number(row.quantity_after) || 0) - (Number(row.quantity_before) || 0);
    const sign = delta < 0 ? '' : '+';
    const kindLabel =
      (movementKindLabels?.[row.kind] && movementKindLabels[row.kind].label) ||
      row.kind ||
      '—';
    const productName =
      productMap?.get(row.product_id) || `Sản phẩm #${row.product_id}`;
    const refCode = formatReferenceCodeFn(row.kind, row.reference_id);
    return [
      row.sku || '',
      productName,
      kindLabel,
      `${sign}${delta}`,
      formatDateTimeFn(row.occurred_at),
      refCode,
      ...(isAdmin
        ? [
            row.actor_id ? `User ${row.actor_id}` : 'Hệ thống',
            row.kind === 'ADJUSTMENT' && row.adjustment_reason
              ? row.adjustment_reason
              : '—',
          ]
        : []),
    ];
  });

  return [headers, ...rows];
}
