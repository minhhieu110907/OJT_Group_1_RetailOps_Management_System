import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { productsApi } from '../../api/productsApi';
import {
  MOVEMENT_KIND_LABELS,
  formatReferenceCode,
  inventoryApi,
} from '../../api/inventoryApi';
import styles from './StockMovementList.module.css';

/**
 * Format date string ISO -> "DD/MM/YYYY HH:mm:ss"
 */
function formatVietnamDateTime(isoString) {
  if (!isoString) return '-';
  try {
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) return String(isoString);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const seconds = String(d.getSeconds()).padStart(2, '0');
    return `${day}/${month}/${year} ${hours}:${minutes}:${seconds}`;
  } catch {
    return String(isoString);
  }
}

export default function StockMovementList() {
  const { user } = useAuth();
  const toast = useToast();

  const isAdmin = user?.role === 'ADMIN';

  // 1. Bộ lọc Server-side (loại biến động, phân trang) & Search Input giao diện
  const [searchKeyword, setSearchKeyword] = useState('');
  const [selectedKind, setSelectedKind] = useState('');
  const [selectedTimeFilter, setSelectedTimeFilter] = useState('ALL');

  // 2. State dữ liệu
  const [movements, setMovements] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10 });
  const [isLoading, setIsLoading] = useState(false);

  // 3. Cache thông tin sản phẩm (name) để hiển thị tên món theo product_id
  const [productMap, setProductMap] = useState(new Map());

  // 4. Modal hiển thị chi tiết Lý do điều chỉnh (Admin only)
  const [viewingReasonItem, setViewingReasonItem] = useState(null);

  // Ref chống race condition
  const requestIdRef = useRef(0);

  // Nạp danh sách sản phẩm để tra cứu tên sản phẩm theo product_id
  useEffect(() => {
    let isMounted = true;
    async function fetchProducts() {
      try {
        const res = await productsApi.getProducts({ page: 1, pageSize: 100 });
        if (isMounted && res?.items) {
          const map = new Map();
          res.items.forEach((p) => {
            map.set(p.id, p.name);
          });
          setProductMap(map);
        }
      } catch {
        // Im lặng fallback nếu lỗi nạp tên
      }
    }
    fetchProducts();
    return () => {
      isMounted = false;
    };
  }, []);

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

  // Cấu hình các cột hiển thị cho STAFF (Không hiển thị giá vốn, lý do nội bộ, actor)
  const columns = useMemo(() => {
    return [
      {
        key: 'sku',
        title: 'MÃ SKU',
        width: '130px',
        render: (row) => <span className={styles.skuHighlight}>{row.sku}</span>,
      },
      {
        key: 'product_name',
        title: 'TÊN SẢN PHẨM',
        render: (row) => {
          const name = productMap.get(row.product_id) || `Sản phẩm #${row.product_id}`;
          return <div className={styles.productName}>{name}</div>;
        },
      },
      {
        key: 'kind',
        title: 'LOẠI BIẾN ĐỘNG',
        width: '160px',
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
        width: '160px',
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
        width: '180px',
        render: (row) => (
          <span className={styles.occurredTime}>{formatVietnamDateTime(row.occurred_at)}</span>
        ),
      },
      {
        key: 'reference',
        title: 'MÃ CHỨNG TỪ THAM CHIẾU',
        width: '190px',
        render: (row) => {
          const refCode = formatReferenceCode(
            row.kind,
            row.reference_id,
            row.occurred_at ? String(row.occurred_at).slice(0, 10) : ''
          );
          return <span className={styles.referenceBadge}>{refCode}</span>;
        },
      },
      // Cột NGƯỜI THỰC HIỆN & LÝ DO: Chỉ hiển thị cho Quản trị viên (ADMIN)
      ...(isAdmin
        ? [
            {
              key: 'actor',
              title: 'NGƯỜI THỰC HIỆN',
              width: '140px',
              render: (row) => (
                <span className={styles.actorBadge}>
                  <span>{row.actor_id ? `User ${row.actor_id}` : 'Hệ thống'}</span>
                </span>
              ),
            },
            {
              key: 'adjustment_reason',
              title: 'LÝ DO ĐIỀU CHỈNH',
              width: '160px',
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
      {/* 1. Thanh bộ lọc giao diện: ô tìm kiếm, loại biến động, thời gian & tổng số lượng */}
      <div className={styles.movementFilterCard}>
        <div className={styles.leftFilters}>
          {/* Ô tìm kiếm giao diện (chưa áp dụng filter client, sẵn sàng cho server-side) */}
          <div className={styles.searchWrap}>
            <span className={styles.searchIcon} aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </span>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Tìm kiếm theo mã SKU, tên sản phẩm..."
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
            />
          </div>

          {/* Lọc loại biến động (Server-side) */}
          <div className={styles.filterGroup}>
            <label htmlFor="kindSelect" className={styles.filterLabel}>
              Loại biến động:
            </label>
            <select
              id="kindSelect"
              className={styles.selectInput}
              value={selectedKind}
              onChange={(e) => {
                setSelectedKind(e.target.value);
                setPagination((prev) => ({ ...prev, page: 1 }));
              }}
            >
              <option value="">Tất cả biến động</option>
              <option value="SALE">Bán hàng POS</option>
              <option value="PURCHASE_CONFIRM">Nhập hàng</option>
              <option value="ORDER_CANCEL">Hoàn trả hủy đơn</option>
              <option value="ADJUSTMENT">Điều chỉnh kho</option>
            </select>
          </div>

          {/* Lọc thời gian giao diện */}
          <div className={styles.filterGroup}>
            <label htmlFor="timeSelect" className={styles.filterLabel}>
              Thời gian:
            </label>
            <select
              id="timeSelect"
              className={styles.selectInput}
              value={selectedTimeFilter}
              onChange={(e) => setSelectedTimeFilter(e.target.value)}
            >
              <option value="ALL">Tất cả thời gian</option>
              <option value="TODAY">Hôm nay</option>
            </select>
          </div>
        </div>

        {/* Tổng cộng bản ghi */}
        <div className={styles.totalSummary}>
          Tổng cộng: <strong>{totalCount}</strong> bản ghi biến động
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

      {/* 4. Modal hiển thị chi tiết lý do điều chỉnh (Admin only, tuyệt đối không dùng icon) */}
      {viewingReasonItem && (
        <div
          className={styles.modalBackdrop}
          onClick={(e) => {
            if (e.target === e.currentTarget) setViewingReasonItem(null);
          }}
        >
          <div className={styles.reasonModalBox}>
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>Lý do điều chỉnh kiểm kê</h3>
            </div>

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
                  {viewingReasonItem.actor_id ? `User ${viewingReasonItem.actor_id}` : 'Hệ thống'}
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

            <div className={styles.modalFooter}>
              <button
                type="button"
                className={styles.modalCloseBtn}
                onClick={() => setViewingReasonItem(null)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

