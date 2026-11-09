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
 * Trang Danh sách Sản phẩm chính thức (Khung chuẩn bàn giao cho Tân tích hợp API - Task T3C9C86)
 * - Phân quyền hiển thị theo vai trò & chuẩn hợp đồng dữ liệu ProductRead:
 *   + Không hiển thị cột "Giá vốn" vì ProductRead không trả trường này và STAFF bị cấm xem giá vốn.
 *   + ADMIN: Hiển thị cột "THAO TÁC" (Sửa / Ngừng bán) và nút "+ Thêm sản phẩm".
 *   + STAFF: Chỉ có quyền xem tra cứu tồn kho & giá bán; ẩn hoàn toàn cột "THAO TÁC" và mọi nút chỉnh sửa / đổi trạng thái.
 */
export default function ProductList() {
  const { user, isMockMode, canUseMock } = useAuth();
  const toast = useToast();

  const isStaff = user?.role !== 'ADMIN';
  const isMockDemoActive = Boolean(isMockMode && canUseMock);

  // 1. Cấu trúc State chuẩn theo hợp đồng phân trang Backend: { items, total, page, page_size }
  const [searchParams, setSearchParams] = useState({
    keyword: '',
    categoryId: '',
    stockStatus: '',
    status: '',
  });
  const [data, setData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    total: 0,
    totalPages: 1,
  });

  // State quản lý Modal xác nhận ngừng bán sản phẩm (Admin-only)
  const [productToDeactivate, setProductToDeactivate] = useState(null);

  // TODO (Tân - T3C9C86): Gọi API lấy danh sách sản phẩm từ Backend khi searchParams hoặc page thay đổi
  useEffect(() => {
    let isMounted = true;

    const fetchProducts = async () => {
      setIsLoading(true);
      try {
        // Chuẩn API Contract Backend (GET /api/v1/products):
        // const res = await axiosClient.get('/products', {
        //   params: {
        //     ...searchParams,
        //     page: pagination.page,
        //     page_size: pagination.page_size,
        //   },
        // });
        // if (isMounted) {
        //   const items = Array.isArray(res.data?.items) ? res.data.items : [];
        //   const total = Number(res.data?.total) || 0;
        //   const pageSize = Number(res.data?.page_size) || pagination.page_size;
        //   setData(items);
        //   setPagination((prev) => ({
        //     ...prev,
        //     page: Number(res.data?.page) || prev.page,
        //     page_size: pageSize,
        //     total,
        //     totalPages: Math.max(1, Math.ceil(total / pageSize)),
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
  }, [searchParams, pagination.page, pagination.page_size, toast]);

  // Xử lý thay đổi bộ lọc tìm kiếm
  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setSearchParams((prev) => ({
      ...prev,
      [name]: value,
    }));
    setPagination((prev) => ({
      ...prev,
      page: 1,
    }));
  };

  // Xử lý chuyển trang trên thanh Pagination
  const handlePageChange = (nextPage) => {
    setPagination((prev) => ({
      ...prev,
      page: nextPage,
    }));
  };

  // Xử lý xác nhận chuyển trạng thái Ngừng bán (INACTIVE) trong Modal (Chỉ dành cho ADMIN)
  const handleConfirmDeactivate = async () => {
    if (!productToDeactivate || isStaff) {
      setProductToDeactivate(null);
      return;
    }

    try {
      // Trong chế độ Real API khi chưa nối endpoint PATCH /api/v1/products/{id}/status (Task T3C9C86):
      // Không tự ý xóa hoặc sửa dòng dữ liệu trong state như thể đã cập nhật thành công trên Backend.
      if (!isMockDemoActive) {
        toast.info(
          `Chức năng cập nhật trạng thái sản phẩm "${productToDeactivate.name}" thuộc phạm vi tích hợp API (Task T3C9C86). Chưa có thay đổi nào được ghi nhận.`
        );
        return;
      }

      setData((prev) =>
        prev.map((item) =>
          item.id === productToDeactivate.id
            ? { ...item, status: 'INACTIVE', activeStatus: 'INACTIVE' }
            : item
        )
      );
      toast.info(
        `Chế độ Mock Demo: Đã chuyển "${productToDeactivate.name}" sang trạng thái Ngừng bán.`
      );
    } catch {
      toast.error('Cập nhật trạng thái sản phẩm thất bại. Vui lòng thử lại.');
    } finally {
      setProductToDeactivate(null);
    }
  };

  // 2. Cấu hình cột theo đúng ProductRead schema và RBAC (STAFF chỉ xem, không có cột Giá vốn và không có cột Thao tác)
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
        render: (row) => <span>{row.category || row.category_id || '—'}</span>,
      },
      {
        key: 'sale_price_vnd',
        title: 'GIÁ BÁN (VND)',
        align: 'right',
        width: '140px',
        render: (row) => (
          <span className={styles.priceText}>
            {formatVND(row.sale_price_vnd ?? row.price)}
          </span>
        ),
      },
      {
        key: 'quantity',
        title: 'TỒN KHO',
        align: 'center',
        width: '110px',
        render: (row) => (
          <span className={styles.stockBadge}>
            {row.quantity ?? row.stock ?? 0}
          </span>
        ),
      },
      {
        key: 'stockStatus',
        title: 'TRẠNG THÁI TỒN KHO',
        align: 'center',
        width: '160px',
        render: (row) => (
          <StockStatusBadge status={row.stockStatus || row.stock_status} />
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI HOẠT ĐỘNG',
        align: 'center',
        width: '170px',
        render: (row) => (
          <ActiveStatusBadge activeStatus={row.activeStatus || row.status} />
        ),
      },
      // Cột THAO TÁC: Ẩn hoàn toàn đối với STAFF theo quy tắc RBAC
      ...(!isStaff
        ? [
            {
              key: 'actions',
              title: 'THAO TÁC',
              align: 'center',
              width: '110px',
              render: (row) => (
                <div className={styles.actionGroup}>
                  <button
                    type="button"
                    className={`${styles.iconActionBtn} ${styles.editBtn}`}
                    onClick={() =>
                      toast.info(
                        `Chức năng chỉnh sửa sản phẩm "${row.name}" thuộc Task T3C9C86.`
                      )
                    }
                    title="Sửa sản phẩm"
                    aria-label="Sửa sản phẩm"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                      <path d="m15 5 4 4" />
                    </svg>
                  </button>

                  <button
                    type="button"
                    className={`${styles.iconActionBtn} ${styles.deleteBtn}`}
                    onClick={() => setProductToDeactivate(row)}
                    title="Ngừng bán sản phẩm"
                    aria-label="Ngừng bán sản phẩm"
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
          ]
        : []),
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
          currentPage={pagination.page}
          totalPages={pagination.totalPages}
          onPageChange={handlePageChange}
        />
      </div>

      {/* 5. Modal xác nhận ngừng bán sản phẩm (Chỉ hiển thị cho ADMIN) */}
      {!isStaff && (
        <Modal
          isOpen={Boolean(productToDeactivate)}
          onClose={() => setProductToDeactivate(null)}
          title="Xác nhận ngừng bán sản phẩm"
          maxWidth="420px"
          footer={
            <>
              <button
                type="button"
                className={modalStyles.cancelBtn}
                onClick={() => setProductToDeactivate(null)}
              >
                Hủy
              </button>
              <button
                type="button"
                className={modalStyles.dangerBtn}
                onClick={handleConfirmDeactivate}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
                <span>Ngừng bán</span>
              </button>
            </>
          }
        >
          Bạn có chắc chắn muốn chuyển sản phẩm này sang trạng thái ngừng bán (INACTIVE)?
        </Modal>
      )}
    </div>
  );
}
