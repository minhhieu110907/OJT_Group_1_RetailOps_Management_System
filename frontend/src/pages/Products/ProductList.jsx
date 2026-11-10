import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import axiosClient, { getApiErrorMessage } from '../../api/axiosClient';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import styles from './ProductList.module.css';

// Hàm định dạng tiền tệ VND chuẩn
const formatVND = (amount) =>
  new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(
    Number(amount) || 0
  );

// Badge hiển thị Trạng thái tồn kho (PROD-04 / INV-04)
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

// Badge hiển thị Trạng thái hoạt động (PROD-01: ACTIVE / INACTIVE)
function ActiveStatusBadge({ activeStatus }) {
  const isSelling = activeStatus !== 'INACTIVE';
  return (
    <span
      className={`${styles.pillBadge} ${
        isSelling ? styles.badgeSuccess : styles.badgeNeutral
      }`}
    >
      {isSelling ? 'Đang bán' : 'Ngừng bán'}
    </span>
  );
}

const INITIAL_PRODUCT_FORM = {
  id: null,
  sku: '',
  name: '',
  category_id: '',
  sale_price_vnd: '',
  status: 'ACTIVE',
};

/**
 * Trang Quản lý Sản phẩm chính thức (RetailOps v1.0 — PROD-01 đến PROD-04)
 * - Tích hợp đầy đủ tính năng Quản lý sản phẩm:
 *   + Xem danh sách sản phẩm & tồn kho hiện tại (GET /api/v1/products).
 *   + Thêm sản phẩm mới (POST /api/v1/products) — Tồn kho ban đầu luôn bằng 0.
 *   + Chỉnh sửa thông tin sản phẩm (PATCH /api/v1/products/{id}).
 *   + Đổi trạng thái Đang bán <-> Ngừng bán (PATCH /api/v1/products/{id}/status).
 *   + Quản lý danh mục sản phẩm (GET/POST/PATCH /api/v1/categories).
 * - Phân quyền RBAC nghiêm ngặt:
 *   + ADMIN: Toàn quyền thao tác tạo, sửa, đổi trạng thái, quản lý danh mục.
 *   + STAFF: Chỉ xem (Read-only), ẩn hoàn toàn các nút thao tác và không hiển thị giá vốn.
 */
export default function ProductList() {
  const { user, isMockMode, canUseMock } = useAuth();
  const toast = useToast();

  const isStaff = user?.role !== 'ADMIN';
  const isMockDemoActive = Boolean(isMockMode && canUseMock);

  // 1. State tìm kiếm, lọc & phân trang (page_size theo API contract)
  const [searchParams, setSearchParams] = useState({
    keyword: '',
    categoryId: '',
    stockStatus: '',
    status: '',
  });
  const [data, setData] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [categoryRefreshTrigger, setCategoryRefreshTrigger] = useState(0);
  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    total: 0,
    totalPages: 1,
  });

  // 2. State Modal Thêm / Sửa sản phẩm (PROD-01)
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [formMode, setFormMode] = useState('create'); // 'create' | 'edit'
  const [productForm, setProductForm] = useState(INITIAL_PRODUCT_FORM);
  const [formError, setFormError] = useState('');
  const [isSubmittingForm, setIsSubmittingForm] = useState(false);

  // 3. State Modal Quản lý Danh mục (PROD-02)
  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [categoryError, setCategoryError] = useState('');
  const [isSubmittingCategory, setIsSubmittingCategory] = useState(false);

  // 4. State Modal xác nhận đổi trạng thái Ngừng bán / Kích hoạt lại
  const [productToDeactivate, setProductToDeactivate] = useState(null);

  // Lấy danh sách Danh mục từ Backend (GET /api/v1/categories)
  useEffect(() => {
    let isMounted = true;
    const loadCategories = async () => {
      try {
        const res = await axiosClient.get('/categories', {
          params: { page: 1, page_size: 100 },
        });
        if (isMounted) {
          const items = Array.isArray(res.data?.items) ? res.data.items : [];
          setCategories(items);
        }
      } catch {
        // Giữ danh sách danh mục hiện tại nếu lỗi
      }
    };

    loadCategories();
    return () => {
      isMounted = false;
    };
  }, [categoryRefreshTrigger]);

  // Map tra cứu nhanh tên danh mục theo category_id
  const categoriesMap = useMemo(() => {
    const map = {};
    categories.forEach((cat) => {
      map[cat.id] = cat.name;
    });
    return map;
  }, [categories]);

  // Gọi API lấy danh sách sản phẩm từ Backend (GET /api/v1/products)
  useEffect(() => {
    let isMounted = true;

    const loadProducts = async () => {
      setIsLoading(true);
      try {
        const res = await axiosClient.get('/products', {
          params: {
            page: pagination.page,
            page_size: pagination.page_size,
          },
        });
        if (isMounted) {
          const items = Array.isArray(res.data?.items) ? res.data.items : [];
          const total = Number(res.data?.total) || 0;
          const pageSize = Number(res.data?.page_size) || pagination.page_size;
          setData(items);
          setPagination((prev) => ({
            ...prev,
            page: Number(res.data?.page) || prev.page,
            page_size: pageSize,
            total,
            totalPages: Math.max(1, Math.ceil(total / pageSize)),
          }));
        }
      } catch (error) {
        if (isMounted) {
          toast.error(
            getApiErrorMessage(error) || 'Không thể tải danh sách sản phẩm.'
          );
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadProducts();

    return () => {
      isMounted = false;
    };
  }, [pagination.page, pagination.page_size, refreshTrigger, toast]);

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

  // Mở Modal Thêm sản phẩm mới (PROD-01)
  const handleOpenCreateModal = () => {
    const firstActiveCategory = categories.find((c) => c.status === 'ACTIVE');
    setFormMode('create');
    setFormError('');
    setProductForm({
      ...INITIAL_PRODUCT_FORM,
      category_id: firstActiveCategory ? String(firstActiveCategory.id) : '',
    });
    setIsProductModalOpen(true);
  };

  // Mở Modal Sửa sản phẩm (PROD-01)
  const handleOpenEditModal = (row) => {
    setFormMode('edit');
    setFormError('');
    setProductForm({
      id: row.id,
      sku: row.sku || '',
      name: row.name || '',
      category_id: String(row.category_id || ''),
      sale_price_vnd: String(row.sale_price_vnd || ''),
      status: row.status || 'ACTIVE',
    });
    setIsProductModalOpen(true);
  };

  // Lưu biểu mẫu Thêm mới (POST /products) hoặc Cập nhật (PATCH /products/{id})
  const handleSubmitProductForm = async (e) => {
    e.preventDefault();
    setFormError('');

    const sku = productForm.sku.trim().toUpperCase();
    const name = productForm.name.trim();
    const categoryId = Number(productForm.category_id);
    const salePriceVnd = Number(productForm.sale_price_vnd);

    if (!sku || !name || !categoryId) {
      setFormError('Vui lòng nhập đầy đủ Mã SKU, Tên sản phẩm và Danh mục.');
      return;
    }

    if (!Number.isInteger(salePriceVnd) || salePriceVnd <= 0) {
      setFormError('Giá bán phải là số nguyên dương VND lớn hơn 0 (PROD-01).');
      return;
    }

    setIsSubmittingForm(true);
    try {
      if (isMockDemoActive) {
        toast.info('Chế độ Mock Demo: Lưu sản phẩm giả lập.');
      } else {
        if (formMode === 'create') {
          await axiosClient.post('/products', {
            sku,
            name,
            category_id: categoryId,
            sale_price_vnd: salePriceVnd,
          });
          toast.success(`Đã tạo sản phẩm mới "${name}" (Tồn kho ban đầu = 0).`);
        } else {
          await axiosClient.patch(`/products/${productForm.id}`, {
            sku,
            name,
            category_id: categoryId,
            sale_price_vnd: salePriceVnd,
          });
          toast.success(`Đã cập nhật thông tin sản phẩm "${name}".`);
        }
        setRefreshTrigger((prev) => prev + 1);
      }
      setIsProductModalOpen(false);
    } catch (error) {
      setFormError(
        getApiErrorMessage(error) || 'Không thể lưu sản phẩm. Vui lòng kiểm tra lại.'
      );
    } finally {
      setIsSubmittingForm(false);
    }
  };

  // Xác nhận đổi trạng thái Ngừng bán / Kích hoạt lại (PATCH /products/{id}/status)
  const handleConfirmDeactivate = async () => {
    if (!productToDeactivate || isStaff) {
      setProductToDeactivate(null);
      return;
    }

    try {
      if (isMockDemoActive) {
        setData((prev) =>
          prev.map((item) =>
            item.id === productToDeactivate.id
              ? { ...item, status: 'INACTIVE', activeStatus: 'INACTIVE' }
              : item
          )
        );
        toast.info(
          `Chế độ Mock: Đã chuyển "${productToDeactivate.name}" sang trạng thái Ngừng bán.`
        );
      } else {
        const nextStatus =
          productToDeactivate.status === 'INACTIVE' ? 'ACTIVE' : 'INACTIVE';
        await axiosClient.patch(`/products/${productToDeactivate.id}/status`, {
          status: nextStatus,
        });
        toast.success(
          nextStatus === 'INACTIVE'
            ? `Đã ngừng bán sản phẩm "${productToDeactivate.name}".`
            : `Đã kích hoạt lại sản phẩm "${productToDeactivate.name}".`
        );
        setRefreshTrigger((prev) => prev + 1);
      }
    } catch (error) {
      toast.error(
        getApiErrorMessage(error) ||
          'Cập nhật trạng thái sản phẩm thất bại. Vui lòng thử lại.'
      );
    } finally {
      setProductToDeactivate(null);
    }
  };

  // Tạo danh mục mới (POST /categories - PROD-02)
  const handleCreateCategory = async (e) => {
    e.preventDefault();
    setCategoryError('');
    const trimmed = newCategoryName.trim();
    if (!trimmed) {
      setCategoryError('Vui lòng nhập tên danh mục.');
      return;
    }

    setIsSubmittingCategory(true);
    try {
      await axiosClient.post('/categories', { name: trimmed });
      setNewCategoryName('');
      setCategoryRefreshTrigger((prev) => prev + 1);
      toast.success(`Đã thêm danh mục "${trimmed}".`);
    } catch (error) {
      setCategoryError(
        getApiErrorMessage(error) || 'Thêm danh mục thất bại.'
      );
    } finally {
      setIsSubmittingCategory(false);
    }
  };

  // Lọc dữ liệu client-side theo từ khóa, danh mục, tồn kho và trạng thái hoạt động
  const filteredData = useMemo(() => {
    return data.filter((item) => {
      if (searchParams.keyword) {
        const kw = searchParams.keyword.trim().toLowerCase();
        const skuMatch = String(item.sku || '').toLowerCase().includes(kw);
        const nameMatch = String(item.name || '').toLowerCase().includes(kw);
        if (!skuMatch && !nameMatch) return false;
      }
      if (searchParams.categoryId) {
        if (String(item.category_id) !== String(searchParams.categoryId)) {
          return false;
        }
      }
      if (searchParams.status) {
        const itemStatus = item.status || item.activeStatus;
        if (itemStatus !== searchParams.status) return false;
      }
      if (searchParams.stockStatus) {
        const qty = Number(item.quantity ?? item.stock ?? 0);
        if (searchParams.stockStatus === 'OUT_OF_STOCK' && qty > 0) return false;
        if (searchParams.stockStatus === 'LOW_STOCK' && (qty <= 0 || qty > 5))
          return false;
        if (searchParams.stockStatus === 'IN_STOCK' && qty <= 5) return false;
      }
      return true;
    });
  }, [data, searchParams]);

  // Cấu hình cột hiển thị theo chuẩn ProductRead và an ninh RBAC
  const columns = useMemo(() => {
    const baseColumns = [
      {
        key: 'sku',
        title: 'MÃ SKU',
        width: '120px',
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
        render: (row) => (
          <span>
            {row.category ||
              categoriesMap[row.category_id] ||
              (row.category_id ? `Danh mục #${row.category_id}` : '—')}
          </span>
        ),
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
        render: (row) => {
          let calcStatus = 'IN_STOCK';
          const qty = Number(row.quantity ?? row.stock ?? 0);
          if (qty <= 0) calcStatus = 'OUT_OF_STOCK';
          else if (qty <= 5) calcStatus = 'LOW_STOCK';
          return (
            <StockStatusBadge
              status={row.stockStatus || row.stock_status || calcStatus}
            />
          );
        },
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
      // Cột THAO TÁC: Chỉ hiển thị cho Quản trị viên (ADMIN), ẩn hoàn toàn với STAFF
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
                    onClick={() => handleOpenEditModal(row)}
                    title="Chỉnh sửa sản phẩm"
                    aria-label="Chỉnh sửa sản phẩm"
                  >
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
                      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                      <path d="m15 5 4 4" />
                    </svg>
                  </button>

                  <button
                    type="button"
                    className={`${styles.iconActionBtn} ${styles.deleteBtn}`}
                    onClick={() => setProductToDeactivate(row)}
                    title={
                      row.status === 'INACTIVE'
                        ? 'Kích hoạt lại bán hàng'
                        : 'Ngừng bán sản phẩm'
                    }
                    aria-label="Đổi trạng thái sản phẩm"
                  >
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
  }, [isStaff, categoriesMap]);

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header trang */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Quản lý sản phẩm</h1>
          <p className={styles.pageSubtitle}>
            Danh mục sản phẩm kinh doanh và theo dõi tồn kho tại cửa hàng
          </p>
        </div>

        {!isStaff ? (
          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.secondaryBtn}
              onClick={() => setIsCategoryModalOpen(true)}
            >
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
                <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                <line x1="7" y1="7" x2="7.01" y2="7" />
              </svg>
              <span>Quản lý Danh mục</span>
            </button>

            <button
              type="button"
              className={styles.primaryBtn}
              onClick={handleOpenCreateModal}
            >
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
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span> Thêm sản phẩm</span>
            </button>
          </div>
        ) : (
          <span className={styles.readOnlyTag}>
            Chế độ nhân viên (Tra cứu dữ liệu)
          </span>
        )}
      </div>

      {/* 2. Thanh tìm kiếm & Bộ lọc */}
      <div className={styles.filterCard}>
        <div className={styles.searchWrap}>
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
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>

          <select
            name="stockStatus"
            value={searchParams.stockStatus}
            onChange={handleFilterChange}
            className={styles.filterSelect}
          >
            <option value="">Tất cả trạng thái tồn kho</option>
            <option value="IN_STOCK">Còn hàng (&gt;5)</option>
            <option value="LOW_STOCK">Tồn thấp (1-5)</option>
            <option value="OUT_OF_STOCK">Hết hàng (0)</option>
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
        data={filteredData}
        rowKey="id"
        isLoading={isLoading}
        emptyText="Chưa có dữ liệu sản phẩm. Bấm '+ Thêm sản phẩm' để tạo mới."
      />

      {/* 4. Phân trang */}
      <div className={styles.paginationRow}>
        <Pagination
          currentPage={pagination.page}
          totalPages={pagination.totalPages}
          onPageChange={handlePageChange}
        />
      </div>

      {/* 5. Modal Thêm / Chỉnh sửa sản phẩm (Chỉ dành cho ADMIN) */}
      {!isStaff && (
        <Modal
          isOpen={isProductModalOpen}
          onClose={() => setIsProductModalOpen(false)}
          title={
            formMode === 'create'
              ? 'Thêm sản phẩm mới'
              : `Chỉnh sửa sản phẩm: ${productForm.sku}`
          }
          maxWidth="540px"
          footer={
            <>
              <button
                type="button"
                className={modalStyles.cancelBtn}
                onClick={() => setIsProductModalOpen(false)}
                disabled={isSubmittingForm}
              >
                Hủy
              </button>
              <button
                type="button"
                className={modalStyles.confirmBtn}
                onClick={handleSubmitProductForm}
                disabled={isSubmittingForm}
              >
                {isSubmittingForm
                  ? 'Đang lưu...'
                  : formMode === 'create'
                  ? 'Thêm sản phẩm'
                  : 'Lưu thay đổi'}
              </button>
            </>
          }
        >
          <form onSubmit={handleSubmitProductForm} className={styles.modalForm}>
            {formError && <div className={styles.formErrorBox}>{formError}</div>}

            <div className={styles.formRowTwoCols}>
              <div className={styles.formField}>
                <label className={styles.formLabel}>
                  MÃ SKU <span className={styles.requiredMark}>*</span>
                </label>
                <input
                  type="text"
                  value={productForm.sku}
                  onChange={(e) =>
                    setProductForm((prev) => ({
                      ...prev,
                      sku: e.target.value.toUpperCase(),
                    }))
                  }
                  placeholder="VD: COCA-330ML"
                  className={styles.formInput}
                  disabled={formMode === 'edit'}
                  maxLength={64}
                  required
                />
              </div>

              <div className={styles.formField}>
                <label className={styles.formLabel}>
                  DANH MỤC <span className={styles.requiredMark}>*</span>
                </label>
                <select
                  value={productForm.category_id}
                  onChange={(e) =>
                    setProductForm((prev) => ({
                      ...prev,
                      category_id: e.target.value,
                    }))
                  }
                  className={styles.formSelect}
                  required
                >
                  <option value="">-- Chọn danh mục --</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className={styles.formField}>
              <label className={styles.formLabel}>
                TÊN SẢN PHẨM <span className={styles.requiredMark}>*</span>
              </label>
              <input
                type="text"
                value={productForm.name}
                onChange={(e) =>
                  setProductForm((prev) => ({
                    ...prev,
                    name: e.target.value,
                  }))
                }
                placeholder="VD: Nước giải khát Coca Cola lon 330ml"
                className={styles.formInput}
                maxLength={160}
                required
              />
            </div>

            <div className={styles.formField}>
              <label className={styles.formLabel}>
                GIÁ BÁN HIỆN TẠI (VND){' '}
                <span className={styles.requiredMark}>*</span>
              </label>
              <input
                type="number"
                value={productForm.sale_price_vnd}
                onChange={(e) =>
                  setProductForm((prev) => ({
                    ...prev,
                    sale_price_vnd: e.target.value,
                  }))
                }
                placeholder="VD: 10000"
                min="1"
                step="1"
                className={styles.formInput}
                required
              />
            </div>

            {formMode === 'create' && (
              <div className={styles.formHintBox}>
                <strong>Quy tắc nghiệp vụ RetailOps (PROD-01):</strong> Sản phẩm
                mới tạo sẽ tự động khởi tạo tồn kho bằng 0. Số lượng tồn kho chỉ
                được tăng khi Admin xác nhận Phiếu nhập hàng (Purchasing) hoặc
                kiểm kê kho thực tế (Inventory Adjustment).
              </div>
            )}
          </form>
        </Modal>
      )}

      {/* 6. Modal Quản lý Danh mục (Chỉ dành cho ADMIN) */}
      {!isStaff && (
        <Modal
          isOpen={isCategoryModalOpen}
          onClose={() => setIsCategoryModalOpen(false)}
          title="Quản lý Danh mục Sản phẩm"
          maxWidth="480px"
          footer={
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={() => setIsCategoryModalOpen(false)}
            >
              Đóng
            </button>
          }
        >
          <div className={styles.modalForm}>
            {categoryError && (
              <div className={styles.formErrorBox}>{categoryError}</div>
            )}

            <form
              onSubmit={handleCreateCategory}
              className={styles.categoryInlineForm}
            >
              <input
                type="text"
                value={newCategoryName}
                onChange={(e) => setNewCategoryName(e.target.value)}
                placeholder="Tên danh mục mới..."
                className={styles.formInput}
                maxLength={120}
              />
              <button
                type="submit"
                className={styles.primaryBtn}
                disabled={isSubmittingCategory}
              >
                {isSubmittingCategory ? 'Đang thêm...' : 'Thêm'}
              </button>
            </form>

            <div className={styles.categoryList}>
              {categories.map((cat) => (
                <div key={cat.id} className={styles.categoryItem}>
                  <span className={styles.categoryItemName}>{cat.name}</span>
                  <span
                    className={`${styles.pillBadge} ${
                      cat.status === 'ACTIVE'
                        ? styles.badgeSuccess
                        : styles.badgeNeutral
                    }`}
                  >
                    {cat.status === 'ACTIVE' ? 'Hoạt động' : 'Ngừng'}
                  </span>
                </div>
              ))}
              {categories.length === 0 && (
                <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>
                  Chưa có danh mục nào. Hãy thêm danh mục đầu tiên.
                </p>
              )}
            </div>
          </div>
        </Modal>
      )}

      {/* 7. Modal xác nhận chuyển trạng thái sản phẩm */}
      {!isStaff && (
        <Modal
          isOpen={Boolean(productToDeactivate)}
          onClose={() => setProductToDeactivate(null)}
          title="Xác nhận trạng thái sản phẩm"
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
                className={
                  productToDeactivate?.status === 'INACTIVE'
                    ? modalStyles.confirmBtn
                    : modalStyles.dangerBtn
                }
                onClick={handleConfirmDeactivate}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
                <span>
                  {productToDeactivate?.status === 'INACTIVE'
                    ? 'Kích hoạt lại'
                    : 'Ngừng bán'}
                </span>
              </button>
            </>
          }
        >
          Bạn có chắc chắn muốn chuyển sản phẩm{' '}
          <strong>&quot;{productToDeactivate?.name}&quot;</strong> sang trạng
          thái{' '}
          <strong>
            {productToDeactivate?.status === 'INACTIVE'
              ? 'Đang bán '
              : 'Ngừng bán'}
          </strong>
          ?
        </Modal>
      )}
    </div>
  );
}
