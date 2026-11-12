import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Pagination, Table, useToast } from '../../components/common';
import { getApiErrorMessage } from '../../api/axiosClient';
import { categoriesApi } from '../../api/categoriesApi';
import styles from './CategoryList.module.css';

const INITIAL_FORM = {
  id: null,
  name: '',
  description: '',
  status: 'ACTIVE',
};

export default function CategoryList() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const toast = useToast();

  // 1. State tìm kiếm, tab trạng thái & phân trang (Server-side)
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState(''); // '' = Tất cả, 'ACTIVE', 'INACTIVE'
  const [data, setData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [stats, setStats] = useState({
    all: 0,
    active: 0,
    inactive: 0,
  });

  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 8,
    total: 0,
    totalPages: 1,
  });

  // 2. State Drawer Thêm mới / Chỉnh sửa
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState('create'); // 'create' | 'edit'
  const [categoryForm, setCategoryForm] = useState(INITIAL_FORM);
  const [formError, setFormError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const requestIdRef = useRef(0);
  const searchInputRef = useRef(null);

  // Debounce tìm kiếm
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim());
      setPagination((prev) => ({ ...prev, page: 1 }));
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Load danh sách danh mục (100% Server-side API, không filter client)
  const loadCategories = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);

    try {
      const res = await categoriesApi.getCategories({
        page: pagination.page,
        pageSize: pagination.page_size,
        status: statusFilter || undefined,
        search: debouncedSearch || undefined,
      });

      if (currentRequestId === requestIdRef.current) {
        setData(res.items || []);
        setPagination((prev) => ({
          ...prev,
          total: res.total || 0,
          totalPages: res.totalPages || 1,
        }));
        if (res.stats) {
          setStats(res.stats);
        } else {
          setStats((prev) => ({
            ...prev,
            ...(statusFilter === '' ? { all: res.total || 0 } : {}),
            ...(statusFilter === 'ACTIVE' ? { active: res.total || 0 } : {}),
            ...(statusFilter === 'INACTIVE' ? { inactive: res.total || 0 } : {}),
          }));
        }
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        toast.error(getApiErrorMessage(err, 'Không thể tải danh sách danh mục.'));
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [pagination.page, pagination.page_size, statusFilter, debouncedSearch, toast]);

  useEffect(() => {
    loadCategories();
  }, [loadCategories, refreshTrigger]);

  // Xử lý mở Drawer tạo mới (chỉ ADMIN)
  const handleOpenCreateDrawer = useCallback(() => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên (ADMIN) mới có quyền thêm danh mục.');
      return;
    }
    setDrawerMode('create');
    setCategoryForm({ ...INITIAL_FORM });
    setFormError('');
    setIsDrawerOpen(true);
  }, [isAdmin, toast]);

  // Xử lý mở Drawer chỉnh sửa (chỉ ADMIN)
  const handleOpenEditDrawer = useCallback((category) => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên (ADMIN) mới có quyền chỉnh sửa danh mục.');
      return;
    }
    setDrawerMode('edit');
    setCategoryForm({
      id: category.id,
      name: category.name || '',
      description: category.description || '',
      status: category.status || 'ACTIVE',
    });
    setFormError('');
    setIsDrawerOpen(true);
  }, [isAdmin, toast]);

  const handleCloseDrawer = useCallback(() => {
    if (isSubmitting) return;
    setIsDrawerOpen(false);
    setFormError('');
  }, [isSubmitting]);

  // Lắng nghe phím tắt: F2 (Focus tìm kiếm), F3 (Thêm mới - chỉ ADMIN), Esc (Đóng drawer)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'F2') {
        e.preventDefault();
        searchInputRef.current?.focus();
      } else if (e.key === 'F3' && isAdmin) {
        e.preventDefault();
        handleOpenCreateDrawer();
      } else if (e.key === 'Escape' && isDrawerOpen) {
        e.preventDefault();
        handleCloseDrawer();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isAdmin, isDrawerOpen, isSubmitting, handleCloseDrawer, handleOpenCreateDrawer]);

  // Toggle trạng thái ACTIVE / INACTIVE (PROD-02 - chỉ ADMIN)
  const handleToggleStatus = useCallback(async (category) => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên (ADMIN) mới có quyền thay đổi trạng thái danh mục.');
      return;
    }
    const nextStatus = category.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    try {
      await categoriesApi.updateCategoryStatus(category.id, nextStatus);
      toast.success(
        nextStatus === 'ACTIVE'
          ? `Đã kích hoạt lại danh mục "${category.name}".`
          : `Đã ngừng hoạt động danh mục "${category.name}".`
      );
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Không thể thay đổi trạng thái danh mục.'));
    }
  }, [isAdmin, toast]);

  // Submit form tạo / sửa danh mục (chỉ gửi name theo contract backend extra="forbid", chỉ ADMIN)
  const handleSubmitForm = async (e) => {
    e.preventDefault();
    if (!isAdmin) {
      const msg = 'Chỉ Quản trị viên (ADMIN) mới có quyền thực hiện thao tác này.';
      setFormError(msg);
      toast.error(msg);
      return;
    }
    setFormError('');

    const trimmedName = categoryForm.name.trim();
    if (!trimmedName) {
      setFormError('Vui lòng nhập tên danh mục.');
      return;
    }
    if (trimmedName.length > 120) {
      setFormError('Tên danh mục không được vượt quá 120 ký tự.');
      return;
    }

    setIsSubmitting(true);
    try {
      if (drawerMode === 'create') {
        await categoriesApi.createCategory({
          name: trimmedName,
        });
        toast.success(`Đã thêm danh mục "${trimmedName}" thành công!`);
      } else {
        await categoriesApi.updateCategory(categoryForm.id, {
          name: trimmedName,
        });
        toast.success(`Đã cập nhật danh mục "${trimmedName}" thành công!`);
      }
      setIsDrawerOpen(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setFormError(getApiErrorMessage(err, 'Lỗi lưu thông tin danh mục.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Cấu hình Cột Table chuẩn component common/Table
  const columns = useMemo(() => {
    const cols = [
      {
        key: 'name',
        title: 'TÊN DANH MỤC',
        width: '200px',
        render: (row) => <span className={styles.categoryName}>{row.name}</span>,
      },
      {
        key: 'description',
        title: 'MÔ TẢ',
        render: (row) => (
          <span className={styles.categoryDesc}>
            {row.description || <span style={{ color: '#9CA3AF' }}>—</span>}
          </span>
        ),
      },
      {
        key: 'product_count',
        title: 'SỐ LƯỢNG SẢN PHẨM',
        align: 'center',
        width: '130px',
        render: (row) => (
          <span className={styles.productCountBadge}>{row.product_count ?? 0}</span>
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI HOẠT ĐỘNG',
        align: 'center',
        width: '160px',
        render: (row) => {
          const isActive = row.status === 'ACTIVE';
          return (
            <span className={isActive ? styles.statusBadgeActive : styles.statusBadgeInactive}>
              <span className={styles.statusDot} />
              <span>{isActive ? 'Đang hoạt động' : 'Ngừng hoạt động'}</span>
            </span>
          );
        },
      },
    ];

    if (isAdmin) {
      cols.push({
        key: 'actions',
        title: 'THAO TÁC',
        align: 'center',
        width: '100px',
        render: (row) => {
          const isActive = row.status === 'ACTIVE';
          return (
            <div className={styles.actionBtns}>
              {/* Nút sửa */}
              <button
                type="button"
                className={styles.iconBtn}
                onClick={() => handleOpenEditDrawer(row)}
                title="Chỉnh sửa danh mục"
                aria-label="Chỉnh sửa danh mục"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>

              {/* Nút khóa / kích hoạt lại trạng thái */}
              <button
                type="button"
                className={`${styles.iconBtn} ${isActive ? styles.iconBtnDeactivate : styles.iconBtnActivate}`}
                onClick={() => handleToggleStatus(row)}
                title={isActive ? 'Ngừng hoạt động danh mục' : 'Kích hoạt lại danh mục'}
                aria-label={isActive ? 'Ngừng hoạt động danh mục' : 'Kích hoạt lại danh mục'}
              >
                {isActive ? (
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                ) : (
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                  </svg>
                )}
              </button>
            </div>
          );
        },
      });
    }

    return cols;
  }, [isAdmin, handleToggleStatus, handleOpenEditDrawer]);

  const startRecord = pagination.total === 0 ? 0 : (pagination.page - 1) * pagination.page_size + 1;
  const endRecord = Math.min(pagination.page * pagination.page_size, pagination.total);

  return (
    <div className={styles.container}>
      {/* 1. Header Trang */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>Quản lý danh mục</h1>
          <p className={styles.subtitle}>
            Quản lý phân loại sản phẩm cho cửa hàng và kho • Múi giờ Asia/Ho_Chi_Minh
          </p>
        </div>

        {isAdmin && (
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={handleOpenCreateDrawer}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Thêm danh mục</span>
          </button>
        )}
      </div>

      {/* 2. Thanh tìm kiếm và bộ lọc Tab Trạng thái */}
      <div className={styles.toolbarCard}>
        <div className={styles.searchWrap}>
          <svg className={styles.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={searchInputRef}
            type="text"
            className={styles.searchInput}
            placeholder="Tìm theo tên danh mục..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className={styles.filterTabsGroup}>
          <span className={styles.filterLabel}>Trạng thái:</span>
          <div className={styles.tabsSegment}>
            <button
              type="button"
              className={`${styles.tabBtn} ${statusFilter === '' ? styles.tabBtnActive : ''}`}
              onClick={() => {
                setStatusFilter('');
                setPagination((p) => ({ ...p, page: 1 }));
              }}
            >
              <span>Tất cả</span>
              {stats.all > 0 && <span>({stats.all})</span>}
            </button>
            <button
              type="button"
              className={`${styles.tabBtn} ${statusFilter === 'ACTIVE' ? styles.tabBtnActive : ''}`}
              onClick={() => {
                setStatusFilter('ACTIVE');
                setPagination((p) => ({ ...p, page: 1 }));
              }}
            >
              <span>Đang hoạt động</span>
              {stats.active > 0 && <span>({stats.active})</span>}
            </button>
            <button
              type="button"
              className={`${styles.tabBtn} ${statusFilter === 'INACTIVE' ? styles.tabBtnActive : ''}`}
              onClick={() => {
                setStatusFilter('INACTIVE');
                setPagination((p) => ({ ...p, page: 1 }));
              }}
            >
              <span>Ngừng hoạt động</span>
              {stats.inactive > 0 && <span>({stats.inactive})</span>}
            </button>
          </div>
        </div>
      </div>

      {/* 3. Bảng hiển thị danh mục dùng component common/Table */}
      <div className={styles.tableCard}>
        <Table
          columns={columns}
          data={data}
          rowKey="id"
          isLoading={isLoading}
          emptyText="Không tìm thấy danh mục phù hợp"
        />

        {/* 4. Thanh phân trang dùng component common/Pagination */}
        <div className={styles.paginationBar}>
          <span className={styles.paginationSummary}>
            Đang hiển thị <strong>{startRecord} - {endRecord}</strong> trên tổng số{' '}
            <strong>{pagination.total}</strong> danh mục
          </span>

          <div className={styles.paginationRight}>
            <Pagination
              currentPage={pagination.page}
              totalPages={pagination.totalPages}
              onPageChange={(nextPage) =>
                setPagination((prev) => ({ ...prev, page: nextPage }))
              }
            />
          </div>
        </div>
      </div>

      {isDrawerOpen && (
        <div className={styles.drawerOverlay} onClick={handleCloseDrawer}>
          <div
            className={styles.drawer}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className={styles.drawerHeader}>
              <div className={styles.drawerTitleWrap}>
                <svg className={styles.drawerIcon} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
                </svg>
                <h2 className={styles.drawerTitle}>
                  {drawerMode === 'create' ? 'Thêm danh mục mới' : 'Chỉnh sửa danh mục'}
                </h2>
              </div>
              <button
                type="button"
                className={styles.closeBtn}
                onClick={handleCloseDrawer}
                disabled={isSubmitting}
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmitForm} className={styles.drawerBody}>
              {formError && <div className={styles.formError}>{formError}</div>}

              <div className={styles.formGroup}>
                <label className={styles.formLabel}>
                  Tên danh mục <span className={styles.requiredStar}>*</span>
                </label>
                <input
                  type="text"
                  className={styles.formInput}
                  placeholder="Ví dụ: Đồ uống đóng chai"
                  value={categoryForm.name}
                  onChange={(e) =>
                    setCategoryForm((prev) => ({ ...prev, name: e.target.value }))
                  }
                  disabled={!isAdmin || isSubmitting}
                  autoFocus
                />
                <p className={styles.fieldHelp}>
                  Tên danh mục là duy nhất trong toàn bộ hệ thống kho &amp; bán hàng.
                </p>
              </div>

              <div className={styles.formGroup}>
                <label className={styles.formLabel}>
                  Mô tả danh mục <span style={{ color: '#9CA3AF', fontWeight: 'normal' }}>(tùy chọn)</span>
                </label>
                <textarea
                  className={styles.formTextarea}
                  placeholder="Nhập mô tả chi tiết danh mục hoặc hướng dẫn phân loại nội bộ..."
                  value={categoryForm.description}
                  onChange={(e) =>
                    setCategoryForm((prev) => ({ ...prev, description: e.target.value }))
                  }
                  disabled={!isAdmin || isSubmitting}
                />
                <p className={styles.fieldHelp}>
                  Giúp nhân viên bán hàng nhận diện nhóm hàng nhanh tại quầy POS.
                </p>
              </div>

              <div style={{ marginTop: 'auto' }} />

              <div className={styles.drawerFooter}>
                <button
                  type="button"
                  className={styles.cancelBtn}
                  onClick={handleCloseDrawer}
                  disabled={isSubmitting}
                >
                  {isAdmin ? 'Hủy bỏ' : 'Đóng'}
                </button>
                {isAdmin && (
                  <button
                    type="submit"
                    className={styles.submitBtn}
                    disabled={isSubmitting}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    <span>{isSubmitting ? 'Đang lưu...' : 'Lưu danh mục'}</span>
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
