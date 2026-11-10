import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { parseAndValidateSalePriceVnd, productsApi } from '../../api/productsApi';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import styles from './ProductList.module.css';

// Định dạng tiền tệ kiểu "28.000 đ" chuẩn giao diện
const formatVND = (amount) => {
  const num = Number(amount) || 0;
  return `${num.toLocaleString('vi-VN')} đ`;
};

const INITIAL_PRODUCT_FORM = {
  id: null,
  sku: '',
  name: '',
  category_id: '',
  sale_price_vnd: '',
  status: 'ACTIVE',
};

export default function ProductList() {
  const { user } = useAuth();
  const toast = useToast();

  const isStaff = user?.role !== 'ADMIN';

  // 1. State tìm kiếm, lọc, sắp xếp & phân trang
  const [searchParams, setSearchParams] = useState({
    keyword: '',
    categoryId: '',
    status: '',
    sort: '',
  });
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [data, setData] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    total: 0,
    totalPages: 1,
  });

  // Chống race condition / stale response khi gõ nhanh hoặc chuyển trang
  const requestIdRef = useRef(0);
  const categoryRequestIdRef = useRef(0);

  // Debounce tìm kiếm từ khóa 300ms tránh spam API liên tục
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedKeyword(searchParams.keyword.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchParams.keyword]);

  // 2. State Modal Thêm / Sửa sản phẩm
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [formMode, setFormMode] = useState('create'); // 'create' | 'edit'
  const [productForm, setProductForm] = useState(INITIAL_PRODUCT_FORM);
  const [formError, setFormError] = useState('');
  const [isSubmittingForm, setIsSubmittingForm] = useState(false);

  // 3. State Modal xác nhận ngừng kích hoạt / kích hoạt lại
  const [productToDeactivate, setProductToDeactivate] = useState(null);

  // 4. State Modal Quản lý danh mục (PROD-02)
  const [isCategoryModalOpen, setIsCategoryModalOpen] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [editingCategoryName, setEditingCategoryName] = useState('');
  const [categoryFormError, setCategoryFormError] = useState('');
  const [isSubmittingCategory, setIsSubmittingCategory] = useState(false);

  // Lấy danh sách Danh mục
  useEffect(() => {
    const currentId = ++categoryRequestIdRef.current;
    const loadCategories = async () => {
      try {
        const res = await productsApi.getCategories({
          page: 1,
          pageSize: 100,
        });
        if (currentId === categoryRequestIdRef.current) {
          setCategories(res.items || []);
        }
      } catch {
        // Giữ nguyên categories
      }
    };

    loadCategories();
    return () => {
      categoryRequestIdRef.current += 1;
    };
  }, []);

  // Map tra cứu tên danh mục
  const categoriesMap = useMemo(() => {
    const map = {};
    categories.forEach((cat) => {
      map[cat.id] = cat.name;
    });
    return map;
  }, [categories]);

  // Lấy danh sách sản phẩm (chống stale response và race condition qua requestIdRef)
  useEffect(() => {
    const currentRequestId = ++requestIdRef.current;

    const loadProducts = async () => {
      setIsLoading(true);
      try {
        const res = await productsApi.getProducts({
          page: pagination.page,
          pageSize: pagination.page_size,
          keyword: debouncedKeyword,
          categoryId: searchParams.categoryId,
          status: searchParams.status,
          sort: searchParams.sort,
        });

        if (currentRequestId === requestIdRef.current) {
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
        if (currentRequestId === requestIdRef.current) {
          toast.error(
            getApiErrorMessage(error) || 'Không thể tải danh sách sản phẩm.'
          );
        }
      } finally {
        if (currentRequestId === requestIdRef.current) {
          setIsLoading(false);
        }
      }
    };

    loadProducts();

    return () => {
      // Hủy hiệu lực của request đang gửi nếu dependency thay đổi hoặc unmount
      requestIdRef.current += 1;
    };
  }, [
    pagination.page,
    pagination.page_size,
    debouncedKeyword,
    searchParams.categoryId,
    searchParams.status,
    searchParams.sort,
    refreshTrigger,
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
      page: 1,
    }));
  };

  // Đặt lại bộ lọc về mặc định
  const handleResetFilters = () => {
    setSearchParams({
      keyword: '',
      categoryId: '',
      status: '',
      sort: '',
    });
    setPagination((prev) => ({
      ...prev,
      page: 1,
    }));
  };

  // Chuyển trang
  const handlePageChange = (nextPage) => {
    setPagination((prev) => ({
      ...prev,
      page: nextPage,
    }));
  };

  // Mở modal Thêm mới
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

  // Mở modal Sửa
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

  // Submit Form Thêm/Sửa
  const handleSubmitProductForm = async (e) => {
    e.preventDefault();
    if (isSubmittingForm) return;
    setFormError('');

    const sku = productForm.sku.trim().toUpperCase();
    const name = productForm.name.trim();
    const categoryId = Number(productForm.category_id);

    // Chặt chẽ: Validate giá bán VND qua validator chuyên dụng (FIX-04)
    // Ngăn chặn 10,5 biến thành 105; chỉ chấp nhận số nguyên dương lớn hơn 0
    const priceValidation = parseAndValidateSalePriceVnd(productForm.sale_price_vnd);
    if (!priceValidation.isValid) {
      setFormError(priceValidation.error);
      return;
    }
    const salePriceVnd = priceValidation.value;

    if (formMode === 'create' && !sku) {
      setFormError('Vui lòng nhập Mã SKU cho sản phẩm mới.');
      return;
    }

    if (!name || !categoryId) {
      setFormError('Vui lòng nhập đầy đủ Tên sản phẩm và Danh mục.');
      return;
    }

    setIsSubmittingForm(true);
    try {
      if (formMode === 'create') {
        await productsApi.createProduct({
          data: {
            sku,
            name,
            category_id: categoryId,
            sale_price_vnd: salePriceVnd,
          },
        });
        toast.success(`Đã thêm sản phẩm "${name}" thành công!`);
      } else {
        // PROD-01 & Backend contract:
        // Cập nhật thông tin sản phẩm KHÔNG gửi status (status dùng PATCH /products/{id}/status)
        // và KHÔNG sửa mã SKU khi đang cập nhật.
        await productsApi.updateProduct({
          id: productForm.id,
          data: {
            name,
            category_id: categoryId,
            sale_price_vnd: salePriceVnd,
          },
        });
        toast.success(`Đã lưu thay đổi cho "${name}"!`);
      }
      setIsProductModalOpen(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (error) {
      setFormError(
        getApiErrorMessage(error) || 'Thao tác không thành công. Vui lòng kiểm tra lại.'
      );
    } finally {
      setIsSubmittingForm(false);
    }
  };

  // Xác nhận Đổi trạng thái (Ngừng kích hoạt / Kích hoạt lại)
  const handleConfirmDeactivate = async () => {
    if (!productToDeactivate) return;

    try {
      const nextStatus =
        productToDeactivate.status === 'INACTIVE' ? 'ACTIVE' : 'INACTIVE';
      await productsApi.updateProductStatus({
        id: productToDeactivate.id,
        status: nextStatus,
      });
      toast.success(
        nextStatus === 'INACTIVE'
          ? `Đã ngừng kinh doanh "${productToDeactivate.name}".`
          : `Đã kích hoạt lại "${productToDeactivate.name}".`
      );
      setRefreshTrigger((prev) => prev + 1);
    } catch (error) {
      toast.error(
        getApiErrorMessage(error) || 'Cập nhật trạng thái thất bại.'
      );
    } finally {
      setProductToDeactivate(null);
    }
  };

  // Mở modal Quản lý danh mục (PROD-02)
  const handleOpenCategoryModal = () => {
    setNewCategoryName('');
    setEditingCategoryId(null);
    setEditingCategoryName('');
    setCategoryFormError('');
    setIsCategoryModalOpen(true);
  };

  // Tạo danh mục mới (PROD-02)
  const handleCreateCategory = async (e) => {
    if (e) e.preventDefault();
    if (isSubmittingCategory) return;
    setCategoryFormError('');

    const trimmed = newCategoryName.trim();
    if (!trimmed) {
      setCategoryFormError('Vui lòng nhập tên danh mục mới.');
      return;
    }

    if (trimmed.length > 100) {
      setCategoryFormError('Tên danh mục không được vượt quá 100 ký tự.');
      return;
    }

    setIsSubmittingCategory(true);
    try {
      const created = await productsApi.createCategory({
        name: trimmed,
      });
      toast.success(`Đã thêm danh mục "${created.name}" thành công!`);
      setNewCategoryName('');
      const res = await productsApi.getCategories({
        page: 1,
        pageSize: 100,
      });
      setCategories(res.items || []);
    } catch (error) {
      setCategoryFormError(
        getApiErrorMessage(error) || 'Không thể tạo danh mục. Vui lòng thử lại.'
      );
    } finally {
      setIsSubmittingCategory(false);
    }
  };

  // Lưu đổi tên danh mục (PROD-02)
  const handleSaveEditCategory = async (catId) => {
    if (isSubmittingCategory) return;
    setCategoryFormError('');

    const trimmed = editingCategoryName.trim();
    if (!trimmed) {
      setCategoryFormError('Tên danh mục không được để trống.');
      return;
    }
    if (trimmed.length > 100) {
      setCategoryFormError('Tên danh mục không được vượt quá 100 ký tự.');
      return;
    }

    setIsSubmittingCategory(true);
    try {
      const updated = await productsApi.updateCategory({
        id: catId,
        name: trimmed,
      });
      toast.success(`Đã đổi tên danh mục thành "${updated.name}"!`);
      setEditingCategoryId(null);
      setEditingCategoryName('');
      const res = await productsApi.getCategories({
        page: 1,
        pageSize: 100,
      });
      setCategories(res.items || []);
    } catch (error) {
      setCategoryFormError(
        getApiErrorMessage(error) || 'Không thể cập nhật tên danh mục.'
      );
    } finally {
      setIsSubmittingCategory(false);
    }
  };

  // Chuyển trạng thái ACTIVE / INACTIVE cho danh mục (PROD-02)
  const handleToggleCategoryStatus = async (cat) => {
    if (isSubmittingCategory) return;
    setCategoryFormError('');

    const nextStatus = cat.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    setIsSubmittingCategory(true);
    try {
      await productsApi.updateCategoryStatus({
        id: cat.id,
        status: nextStatus,
      });
      toast.success(
        nextStatus === 'ACTIVE'
          ? `Đã kích hoạt lại danh mục "${cat.name}".`
          : `Đã ngừng kích hoạt danh mục "${cat.name}".`
      );
      const res = await productsApi.getCategories({
        page: 1,
        pageSize: 100,
      });
      setCategories(res.items || []);
    } catch (error) {
      setCategoryFormError(
        getApiErrorMessage(error) || 'Không thể đổi trạng thái danh mục.'
      );
    } finally {
      setIsSubmittingCategory(false);
    }
  };

  // Cấu hình các cột trong Bảng chuẩn theo hình mẫu
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
        render: (row) => (
          <span className={styles.productNameText}>{row.name}</span>
        ),
      },
      {
        key: 'category',
        title: 'DANH MỤC',
        width: '160px',
        render: (row) => (
          <span className={styles.categoryText}>
            {row.category || categoriesMap[row.category_id] || '—'}
          </span>
        ),
      },
      {
        key: 'sale_price_vnd',
        title: 'GIÁ BÁN (VND)',
        align: 'center',
        width: '140px',
        render: (row) => (
          <span className={styles.priceText}>
            {formatVND(row.sale_price_vnd ?? row.price)}
          </span>
        ),
      },
      {
        key: 'quantity',
        title: (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            TỒN KHO
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </span>
        ),
        align: 'center',
        width: '150px',
        render: (row) => {
          const qty = typeof row.quantity === 'number' ? row.quantity : 0;
          if (qty <= 0) {
            return (
              <div className={styles.stockCell}>
                <span className={styles.stockNumber}>{qty}</span>
                <span className={styles.stockTagDanger}>[Hết hàng]</span>
              </div>
            );
          }
          if (qty <= 5) {
            return (
              <div className={styles.stockCell}>
                <span className={styles.stockNumber}>{qty}</span>
                <span className={styles.stockTagWarning}>[Tồn thấp]</span>
              </div>
            );
          }
          return <span className={styles.stockNumber}>{qty}</span>;
        },
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI HOẠT ĐỘNG',
        align: 'center',
        width: '180px',
        render: (row) => {
          const isSelling = row.status !== 'INACTIVE';
          return (
            <span
              className={`${styles.pillBadge} ${
                isSelling ? styles.badgeSuccess : styles.badgeNeutral
              }`}
            >
              {isSelling ? 'Đang bán' : 'Ngừng bán'}
            </span>
          );
        },
      },
    ];

    // CHỈ ADMIN mới có cột THAO TÁC (2 icon: Sửa và Ngừng / Bật lại)
    if (!isStaff) {
      baseColumns.push({
        key: 'actions',
        title: 'THAO TÁC',
        align: 'center',
        width: '110px',
        render: (row) => {
          const isSelling = row.status !== 'INACTIVE';
          return (
            <div className={styles.actionGroup}>
              {/* Nút 1: Sửa (Pencil Icon) */}
              <button
                type="button"
                className={`${styles.iconBtn} ${styles.editBtn}`}
                onClick={() => handleOpenEditModal(row)}
                title="Chỉnh sửa sản phẩm"
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
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>

              {/* Nút 2: Ngừng kích hoạt (Ban icon) hoặc Kích hoạt lại (Check icon) */}
              {isSelling ? (
                <button
                  type="button"
                  className={`${styles.iconBtn} ${styles.deactivateBtn}`}
                  onClick={() => setProductToDeactivate(row)}
                  title="Ngừng kích hoạt"
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
                    <circle cx="12" cy="12" r="10" />
                    <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                  </svg>
                </button>
              ) : (
                <button
                  type="button"
                  className={`${styles.iconBtn} ${styles.activateBtn}`}
                  onClick={() => setProductToDeactivate(row)}
                  title="Kích hoạt lại"
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
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="9 12 12 15 16 10" />
                  </svg>
                </button>
              )}
            </div>
          );
        },
      });
    }

    return baseColumns;
  }, [categoriesMap, isStaff]);

  return (
    <div className={styles.container}>
      {/* 1. Tiêu đề trang & Nút thêm sản phẩm */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>Quản lý sản phẩm</h1>
          <p className={styles.subtitle}>
            Danh mục sản phẩm kinh doanh tại cửa hàng
          </p>
        </div>

        {!isStaff && (
          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.secondaryBtn}
              onClick={handleOpenCategoryModal}
              title="Quản lý danh mục hàng hóa (PROD-02)"
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
                <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
              </svg>
              <span>Danh mục</span>
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

      {/* 2. Thanh lọc chuẩn theo mẫu */}
      <div className={styles.filterBar}>
        <div className={styles.searchBox}>
          <svg
            className={styles.searchIcon}
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
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
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                setDebouncedKeyword(searchParams.keyword.trim());
              }
            }}
            placeholder="Tìm theo tên, mã SKU..."
            className={styles.searchInput}
          />
        </div>

        <div className={styles.filterControls}>
          <div className={styles.filterItem}>
            <span className={styles.filterLabel}>Danh mục:</span>
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
          </div>

          <div className={styles.filterItem}>
            <span className={styles.filterLabel}>Trạng thái:</span>
            <select
              name="status"
              value={searchParams.status}
              onChange={handleFilterChange}
              className={styles.filterSelect}
            >
              <option value="">Tất cả trạng thái</option>
              <option value="ACTIVE">Đang bán</option>
              <option value="INACTIVE">Ngừng bán</option>
            </select>
          </div>

          <div className={styles.filterItem}>
            <span className={styles.filterLabel}>Sắp xếp:</span>
            <select
              name="sort"
              value={searchParams.sort}
              onChange={handleFilterChange}
              className={styles.filterSelect}
            >
              <option value="">Mặc định</option>
              <option value="name_asc">Tên (A-Z)</option>
              <option value="name_desc">Tên (Z-A)</option>
              <option value="sku_asc">Mã SKU (A-Z)</option>
              <option value="sku_desc">Mã SKU (Z-A)</option>
              <option value="created_desc">Mới nhất</option>
            </select>
          </div>

          <button
            type="button"
            className={styles.filterResetBtn}
            onClick={handleResetFilters}
            title="Đặt lại bộ lọc"
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
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
            </svg>
          </button>
        </div>
      </div>

      {/* 3. Bảng dữ liệu sản phẩm */}
      <Table
        columns={columns}
        data={data}
        rowKey="id"
        isLoading={isLoading}
        emptyText="Không tìm thấy sản phẩm phù hợp."
      />

      {/* 4. Phân trang */}
      <div className={styles.paginationRow}>
        <Pagination
          currentPage={pagination.page}
          totalPages={pagination.totalPages}
          onPageChange={handlePageChange}
        />
      </div>

      {/* 5. Modal Thêm / Chỉnh sửa sản phẩm */}
      {!isStaff && (
        <Modal
          isOpen={isProductModalOpen}
          onClose={() => setIsProductModalOpen(false)}
          title={
            formMode === 'create'
              ? 'Thêm sản phẩm mới'
              : `Chỉnh sửa sản phẩm: ${productForm.sku}`
          }
          maxWidth="500px"
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
                  MÃ SKU {formMode === 'create' && <span className={styles.requiredMark}>*</span>}
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
                  placeholder="VD: SP0001"
                  className={styles.formInput}
                  disabled={formMode === 'edit' || isSubmittingForm}
                  readOnly={formMode === 'edit'}
                  maxLength={64}
                  title={formMode === 'edit' ? 'Mã SKU cố định, không thể chỉnh sửa' : ''}
                />
                {formMode === 'edit' && (
                  <span style={{ fontSize: '11px', color: '#6B7280', marginTop: '2px' }}>
                    Mã SKU cố định sau khi tạo
                  </span>
                )}
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
                    .filter(
                      (c) =>
                        c.status === 'ACTIVE' ||
                        String(c.id) === String(productForm.category_id)
                    )
                    .map((cat) => (
                      <option key={cat.id} value={cat.id}>
                        {cat.name}
                        {cat.status === 'INACTIVE' ? ' (Ngừng hoạt động)' : ''}
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
                placeholder="VD: Sữa tươi tiệt trùng 1L"
                className={styles.formInput}
                disabled={isSubmittingForm}
                maxLength={160}
              />
            </div>

            <div className={styles.formField}>
              <label className={styles.formLabel}>
                GIÁ BÁN (VND) <span className={styles.requiredMark}>*</span>
              </label>
              <input
                type="text"
                value={productForm.sale_price_vnd}
                onChange={(e) =>
                  setProductForm((prev) => ({
                    ...prev,
                    sale_price_vnd: e.target.value,
                  }))
                }
                placeholder="VD: 28000"
                className={styles.formInput}
                disabled={isSubmittingForm}
              />
            </div>
          </form>
        </Modal>
      )}

      {/* 5. Modal Quản lý danh mục (PROD-02) */}
      {!isStaff && isCategoryModalOpen && (
        <Modal
          isOpen={isCategoryModalOpen}
          onClose={() => setIsCategoryModalOpen(false)}
          title="Quản lý danh mục hàng hóa (PROD-02)"
          maxWidth="560px"
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
          {categoryFormError && (
            <div className={styles.formErrorBox} style={{ marginBottom: '12px' }}>
              {categoryFormError}
            </div>
          )}

          {/* Form thêm nhanh danh mục mới */}
          <form onSubmit={handleCreateCategory} className={styles.categoryAddRow}>
            <input
              type="text"
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              placeholder="Nhập tên danh mục mới..."
              className={styles.formInput}
              disabled={isSubmittingCategory}
              maxLength={100}
            />
            <button
              type="submit"
              className={styles.primaryBtn}
              disabled={isSubmittingCategory || !newCategoryName.trim()}
              style={{ whiteSpace: 'nowrap' }}
            >
              Thêm
            </button>
          </form>

          {/* Danh sách các danh mục hiện tại */}
          <div className={styles.categoryListContainer}>
            {categories.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '16px', color: '#6B7280', fontSize: '13px' }}>
                Chưa có danh mục nào.
              </div>
            ) : (
              categories.map((cat) => {
                const isEditing = editingCategoryId === cat.id;
                const isActive = cat.status === 'ACTIVE';

                return (
                  <div key={cat.id} className={styles.categoryItemRow}>
                    {isEditing ? (
                      <input
                        type="text"
                        value={editingCategoryName}
                        onChange={(e) => setEditingCategoryName(e.target.value)}
                        className={styles.formInput}
                        style={{ padding: '4px 8px', fontSize: '13px' }}
                        disabled={isSubmittingCategory}
                        maxLength={100}
                        autoFocus
                      />
                    ) : (
                      <span className={styles.categoryItemName}>{cat.name}</span>
                    )}

                    <div className={styles.categoryItemActions}>
                      <span
                        className={
                          isActive ? styles.badgeActive : styles.badgeInactive
                        }
                      >
                        {isActive ? 'Đang bán' : 'Ngừng bán'}
                      </span>

                      {isEditing ? (
                        <>
                          <button
                            type="button"
                            className={`${styles.iconBtn} ${styles.activateBtn}`}
                            onClick={() => handleSaveEditCategory(cat.id)}
                            disabled={isSubmittingCategory}
                            title="Lưu tên danh mục"
                          >
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          </button>
                          <button
                            type="button"
                            className={styles.iconBtn}
                            onClick={() => setEditingCategoryId(null)}
                            disabled={isSubmittingCategory}
                            title="Hủy sửa"
                          >
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <line x1="18" y1="6" x2="6" y2="18" />
                              <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            className={styles.iconBtn}
                            onClick={() => {
                              setEditingCategoryId(cat.id);
                              setEditingCategoryName(cat.name);
                            }}
                            disabled={isSubmittingCategory}
                            title="Đổi tên danh mục"
                          >
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                            </svg>
                          </button>

                          <button
                            type="button"
                            className={`${styles.iconBtn} ${isActive ? styles.deactivateBtn : styles.activateBtn}`}
                            onClick={() => handleToggleCategoryStatus(cat)}
                            disabled={isSubmittingCategory}
                            title={isActive ? 'Ngừng kích hoạt danh mục' : 'Kích hoạt lại danh mục'}
                          >
                            {isActive ? (
                              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <circle cx="12" cy="12" r="10" />
                                <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                              </svg>
                            ) : (
                              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                                <circle cx="12" cy="12" r="10" />
                                <polyline points="9 12 12 15 16 10" />
                              </svg>
                            )}
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          
        </Modal>
      )}

      {/* 6. Modal xác nhận đổi trạng thái */}
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
                <span>
                  {productToDeactivate?.status === 'INACTIVE'
                    ? 'Kích hoạt lại'
                    : 'Ngừng kích hoạt'}
                </span>
              </button>
            </>
          }
        >
          Bạn có chắc chắn muốn{' '}
          {productToDeactivate?.status === 'INACTIVE'
            ? 'kích hoạt lại kinh doanh'
            : 'ngừng kích hoạt kinh doanh'}{' '}
          cho sản phẩm <strong>&quot;{productToDeactivate?.name}&quot;</strong>?
        </Modal>
      )}
    </div>
  );
}
