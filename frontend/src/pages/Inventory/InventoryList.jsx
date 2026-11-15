import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { categoriesApi } from '../../api/categoriesApi';
import {
  STOCK_STATUS_TABS,
  classifyStockLevel,
  inventoryApi,
} from '../../api/inventoryApi';
import StockMovementList from './StockMovementList';
import styles from './InventoryList.module.css';

export default function InventoryList() {
  const { user } = useAuth();
  const toast = useToast();

  const isAdmin = user?.role === 'ADMIN';

  // 1. Tab chính (Tổng quan tồn kho | Lịch sử biến động)
  const [activeMainTab, setActiveMainTab] = useState('OVERVIEW');

  // 2. Bộ lọc danh mục & tình trạng còn hàng (Hoàn toàn Server-side)
  const [searchKeyword, setSearchKeyword] = useState('');
  const [selectedCategoryId, setSelectedCategoryId] = useState('');
  const [stockStatusFilter, setStockStatusFilter] = useState(STOCK_STATUS_TABS.ALL);

  // 3. Phân trang & Dữ liệu
  const [inventoryItems, setInventoryItems] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [pagination, setPagination] = useState({ page: 1, pageSize: 10 });
  const [isLoading, setIsLoading] = useState(false);

  // 4. Danh mục & Thống kê
  const [categories, setCategories] = useState([]);
  const [lowStockTotal, setLowStockTotal] = useState(0);

  // Ref chống race condition
  const requestIdRef = useRef(0);

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

  // Tải số liệu thống kê cảnh báo tồn kho thấp INV-04
  useEffect(() => {
    let isMounted = true;
    async function fetchLowStockStats() {
      try {
        const res = await inventoryApi.getLowStock({ page: 1, pageSize: 1 });
        if (isMounted) {
          setLowStockTotal(res.total || 0);
        }
      } catch {
        // Bỏ qua lỗi thống kê phụ
      }
    }
    fetchLowStockStats();
    return () => {
      isMounted = false;
    };
  }, []);

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
                    toast.info(`Chức năng điều chỉnh cho SKU ${row.sku} sẽ có trong Modal điều chỉnh.`);
                  }}
                  title="Điều chỉnh tồn kho"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={{ flexShrink: 0 }}
                  >
                    <line x1="4" y1="21" x2="4" y2="14" />
                    <line x1="4" y1="10" x2="4" y2="3" />
                    <line x1="12" y1="21" x2="12" y2="12" />
                    <line x1="12" y1="8" x2="12" y2="3" />
                    <line x1="20" y1="21" x2="20" y2="16" />
                    <line x1="20" y1="12" x2="20" y2="3" />
                    <line x1="1" y1="14" x2="7" y2="14" />
                    <line x1="9" y1="8" x2="15" y2="8" />
                    <line x1="17" y1="16" x2="23" y2="16" />
                  </svg>
                  <span className={styles.actionBtnText}>Điều chỉnh</span>
                </button>
              ),
            },
          ]
        : []),
    ];
  }, [categoryMap, toast, isAdmin]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pagination.pageSize));

  return (
    <div className={styles.container}>
     
      <div className={styles.tabsContainer}>
        <button
          type="button"
          className={`${styles.tabBtn} ${activeMainTab === 'OVERVIEW' ? styles.tabBtnActive : ''}`}
          onClick={() => setActiveMainTab('OVERVIEW')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <span>Tổng quan tồn kho</span>
          <span className={styles.tabCountBadge}>{totalCount} mã</span>
        </button>

        <button
          type="button"
          className={`${styles.tabBtn} ${activeMainTab === 'HISTORY' ? styles.tabBtnActive : ''}`}
          onClick={() => setActiveMainTab('HISTORY')}
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
            <span className={styles.statValue}>{totalCount}</span>
           
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>Đang kinh doanh</div>
          <div className={styles.statBody}>
            <span className={styles.statValue}>
              {inventoryItems.filter((i) => i.status === 'ACTIVE').length}
            </span>
            
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={`${styles.statDot} ${styles.statDotYellow}`} />
            <span>Tồn thấp</span>
          </div>
          <div className={styles.statBody}>
            <span className={styles.statValue}>{lowStockTotal}</span>
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
              {inventoryItems.filter((i) => i.status === 'ACTIVE' && i.quantity === 0).length}
            </span>
            <span className={`${styles.statSubBadge} ${styles.statSubBadgeRed}`}>
              Cần bổ sung ngay
            </span>
          </div>
        </div>
      </div>

      {/* 5. Khung tìm kiếm & Bộ lọc danh mục / tình trạng tồn */}
      <div className={styles.filterCard}>
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
            placeholder="Tìm theo tên sản phẩm, mã SKU..."
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
          />
        </div>

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
        </>
      )}
    </div>
  );
}
