import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { ordersApi } from '../../api/ordersApi';
import { useAuth } from '../../context/AuthContext';
import { formatVnd } from '../../utils/posUtils';
import {
  formatOrderCreatedCellVN,
  getVietnamBusinessDateKey,
} from '../../utils/orderUtils';
import OrderDetailModal from './OrderDetailModal';
import CancelOrderModal from './CancelOrderModal';
import styles from './Orders.module.css';

const PAGE_SIZE = 10;

export default function OrderList() {
  const { user, isMockMode } = useAuth();
  const toast = useToast();

  // Filter states (Single-row filter bar: Search | Single Date | Status | Reset)
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedDate, setSelectedDate] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  // Server data states
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [refreshTick, setRefreshTick] = useState(0);

  // Live clock tick (every 15s) to keep 15-minute cancellation window accurate
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => {
      setNowMs(Date.now());
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  // Detail & Cancel modal states
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null); // { order, remainingMinutes }
  const detailRequestSeqRef = useRef(0);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const todayKey = useMemo(() => getVietnamBusinessDateKey(nowMs), [nowMs]);

  const fetchOrders = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage('');
    try {
      const response = await ordersApi.getOrders({
        isMockMode,
        page,
        pageSize: PAGE_SIZE,
        status: statusFilter || undefined,
        fromDate: selectedDate || undefined,
        toDate: selectedDate || undefined,
        search: debouncedSearch || undefined,
      });
      setOrders(response.items);
      setTotal(response.total);
    } catch (err) {
      const msg = getApiErrorMessage(
        err,
        'Không thể tải danh sách lịch sử đơn hàng.'
      );
      setErrorMessage(msg);
      setOrders([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
    }
  }, [isMockMode, page, statusFilter, selectedDate, debouncedSearch]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders, refreshTick]);

  const handleResetFilters = () => {
    setSearchQuery('');
    setDebouncedSearch('');
    setSelectedDate('');
    setStatusFilter('');
    setPage(1);
  };

  const syncUpdatedOrderInState = useCallback((updatedOrder) => {
    if (!updatedOrder || typeof updatedOrder.id !== 'number') return;
    setOrders((prev) =>
      prev.map((item) => (item.id === updatedOrder.id ? updatedOrder : item))
    );
    setSelectedOrder((prev) =>
      prev && prev.id === updatedOrder.id ? updatedOrder : prev
    );
  }, []);

  const handleOpenDetail = async (rowOrder) => {
    setNowMs(Date.now());
    setSelectedOrder(rowOrder);
    const reqSeq = ++detailRequestSeqRef.current;

    try {
      const freshOrder = await ordersApi.getOrderById({
        isMockMode,
        orderId: rowOrder.id,
      });
      if (detailRequestSeqRef.current === reqSeq) {
        syncUpdatedOrderInState(freshOrder);
      }
    } catch {
      // Keep the row snapshot visible if background refresh fails
    }
  };

  const handleCloseDetail = () => {
    detailRequestSeqRef.current += 1;
    setSelectedOrder(null);
  };

  const handleOpenCancelModal = (orderToCancel, remainingMinutes) => {
    setCancelTarget({
      order: orderToCancel,
      remainingMinutes,
    });
  };

  const handleCloseCancelModal = () => {
    setCancelTarget(null);
  };

  const handleOrderCancelled = (updatedOrder) => {
    syncUpdatedOrderInState(updatedOrder);
    setCancelTarget(null);
    setRefreshTick((t) => t + 1);
  };

  const handleReloadOrderFromConflict = (latestOrder) => {
    syncUpdatedOrderInState(latestOrder);
    setRefreshTick((t) => t + 1);
  };

  const columns = useMemo(
    () => [
      {
        key: 'id',
        title: 'MÃ ĐƠN',
        width: '120px',
        render: (row) => (
          <span className={styles.orderIdCell}>#{row.id}</span>
        ),
      },
      {
        key: 'sold_at',
        title: 'THỜI GIAN TẠO',
        width: '190px',
        render: (row) => {
          const { primary, secondary } = formatOrderCreatedCellVN(
            row.sold_at,
            nowMs
          );
          return (
            <span className={styles.createdTimeCell}>
              <span>{primary}</span>
              {secondary && (
                <span className={styles.createdTimeSecondary}>{secondary}</span>
              )}
            </span>
          );
        },
      },
      {
        key: 'created_by',
        title: 'NGƯỜI TẠO',
        width: '150px',
        render: (row) => {
          const isCurrentAdmin =
            user?.id === row.created_by && user?.role === 'ADMIN';
          return (
            <span className={styles.creatorCell}>
              {isCurrentAdmin
                ? `Admin #${row.created_by}`
                : `Nhân viên #${row.created_by}`}
            </span>
          );
        },
      },
      {
        key: 'items_count',
        title: 'SỐ MẶT HÀNG',
        width: '140px',
        render: (row) => {
          const totalUnits = Array.isArray(row.items)
            ? row.items.reduce((sum, item) => sum + (item.quantity || 0), 0)
            : 0;
          return (
            <span className={styles.itemsCountCell}>{totalUnits} sản phẩm</span>
          );
        },
      },
      {
        key: 'total_vnd',
        title: 'TỔNG TIỀN',
        width: '150px',
        render: (row) => (
          <span className={styles.totalAmountCell}>
            {formatVnd(row.total_vnd)}
          </span>
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI',
        width: '150px',
        render: (row) =>
          row.status === 'COMPLETED' ? (
            <span className={styles.statusCompleted}>Đã hoàn tất</span>
          ) : (
            <span className={styles.statusCancelled}>Đã hủy</span>
          ),
      },
      {
        key: 'actions',
        title: 'THAO TÁC',
        align: 'right',
        width: '140px',
        render: (row) => (
          <div className={styles.actionGroup}>
            <button
              type="button"
              className={styles.viewBtn}
              onClick={() => handleOpenDetail(row)}
            >
              Xem chi tiết
            </button>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [nowMs, user]
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const startIndex = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const endIndex = Math.min(total, page * PAGE_SIZE);

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Lịch sử đơn hàng</h1>
          <p className={styles.pageSubtitle}>
            Tra cứu các đơn hàng tại cửa hàng
          </p>
        </div>
        <span className={styles.timezoneBadge}>
          Quy tắc: Hủy trong 15 phút (Nhân viên) | Cùng ngày (Admin)
        </span>
      </div>

      {/* 2. Single-row Filter Card */}
      <div className={styles.filterCard}>
        <div className={styles.filterRowSingle}>
          {/* Search input */}
          <div className={styles.searchBoxWrap}>
            <span className={styles.searchIcon} aria-hidden="true">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </span>
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Theo mã đơn"
              aria-label="Theo mã đơn"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Single Date filter */}
          <div className={styles.dateFilterWrap}>
            <span className={styles.dateCalendarIcon} aria-hidden="true">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </span>
            <span className={styles.datePrefixLabel}>Ngày bán:</span>
            <input
              type="date"
              className={styles.dateInputInline}
              aria-label="Ngày bán"
              value={selectedDate}
              onChange={(e) => {
                setSelectedDate(e.target.value);
                setPage(1);
              }}
            />
            {selectedDate === todayKey && (
              <span className={styles.todayBadgeInline}>(Hôm nay)</span>
            )}
          </div>

          {/* Status dropdown */}
          <select
            className={styles.statusSelectSingle}
            aria-label="Lọc theo trạng thái đơn hàng"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Tất cả trạng thái</option>
            <option value="COMPLETED">Đã hoàn tất</option>
            <option value="CANCELLED">Đã hủy</option>
          </select>

          {/* Reset filters button */}
          <button
            type="button"
            className={styles.resetFilterBtn}
            onClick={handleResetFilters}
          >
            Xóa bộ lọc
          </button>
        </div>
      </div>

      {/* 3. Error Banner or Table Card */}
      {errorMessage ? (
        <div className={styles.errorStateBox} role="alert">
          <strong>Không thể tải lịch sử đơn hàng</strong>
          <p>{errorMessage}</p>
        </div>
      ) : (
        <div className={styles.tableCard}>
          <Table
            columns={columns}
            data={orders}
            rowKey="id"
            isLoading={isLoading}
            emptyText="Không tìm thấy đơn hàng nào phù hợp với bộ lọc hiện tại."
          />

          <div className={styles.tableFooterBar}>
            <span className={styles.tableSummaryText}>
              Hiển thị {startIndex} - {endIndex} trên tổng số {total} đơn hàng
            </span>
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          </div>
        </div>
      )}

      {/* 4. Bottom Immutable Rule & Cancellation Policy Banner */}
      <div className={styles.immutableRuleBanner}>
        <div className={styles.immutableRuleLeft}>
          <h2 className={styles.immutableRuleTitle}>
            Nguyên tắc bất biến đơn hàng &amp; Quyền hủy
          </h2>
          <p className={styles.immutableRuleDesc}>
            Đơn hàng sau khi hoàn tất là cố định. Nhân viên chỉ được hủy đơn do
            chính mình tạo trong 15 phút (Asia/Ho_Chi_Minh). Quản trị viên
            (Admin) được phép hủy trong ngày.
          </p>
        </div>
        <span className={styles.autoRestoreBadge}>
          Kho hàng: Tự động hoàn trả
        </span>
      </div>

      {/* 5. Order Detail Modal */}
      {selectedOrder && !cancelTarget && (
        <OrderDetailModal
          order={selectedOrder}
          user={user}
          nowMs={nowMs}
          onClose={handleCloseDetail}
          onOpenCancelModal={handleOpenCancelModal}
        />
      )}

      {/* 6. Cancel Order Confirmation & Error Modal */}
      {cancelTarget && (
        <CancelOrderModal
          order={cancelTarget.order}
          user={user}
          isMockMode={isMockMode}
          remainingMinutes={cancelTarget.remainingMinutes}
          onClose={handleCloseCancelModal}
          onCancelled={handleOrderCancelled}
          onReloadOrder={handleReloadOrderFromConflict}
          toast={toast}
        />
      )}
    </div>
  );
}
