import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { productsApi } from '../../api/productsApi';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import styles from './ProductList.module.css';

// Định dạng tiền tệ VND chuẩn
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
 *   + Thêm sản phẩm mới (POST /api/v1/products) — Tồn kho ban đầu luôn bằng 0 (PROD-01).
 *   + Chỉnh sửa thông tin sản phẩm (PATCH /api/v1/products/{id}).
 *   + Đổi trạng thái Đang bán <-> Ngừng bán (PATCH /api/v1/products/{id}/status).
 *   + Quản lý danh mục sản phẩm (GET/POST/PATCH /api/v1/categories - PROD-02).
 * - Real / Mock Strategy:
 *   + Trong Mock mode: xử lý dữ liệu qua adapter, lọc trên toàn bộ dataset trước khi phân trang.
 *   + Trong Real mode: kết nối trực tiếp FastAPI Backend và xác thực schema ProductRead nghiêm ngặt.
 * - Phân quyền RBAC nghiêm ngặt:
 *   + ADMIN: Toàn quyền thao tác tạo, sửa, đổi trạng thái, quản lý danh mục.
 *   + STAFF: Chỉ xem (Read-only), ẩn hoàn toàn các nút thao tác và không hiển thị giá vốn.
 */
export default function ProductList() {
  const { user, isMockMode, canUseMock } = useAuth();
  const toast = useToast();

  const isStaff = user?.role !== 'ADMIN';
  const isMockDemoActive = Boolean(isMockMode && canUseMock);

  // 1. State tìm kiếm, lọc & phân trang
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
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [editingCategoryName, setEditingCategoryName] = useState('');
  const [categoryError, setCategoryError] = useState('');
  const [isSubmittingCategory, setIsSubmittingCategory] = useState(false);

  // 4. State Modal xác nhận đổi trạng thái Ngừng bán / Kích hoạt lại
  const [productToDeactivate, setProductToDeactivate] = useState(null);

  // Lấy danh sách Danh mục qua adapter
  useEffect(() => {
    let isMounted = true;
    const loadCategories = async () => {
      try {
        const res = await productsApi.getCategories({
          isMockMode: isMockDemoActive,
          page: 1,
          pageSize: 100,
        });
        if (isMounted) {
          setCategories(res.items || []);
        }
      } catch {
        // Giữ danh sách danh mục hiện tại nếu xảy ra lỗi
      }
    };

    loadCategories();
    return () => {
      isMounted = false;
    };
  }, [categoryRefreshTrigger, isMockDemoActive]);

  // Map tra cứu nhanh tên danh mục theo category_id
  const categoriesMap = useMemo(() => {
    const map = {};
    categories.forEach((cat) => {
      map[cat.id] = cat.name;
    });
    return map;
  }, [categories]);

  // Lấy danh sách sản phẩm qua adapter (lọc & phân trang đồng bộ)
  useEffect(() => {
    let isMounted = true;

    const loadProducts = async () => {
      setIsLoading(true);
      try {
        const res = await productsApi.getProducts({
          isMockMode: isMockDemoActive,
          page: pagination.page,
          pageSize: pagination.page_size,
          keyword: searchParams.keyword,
          categoryId: searchParams.categoryId,
          status: searchParams.status,
          stockStatus: searchParams.stockStatus,
        });

        if (isMounted) {
          setData(res.items || []);
          setPagination((prev) => ({
            ...prev,
            page: res.page,
            page_size: res.page_size,
            total: res.total,
            totalPages: Math.max(1, Math.ceil(res.total / res.page_size)),
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
  }, [
    pagination.page,
    pagination.page_size,
    searchParams.keyword,
    searchParams.categoryId,
    searchParams.status,
    searchParams.stockStatus,
    refreshTrigger,
    isMockDemoActive,
    toast,
  ]);

  // Xử lý thay đổi bộ lọc tìm kiếm
  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setSearchParams((prev) => ({
      ...prev,
      [name]: value,
    }));
    setPagination((prev) => ({
      ...prev,
      page: 1, // Reset về trang 1 khi thay đổi điều kiện lọc
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

  // Lưu biểu mẫu Thêm mới (POST) hoặc Cập nhật (PATCH)
  const handleSubmitProductForm = async (e) => {
    e.preventDefault();
    if (isSubmittingForm) return;
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
      if (formMode === 'create') {
        await productsApi.createProduct({
          isMockMode: isMockDemoActive,
          data: {
            sku,
            name,
            category_id: categoryId,
            sale_price_vnd: salePriceVnd,
          },
        });
        toast.success(
          isMockDemoActive
            ? `[Mock] Đã tạo sản phẩm "${name}" thành công!`
            : `Đã tạo sản phẩm "${name}" thành công!`
        );
      } else {
        await productsApi.updateProduct({
          isMockMode: isMockDemoActive,
          id: productForm.id,
          data: {
            sku,
            name,
            category_id: categoryId,
            sale_price_vnd: salePriceVnd,
          },
        });
        toast.success(
          isMockDemoActive
            ? `[Mock] Đã cập nhật thông tin sản phẩm "${name}"!`
            : `Đã cập nhật thông tin sản phẩm "${name}"!`
        );
      }
      setIsProductModalOpen(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (error) {
      setFormError(
        getApiErrorMessage(error) ||
          (formMode === 'create'
            ? 'Không thể tạo sản phẩm. Vui lòng kiểm tra lại thông tin.'
            : 'Không thể cập nhật sản phẩm. Vui lòng thử lại.')
      );
    } finally {
      setIsSubmittingForm(false);
    }
  };

  // Xác nhận đổi trạng thái Đang bán <-> Ngừng bán (PATCH /status)
  const handleConfirmDeactivate = async () => {
    if (!productToDeactivate) return;

    try {
      const nextStatus =
        productToDeactivate.status === 'INACTIVE' ? 'ACTIVE' : 'INACTIVE';
      await productsApi.updateProductStatus({
        isMockMode: isMockDemoActive,
        id: productToDeactivate.id,
        status: nextStatus,
      });
      toast.success(
        nextStatus === 'INACTIVE'
          ? `Đã chuyển sản phẩm "${productToDeactivate.name}" sang trạng thái Ngừng bán.`
          : `Đã kích hoạt lại sản phẩm "${productToDeactivate.name}".`
      );
      setRefreshTrigger((prev) => prev + 1);
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
    if (isSubmittingCategory) return;
    setCategoryError('');
    const trimmed = newCategoryName.trim();
    if (!trimmed) {
      setCategoryError('Vui lòng nhập tên danh mục.');
      return;
    }

    setIsSubmittingCategory(true);
    try {
      await productsApi.createCategory({
        isMockMode: isMockDemoActive,
        name: trimmed,
      });
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

  // Chỉnh sửa tên danh mục (PATCH /categories/{id} - PROD-02)
  const handleSaveEditCategory = async (id) => {
    const trimmed = editingCategoryName.trim();
    if (!trimmed) {
      setCategoryError('Tên danh mục không được để trống.');
      return;
    }
    setIsSubmittingCategory(true);
    try {
      await productsApi.updateCategory({
        isMockMode: isMockDemoActive,
        id,
        name: trimmed,
      });
      setEditingCategoryId(null);
      setEditingCategoryName('');
      setCategoryRefreshTrigger((prev) => prev + 1);
      toast.success('Đã cập nhật tên danh mục.');
    } catch (error) {
      setCategoryError(
        getApiErrorMessage(error) || 'Cập nhật danh mục thất bại.'
      );
    } finally {
      setIsSubmittingCategory(false);
    }
  };

  // Chuyển trạng thái danh mục ACTIVE / INACTIVE (PATCH /categories/{id}/status - PROD-02)
  const handleToggleCategoryStatus = async (cat) => {
    const nextStatus = cat.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    setIsSubmittingCategory(true);
    try {
      await productsApi.updateCategoryStatus({
        isMockMode: isMockDemoActive,
        id: cat.id,
        status: nextStatus,
      });
      setCategoryRefreshTrigger((prev) => prev + 1);
      toast.success(
        nextStatus === 'ACTIVE'
          ? `Đã kích hoạt danh mục "${cat.name}".`
          : `Đã ngừng hoạt động danh mục "${cat.name}".`
      );
    } catch (error) {
      setCategoryError(
        getApiErrorMessage(error) || 'Cập nhật trạng thái danh mục thất bại.'
      );
    } finally {
      setIsSubmittingCategory(false);
    }
  };

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
        render: (row) => {
          // Xác thực schema ProductRead: KHÔNG mặc định missing quantity thành 0
          if (typeof row.quantity !== 'number' || Number.isNaN(row.quantity)) {
            return (
              <span
                className={styles.corruptedBadge}
                title="Dữ liệu tồn kho không hợp lệ từ máy chủ"
              >
                N/A
              </span>
            );
          }
          return <span className={styles.stockBadge}>{row.quantity}</span>;
        },
      },
      {
        key: 'stockStatus',
        title: 'TRẠNG THÁI TỒN KHO',
        align: 'center',
        width: '160px',
        render: (row) => {
          if (typeof row.quantity !== 'number' || Number.isNaN(row.quantity)) {
            return <span className={styles.badgeNeutral}>Không xác định</span>;
          }
          let calcStatus = 'IN_STOCK';
          if (row.quantity <= 0) calcStatus = 'OUT_OF_STOCK';
          else if (row.quantity <= 5) calcStatus = 'LOW_STOCK';
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
          <ActiveStatusBadge activeStatus={row.status || row.activeStatus} />
        ),
      },
    ];

    // CHỈ ADMIN mới có cột THAO TÁC. Nhân viên STAFF không có quyền sửa / ngừng bán.
    if (!isStaff) {
      baseColumns.push({
        key: 'actions',
        title: 'THAO TÁC',
        align: 'center',
        width: '160px',
        render: (row) => (
          <div className={styles.actionButtonGroup}>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={() => handleOpenEditModal(row)}
              title="Chỉnh sửa sản phẩm"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              <span>Sửa</span>
            </button>

            <button
              type="button"
              className={`${styles.actionBtn} ${
                row.status === 'INACTIVE'
                  ? styles.actionBtnActive
                  : styles.actionBtnDanger
              }`}
              onClick={() => setProductToDeactivate(row)}
              title={
                row.status === 'INACTIVE'
                  ? 'Kích hoạt lại kinh doanh'
                  : 'Ngừng kinh doanh sản phẩm'
              }
            >
              {row.status === 'INACTIVE' ? (
                <>
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>Bật lại</span>
                </>
              ) : (
                <>
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                  <span>Ngừng</span>
                </>
              )}
            </button>
          </div>
        ),
      });
    }

    return baseColumns;
  }, [categoriesMap, isStaff]);

  return (
    <div className={styles.container}>
      {/* 1. Header Trang & Nút Thao Tác (ADMIN ONLY) */}
      <div className={styles.header}>
        <div className={styles.headerTitleGroup}>
          <div className={styles.titleWithBadge}>
            <h1 className={styles.title}>Quản lý Sản phẩm</h1>
            {isMockDemoActive ? (
              <span className={styles.mockBadgeActive} title="Chế độ Mock Demo">
                Mock Mode
              </span>
            ) : (
              <span className={styles.realApiBadge} title="Kết nối API thật">
                Real API
              </span>
            )}
          </div>
          <p className={styles.subtitle}>
            {isStaff
              ? 'Tra cứu danh mục, giá bán và tình trạng tồn kho sản phẩm.'
              : 'Theo dõi tồn kho, quản lý danh mục và điều chỉnh trạng thái sản phẩm.'}
          </p>
        </div>

        {/* Cụm nút thao tác (ADMIN mới có quyền Thêm sản phẩm / Quản lý Danh mục) */}
        {!isStaff && (
          <div className={styles.actionButtons}>
            <button
              type="button"
              className={styles.secondaryBtn}
              onClick={() => {
                setCategoryError('');
                setIsCategoryModalOpen(true);
              }}
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
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              <span>Quản lý danh mục</span>
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
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>Thêm sản phẩm</span>
            </button>
          </div>
        )}
      </div>

      {/* 2. Thanh Tìm Kiếm & Bộ Lọc Đa Điều Kiện */}
      <div className={styles.filterBar}>
        <div className={styles.searchBox}>
          <svg
            className={styles.searchIcon}
            width="18"
            height="18"
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
          <input
            type="text"
            name="keyword"
            value={searchParams.keyword}
            onChange={handleFilterChange}
            placeholder="Tìm theo Mã SKU hoặc Tên sản phẩm..."
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
        data={data}
        rowKey="id"
        isLoading={isLoading}
        emptyText="Không tìm thấy sản phẩm phù hợp với bộ lọc."
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
                  disabled={isSubmittingForm}
                  maxLength={64}
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
                  className={styles.formInput}
                  disabled={isSubmittingForm}
                >
                  <option value="">-- Chọn danh mục --</option>
                  {categories
                    .filter((c) => c.status === 'ACTIVE')
                    .map((cat) => (
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
                placeholder="VD: Nước ngọt Coca Cola lon 330ml"
                className={styles.formInput}
                disabled={isSubmittingForm}
                maxLength={160}
              />
            </div>

            <div className={styles.formRowTwoCols}>
              <div className={styles.formField}>
                <label className={styles.formLabel}>
                  GIÁ BÁN (VND) <span className={styles.requiredMark}>*</span>
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
                  className={styles.formInput}
                  disabled={isSubmittingForm}
                  min={1}
                />
              </div>

              <div className={styles.formField}>
                <label className={styles.formLabel}>TRẠNG THÁI</label>
                <select
                  value={productForm.status}
                  onChange={(e) =>
                    setProductForm((prev) => ({
                      ...prev,
                      status: e.target.value,
                    }))
                  }
                  className={styles.formInput}
                  disabled={isSubmittingForm || formMode === 'create'}
                >
                  <option value="ACTIVE">Đang bán (ACTIVE)</option>
                  <option value="INACTIVE">Ngừng bán (INACTIVE)</option>
                </select>
              </div>
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

      {/* 6. Modal Quản lý Danh mục (Chỉ dành cho ADMIN - PROD-02) */}
      {!isStaff && (
        <Modal
          isOpen={isCategoryModalOpen}
          onClose={() => {
            setIsCategoryModalOpen(false);
            setEditingCategoryId(null);
            setCategoryError('');
          }}
          title="Quản lý Danh mục Sản phẩm (PROD-02)"
          maxWidth="520px"
          footer={
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={() => {
                setIsCategoryModalOpen(false);
                setEditingCategoryId(null);
                setCategoryError('');
              }}
            >
              Đóng
            </button>
          }
        >
          <div className={styles.modalForm}>
            {categoryError && (
              <div className={styles.formErrorBox}>{categoryError}</div>
            )}

            {/* Form tạo mới danh mục */}
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
                disabled={isSubmittingCategory}
              />
              <button
                type="submit"
                className={styles.primaryBtn}
                disabled={isSubmittingCategory}
              >
                {isSubmittingCategory ? 'Đang thêm...' : 'Thêm'}
              </button>
            </form>

            {/* Danh sách danh mục hiện có + Chỉnh sửa / Đổi trạng thái */}
            <div className={styles.categoryList}>
              {categories.map((cat) => (
                <div key={cat.id} className={styles.categoryItem}>
                  {editingCategoryId === cat.id ? (
                    <div style={{ display: 'flex', gap: '6px', flex: 1 }}>
                      <input
                        type="text"
                        value={editingCategoryName}
                        onChange={(e) => setEditingCategoryName(e.target.value)}
                        className={styles.formInput}
                        maxLength={120}
                        style={{ padding: '4px 8px', fontSize: '13px' }}
                        autoFocus
                      />
                      <button
                        type="button"
                        className={`${styles.categorySmallBtn} ${styles.categorySmallBtnPrimary}`}
                        onClick={() => handleSaveEditCategory(cat.id)}
                        disabled={isSubmittingCategory}
                      >
                        Lưu
                      </button>
                      <button
                        type="button"
                        className={styles.categorySmallBtn}
                        onClick={() => setEditingCategoryId(null)}
                      >
                        Hủy
                      </button>
                    </div>
                  ) : (
                    <>
                      <span className={styles.categoryItemName}>{cat.name}</span>
                      <div className={styles.categoryActions}>
                        <span
                          className={`${styles.pillBadge} ${
                            cat.status === 'ACTIVE'
                              ? styles.badgeSuccess
                              : styles.badgeNeutral
                          }`}
                        >
                          {cat.status === 'ACTIVE' ? 'Hoạt động' : 'Ngừng'}
                        </span>
                        <button
                          type="button"
                          className={styles.categorySmallBtn}
                          onClick={() => {
                            setEditingCategoryId(cat.id);
                            setEditingCategoryName(cat.name);
                            setCategoryError('');
                          }}
                          disabled={isSubmittingCategory}
                          title="Sửa tên danh mục"
                        >
                          Sửa
                        </button>
                        <button
                          type="button"
                          className={styles.categorySmallBtn}
                          onClick={() => handleToggleCategoryStatus(cat)}
                          disabled={isSubmittingCategory}
                          title={
                            cat.status === 'ACTIVE'
                              ? 'Ngừng hoạt động danh mục'
                              : 'Kích hoạt lại danh mục'
                          }
                        >
                          {cat.status === 'ACTIVE' ? 'Ngừng' : 'Bật'}
                        </button>
                      </div>
                    </>
                  )}
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
              ? 'Đang bán (ACTIVE)'
              : 'Ngừng bán (INACTIVE)'}
          </strong>
          ?
        </Modal>
      )}
    </div>
  );
}
