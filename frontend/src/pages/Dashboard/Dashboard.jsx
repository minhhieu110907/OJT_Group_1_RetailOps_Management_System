import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { analyticsApi } from '../../api/analyticsApi';
import { getApiErrorMessage } from '../../api/axiosClient';
import { ordersApi } from '../../api/ordersApi';
import { useAuth } from '../../context/AuthContext';
import {
  buildDashboardSeriesBuckets,
  computeOrderStructureMetrics,
  DASHBOARD_PRESETS,
  executeGuardedDashboardFetch,
  formatIsoDateShortVN,
  formatVietnamDateTime,
  formatVietnamPeriodRange,
  resolveDashboardDateRange,
} from '../../utils/analyticsUtils';
import {
  executeVerifiedOrderDetailFetch,
  formatOrderActorLabel,
} from '../../utils/orderUtils';
import { formatVnd } from '../../utils/posUtils';
import OrderDetailModal from '../Orders/OrderDetailModal';
import styles from './Dashboard.module.css';

const PRESET_OPTIONS = [
  { key: DASHBOARD_PRESETS.TODAY, label: 'Hôm nay' },
  { key: DASHBOARD_PRESETS.LAST_7_DAYS, label: '7 ngày gần nhất' },
  { key: DASHBOARD_PRESETS.LAST_30_DAYS, label: '30 ngày qua' },
  { key: DASHBOARD_PRESETS.THIS_MONTH, label: 'Tháng này' },
];

function formatCompactVnd(amount) {
  if (typeof amount !== 'number' || amount <= 0) return '0 đ';
  if (amount >= 1_000_000) {
    const millions = Math.round((amount / 1_000_000) * 100) / 100;
    return `${String(millions).replace('.', ',')}M đ`;
  }
  if (amount >= 1_000) {
    return `${Math.round(amount / 1_000)}K đ`;
  }
  return formatVnd(amount);
}

export default function Dashboard() {
  const { user, isMockMode } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [preset, setPreset] = useState(DASHBOARD_PRESETS.TODAY);
  const activeRange = useMemo(() => resolveDashboardDateRange(preset), [preset]);
  const seriesBuckets = useMemo(() => buildDashboardSeriesBuckets(preset), [preset]);

  const [dashboardData, setDashboardData] = useState(null);
  const [seriesRows, setSeriesRows] = useState([]);
  const [todayOrders, setTodayOrders] = useState([]);
  const [todayOrdersTotal, setTodayOrdersTotal] = useState(0);

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [errorStatus, setErrorStatus] = useState(null);

  // Order detail modal state for "Doanh thu trong ngày" eye button
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isDetailVerified, setIsDetailVerified] = useState(false);
  const [detailError, setDetailError] = useState('');

  const fetchSeqRef = useRef(0);
  const detailSeqRef = useRef(0);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const fetchAllDashboardData = useCallback(
    async (targetPreset, targetRange, targetBuckets) => {
      if (!isAdmin) return;
      setIsLoading(true);
      setErrorMessage('');
      setErrorStatus(null);

      await executeGuardedDashboardFetch({
        seqRef: fetchSeqRef,
        isMountedRef,
        fetcher: async () => {
          const mainPromise = analyticsApi.getDashboard({
            isMockMode,
            from: targetRange.from,
            to: targetRange.to,
          });

          const bucketPromises = targetBuckets.map((b) =>
            analyticsApi
              .getSalesAnalytics({
                isMockMode,
                from: b.from,
                to: b.to,
              })
              .then((summary) => ({ ...b, summary }))
          );

          const ordersPromise =
            targetPreset === DASHBOARD_PRESETS.TODAY
              ? ordersApi
                  .getOrders({
                    isMockMode,
                    page: 1,
                    page_size: 6,
                    from_date: targetRange.from,
                    to_date: targetRange.to,
                  })
                  .catch(() => ({ items: [], total: 0 }))
              : Promise.resolve({ items: [], total: 0 });

          const [mainData, resolvedBuckets, ordersPage] = await Promise.all([
            mainPromise,
            Promise.all(bucketPromises),
            ordersPromise,
          ]);

          return { mainData, resolvedBuckets, ordersPage };
        },
        onSuccess: ({ mainData, resolvedBuckets, ordersPage }) => {
          setDashboardData(mainData);
          setSeriesRows(resolvedBuckets);
          setTodayOrders(ordersPage.items || []);
          setTodayOrdersTotal(ordersPage.total || 0);
        },
        onError: (err) => {
          setErrorStatus(err?.response?.status ?? null);
          setErrorMessage(
            getApiErrorMessage(err, 'Không thể tải dữ liệu Tổng quan cửa hàng từ máy chủ.')
          );
        },
        onFinally: () => {
          setIsLoading(false);
        },
      });
    },
    [isAdmin, isMockMode]
  );

  useEffect(() => {
    if (!isAdmin) return;
    fetchAllDashboardData(preset, activeRange, seriesBuckets);
  }, [isAdmin, preset, activeRange, seriesBuckets, fetchAllDashboardData]);

  const handleOpenOrderDetail = useCallback(
    async (rowOrder) => {
      if (!rowOrder?.id) return;
      setSelectedOrder(rowOrder);
      setIsDetailLoading(true);
      setIsDetailVerified(false);
      setDetailError('');

      await executeVerifiedOrderDetailFetch({
        seqRef: detailSeqRef,
        isMountedRef,
        orderId: rowOrder.id,
        fetcher: (id) => ordersApi.getOrderById(id, { isMockMode }),
        onVerified: (freshOrder) => {
          setSelectedOrder(freshOrder);
          setIsDetailVerified(true);
        },
        onError: (err) => {
          setIsDetailVerified(false);
          setDetailError(
            getApiErrorMessage(err, 'Không thể tải chi tiết đơn hàng từ máy chủ.')
          );
        },
        onFinally: () => {
          setIsDetailLoading(false);
        },
      });
    },
    [isMockMode]
  );

  const handleCloseOrderDetail = useCallback(() => {
    detailSeqRef.current += 1;
    setSelectedOrder(null);
    setIsDetailLoading(false);
    setIsDetailVerified(false);
    setDetailError('');
  }, []);

  const sales = dashboardData?.sales;
  const lowStockCount = dashboardData?.low_stock_count ?? 0;

  const orderStructure = useMemo(
    () =>
      computeOrderStructureMetrics(
        sales?.completed_orders ?? 0,
        sales?.cancelled_orders ?? 0
      ),
    [sales]
  );

  // Compute chart geometry & 3 summary stats from seriesRows
  const chartModel = useMemo(() => {
    const items = seriesRows || [];
    if (items.length === 0) {
      return {
        points: [],
        linePath: '',
        areaPath: '',
        avgRevenue: 0,
        peakLabel: '—',
        peakRevenue: 0,
        totalRevenue: 0,
      };
    }

    const revenues = items.map((item) => item.summary?.revenue_vnd || 0);
    const totalRevenue = revenues.reduce((acc, v) => acc + v, 0);
    const avgRevenue = Math.round(totalRevenue / items.length);

    let peakIdx = 0;
    revenues.forEach((val, idx) => {
      if (val >= revenues[peakIdx]) {
        peakIdx = idx;
      }
    });

    const maxVal = Math.max(...revenues, 1);
    const leftX = 48;
    const rightX = 610;
    const topY = 34;
    const bottomY = 162;
    const usableW = rightX - leftX;
    const usableH = bottomY - topY;

    const points = items.map((item, idx) => {
      const rev = item.summary?.revenue_vnd || 0;
      const x =
        items.length === 1
          ? (leftX + rightX) / 2
          : leftX + (idx / (items.length - 1)) * usableW;
      const y = bottomY - (rev / maxVal) * usableH;
      return {
        key: item.key,
        x: Math.round(x * 10) / 10,
        y: Math.round(y * 10) / 10,
        label: item.chartLabel,
        revenue: rev,
        isPeak: idx === peakIdx,
        isLatest: idx === items.length - 1,
      };
    });

    const linePath = points
      .map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${pt.x} ${pt.y}`)
      .join(' ');
    const areaPath = `${linePath} L ${points[points.length - 1].x} ${bottomY} L ${points[0].x} ${bottomY} Z`;

    return {
      points,
      linePath,
      areaPath,
      avgRevenue,
      peakLabel: items[peakIdx]?.chartLabel || '—',
      peakRevenue: revenues[peakIdx] || 0,
      totalRevenue,
    };
  }, [seriesRows]);

  const tableRowsNewestFirst = useMemo(
    () => [...seriesRows].reverse(),
    [seriesRows]
  );

  const tableTotals = useMemo(() => {
    const completed = seriesRows.reduce(
      (acc, r) => acc + (r.summary?.completed_orders || 0),
      0
    );
    const cancelled = seriesRows.reduce(
      (acc, r) => acc + (r.summary?.cancelled_orders || 0),
      0
    );
    const revenue = seriesRows.reduce(
      (acc, r) => acc + (r.summary?.revenue_vnd || 0),
      0
    );
    const aov = completed > 0 ? Math.round(revenue / completed) : 0;
    return { completed, cancelled, revenue, aov };
  }, [seriesRows]);

  if (!isAdmin) {
    return (
      <div className={styles.pageContainer}>
        <div className={styles.stateCard}>
          <h2 className={styles.pageTitle}>Không có quyền truy cập</h2>
          <p className={styles.pageSubtitle}>
            Trang Tổng quan cửa hàng chỉ dành cho tài khoản Quản trị viên (ADMIN).
          </p>
        </div>
      </div>
    );
  }

  const isWeeklyMode =
    preset === DASHBOARD_PRESETS.LAST_30_DAYS ||
    preset === DASHBOARD_PRESETS.THIS_MONTH;

  // SVG Donut geometry
  const donutRadius = 54;
  const donutCircumference = 2 * Math.PI * donutRadius;
  const completedArc = (orderStructure.completedPct / 100) * donutCircumference;
  const cancelledArc = (orderStructure.cancelledPct / 100) * donutCircumference;

  return (
    <div className={styles.pageContainer}>
      {/* Top Header + 4-pill Segmented Filter */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Tổng quan cửa hàng</h1>
          <p className={styles.pageSubtitle}>
            <span>{activeRange.periodLabel}</span>
            <span>•</span>
            <span>Múi giờ Asia/Ho_Chi_Minh</span>
          </p>
        </div>

        <div className={styles.headerRight}>
          <div className={styles.segmentedBar} role="group" aria-label="Bộ lọc kỳ thống kê">
            {PRESET_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                className={`${styles.segmentBtn} ${
                  preset === opt.key ? styles.segmentBtnActive : ''
                }`}
                onClick={() => setPreset(opt.key)}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className={styles.periodChipRow}>
            <span className={styles.periodChip}>
              Kỳ báo cáo:{' '}
              {sales
                ? formatVietnamPeriodRange(sales.period_start, sales.period_end_exclusive)
                : activeRange.from === activeRange.to
                ? formatIsoDateShortVN(activeRange.from)
                : `${formatIsoDateShortVN(activeRange.from)} - ${formatIsoDateShortVN(
                    activeRange.to
                  )}`}
            </span>
            <button
              type="button"
              className={styles.refreshBtn}
              onClick={() => fetchAllDashboardData(preset, activeRange, seriesBuckets)}
              disabled={isLoading}
            >
              {isLoading ? 'Đang tải...' : 'Làm mới'}
            </button>
          </div>
        </div>
      </div>

      {errorMessage && (
        <div className={styles.errorCard} role="alert">
          <div>
            <p className={styles.errorTitle}>
              {errorStatus === 401 || errorStatus === 403
                ? 'Lỗi xác thực hoặc phân quyền'
                : 'Không thể tải dữ liệu Dashboard'}
            </p>
            <p className={styles.errorText}>{errorMessage}</p>
          </div>
          <button
            type="button"
            className={styles.retryBtn}
            onClick={() => fetchAllDashboardData(preset, activeRange, seriesBuckets)}
          >
            Thử lại
          </button>
        </div>
      )}

      {/* Row 1: 4 KPI Cards */}
      <div className={styles.kpiGrid}>
        <div className={styles.kpiCard}>
          <div className={styles.kpiTopRow}>
            <span className={styles.kpiLabel}>Doanh thu bán hàng</span>
            <span className={`${styles.kpiIconBox} ${styles.kpiIconEmerald}`}>₫</span>
          </div>
          <div className={styles.kpiValue}>
            {sales ? formatVnd(sales.revenue_vnd) : '0 ₫'}
          </div>
          <span className={styles.kpiSub}>Từ các đơn COMPLETED</span>
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiTopRow}>
            <span className={styles.kpiLabel}>Số đơn hoàn tất</span>
            <span className={`${styles.kpiIconBox} ${styles.kpiIconSlate}`}>✓</span>
          </div>
          <div className={styles.kpiValue}>
            {sales ? sales.completed_orders.toLocaleString('vi-VN') : '0'}{' '}
            <span className={styles.kpiUnit}>đơn</span>
          </div>
          <span className={styles.kpiSub}>
            <span className={styles.greenDot} />
            Giao dịch COMPLETED
          </span>
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiTopRow}>
            <span className={styles.kpiLabel}>Số đơn đã hủy</span>
            <span className={`${styles.kpiIconBox} ${styles.kpiIconRed}`}>✕</span>
          </div>
          <div className={`${styles.kpiValue} ${styles.kpiValueRed}`}>
            {sales ? sales.cancelled_orders.toLocaleString('vi-VN') : '0'}{' '}
            <span className={styles.kpiUnitRed}>đơn</span>
          </div>
          <span className={styles.kpiSub}>CANCELLED theo kỳ bán ban đầu</span>
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiTopRow}>
            <span className={styles.kpiLabel}>Giá trị trung bình đơn (AOV)</span>
            <span className={`${styles.kpiIconBox} ${styles.kpiIconEmerald}`}>≡</span>
          </div>
          <div className={styles.kpiValue}>
            {sales ? formatVnd(sales.aov_vnd) : '0 ₫'}
          </div>
          <span className={styles.kpiSub}>Tính trên đơn COMPLETED</span>
        </div>
      </div>

      {/* Row 2: Left Trend Chart + Right Order Breakdown & Low Stock Card */}
      <div className={styles.middleGrid}>
        <section className={styles.panelCard} aria-label="Biểu đồ xu hướng doanh thu">
          <div className={styles.panelHeader}>
            <div>
              <h2 className={styles.panelTitle}>
                {isWeeklyMode
                  ? 'Biểu đồ xu hướng doanh thu theo tuần'
                  : 'Doanh thu 7 ngày gần nhất'}
              </h2>
              <p className={styles.panelSubtitle}>
                {isWeeklyMode
                  ? `Gom theo ${seriesBuckets.length} chặng tuần trong kỳ đã chọn`
                  : `Xu hướng bán hàng 7 ngày qua (${
                      seriesBuckets[0]?.chartLabel || ''
                    } - ${seriesBuckets[seriesBuckets.length - 1]?.chartLabel || ''})`}
              </p>
            </div>
            <span className={styles.legendPill}>
              <span className={styles.greenDot} />
              Doanh thu
            </span>
          </div>

          <div className={styles.chartWrap}>
            <svg
              viewBox="0 0 650 195"
              className={styles.chartSvg}
              role="img"
              aria-label="Biểu đồ đường xu hướng doanh thu"
            >
              <defs>
                <linearGradient id="dashboardAreaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0d9488" stopOpacity="0.28" />
                  <stop offset="100%" stopColor="#0d9488" stopOpacity="0.02" />
                </linearGradient>
              </defs>

              {/* Horizontal grid lines */}
              {[38, 79, 120, 162].map((y) => (
                <line
                  key={y}
                  x1="40"
                  y1={y}
                  x2="618"
                  y2={y}
                  stroke="#f1f5f9"
                  strokeWidth="1"
                />
              ))}

              {chartModel.areaPath && (
                <path d={chartModel.areaPath} fill="url(#dashboardAreaGrad)" />
              )}
              {chartModel.linePath && (
                <path
                  d={chartModel.linePath}
                  fill="none"
                  stroke="#0d9488"
                  strokeWidth="2.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {chartModel.points.map((pt) => (
                <g key={pt.key}>
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r={pt.isLatest ? 5 : 4}
                    fill={pt.isLatest ? '#0d9488' : '#ffffff'}
                    stroke="#0d9488"
                    strokeWidth="2.2"
                  />
                  {pt.isLatest && (
                    <g>
                      <rect
                        x={Math.min(Math.max(pt.x - 42, 12), 555)}
                        y={Math.max(pt.y - 32, 4)}
                        width="84"
                        height="22"
                        rx="6"
                        fill="#0f172a"
                      />
                      <text
                        x={Math.min(Math.max(pt.x, 54), 597)}
                        y={Math.max(pt.y - 17, 19)}
                        textAnchor="middle"
                        fill="#ffffff"
                        fontSize="11"
                        fontWeight="700"
                      >
                        {formatCompactVnd(pt.revenue)}
                      </text>
                    </g>
                  )}
                  <text
                    x={pt.x}
                    y="184"
                    textAnchor="middle"
                    fill={pt.isLatest ? '#0f172a' : '#64748b'}
                    fontSize="11.5"
                    fontWeight={pt.isLatest ? '700' : '500'}
                  >
                    {pt.label}
                  </text>
                </g>
              ))}
            </svg>
          </div>

          <div className={styles.chartSummaryGrid}>
            <div className={styles.chartStatBox}>
              <span className={styles.chartStatLabel}>
                {isWeeklyMode ? 'Trung bình tuần:' : 'Trung bình ngày:'}
              </span>
              <span className={styles.chartStatValue}>
                {formatVnd(chartModel.avgRevenue)}
              </span>
            </div>
            <div className={styles.chartStatBox}>
              <span className={styles.chartStatLabel}>
                {isWeeklyMode
                  ? `Tuần cao nhất (${chartModel.peakLabel}):`
                  : `Ngày cao nhất (${chartModel.peakLabel}):`}
              </span>
              <span className={styles.chartStatValue}>
                {formatVnd(chartModel.peakRevenue)}
              </span>
            </div>
            <div className={styles.chartStatBox}>
              <span className={styles.chartStatLabel}>
                {isWeeklyMode ? 'Tổng cộng kỳ:' : 'Tổng tuần 7 ngày:'}
              </span>
              <span className={styles.chartStatValueEmerald}>
                {formatVnd(chartModel.totalRevenue)}
              </span>
            </div>
          </div>
        </section>

        {/* Right Column: Order Breakdown & Cancellation Rate + Low Stock Alert */}
        <section className={styles.panelCard} aria-label="Cơ cấu đơn và tỷ lệ hủy">
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Cơ cấu đơn &amp; Tỷ lệ hủy</h2>
            <span className={styles.badgeGray}>{activeRange.badgeLabel}</span>
          </div>

          <div className={styles.donutSection}>
            <div className={styles.donutSvgWrap}>
              <svg viewBox="0 0 140 140" className={styles.donutSvg}>
                <circle
                  cx="70"
                  cy="70"
                  r={donutRadius}
                  fill="none"
                  stroke="#e2e8f0"
                  strokeWidth="16"
                />
                {orderStructure.total > 0 && (
                  <>
                    <circle
                      cx="70"
                      cy="70"
                      r={donutRadius}
                      fill="none"
                      stroke="#0d9488"
                      strokeWidth="16"
                      strokeDasharray={`${completedArc} ${donutCircumference}`}
                      strokeDashoffset="0"
                    />
                    {orderStructure.cancelled > 0 && (
                      <circle
                        cx="70"
                        cy="70"
                        r={donutRadius}
                        fill="none"
                        stroke="#ef4444"
                        strokeWidth="16"
                        strokeDasharray={`${cancelledArc} ${donutCircumference}`}
                        strokeDashoffset={-completedArc}
                      />
                    )}
                  </>
                )}
              </svg>
              <div className={styles.donutCenterText}>
                <span className={styles.donutPercent}>
                  {orderStructure.completedPctLabel}
                </span>
                <span className={styles.donutSub}>
                  Hoàn tất ({orderStructure.total.toLocaleString('vi-VN')} đơn)
                </span>
              </div>
            </div>

            <div className={styles.donutStatsCol}>
              <div className={styles.statPillGreen}>
                Hoàn tất: {orderStructure.completed.toLocaleString('vi-VN')} đơn (
                {orderStructure.completedPctLabel})
              </div>
              <div className={styles.statPillRed}>
                Đã hủy: {orderStructure.cancelled.toLocaleString('vi-VN')} đơn (
                {orderStructure.cancelledPctLabel})
              </div>
            </div>
          </div>

          <div className={styles.lowStockAlertBar}>
            <span>
              ⚠ Cảnh báo tồn kho: {lowStockCount.toLocaleString('vi-VN')} sản phẩm sắp
              hết (≤ 5)
            </span>
            <Link to="/inventory" className={styles.lowStockLink}>
              → Xem tồn kho
            </Link>
          </div>

          <p className={styles.accountingRuleNote}>
            Quy tắc hạch toán: <strong>Theo thời điểm bán ban đầu</strong>
          </p>
        </section>
      </div>

      {/* Row 3: Bottom Table according to selected filter mode */}
      <section className={styles.tableCard}>
        {preset === DASHBOARD_PRESETS.TODAY ? (
          <>
            <div className={styles.panelHeader}>
              <div>
                <h2 className={styles.panelTitle}>Doanh thu trong ngày</h2>
                <p className={styles.panelSubtitle}>
                  Các giao dịch POS phát sinh trong ngày hôm nay
                </p>
              </div>
              <div className={styles.tableHeaderRight}>
                <span className={styles.tableMetaText}>
                  Tổng cộng:{' '}
                  <strong>
                    {(sales?.completed_orders ?? todayOrdersTotal).toLocaleString('vi-VN')}{' '}
                    giao dịch
                  </strong>
                </span>
                <Link to="/orders" className={styles.viewAllLink}>
                  Xem tất cả đơn hàng &gt;
                </Link>
              </div>
            </div>

            {todayOrders.length === 0 ? (
              <p className={styles.emptyText}>
                Chưa có giao dịch nào phát sinh trong ngày hôm nay.
              </p>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>MÃ ĐƠN</th>
                      <th>THỜI GIAN</th>
                      <th>NGƯỜI TẠO</th>
                      <th className={styles.centerCell}>SỐ SP</th>
                      <th className={styles.numCell}>TỔNG TIỀN (VND)</th>
                      <th className={styles.centerCell}>TRẠNG THÁI</th>
                      <th className={styles.centerCell}>CHI TIẾT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {todayOrders.map((ord) => {
                      const itemCount = Array.isArray(ord.items)
                        ? ord.items.reduce((sum, it) => sum + (it.quantity || 0), 0)
                        : ord.item_count ?? '—';
                      const isCompleted = ord.status === 'COMPLETED';
                      return (
                        <tr key={ord.id}>
                          <td className={styles.orderCodeCell}>
                            #{ord.order_code || `HD-${ord.id}`}
                          </td>
                          <td>{formatVietnamDateTime(ord.sold_at || ord.created_at)}</td>
                          <td>{formatOrderActorLabel(ord, user)}</td>
                          <td className={styles.centerCell}>
                            {typeof itemCount === 'number' ? `${itemCount} món` : itemCount}
                          </td>
                          <td className={styles.numCell}>
                            <strong>{formatVnd(ord.total_vnd)}</strong>
                          </td>
                          <td className={styles.centerCell}>
                            <span
                              className={
                                isCompleted
                                  ? styles.statusBadgeCompleted
                                  : styles.statusBadgeCancelled
                              }
                            >
                              {isCompleted ? 'Hoàn tất' : 'Đã hủy'}
                            </span>
                          </td>
                          <td className={styles.centerCell}>
                            <button
                              type="button"
                              className={styles.eyeBtn}
                              title="Xem chi tiết đơn hàng"
                              onClick={() => handleOpenOrderDetail(ord)}
                            >
                              👁
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <>
            <div className={styles.panelHeader}>
              <div>
                <h2 className={styles.panelTitle}>
                  {isWeeklyMode ? 'Doanh thu theo tuần' : 'Doanh thu theo ngày'}
                </h2>
                <p className={styles.panelSubtitle}>
                  {isWeeklyMode
                    ? 'Tổng hợp đối soát đơn COMPLETED và CANCELLED theo từng tuần trong kỳ'
                    : 'Dữ liệu đối soát đơn hàng COMPLETED và CANCELLED từng ngày làm việc'}
                </p>
              </div>
              <span className={styles.badgeGray}>
                {activeRange.badgeLabel}: {formatIsoDateShortVN(activeRange.from)} -{' '}
                {formatIsoDateShortVN(activeRange.to)}
              </span>
            </div>

            <div className={styles.tableWrap}>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>
                      {isWeeklyMode
                        ? 'KHOẢNG THỜI GIAN (TUẦN)'
                        : 'NGÀY KINH DOANH (ASIA/HO_CHI_MINH)'}
                    </th>
                    <th className={styles.numCell}>ĐƠN HOÀN TẤT</th>
                    <th className={styles.numCell}>ĐƠN HỦY</th>
                    <th className={styles.numCell}>DOANH THU HOÀN TẤT (VND)</th>
                    <th className={styles.numCell}>AOV TRUNG BÌNH</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRowsNewestFirst.map((row) => {
                    const s = row.summary;
                    return (
                      <tr key={row.key}>
                        <td>
                          {row.isToday && <span className={styles.greenDot} />}{' '}
                          <strong>{row.tableLabel}</strong>
                        </td>
                        <td className={`${styles.numCell} ${styles.completedNum}`}>
                          {s ? `${s.completed_orders.toLocaleString('vi-VN')} đơn` : '0 đơn'}
                        </td>
                        <td className={`${styles.numCell} ${styles.cancelledNum}`}>
                          {s ? `${s.cancelled_orders.toLocaleString('vi-VN')} đơn` : '0 đơn'}
                        </td>
                        <td className={styles.numCell}>
                          <strong>{s ? formatVnd(s.revenue_vnd) : '0 ₫'}</strong>
                        </td>
                        <td className={styles.numCell}>
                          {s ? formatVnd(s.aov_vnd) : '0 ₫'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr>
                    <td>
                      TỔNG CỘNG KỲ PHÂN TÍCH (
                      {preset === DASHBOARD_PRESETS.LAST_7_DAYS
                        ? '7 NGÀY'
                        : preset === DASHBOARD_PRESETS.LAST_30_DAYS
                        ? '30 NGÀY'
                        : 'THÁNG NÀY'}
                      )
                    </td>
                    <td className={`${styles.numCell} ${styles.completedNum}`}>
                      {(sales?.completed_orders ?? tableTotals.completed).toLocaleString(
                        'vi-VN'
                      )}{' '}
                      đơn
                    </td>
                    <td className={`${styles.numCell} ${styles.cancelledNum}`}>
                      {(sales?.cancelled_orders ?? tableTotals.cancelled).toLocaleString(
                        'vi-VN'
                      )}{' '}
                      đơn
                    </td>
                    <td className={`${styles.numCell} ${styles.revenueNum}`}>
                      {formatVnd(sales?.revenue_vnd ?? tableTotals.revenue)}
                    </td>
                    <td className={styles.numCell}>
                      {formatVnd(sales?.aov_vnd ?? tableTotals.aov)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </>
        )}

        <div className={styles.tableFooterNote}>
          <span className={styles.greenDot} />
          <span>
            Báo cáo chỉ thống kê doanh thu từ các giao dịch đã hoàn tất (COMPLETED). Mọi
            đơn hủy (CANCELLED) được gán về đúng ngày bán ban đầu theo múi giờ
            Asia/Ho_Chi_Minh.
          </span>
        </div>
      </section>

      {selectedOrder && (
        <OrderDetailModal
          order={selectedOrder}
          currentUser={user}
          isLoading={isDetailLoading}
          isVerified={isDetailVerified}
          errorMessage={detailError}
          onRetry={() => handleOpenOrderDetail(selectedOrder)}
          onClose={handleCloseOrderDetail}
        />
      )}
    </div>
  );
}
