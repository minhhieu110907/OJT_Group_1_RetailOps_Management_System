import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import {
  DEFAULT_PRODUCT_SORT,
  RESTOCK_FIRST_SORT,
  STOCK_FILTER_TABS,
  classifyProductStock,
  computeProductStockStats,
  filterProductsByStockTab,
  isOutOfStockProduct,
  parseAndValidateSalePriceVnd,
  productsApi,
} from '../../api/productsApi';
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
  const { user, isMockMode, canUseMock } = useAuth();
  const toast = useToast();

  const isStaff = user?.role !== 'ADMIN';
  const isMock = Boolean(isMockMode && canUseMock);

  // 1. State tìm kiếm, lọc, sắp xếp & phân trang
  const [searchParams, setSearchParams] = useState({
    keyword: '',
    categoryId: '',
    status: '',
    sort: DEFAULT_PRODUCT_SORT,
  });
  const [stockFilter, setStockFilter] = useState(STOCK_FILTER_TABS.ALL);
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [data, setData] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isCategoriesLoading, setIsCategoriesLoading] = useState(!isMock);
  const [categoryLoadError, setCategoryLoadError] = useState('');
  const [categoryRetryTrigger, setCategoryRetryTrigger] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
  });

  // Chống race condition / stale response khi gõ nhanh hoặc chuyển trang
  const requestIdRef = useRef(0);
  const categoryRequestIdRef = useRef(0);
  const isStatusMutationPendingRef = useRef(false);

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
  const [initialProductForm, setInitialProductForm] = useState(INITIAL_PRODUCT_FORM);
  const [formError, setFormError] = useState('');
  const [isSubmittingForm, setIsSubmittingForm] = useState(false);

  // 3. State Modal xác nhận ngừng kích hoạt / kích hoạt lại
  const [productToDeactivate, setProductToDeactivate] = useState(null);
  const [isSubmittingStatus, setIsSubmittingStatus] = useState(false);

  // Lấy danh sách Danh mục (F03: Error handling + retry, F06: fetchAll safe pagination)
  const reloadCategories = useCallback(() => {
    setCategoryLoadError('');
    setIsCategoriesLoading(true);
    setCategoryRetryTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (isMock) return;
    const currentId = ++categoryRequestIdRef.current;
    productsApi
      .getCategories({
        page: 1,
        pageSize: 100,
        fetchAll: true,
      })
      .then((res) => {
        if (currentId === categoryRequestIdRef.current) {
          setCategories(res.items || []);
          if (res.isTruncated) {
            toast.warning(`Chỉ hiển thị được ${res.items.length}/${res.total} danh mục do đạt giới hạn tải.`);
          }
          setCategoryLoadError('');
        }
      })
      .catch((error) => {
        if (currentId === categoryRequestIdRef.current) {
          setCategoryLoadError(
            getApiErrorMessage(error) || 'Không thể tải danh mục sản phẩm.'
          );
        }
      })
      .finally(() => {
        if (currentId === categoryRequestIdRef.current) {
          setIsCategoriesLoading(false);
        }
      });

    return () => {
      categoryRequestIdRef.current += 1;
    };
  }, [categoryRetryTrigger, isMock, toast]);

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
      if (isMock) {
        setData([]);
        setIsLoading(false);
        return;
      }
      setIsLoading(true);
      try {
        const res = await productsApi.getProducts({
          page: 1,
          pageSize: 100,
          keyword: debouncedKeyword,
          categoryId: searchParams.categoryId,
          status: searchParams.status,
          sort: searchParams.sort,
          fetchAll: true,
        });

        if (currentRequestId === requestIdRef.current) {
          setData(res.items || []);
          if (res.isTruncated) {
            toast.warning(
              `Chỉ hiển thị được ${res.items.length}/${res.total} sản phẩm do đạt giới hạn tải.`
            );
          }
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
    debouncedKeyword,
    searchParams.categoryId,
    searchParams.status,
    searchParams.sort,
    refreshTrigger,
    isMock,
    toast,
  ]);

  // Thống kê số lượng tồn kho cho 3 pill (Tất cả / Hết hàng / Sắp hết) trên phạm vi dữ liệu hiện tại
  const stockStats = useMemo(() => computeProductStockStats(data), [data]);

  // Lọc theo tab tồn kho và giữ nguyên thứ tự đã được Backend sắp xếp tại database
  const filteredAndSortedProducts = useMemo(
    () => filterProductsByStockTab(data, stockFilter),
    [data, stockFilter]
  );

  const totalPages = useMemo(
    () =>
      Math.max(
        1,
        Math.ceil(filteredAndSortedProducts.length / pagination.page_size)
      ),
    [filteredAndSortedProducts.length, pagination.page_size]
  );

  const currentPage = Math.min(pagination.page, totalPages);

  const paginatedData = useMemo(() => {
    const startIndex = (currentPage - 1) * pagination.page_size;
    return filteredAndSortedProducts.slice(
      startIndex,
      startIndex + pagination.page_size
    );
  }, [filteredAndSortedProducts, currentPage, pagination.page_size]);

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

  // Xử lý chọn pill bộ lọc thống kê tồn kho (CHANGE A)
  const handleStockFilterChange = (nextTab) => {
    setStockFilter(nextTab);
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
      sort: DEFAULT_PRODUCT_SORT,
    });
    setStockFilter(STOCK_FILTER_TABS.ALL);
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

  // Mở modal Thêm mới (F02: Chặn khi ở chế độ Mock; F03: Chặn thêm sản phẩm nếu chưa tải được danh mục)
  const handleOpenCreateModal = () => {
    if (isMock) {
      toast.warning(
        'Chế độ Mock Demo không được hỗ trợ trong Quản lý sản phẩm. Vui lòng chuyển sang Real API.'
      );
      return;
    }
    if (categoryLoadError || categories.length === 0) {
      toast.warning('Vui lòng tải thành công danh mục trước khi thêm sản phẩm mới.');
      reloadCategories();
      return;
    }
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
  const handleOpenEditModal = useCallback(
    (row) => {
      if (isMock) return;
      setFormMode('edit');
      setFormError('');
      const formData = {
        id: row.id,
        sku: row.sku || '',
        name: row.name || '',
        category_id: String(row.category_id || ''),
        sale_price_vnd: String(row.sale_price_vnd || ''),
        status: row.status || 'ACTIVE',
      };
      setProductForm(formData);
      setInitialProductForm(formData);
      setIsProductModalOpen(true);
    },
    [isMock]
  );

  // Submit Form Thêm/Sửa
  const handleSubmitProductForm = async (e) => {
    e.preventDefault();
    if (isMock || isSubmittingForm) return;
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

    // Dirty-state check: Nếu là chế độ Edit mà không có bất kỳ thay đổi nào thì KHÔNG gửi API PATCH
    if (formMode === 'edit') {
      const isNameSame = name === (initialProductForm.name || '').trim();
      const isCategorySame = categoryId === Number(initialProductForm.category_id);
      const isPriceSame = salePriceVnd === Number(initialProductForm.sale_price_vnd);

      if (isNameSame && isCategorySame && isPriceSame) {
        toast.info('Không có thay đổi nào để lưu.');
        setIsProductModalOpen(false);
        return;
      }
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

  // Xác nhận Đổi trạng thái (Ngừng kích hoạt / Kích hoạt lại) — F04 Double-submit protection
  const handleConfirmDeactivate = async () => {
    if (!productToDeactivate || isStatusMutationPendingRef.current || isSubmittingStatus) {
      return;
    }
    isStatusMutationPendingRef.current = true;
    setIsSubmittingStatus(true);

    try {
      const nextStatus =
        productToDeactivate.status === 'INACTIVE' ? 'ACTIVE' : 'INACTIVE';
      await productsApi.updateProductStatus({
        id: productToDeactivate.id,
        status: nextStatus,
      });
      if (nextStatus === 'INACTIVE') {
        toast.error(`Đã ngừng kinh doanh "${productToDeactivate.name}".`);
      } else {
        toast.success(`Đã kích hoạt lại "${productToDeactivate.name}".`);
      }
      setProductToDeactivate(null);
      setRefreshTrigger((prev) => prev + 1);
    } catch (error) {
      toast.error(
        getApiErrorMessage(error) || 'Cập nhật trạng thái thất bại.'
      );
    } finally {
      isStatusMutationPendingRef.current = false;
      setIsSubmittingStatus(false);
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
        title: 'TỒN KHO',
        align: 'center',
        width: '150px',
        render: (row) => {
          const stockClass = classifyProductStock(row);
          if (stockClass === 'OUT_OF_STOCK') {
            return (
              <div className={styles.stockCell}>
                <span className={styles.stockNumber}>{row.quantity}</span>
                <span className={styles.stockTagDanger}>Hết hàng</span>
              </div>
            );
          }
          if (stockClass === 'LOW_STOCK') {
            return (
              <div className={styles.stockCell}>
                <span className={styles.stockNumber}>{row.quantity}</span>
                <span className={styles.stockTagWarning}>Sắp hết</span>
              </div>
            );
          }
          if (stockClass === 'NORMAL_STOCK') {
            return <span className={styles.stockNumber}>{row.quantity}</span>;
          }
          return <span className={styles.stockNumber}>—</span>;
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
  }, [categoriesMap, handleOpenEditModal, isStaff]);

  return (
    <div className={styles.container}>
      {/* Cảnh báo chế độ Mock Mode không được hỗ trợ (F02) */}
      {isMock && (
        <div className={styles.mockWarningBanner}>
          <div className={styles.mockWarningTitle}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span>Chế độ Mock Demo không được hỗ trợ trong Quản lý sản phẩm</span>
          </div>
          <p>
            Module Quản lý sản phẩm yêu cầu kết nối trực tiếp với Real API Backend để đảm bảo tính toàn vẹn dữ liệu. Vui lòng tắt chế độ Mock Demo hoặc đăng nhập bằng tài khoản quản trị thực tế.
          </p>
        </div>
      )}

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
              className={styles.primaryBtn}
              onClick={handleOpenCreateModal}
              disabled={isMock}
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
              disabled={isCategoriesLoading}
            >
              <option value="">
                {isCategoriesLoading
                  ? 'Đang tải danh mục...'
                  : categoryLoadError
                  ? 'Lỗi tải danh mục'
                  : 'Tất cả danh mục'}
              </option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
            {categoryLoadError && (
              <button
                type="button"
                className={styles.retryCategoryBtn}
                onClick={reloadCategories}
                title="Tải lại danh mục"
              >
                Thử lại
              </button>
            )}
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
              <option value={RESTOCK_FIRST_SORT}>Cần nhập trước</option>
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

      {/* Bộ lọc thống kê tồn kho (CHANGE A: Chỉ 3 mục cố định) */}
      <div
        className={styles.stockFilterBar}
        role="group"
        aria-label="Bộ lọc thống kê tồn kho"
      >
        <button
          type="button"
          className={`${styles.stockFilterPill} ${styles.stockPillAll} ${
            stockFilter === STOCK_FILTER_TABS.ALL ? styles.stockPillActive : ''
          }`}
          aria-pressed={stockFilter === STOCK_FILTER_TABS.ALL}
          onClick={() => handleStockFilterChange(STOCK_FILTER_TABS.ALL)}
        >
          <span>Tất cả</span>
          <span className={styles.stockPillCount}>{stockStats.all}</span>
        </button>

        <button
          type="button"
          className={`${styles.stockFilterPill} ${styles.stockPillOut} ${
            stockFilter === STOCK_FILTER_TABS.OUT_OF_STOCK
              ? styles.stockPillActive
              : ''
          }`}
          aria-pressed={stockFilter === STOCK_FILTER_TABS.OUT_OF_STOCK}
          onClick={() => handleStockFilterChange(STOCK_FILTER_TABS.OUT_OF_STOCK)}
        >
          <span>Hết hàng</span>
          <span className={styles.stockPillCount}>{stockStats.outOfStock}</span>
        </button>

        <button
          type="button"
          className={`${styles.stockFilterPill} ${styles.stockPillLow} ${
            stockFilter === STOCK_FILTER_TABS.LOW_STOCK
              ? styles.stockPillActive
              : ''
          }`}
          aria-pressed={stockFilter === STOCK_FILTER_TABS.LOW_STOCK}
          onClick={() => handleStockFilterChange(STOCK_FILTER_TABS.LOW_STOCK)}
        >
          <span>Sắp hết</span>
          <span className={styles.stockPillCount}>{stockStats.lowStock}</span>
        </button>
      </div>

      {/* 3. Bảng dữ liệu sản phẩm */}
      <Table
        columns={columns}
        data={paginatedData}
        rowKey="id"
        isLoading={isLoading}
        emptyText="Không tìm thấy sản phẩm phù hợp."
        rowClassName={(row) =>
          isOutOfStockProduct(row) ? styles.outOfStockRow : ''
        }
      />

      {/* 4. Phân trang */}
      <div className={styles.paginationRow}>
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
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
                {categoryLoadError && (
                  <div style={{ marginTop: '4px' }}>
                    <span style={{ fontSize: '11px', color: '#DC2626' }}>
                      Không thể tải danh mục.{' '}
                    </span>
                    <button
                      type="button"
                      className={styles.retryCategoryBtn}
                      onClick={reloadCategories}
                    >
                      Thử lại
                    </button>
                  </div>
                )}
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

      {/* 5. Modal xác nhận đổi trạng thái */}
      {!isStaff && (
        <Modal
          isOpen={Boolean(productToDeactivate)}
          onClose={() => {
            if (!isSubmittingStatus) setProductToDeactivate(null);
          }}
          title="Xác nhận trạng thái sản phẩm"
          maxWidth="420px"
          footer={
            <>
              <button
                type="button"
                className={modalStyles.cancelBtn}
                onClick={() => setProductToDeactivate(null)}
                disabled={isSubmittingStatus}
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
                disabled={isSubmittingStatus}
              >
                <span>
                  {isSubmittingStatus
                    ? 'Đang cập nhật...'
                    : productToDeactivate?.status === 'INACTIVE'
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
