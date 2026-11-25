import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { CustomSelect, Modal, Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { productsApi } from '../../api/productsApi';
import {
  MOVEMENT_KIND_LABELS,
  formatReferenceCode,
  formatVietnamDateTime,
  inventoryApi,
} from '../../api/inventoryApi';
import { downloadStyledExcelRows } from '../../utils/csvDownload';
import {
  MAX_EXPORT_ROWS,
  buildStockMovementExportRows,
  collectStockMovementsForExport,
} from '../../utils/exportReportHelpers';
import styles from './StockMovementList.module.css';

export default function StockMovementList() {
  const { user } = useAuth();
  const toast = useToast();

  const isAdmin = user?.role === 'ADMIN';

  // 1. Bộ lọc Server-side (loại biến động)
  const [selectedKind, setSelectedKind] = useState('');

  // 2. State dữ liệu
  const [movements, setMovements] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10 });
  const [isLoading, setIsLoading] = useState(false);
  const [isExportingExcel, setIsExportingExcel] = useState(false);

  // 3. Cache thông tin sản phẩm (name) chỉ tra cứu theo IDs xuất hiện trong trang
  const [productMap, setProductMap] = useState(new Map());
  const pendingIdsRef = useRef(new Set());
  const failedRetryCountsRef = useRef(new Map()); // pid -> retryCount
  const MAX_PRODUCT_LOOKUP_RETRIES = 2;

  // 4. Modal hiển thị chi tiết Lý do điều chỉnh (Admin only)
  const [viewingReasonItem, setViewingReasonItem] = useState(null);

  // F11: Đóng modal xem lý do nếu role thay đổi hoặc session không còn là ADMIN
  useEffect(() => {
    if (!isAdmin) {
      setViewingReasonItem(null);
    }
  }, [isAdmin]);

  // Ref chống race condition
  const requestIdRef = useRef(0);

  // F09: Tra cứu tên sản phẩm có giới hạn chỉ cho các product_id có trên trang hiện tại
  useEffect(() => {
    let isMounted = true;
    const missingIds = movements
      .map((m) => m.product_id)
      .filter((pid) => {
        if (!pid) return false;
        // Nếu đã có tên trong cache -> không cần nạp
        if (productMap.has(pid)) return false;
        // Nếu đang trong tiến trình nạp (pending) -> không gửi trùng
        if (pendingIdsRef.current.has(pid)) return false;
        // Nếu đã thử thất bại quá số lần cho phép -> ngừng retry
        const retryCount = failedRetryCountsRef.current.get(pid) || 0;
        return retryCount < MAX_PRODUCT_LOOKUP_RETRIES;
      });

    const uniqueMissingIds = [...new Set(missingIds)];
    if (uniqueMissingIds.length === 0) return;

    // Đánh dấu ngay vào pendingIdsRef để chống duplicate in-flight requests
    uniqueMissingIds.forEach((pid) => pendingIdsRef.current.add(pid));

    async function resolvePageProductNames() {
      try {
        const resolvedEntries = await Promise.all(
          uniqueMissingIds.map(async (pid) => {
            try {
              const p = await productsApi.getProduct(pid);
              return { pid, name: p?.name || null, success: Boolean(p?.name) };
            } catch {
              return { pid, name: null, success: false };
            }
          })
        );

        // Giải phóng cờ pending và ghi nhận retry count nếu thất bại
        resolvedEntries.forEach(({ pid, success }) => {
          pendingIdsRef.current.delete(pid);
          if (!success) {
            const count = failedRetryCountsRef.current.get(pid) || 0;
            failedRetryCountsRef.current.set(pid, count + 1);
          }
        });

        if (isMounted) {
          const successfulEntries = resolvedEntries.filter((e) => e.success);
          if (successfulEntries.length > 0) {
            setProductMap((prev) => {
              const next = new Map(prev);
              for (const { pid, name } of successfulEntries) {
                next.set(pid, name);
              }
              return next;
            });
          }
        }
      } catch {
        // Giải phóng cờ pending nếu có lỗi bất ngờ
        uniqueMissingIds.forEach((pid) => pendingIdsRef.current.delete(pid));
      }
    }

    resolvePageProductNames();
    return () => {
      isMounted = false;
    };
  }, [movements, productMap]);

  // Gọi API lấy lịch sử biến động kho cho STAFF (Server-side)
  const loadMovements = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);

    try {
      const res = await inventoryApi.getStockMovements({
        page: pagination.page,
        pageSize: pagination.pageSize,
        kind: selectedKind || null,
      });

      if (currentRequestId === requestIdRef.current) {
        setMovements(res.items || []);
        setTotalCount(res.total || 0);
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        const msg = getApiErrorMessage(err, 'Không thể tải lịch sử biến động kho.');
        toast.error(msg);
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [pagination.page, pagination.pageSize, selectedKind, toast]);

  useEffect(() => {
    loadMovements();
  }, [loadMovements]);

  const handleExportExcel = useCallback(async () => {
    if (isExportingExcel) return;
    setIsExportingExcel(true);
    try {
      const exportResult = await collectStockMovementsForExport({
        selectedKind,
        inventoryApi,
        existingProductMap: productMap,
        maxRows: MAX_EXPORT_ROWS,
      });

      if (exportResult.items.length === 0) {
        toast.warning('Không có dữ liệu biến động kho để xuất Excel.');
        return;
      }

      const rows = buildStockMovementExportRows(exportResult.items, {
        isAdmin,
        productMap: exportResult.productMap,
        formatDateTimeFn: formatVietnamDateTime,
        formatReferenceCodeFn: formatReferenceCode,
        movementKindLabels: MOVEMENT_KIND_LABELS,
      });

      await downloadStyledExcelRows(
        rows,
        `stock_movements_${selectedKind || 'all'}.xlsx`
      );

      if (exportResult.isTruncated) {
        toast.warning(
          `Đã xuất ${exportResult.items.length}/${exportResult.totalAvailable} bản ghi biến động kho (còn ${exportResult.remainingCount} bản ghi chưa xuất do giới hạn ${MAX_EXPORT_ROWS} bản ghi).`
        );
      } else {
        toast.success(
          `Xuất Excel thành công (${exportResult.items.length} bản ghi biến động kho)!`
        );
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Không thể xuất Excel lịch sử biến động kho.'));
    } finally {
      setIsExportingExcel(false);
    }
  }, [isExportingExcel, selectedKind, isAdmin, productMap, toast]);

  const formatActorLabel = useCallback(
    (actorId) => {
      if (!actorId) return 'Hệ thống';
      if (user?.id && Number(actorId) === Number(user.id)) {
        return user.full_name?.trim() || user.email || `User ${actorId}`;
      }
      return `User ${actorId}`;
    },
    [user?.id, user?.full_name, user?.email]
  );

  // Cấu hình các cột hiển thị cho STAFF (Không hiển thị giá vốn, lý do nội bộ, actor)
  const columns = useMemo(() => {
    return [
      {
        key: 'sku',
        title: 'MÃ SKU',
        width: isAdmin ? '9%' : '12%',
        render: (row) => <span className={styles.skuHighlight}>{row.sku}</span>,
      },
      {
        key: 'product_name',
        title: 'TÊN SẢN PHẨM',
        width: isAdmin ? '19%' : '25%',
        render: (row) => {
          const name = productMap.get(row.product_id) || `Sản phẩm #${row.product_id}`;
          return <div className={styles.productName}>{name}</div>;
        },
      },
      {
        key: 'kind',
        title: 'LOẠI BIẾN ĐỘNG',
        width: isAdmin ? '13%' : '16%',
        render: (row) => {
          const meta = MOVEMENT_KIND_LABELS[row.kind] || {
            label: row.kind,
            badgeClass: 'badgeMovementAdjustment',
          };
          return (
            <span className={styles[meta.badgeClass] || styles.badgeMovementAdjustment}>
              {meta.label}
            </span>
          );
        },
      },
      {
        key: 'quantity_change',
        title: 'SỐ LƯỢNG THAY ĐỔI',
        align: 'center',
        width: isAdmin ? '11%' : '14%',
        render: (row) => {
          const delta = row.quantity_after - row.quantity_before;
          const isNegative = delta < 0;
          const sign = isNegative ? '' : '+';
          const cssClass = isNegative ? styles.qtyDecrease : styles.qtyIncrease;
          return <span className={cssClass}>{`${sign}${delta}`}</span>;
        },
      },
      {
        key: 'occurred_at',
        title: 'THỜI ĐIỂM GHI NHẬN',
        width: isAdmin ? '14%' : '17%',
        render: (row) => (
          <span className={styles.occurredTime}>{formatVietnamDateTime(row.occurred_at)}</span>
        ),
      },
      {
        key: 'reference',
        title: 'MÃ CHỨNG TỪ THAM CHIẾU',
        width: isAdmin ? '13%' : '16%',
        render: (row) => {
          const refCode = formatReferenceCode(row.kind, row.reference_id);
          return <span className={styles.referenceBadge}>{refCode}</span>;
        },
      },
      // Cột NGƯỜI THỰC HIỆN & LÝ DO: Chỉ hiển thị cho Quản trị viên (ADMIN)
      ...(isAdmin
        ? [
            {
              key: 'actor',
              title: 'NGƯỜI THỰC HIỆN',
              width: '10%',
              render: (row) => (
                <span className={styles.actorBadge}>
                  <span>{formatActorLabel(row.actor_id)}</span>
                </span>
              ),
            },
            {
              key: 'adjustment_reason',
              title: 'LÝ DO ĐIỀU CHỈNH',
              width: '11%',
              align: 'center',
              render: (row) => {
                if (row.kind === 'ADJUSTMENT' && row.adjustment_reason) {
                  return (
                    <button
                      type="button"
                      className={styles.viewReasonBtn}
                      onClick={() => setViewingReasonItem(row)}
                      title="Xem lý do điều chỉnh"
                    >
                      Xem lý do
                    </button>
                  );
                }
                return <span className={styles.reasonEmpty}>-</span>;
              },
            },
          ]
        : []),
    ];
  }, [productMap, isAdmin]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pagination.pageSize));

  return (
    <div className={styles.movementContainer}>
      {/* 1. Thanh bộ lọc: loại biến động & tổng số lượng */}
      <div className={styles.movementFilterCard}>
        <div className={styles.leftFilters}>
          {/* Lọc loại biến động (Server-side) */}
          <div className={styles.filterGroup}>
            <label htmlFor="kindSelect" className={styles.filterLabel}>
              Loại biến động:
            </label>
            <CustomSelect
              id="kindSelect"
              value={selectedKind}
              onChange={(e) => {
                setSelectedKind(e.target.value);
                setPagination((prev) => ({ ...prev, page: 1 }));
              }}
              options={[
                { value: '', label: 'Tất cả biến động' },
                { value: 'SALE', label: 'Bán hàng POS' },
                { value: 'PURCHASE_CONFIRM', label: 'Nhập hàng' },
                { value: 'ORDER_CANCEL', label: 'Hoàn trả hủy đơn' },
                { value: 'ADJUSTMENT', label: 'Điều chỉnh kho' },
              ]}
            />
          </div>
        </div>

        {/* Tổng cộng bản ghi & Xuất Excel */}
        <div className={styles.rightSummaryActions}>
          <div className={styles.totalSummary}>
            Tổng cộng: <strong>{totalCount}</strong> bản ghi biến động
          </div>
          <button
            type="button"
            className={styles.exportExcelBtn}
            onClick={handleExportExcel}
            disabled={isExportingExcel || isLoading || totalCount === 0}
          >
            {isExportingExcel ? 'Đang xuất...' : 'Xuất Excel'}
          </button>
        </div>
      </div>

      {/* 2. Bảng dữ liệu tái sử dụng Table common */}
      <div className={styles.tableWrap}>
        <Table
          columns={columns}
          data={movements}
          rowKey="id"
          isLoading={isLoading}
          emptyText="Không có bản ghi biến động kho nào."
        />

        {/* 3. Phân trang căn phải (bỏ dòng '1 - 10 trên tổng số') */}
        {totalCount > 0 && (
          <div className={styles.paginationRightWrap}>
            <Pagination
              currentPage={pagination.page}
              totalPages={totalPages}
              onPageChange={(newPage) => {
                setPagination((prev) => ({ ...prev, page: newPage }));
              }}
            />
          </div>
        )}
      </div>

      {/* 4. Modal hiển thị chi tiết lý do điều chỉnh (Admin only, dùng chung Modal component) */}
      <Modal
        isOpen={isAdmin && Boolean(viewingReasonItem)}
        onClose={() => setViewingReasonItem(null)}
        title="Lý do điều chỉnh kiểm kê"
        maxWidth="500px"
        footer={
          <button
            type="button"
            className={styles.modalCloseBtn}
            onClick={() => setViewingReasonItem(null)}
          >
            Đóng
          </button>
        }
      >
        {isAdmin && viewingReasonItem && (
          <div className={styles.modalBody}>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Mã SKU:</span>
              <span className={styles.metaValue}>{viewingReasonItem.sku}</span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Sản phẩm:</span>
              <span className={styles.metaValue}>
                {productMap.get(viewingReasonItem.product_id) || `Sản phẩm #${viewingReasonItem.product_id}`}
              </span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Người thực hiện:</span>
              <span className={styles.metaValue}>
                {formatActorLabel(viewingReasonItem.actor_id)}
              </span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Thời gian:</span>
              <span className={styles.metaValue}>{formatVietnamDateTime(viewingReasonItem.occurred_at)}</span>
            </div>

            <div className={styles.reasonBox}>
              <div className={styles.reasonBoxLabel}>Nội dung lý do kiểm toán:</div>
              <div className={styles.reasonContent}>
                {viewingReasonItem.adjustment_reason}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

