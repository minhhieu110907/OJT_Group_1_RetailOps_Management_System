import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useInventorySession } from '../../context/InventorySessionContext';
import { Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { categoriesApi } from '../../api/categoriesApi';
import {
  STOCK_STATUS_TABS,
  classifyStockLevel,
  inventoryApi,
} from '../../api/inventoryApi';
import { isValidAuthoritativeInventory } from './inventoryAdjustmentController';
import StockMovementList from './StockMovementList';
import InventoryAdjustModal from './InventoryAdjustModal';
import styles from './InventoryList.module.css';

export default function InventoryList() {
  const { user } = useAuth();
  const toast = useToast();
  const { liftedSession, updateLiftedSession, clearLiftedSession } = useInventorySession();

  const isAdmin = user?.role === 'ADMIN';

  // 1. Tab chính (Tổng quan tồn kho | Lịch sử biến động)
  const [activeMainTab, setActiveMainTab] = useState('OVERVIEW');

  // 2. Bộ lọc danh mục & tình trạng còn hàng (Hoàn toàn Server-side)
  const [selectedCategoryId, setSelectedCategoryId] = useState('');
  const [stockStatusFilter, setStockStatusFilter] = useState(STOCK_STATUS_TABS.ALL);

  // 3. Phân trang & Dữ liệu
  const [inventoryItems, setInventoryItems] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10 });
  const [isLoading, setIsLoading] = useState(false);

  // 4. Danh mục & Thống kê KPI toàn kho (Authoritative Global Counts)
  const [categories, setCategories] = useState([]);
  const [kpiStats, setKpiStats] = useState({
    totalProducts: null,
    activeProducts: null,
    lowStock: null,
    outOfStock: null,
    isLoading: true,
  });

  // 5. State Modal Điều chỉnh tồn kho (Admin only)
  // Local active product or restored from lifted session (persists across route navigation)
  const [localAdjustingProduct, setLocalAdjustingProduct] = useState(null);
  const adjustingProduct = localAdjustingProduct || liftedSession?.product || null;
  const pendingAmbiguousProduct = liftedSession?.product || null;

  // Stable callback with semantic equality guard to completely eliminate update loops
  const handleAmbiguousStateChange = useCallback((newSession) => {
    updateLiftedSession(newSession);
  }, [updateLiftedSession]);

  // Ref chống race condition
  const requestIdRef = useRef(0);
  const kpiRequestIdRef = useRef(0);
  const modalReloadRequestIdRef = useRef(0);

  // Tải danh sách danh mục để hiển thị chips
  useEffect(() => {
    let isMounted = true;
    async function fetchCategories() {
      try {
        const res = await categoriesApi.getCategories({ page: 1, pageSize: 50, status: 'ACTIVE' });
        if (isMounted && res?.items) {
          setCategories(res.items);
        }
      } catch {
        // Im lặng fallback nếu danh mục lỗi nhẹ
      }
    }
    fetchCategories();
    return () => {
      isMounted = false;
    };
  }, []);

  // Map category_id -> category_name
  const categoryMap = useMemo(() => {
    const map = new Map();
    categories.forEach((cat) => {
      map.set(cat.id, cat.name);
    });
    return map;
  }, [categories]);

  // F01: Tải số liệu thống kê KPI toàn kho (Semantics chính xác qua total của API)
  const loadKpiStats = useCallback(async () => {
    const currentKpiId = ++kpiRequestIdRef.current;
    try {
      // 1. Tổng mã hàng: GET /inventory?page=1&page_size=1
      // 2. Đang kinh doanh: GET /inventory?status=ACTIVE&page=1&page_size=1
      // 3. Tồn thấp (P0 <= 5 cho ACTIVE bao gồm = 0): GET /inventory/low-stock?page=1&page_size=1
      // 4. Hết hàng (ACTIVE và quantity = 0): GET /inventory?status=ACTIVE&in_stock=false&page=1&page_size=1
      const [totalRes, activeRes, lowStockRes, outOfStockRes] = await Promise.all([
        inventoryApi.getInventory({ page: 1, pageSize: 1 }),
        inventoryApi.getInventory({ status: 'ACTIVE', page: 1, pageSize: 1 }),
        inventoryApi.getLowStock({ page: 1, pageSize: 1 }),
        inventoryApi.getInventory({ status: 'ACTIVE', inStock: false, page: 1, pageSize: 1 }),
      ]);

      if (currentKpiId === kpiRequestIdRef.current) {
        setKpiStats({
          totalProducts: totalRes?.total ?? 0,
          activeProducts: activeRes?.total ?? 0,
          lowStock: lowStockRes?.total ?? 0,
          outOfStock: outOfStockRes?.total ?? 0,
          isLoading: false,
        });
      }
    } catch {
      if (currentKpiId === kpiRequestIdRef.current) {
        // Không hiển thị số 0 giả mạo khi API lỗi
        setKpiStats((prev) => ({
          ...prev,
          isLoading: false,
        }));
      }
    }
  }, []);

  // Tải KPI khi mở màn hình
  useEffect(() => {
    loadKpiStats();
  }, [loadKpiStats]);

  // Tải dữ liệu tồn kho từ Backend API
  const loadInventory = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);

    try {
      // Xác định param query theo filter
      let statusParam = null;
      let inStockParam = null;

      if (stockStatusFilter === STOCK_STATUS_TABS.IN_STOCK) {
        inStockParam = true;
      } else if (stockStatusFilter === STOCK_STATUS_TABS.OUT_OF_STOCK) {
        inStockParam = false;
      }

      const res = await inventoryApi.getInventory({
        page: pagination.page,
        pageSize: pagination.pageSize,
        categoryId: selectedCategoryId ? Number(selectedCategoryId) : null,
        status: statusParam,
        inStock: inStockParam,
      });

      if (currentRequestId === requestIdRef.current) {
        setInventoryItems(res.items || []);
        setTotalCount(res.total || 0);
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        const msg = getApiErrorMessage(err, 'Không thể tải danh sách tồn kho.');
        toast.error(msg);
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [pagination.page, pagination.pageSize, selectedCategoryId, stockStatusFilter, toast]);

  // Gọi loadInventory khi thay đổi trang hoặc bộ lọc
  useEffect(() => {
    loadInventory();
  }, [loadInventory]);

  // Cấu hình các cột cho Component Table dùng chung
  const columns = useMemo(() => {
    return [
      {
        key: 'sku',
        title: 'MÃ SKU',
        width: '150px',
        render: (row) => <span className={styles.skuCell}>{row.sku}</span>,
      },
      {
        key: 'name',
        title: 'TÊN SẢN PHẨM',
        render: (row) => <div className={styles.productNameCell}>{row.name}</div>,
      },
      {
        key: 'category',
        title: 'DANH MỤC',
        width: '150px',
        render: (row) => (
          <span>{categoryMap.get(row.category_id) || `Danh mục #${row.category_id}`}</span>
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI BÁN',
        width: '140px',
        render: (row) => {
          const isActive = row.status === 'ACTIVE';
          return (
            <span className={isActive ? styles.statusBadgeActive : styles.statusBadgeInactive}>
              <span
                className={isActive ? styles.statusDotGreen : styles.statusDotGray}
                aria-hidden="true"
              />
              {isActive ? 'Đang bán' : 'Ngừng bán'}
            </span>
          );
        },
      },
      {
        key: 'quantity',
        title: 'TỒN KHO HIỆN TẠI',
        align: 'center',
        width: '160px',
        render: (row) => <span className={styles.quantityCell}>{row.quantity}</span>,
      },
      {
        key: 'stock_level',
        title: 'TÌNH TRẠNG TỒN',
        width: '160px',
        render: (row) => {
          const classification = classifyStockLevel(row.quantity, row.status);
          return (
            <span className={styles[classification.badgeClass] || styles.badgeNormal}>
              {classification.label}
            </span>
          );
        },
      },
      // Cột THAO TÁC: Chỉ hiển thị cho Quản trị viên (ADMIN), ẩn hoàn toàn với STAFF
      ...(isAdmin
        ? [
            {
              key: 'action',
              title: 'THAO TÁC',
              align: 'center',
              width: '130px',
              render: (row) => (
                <button
                  type="button"
                  className={styles.actionBtn}
                  onClick={() => {
                    if (pendingAmbiguousProduct && pendingAmbiguousProduct.product_id !== row.product_id) {
                      toast.warning('Đang có phiên kiểm kê chưa rõ kết quả đối soát. Vui lòng hoàn tất đối soát trước khi mở sản phẩm khác.');
                      return;
                    }
                    setLocalAdjustingProduct(row);
                  }}
                  title="Điều chỉnh tồn kho"
                >
                  <span className={styles.actionBtnText}>Điều chỉnh</span>
                </button>
              ),
            },
          ]
        : []),
    ];
  }, [categoryMap, isAdmin, pendingAmbiguousProduct, toast]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pagination.pageSize));

  return (
    <div className={styles.container}>
     
      <div className={styles.tabsContainer}>
        <button
          type="button"
          className={`${styles.tabBtn} ${activeMainTab === 'OVERVIEW' ? styles.tabBtnActive : ''}`}
          onClick={() => {
            if (pendingAmbiguousProduct) {
              toast.warning('Đang có phiên kiểm kê chưa rõ kết quả đối soát. Vui lòng hoàn tất đối soát trước khi chuyển tab.');
              return;
            }
            setActiveMainTab('OVERVIEW');
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <span>Tổng quan tồn kho</span>
        </button>

        <button
          type="button"
          className={`${styles.tabBtn} ${activeMainTab === 'HISTORY' ? styles.tabBtnActive : ''}`}
          onClick={() => {
            if (pendingAmbiguousProduct) {
              toast.warning('Đang có phiên kiểm kê chưa rõ kết quả đối soát. Vui lòng hoàn tất đối soát trước khi chuyển tab.');
              return;
            }
            setActiveMainTab('HISTORY');
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <span>Lịch sử biến động</span>
        </button>
      </div>

      {activeMainTab === 'HISTORY' ? (
        <StockMovementList />
      ) : (
        <>
          <div className={styles.statGrid}>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>Tổng mã hàng</div>
          <div className={styles.statBody}>
            <span className={styles.statValue}>
              {kpiStats.isLoading && kpiStats.totalProducts === null ? '—' : kpiStats.totalProducts ?? '—'}
            </span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>Đang kinh doanh</div>
          <div className={styles.statBody}>
            <span className={styles.statValue}>
              {kpiStats.isLoading && kpiStats.activeProducts === null ? '—' : kpiStats.activeProducts ?? '—'}
            </span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={`${styles.statDot} ${styles.statDotYellow}`} />
            <span>Tồn thấp</span>
          </div>
          <div className={styles.statBody}>
            <span className={styles.statValue}>
              {kpiStats.isLoading && kpiStats.lowStock === null ? '—' : kpiStats.lowStock ?? '—'}
            </span>
            <span className={`${styles.statSubBadge} ${styles.statSubBadgeYellow}`}>
              Cần nhập thêm
            </span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={`${styles.statDot} ${styles.statDotRed}`} />
            <span>Hết hàng</span>
          </div>
          <div className={styles.statBody}>
            <span className={styles.statValue}>
              {kpiStats.isLoading && kpiStats.outOfStock === null ? '—' : kpiStats.outOfStock ?? '—'}
            </span>
            <span className={`${styles.statSubBadge} ${styles.statSubBadgeRed}`}>
              Cần bổ sung ngay
            </span>
          </div>
        </div>
      </div>

      {/* 5. Bộ lọc danh mục & tình trạng tồn */}
      <div className={styles.filterCard}>
        <div className={styles.filterControls}>
          {/* Lọc danh mục */}
          <div className={styles.filterRow}>
            <span className={styles.filterLabel}>Danh mục:</span>
            <div className={styles.filterChips}>
              <button
                type="button"
                className={`${styles.chipBtn} ${selectedCategoryId === '' ? styles.chipBtnActive : ''}`}
                onClick={() => {
                  setSelectedCategoryId('');
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              >
                Tất cả
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  className={`${styles.chipBtn} ${
                    String(selectedCategoryId) === String(cat.id) ? styles.chipBtnActive : ''
                  }`}
                  onClick={() => {
                    setSelectedCategoryId(String(cat.id));
                    setPagination((prev) => ({ ...prev, page: 1 }));
                  }}
                >
                  {cat.name}
                </button>
              ))}
            </div>
          </div>

          {/* Lọc tình trạng tồn (Đang bán) */}
          <div className={styles.filterRow}>
            <span className={styles.filterLabel}>Tình trạng tồn (Đang bán):</span>
            <div className={styles.filterChips}>
              <button
                type="button"
                className={`${styles.chipBtn} ${
                  stockStatusFilter === STOCK_STATUS_TABS.ALL ? styles.chipBtnActive : ''
                }`}
                onClick={() => {
                  setStockStatusFilter(STOCK_STATUS_TABS.ALL);
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              >
                Tất cả
              </button>
              <button
                type="button"
                className={`${styles.chipBtn} ${
                  stockStatusFilter === STOCK_STATUS_TABS.IN_STOCK ? styles.chipBtnActive : ''
                }`}
                onClick={() => {
                  setStockStatusFilter(STOCK_STATUS_TABS.IN_STOCK);
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              >
                Còn hàng
              </button>
              <button
                type="button"
                className={`${styles.chipBtn} ${
                  stockStatusFilter === STOCK_STATUS_TABS.OUT_OF_STOCK ? styles.chipBtnActive : ''
                }`}
                onClick={() => {
                  setStockStatusFilter(STOCK_STATUS_TABS.OUT_OF_STOCK);
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              >
                Hết hàng
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 6. Bảng dữ liệu tái sử dụng Component Table common */}
      <div className={styles.tableWrap}>
        <Table
          columns={columns}
          data={inventoryItems}
          rowKey="product_id"
          isLoading={isLoading}
          emptyText="Không tìm thấy sản phẩm nào trong kho thỏa mãn điều kiện lọc."
        />

        {/* 7. Phân trang tái sử dụng Component Pagination common */}
        {totalCount > 0 && (
          <div className={styles.paginationWrap}>
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

      {/* 8. Modal Điều chỉnh tồn kho (Admin only, hoàn toàn không dùng icon) */}
      {isAdmin && (adjustingProduct || pendingAmbiguousProduct) && (
        <InventoryAdjustModal
          isOpen={Boolean(adjustingProduct || pendingAmbiguousProduct)}
          product={adjustingProduct || pendingAmbiguousProduct}
          categoryName={categoryMap.get((adjustingProduct || pendingAmbiguousProduct).category_id) || ''}
          initialDraft={liftedSession}
          onAmbiguousStateChange={handleAmbiguousStateChange}
          onClose={() => {
            modalReloadRequestIdRef.current++;
            setLocalAdjustingProduct(null);
            clearLiftedSession();
          }}
          onReloadLatest={async (productId) => {
            const currentAttemptId = ++modalReloadRequestIdRef.current;
            try {
              // Tách biệt loading: không set isLoading của bảng ngoài để tránh kẹt loading bảng khi reload modal
              const latestData = await inventoryApi.getProductInventory(productId);

              // 1. Race & Identity checks: attempt phải còn active, modal còn mở, actor còn là ADMIN
              const currentActiveProduct = adjustingProduct || pendingAmbiguousProduct;
              if (
                currentAttemptId !== modalReloadRequestIdRef.current ||
                !currentActiveProduct ||
                currentActiveProduct.product_id !== productId ||
                !isAdmin
              ) {
                return null;
              }

              // 2. Authoritative Payload Validation: FAIL-CLOSED trước mọi side effect tại parent!
              if (!isValidAuthoritativeInventory(latestData, productId)) {
                // Tuyệt đối KHÔNG gọi setAdjustingProduct, KHÔNG toast success, KHÔNG refresh bảng
                throw new Error('Dữ liệu tồn kho nhận từ máy chủ không hợp lệ hoặc sai mã sản phẩm.');
              }

              // 3. Side effects CHỈ ĐƯỢC CHẠY sau khi toàn bộ validation đã thành công
              setLocalAdjustingProduct(latestData);
              toast.info(`Đã cập nhật phiên bản tồn kho mới nhất (v${latestData.stock_version}).`);
              loadInventory();
              return latestData;
            } catch (err) {
              const msg = getApiErrorMessage(err, 'Không thể làm mới dữ liệu sản phẩm.');
              // Chỉ toast lỗi nếu reload attempt này vẫn đang active
              if (currentAttemptId === modalReloadRequestIdRef.current) {
                toast.error(msg);
              }
              // Rethrow để modal con bắt được thất bại và giữ nguyên conflictData/trạng thái AMBIGUOUS
              throw err;
            }
          }}
          onSuccess={(res) => {
            const currentActiveProduct = adjustingProduct || pendingAmbiguousProduct;
            toast.success(
              res?.movement_created
                ? `Đã điều chỉnh tồn kho cho ${currentActiveProduct?.sku} thành công!`
                : `Đã kiểm kê ${currentActiveProduct?.sku}: Số lượng tồn kho không đổi.`
            );
            modalReloadRequestIdRef.current++;
            setLocalAdjustingProduct(null);
            clearLiftedSession();
            // Refresh lại danh sách tồn kho và KPI
            loadInventory();
            loadKpiStats();
          }}
        />
      )}
        </>
      )}
    </div>
  );
}
