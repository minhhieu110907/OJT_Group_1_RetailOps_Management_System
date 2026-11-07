import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import styles from './ProductList.module.css';

// Hàm định dạng tiền tệ VND
const formatVND = (amount) =>
  new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(
    Number(amount) || 0
  );

// Badge hiển thị Trạng thái tồn kho
function StockStatusBadge({ status }) {
  const config = {
    IN_STOCK: { label: 'Còn hàng', className: styles.badgeSuccess },
    LOW_STOCK: { label: 'Tồn thấp', className: styles.badgeWarning },
    OUT_OF_STOCK: { label: 'Hết hàng', className: styles.badgeDanger },
  };
  const current = config[status] || config.IN_STOCK;
  return (
    <span className={`${styles.pillBadge} ${current.className}`}>
      {current.label}
    </span>
  );
}

// Badge hiển thị Trạng thái hoạt động
function ActiveStatusBadge({ activeStatus }) {
  const isSelling = activeStatus !== 'INACTIVE';
  return (
    <span
      className={`${styles.pillBadge} ${isSelling ? styles.badgeSuccess : styles.badgeNeutral
        }`}
    >
      {isSelling ? 'Đang bán' : 'Ngừng bán'}
    </span>
  );
}

/**
 * Trang Danh sách Sản phẩm chính thức (Khung chuẩn bàn giao cho Tân tích hợp API)
 * - Phân quyền hiển thị theo vai trò:
 *   + ADMIN: Xem đầy đủ cột "Giá vốn", nút "Sửa" (icon bút chì), nút "Xóa" (icon thùng rác) và nút "+ Thêm sản phẩm".
 *   + STAFF: Ẩn hoàn toàn cột "Giá vốn" và ẩn nút "Sửa" sản phẩm.
 */
export default function ProductList() {
  const { user } = useAuth();
  const toast = useToast();

  const isStaff = user?.role === 'STAFF';

  // 1. Cấu trúc State chuẩn để Tân tiếp quản gọi API thật qua axiosClient
  const [searchParams, setSearchParams] = useState({
    keyword: '',
    categoryId: '',
    stockStatus: '',
    status: '',
  });
  const [data, setData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [pagination, setPagination] = useState({
    currentPage: 1,
    pageSize: 10,
    totalPages: 1,
    totalItems: 0,
  });

  // State quản lý Modal xác nhận xóa sản phẩm
  const [productToDelete, setProductToDelete] = useState(null);

  // TODO (Tân): Gọi API lấy danh sách sản phẩm từ Backend khi searchParams hoặc currentPage thay đổi
  useEffect(() => {
    let isMounted = true;

    const fetchProducts = async () => {
      setIsLoading(true);
      try {
        // Ví dụ khi ghép API thật:
        // const res = await axiosClient.get('/products', {
        //   params: {
        //     ...searchParams,
        //     page: pagination.currentPage,
        //     limit: pagination.pageSize,
        //   },
        // });
        // if (isMounted) {
        //   setData(res.data.items || []);
        //   setPagination((prev) => ({
        //     ...prev,
        //     totalPages: res.data.totalPages || 1,
        //     totalItems: res.data.totalItems || 0,
        //   }));
        // }
      } catch {
        if (isMounted) {
          toast.error('Không thể tải danh sách sản phẩm.');
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchProducts();

    return () => {
      isMounted = false;
    };
  }, [searchParams, pagination.currentPage, pagination.pageSize, toast]);

  // Xử lý thay đổi bộ lọc tìm kiếm
  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setSearchParams((prev) => ({
      ...prev,
      [name]: value,
    }));
    setPagination((prev) => ({
      ...prev,
      currentPage: 1,
    }));
  };

  // Xử lý chuyển trang trên thanh Pagination
  const handlePageChange = (nextPage) => {
    setPagination((prev) => ({
      ...prev,
      currentPage: nextPage,
    }));
  };

  // Xử lý xác nhận xóa sản phẩm trong Modal
  const handleConfirmDelete = async () => {
    if (!productToDelete) return;

    try {
      // TODO (Tân): Gọi await axiosClient.delete(`/products/${productToDelete.id}`)
      setData((prev) => prev.filter((item) => item.id !== productToDelete.id));
      toast.success(`Đã xóa sản phẩm "${productToDelete.name}"`);
    } catch {
      toast.error('Xóa sản phẩm thất bại. Vui lòng thử lại.');
    } finally {
      setProductToDelete(null);
    }
  };

  // 2. Cấu hình cột động theo vai trò (Ẩn cột "Giá vốn" và nút "Sửa" nếu user.role === 'STAFF')
  const columns = useMemo(() => {
    const baseColumns = [
      {
        key: 'sku',
        title: 'MÃ SKU',
        width: '110px',
        render: (row) => <span className={styles.skuText}>{row.sku}</span>,
      },
      {
        key: 'name',
        title: 'TÊN SẢN PHẨM',
        render: (row) => <span className={styles.productName}>{row.name}</span>,
      },
      {
        key: 'category',
        title: 'DANH MỤC',
      },
      // Cột GIÁ VỐN: Chỉ hiển thị khi KHÔNG phải là STAFF (tức là ADMIN)
      ...(!isStaff
        ? [
          {
            key: 'costPrice',
            title: 'GIÁ VỐN (VND)',
            align: 'right',
            width: '140px',
            render: (row) => (
              <span className={styles.costPriceText}>
                {formatVND(row.costPrice)}
              </span>
            ),
          },
        ]
        : []),
      {
        key: 'price',
        title: 'GIÁ BÁN (VND)',
        align: 'right',
        width: '140px',
        render: (row) => (
          <span className={styles.priceText}>{formatVND(row.price)}</span>
        ),
      },
      {
        key: 'stock',
        title: 'TỒN KHO',
        align: 'center',
        width: '110px',
        render: (row) => <span className={styles.stockBadge}>{row.stock}</span>,
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI TỒN KHO',
        align: 'center',
        width: '160px',
        render: (row) => <StockStatusBadge status={row.status} />,
      },
      {
        key: 'activeStatus',
        title: 'TRẠNG THÁI HOẠT ĐỘNG',
        align: 'center',
        width: '170px',
        render: (row) => <ActiveStatusBadge activeStatus={row.activeStatus} />,
      },
      {
        key: 'actions',
        title: 'THAO TÁC',
        align: 'center',
        width: '110px',
        render: (row) => (
          <div className={styles.actionGroup}>
            {/* Nút Sửa (Icon bút chì): Ẩn hoàn toàn nếu user.role === 'STAFF' */}
            {!isStaff && (
              <button
                type="button"
                className={`${styles.iconActionBtn} ${styles.editBtn}`}
                onClick={() =>
                  toast.info(`Chỉnh sửa sản phẩm: ${row.name}`)
                }
                title="Sửa sản phẩm"
                aria-label="Sửa sản phẩm"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                  <path d="m15 5 4 4" />
                </svg>
              </button>
            )}

            {/* Nút Xóa (Icon thùng rác): Mở Modal xác nhận xóa */}
            <button
              type="button"
              className={`${styles.iconActionBtn} ${styles.deleteBtn}`}
              onClick={() => setProductToDelete(row)}
              title="Xóa sản phẩm"
              aria-label="Xóa sản phẩm"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <line x1="10" y1="11" x2="10" y2="17" />
                <line x1="14" y1="11" x2="14" y2="17" />
              </svg>
            </button>
          </div>
        ),
      },
    ];

    return baseColumns;
  }, [isStaff, toast]);

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header trang */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Quản lý sản phẩm</h1>
          <p className={styles.pageSubtitle}>
            Danh mục sản phẩm kinh doanh tại cửa hàng
          </p>
        </div>

        {!isStaff && (
          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={() =>
                toast.info('Tính năng thêm sản phẩm sẽ được kết nối API.')
              }
            >
              <span>+ Thêm sản phẩm</span>
            </button>
          </div>
        )}
      </div>

      {/* 2. Thanh tìm kiếm & Bộ lọc (searchParams) */}
      <div className={styles.filterCard}>
        <div className={styles.searchWrap}>
          <span className={styles.searchIcon} aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>
          <input
            type="text"
            name="keyword"
            value={searchParams.keyword}
            onChange={handleFilterChange}
            placeholder="Tìm theo tên sản phẩm, mã SKU..."
            className={styles.searchInput}
          />
        </div>

        <div className={styles.filterGroup}>
          <select
            name="categoryId"
            value={searchParams.categoryId}
            onChange={handleFilterChange}
            className={styles.filterSelect}
          >
            <option value="">Tất cả danh mục</option>
          </select>

          <select
            name="stockStatus"
            value={searchParams.stockStatus}
            onChange={handleFilterChange}
            className={styles.filterSelect}
          >
            <option value="">Tất cả trạng thái tồn kho</option>
            <option value="IN_STOCK">Còn hàng</option>
            <option value="LOW_STOCK">Tồn thấp</option>
            <option value="OUT_OF_STOCK">Hết hàng</option>
          </select>

          <select
            name="status"
            value={searchParams.status}
            onChange={handleFilterChange}
            className={styles.filterSelect}
          >
            <option value="">Tất cả trạng thái hoạt động</option>
            <option value="ACTIVE">Đang bán</option>
            <option value="INACTIVE">Ngừng bán</option>
          </select>
        </div>
      </div>

      {/* 3. Bảng dữ liệu sản phẩm */}
      <Table
        columns={columns}
        data={data}
        rowKey="id"
        isLoading={isLoading}
        emptyText="Chưa có dữ liệu sản phẩm. Hãy kết nối API để hiển thị danh sách."
      />

      {/* 4. Phân trang */}
      <div className={styles.paginationRow}>
        <Pagination
          currentPage={pagination.currentPage}
          totalPages={pagination.totalPages}
          onPageChange={handlePageChange}
        />
      </div>

      {/* 5. Modal xác nhận xóa sản phẩm */}
      <Modal
        isOpen={Boolean(productToDelete)}
        onClose={() => setProductToDelete(null)}
        title="Xác nhận xóa sản phẩm"
        maxWidth="420px"
        footer={
          <>
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={() => setProductToDelete(null)}
            >
              Hủy
            </button>
            <button
              type="button"
              className={modalStyles.dangerBtn}
              onClick={handleConfirmDelete}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
              <span>Xóa sản phẩm</span>
            </button>
          </>
        }
      >
        Bạn muốn xóa sản phẩm này?
      </Modal>
    </div>
  );
}
