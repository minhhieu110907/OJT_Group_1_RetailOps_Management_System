import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CustomDatePicker, CustomSelect, Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { ordersApi } from '../../api/ordersApi';
import { useAuth } from '../../context/AuthContext';
import { downloadCsvReport } from '../../utils/csvDownload';
import { formatVnd } from '../../utils/posUtils';
import {
  executeGuardedOrderListFetch,
  executeVerifiedOrderDetailFetch,
  formatOrderActorLabel,
  formatOrderCreatedCellVN,
  getVietnamBusinessDateKey,
} from '../../utils/orderUtils';
import OrderDetailModal from './OrderDetailModal';
import CancelOrderModal from './CancelOrderModal';
import styles from './Orders.module.css';

const PAGE_SIZE = 10;

function parseIsoDateParam(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.trim())
    ? value.trim()
    : '';
}

export default function OrderList() {
  const { user, isMockMode } = useAuth();
  const toast = useToast();

  // Filter states (Single-row filter bar: Search | Single Date | Status | Reset)
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [urlDateRange, setUrlDateRange] = useState(() => {
    if (typeof window === 'undefined') return null;
    const params = new URLSearchParams(window.location.search);
    const from = parseIsoDateParam(params.get('from_date'));
    const to = parseIsoDateParam(params.get('to_date'));
    if (from && to && from !== to) {
      return { from, to };
    }
    return null;
  });
  const [selectedDate, setSelectedDate] = useState(() => {
    if (typeof window === 'undefined') return '';
    const params = new URLSearchParams(window.location.search);
    const from = parseIsoDateParam(params.get('from_date'));
    const to = parseIsoDateParam(params.get('to_date'));
    if (from && (!to || from === to)) {
      return from;
    }
    return '';
  });
  const [statusFilter, setStatusFilter] = useState(() => {
    if (typeof window === 'undefined') return '';
    const param = new URLSearchParams(window.location.search).get('status');
    return param === 'COMPLETED' || param === 'CANCELLED' ? param : '';
  });
  const [page, setPage] = useState(1);

  // Server data states
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
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

  // Lifecycle & generation guards
  const isMountedRef = useRef(true);
  const listRequestSeqRef = useRef(0);
  const detailRequestSeqRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      listRequestSeqRef.current += 1;
      detailRequestSeqRef.current += 1;
    };
  }, []);

  // Verified detail & Cancel modal states
  const [detailState, setDetailState] = useState({
    order: null,
    status: 'idle', // 'idle' | 'loading' | 'verified' | 'error'
    error: '',
  });
  const [cancelTarget, setCancelTarget] = useState(null); // { order, remainingMinutes }
  const [cancelIntentsByOrder, setCancelIntentsByOrder] = useState({});

  // Debounce search input without resetting page on initial mount
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch((prev) => {
        if (prev !== searchQuery) {
          setPage(1);
        }
        return searchQuery;
      });
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const todayKey = useMemo(() => getVietnamBusinessDateKey(nowMs), [nowMs]);

  const fetchOrders = useCallback(async () => {
    await executeGuardedOrderListFetch({
      seqRef: listRequestSeqRef,
      isMountedRef,
      fetchFn: () =>
        ordersApi.getOrders({
          isMockMode,
          page,
          pageSize: PAGE_SIZE,
          status: statusFilter || undefined,
          fromDate: urlDateRange?.from || selectedDate || undefined,
          toDate: urlDateRange?.to || selectedDate || undefined,
          search: debouncedSearch || undefined,
        }),
      onStart: () => {
        setIsLoading(true);
        setErrorMessage('');
      },
      onSuccess: (response) => {
        setOrders(response.items);
        setTotal(response.total);
        setErrorMessage('');
      },
      onError: (err) => {
        const msg = getApiErrorMessage(
          err,
          'Không thể tải danh sách lịch sử đơn hàng.'
        );
        setErrorMessage(msg);
        setOrders([]);
        setTotal(0);
      },
      onFinally: () => {
        setIsLoading(false);
      },
    });
  }, [isMockMode, page, statusFilter, selectedDate, urlDateRange, debouncedSearch]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders, refreshTick]);

  const handleResetFilters = () => {
    setSearchQuery('');
    setDebouncedSearch('');
    setSelectedDate('');
    setUrlDateRange(null);
    setStatusFilter('');
    setPage(1);
  };

  const syncUpdatedOrderInState = useCallback((updatedOrder) => {
    if (!updatedOrder || typeof updatedOrder.id !== 'number') return;
    setOrders((prev) =>
      prev.map((item) => (item.id === updatedOrder.id ? updatedOrder : item))
    );
    setDetailState((prev) =>
      prev.order && prev.order.id === updatedOrder.id
        ? { order: updatedOrder, status: 'verified', error: '' }
        : prev
    );
  }, []);

  const handleOpenDetail = useCallback(
    async (rowOrder) => {
      if (!rowOrder?.id) return;
      setNowMs(Date.now());
      await executeVerifiedOrderDetailFetch({
        seqRef: detailRequestSeqRef,
        isMountedRef,
        orderSnapshot: rowOrder,
        fetchByIdFn: (orderId) =>
          ordersApi.getOrderById({
            isMockMode,
            orderId,
          }),
        onLoading: (snapshot) => {
          setDetailState({
            order: snapshot,
            status: 'loading',
            error: '',
          });
        },
        onVerified: (freshOrder) => {
          setOrders((prev) =>
            prev.map((item) => (item.id === freshOrder.id ? freshOrder : item))
          );
          setDetailState({
            order: freshOrder,
            status: 'verified',
            error: '',
          });
        },
        onError: (err) => {
          const msg = getApiErrorMessage(
            err,
            'Không thể xác minh thông tin chi tiết đơn hàng từ máy chủ.'
          );
          setDetailState((prev) =>
            prev.order?.id === rowOrder.id
              ? { ...prev, status: 'error', error: msg }
              : prev
          );
        },
      });
    },
    [isMockMode]
  );

  const handleCloseDetail = () => {
    detailRequestSeqRef.current += 1;
    setDetailState({
      order: null,
      status: 'idle',
      error: '',
    });
  };

  const handleOpenCancelModal = (orderToCancel, remainingMinutes) => {
    if (
      detailState.status !== 'verified' ||
      detailState.order?.id !== orderToCancel?.id
    ) {
      return;
    }
    setCancelTarget({
      order: detailState.order,
      remainingMinutes,
    });
  };

  const handleUpdateCancelIntent = useCallback((orderId, nextIntent) => {
    if (!orderId) return;
    setCancelIntentsByOrder((prev) => ({
      ...prev,
      [orderId]: nextIntent,
    }));
  }, []);

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

  const handleExportCsv = useCallback(async () => {
    if (user?.role !== 'ADMIN') return;
    setIsExporting(true);
    try {
      await downloadCsvReport(
        () =>
          ordersApi.exportOrdersCsv({
            isMockMode,
            status: statusFilter || undefined,
            fromDate: urlDateRange?.from || selectedDate || undefined,
            toDate: urlDateRange?.to || selectedDate || undefined,
            search: debouncedSearch || undefined,
          }),
        `orders_export_${urlDateRange ? `${urlDateRange.from}_${urlDateRange.to}` : selectedDate || 'all'}.xlsx`,
        { format: 'xlsx' }
      );
      toast.success('Xuất báo cáo Excel đơn hàng thành công!');
    } catch (err) {
      toast.error(err.message || 'Không thể xuất báo cáo đơn hàng.');
    } finally {
      setIsExporting(false);
    }
  }, [user, isMockMode, statusFilter, urlDateRange, selectedDate, debouncedSearch, toast]);

  const columns = useMemo(
    () => [
      {
        key: 'id',
        title: 'MÃ ĐƠN',
        width: '10%',
        render: (row) => (
          <span className={styles.orderIdCell}>#{row.id}</span>
        ),
      },
      {
        key: 'sold_at',
        title: 'THỜI GIAN TẠO',
        width: '18%',
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
        width: '16%',
        render: (row) => (
          <span className={styles.creatorCell}>
            {formatOrderActorLabel(row.created_by, user, row.created_by_name)}
          </span>
        ),
      },
      {
        key: 'items_count',
        title: 'SỐ MẶT HÀNG',
        width: '13%',
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
        width: '15%',
        render: (row) => (
          <span className={styles.totalAmountCell}>
            {formatVnd(row.total_vnd)}
          </span>
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI',
        width: '14%',
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
        width: '14%',
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
          Quy tắc: Hủy trong 15 phút (Nhân viên) | Cùng ngày (Quản trị viên)
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

          {/* Single Date filter — full-box clickable themed calendar */}
          <CustomDatePicker
            className={styles.orderDatePicker}
            prefixLabel="Ngày bán:"
            placeholder="Tất cả các ngày"
            ariaLabel="Ngày bán"
            value={selectedDate}
            badgeText={selectedDate === todayKey ? '(Hôm nay)' : ''}
            onChange={(e) => {
              setUrlDateRange(null);
              setSelectedDate(e.target.value);
              setPage(1);
            }}
          />

          {/* Status dropdown + conditional reset button */}
          <div className={styles.statusAndResetRow}>
            <CustomSelect
              ariaLabel="Lọc theo trạng thái đơn hàng"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              options={[
                { value: '', label: 'Tất cả trạng thái' },
                { value: 'COMPLETED', label: 'Đã hoàn tất' },
                { value: 'CANCELLED', label: 'Đã hủy' },
              ]}
            />

            {(searchQuery.trim() || selectedDate || urlDateRange || statusFilter) && (
              <button
                type="button"
                className={styles.resetFilterBtn}
                onClick={handleResetFilters}
              >
                Xóa bộ lọc
              </button>
            )}

            {/* Export Excel button (Admin only) */}
            {user?.role === 'ADMIN' && (
              <button
                type="button"
                className={styles.exportCsvBtn}
                onClick={handleExportCsv}
                disabled={isExporting}
              >
                {isExporting ? 'Đang xuất...' : 'Xuất Excel'}
              </button>
            )}
          </div>
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
            chính mình tạo trong 15 phút. Quản trị viên được phép hủy
            trong ngày.
          </p>
        </div>
        <span className={styles.autoRestoreBadge}>
          Kho hàng: Tự động hoàn trả
        </span>
      </div>

      {/* 5. Order Detail Modal */}
      {detailState.order && !cancelTarget && (
        <OrderDetailModal
          order={detailState.order}
          detailStatus={detailState.status}
          detailError={detailState.error}
          onRetryDetail={handleOpenDetail}
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
          cancelIntent={cancelIntentsByOrder[cancelTarget.order.id]}
          onUpdateCancelIntent={handleUpdateCancelIntent}
          onClose={handleCloseCancelModal}
          onCancelled={handleOrderCancelled}
          onReloadOrder={handleReloadOrderFromConflict}
          toast={toast}
        />
      )}
    </div>
  );
}
