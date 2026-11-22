import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
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

  // 2. State Modal Thêm mới / Chỉnh sửa
  const categoryFormId = useId();
  const isSubmittingRef = useRef(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState('create'); // 'create' | 'edit'
  const [categoryForm, setCategoryForm] = useState(INITIAL_FORM);
  const [initialCategoryForm, setInitialCategoryForm] = useState(INITIAL_FORM);
  const [formError, setFormError] = useState('');
  const [conflictData, setConflictData] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [categoryToToggle, setCategoryToToggle] = useState(null);
  const [isTogglingStatus, setIsTogglingStatus] = useState(false);

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

  // Xử lý mở Modal tạo mới (chỉ ADMIN)
  const handleOpenCreateModal = useCallback(() => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên mới có quyền thêm danh mục.');
      return;
    }
    setModalMode('create');
    setCategoryForm({ ...INITIAL_FORM });
    setFormError('');
    setConflictData(null);
    setIsModalOpen(true);
  }, [isAdmin, toast]);

  // Xử lý mở Modal chỉnh sửa (chỉ ADMIN)
  const handleOpenEditModal = useCallback((category) => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên mới có quyền chỉnh sửa danh mục.');
      return;
    }
    const formData = {
      id: category.id,
      name: category.name || '',
      description: category.description || '',
      status: category.status || 'ACTIVE',
      updated_at: category.updated_at,
    };
    setModalMode('edit');
    setCategoryForm(formData);
    setInitialCategoryForm(formData);
    setFormError('');
    setConflictData(null);
    setIsModalOpen(true);
  }, [isAdmin, toast]);

  const handleCloseModal = useCallback(() => {
    if (isSubmitting) return;
    setIsModalOpen(false);
    setFormError('');
    setConflictData(null);
  }, [isSubmitting]);

  // Lắng nghe phím tắt: F2 (Focus tìm kiếm), F3 (Thêm mới - chỉ ADMIN), Esc (Đóng modal)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'F2') {
        e.preventDefault();
        searchInputRef.current?.focus();
      } else if (e.key === 'F3' && isAdmin) {
        e.preventDefault();
        handleOpenCreateModal();
      } else if (e.key === 'Escape' && isModalOpen) {
        e.preventDefault();
        handleCloseModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isAdmin, isModalOpen, isSubmitting, handleCloseModal, handleOpenCreateModal]);

  // Mở modal xác nhận đổi trạng thái ACTIVE / INACTIVE (PROD-02 - chỉ ADMIN)
  const handleToggleStatus = useCallback(
    (category) => {
      if (!isAdmin) {
        toast.error('Chỉ Quản trị viên mới có quyền thay đổi trạng thái danh mục.');
        return;
      }
      setCategoryToToggle(category);
    },
    [isAdmin, toast]
  );

  // Xác nhận đổi trạng thái ACTIVE / INACTIVE
  const handleConfirmToggleStatus = useCallback(async () => {
    if (!categoryToToggle || isTogglingStatus) return;
    const nextStatus = categoryToToggle.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    setIsTogglingStatus(true);
    try {
      // Đối soát trạng thái thực tế từ máy chủ trước khi cập nhật
      const latest = await categoriesApi.getCategory(categoryToToggle.id);
      if (latest && latest.status !== categoryToToggle.status) {
        toast.warning(
          `Danh mục "${categoryToToggle.name}" đã được thay đổi trạng thái trước đó bởi người dùng khác. Đang làm mới dữ liệu...`
        );
        setCategoryToToggle(null);
        setRefreshTrigger((prev) => prev + 1);
        return;
      }

      await categoriesApi.updateCategoryStatus(categoryToToggle.id, nextStatus);
      if (nextStatus === 'INACTIVE') {
        toast.error(`Đã ngừng hoạt động danh mục "${categoryToToggle.name}".`);
      } else {
        toast.success(`Đã kích hoạt lại danh mục "${categoryToToggle.name}".`);
      }
      setCategoryToToggle(null);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      if (err?.response?.status === 409) {
        toast.warning(
          `Danh mục "${categoryToToggle.name}" đã được sửa trước đó. Đang làm mới dữ liệu...`
        );
      } else {
        const errMsg = getApiErrorMessage(err, 'Không thể thay đổi trạng thái danh mục.');
        toast.error(errMsg);
      }
      setCategoryToToggle(null);
      setRefreshTrigger((prev) => prev + 1);
    } finally {
      setIsTogglingStatus(false);
    }
  }, [categoryToToggle, isTogglingStatus, toast]);

  // Tải lại dữ liệu mới nhất khi có xung đột (HTTP 409 / Stale)
  const handleReloadLatestCategory = useCallback(async () => {
    if (!categoryForm.id) return;
    setIsSubmitting(true);
    try {
      const latest = await categoriesApi.getCategory(categoryForm.id);
      const updatedFormData = {
        id: latest.id,
        name: latest.name || '',
        description: latest.description || '',
        status: latest.status || 'ACTIVE',
        updated_at: latest.updated_at,
      };
      setCategoryForm(updatedFormData);
      setInitialCategoryForm(updatedFormData);
      setConflictData(null);
      setFormError('');
      setRefreshTrigger((prev) => prev + 1);
      toast.info('Đã cập nhật dữ liệu danh mục mới nhất từ hệ thống.');
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Không thể tải dữ liệu danh mục mới nhất.'));
    } finally {
      setIsSubmitting(false);
    }
  }, [categoryForm.id, toast]);

  // Submit form tạo / sửa danh mục (chỉ ADMIN)
  const handleSubmitForm = async (e) => {
    if (e && typeof e.preventDefault === 'function') {
      e.preventDefault();
    }
    if (!isAdmin) {
      const msg = 'Chỉ Quản trị viên mới có quyền thực hiện thao tác này.';
      setFormError(msg);
      toast.error(msg);
      return;
    }
    if (isSubmittingRef.current) {
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

    const trimmedDescription = categoryForm.description.trim();
    if (trimmedDescription.length > 2000) {
      setFormError('Mô tả danh mục không được vượt quá 2000 ký tự.');
      return;
    }

    // Dirty-state check: Nếu là modal Sửa, đối soát xung đột trước
    if (modalMode === 'edit') {
      try {
        const latestCategory = await categoriesApi.getCategory(categoryForm.id);
        if (
          initialCategoryForm.updated_at &&
          latestCategory.updated_at &&
          latestCategory.updated_at !== initialCategoryForm.updated_at
        ) {
          setConflictData({
            message:
              'Dữ liệu danh mục đã được thay đổi gần đây bởi một phiên làm việc khác (HTTP 409 Conflict). Vui lòng tải lại dữ liệu mới nhất để đối soát trước khi cập nhật.',
            latest: latestCategory,
          });
          setRefreshTrigger((prev) => prev + 1);
          return;
        }
      } catch (fetchErr) {
        if (fetchErr?.response?.status === 404) {
          toast.error('Danh mục không còn tồn tại trên hệ thống.');
          setIsModalOpen(false);
          setRefreshTrigger((prev) => prev + 1);
          return;
        }
        const errorMsg = getApiErrorMessage(
          fetchErr,
          'Không thể kiểm tra phiên bản dữ liệu mới nhất từ máy chủ.'
        );
        setFormError(errorMsg);
        return;
      }

      const isNameSame = trimmedName === (initialCategoryForm.name || '').trim();
      const isDescSame = (trimmedDescription || null) === ((initialCategoryForm.description || '').trim() || null);
      if (isNameSame && isDescSame) {
        toast.info('Không có thay đổi nào để lưu.');
        setIsModalOpen(false);
        setRefreshTrigger((prev) => prev + 1);
        return;
      }
    }

    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      if (modalMode === 'create') {
        await categoriesApi.createCategory({
          name: trimmedName,
          description: trimmedDescription || null,
        });
        toast.success(`Đã thêm danh mục "${trimmedName}" thành công!`);
      } else {
        await categoriesApi.updateCategory(categoryForm.id, {
          name: trimmedName,
          description: trimmedDescription || null,
        });
        toast.success(`Đã cập nhật danh mục "${trimmedName}" thành công!`);
      }
      setIsModalOpen(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      if (err?.response?.status === 409) {
        setConflictData({
          message:
            getApiErrorMessage(err) ||
            'Dữ liệu đã thay đổi gần đây trên hệ thống (HTTP 409). Vui lòng tải lại dữ liệu mới nhất trước khi tiếp tục.',
        });
      } else {
        setFormError(getApiErrorMessage(err, 'Lỗi lưu thông tin danh mục.'));
      }
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  // Cấu hình Cột Table chuẩn component common/Table
  const columns = useMemo(() => {
    const cols = [
      {
        key: 'name',
        title: 'TÊN DANH MỤC',
        width: isAdmin ? '22%' : '24%',
        render: (row) => <span className={styles.categoryName}>{row.name}</span>,
      },
      {
        key: 'description',
        title: 'MÔ TẢ',
        width: isAdmin ? '36%' : '42%',
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
        width: isAdmin ? '14%' : '15%',
        render: (row) => (
          <span className={styles.productCountBadge}>{row.product_count ?? 0}</span>
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI HOẠT ĐỘNG',
        align: 'center',
        width: isAdmin ? '18%' : '19%',
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
        width: '10%',
        render: (row) => {
          const isActive = row.status === 'ACTIVE';
          return (
            <div className={styles.actionBtns}>
              {/* Nút sửa */}
              <button
                type="button"
                className={styles.iconBtn}
                onClick={() => handleOpenEditModal(row)}
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
  }, [isAdmin, handleToggleStatus, handleOpenEditModal]);

  const startRecord = pagination.total === 0 ? 0 : (pagination.page - 1) * pagination.page_size + 1;
  const endRecord = Math.min(pagination.page * pagination.page_size, pagination.total);

  return (
    <div className={styles.container}>
      {/* 1. Header Trang */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>Quản lý danh mục</h1>
          <p className={styles.subtitle}>
            Quản lý phân loại sản phẩm cho cửa hàng và kho
          </p>
        </div>

        {isAdmin && (
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={handleOpenCreateModal}
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

      {/* 5. Modal Thêm mới / Chỉnh sửa danh mục */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={modalMode === 'create' ? 'Thêm danh mục mới' : 'Chỉnh sửa danh mục'}
        maxWidth="500px"
        footer={
          <>
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={handleCloseModal}
              disabled={isSubmitting}
            >
              Hủy
            </button>
            {isAdmin && (
              <button
                type="submit"
                form={categoryFormId}
                className={modalStyles.confirmBtn}
                disabled={!isAdmin || isSubmitting}
              >
                {isSubmitting
                  ? 'Đang lưu...'
                  : modalMode === 'create'
                  ? 'Thêm danh mục'
                  : 'Lưu thay đổi'}
              </button>
            )}
          </>
        }
      >
        <form
          id={categoryFormId}
          onSubmit={handleSubmitForm}
          className={styles.modalForm}
        >
          {conflictData && (
            <div className={styles.conflictCard} role="alert">
              <div className={styles.conflictHeaderRow}>
                <div className={styles.conflictTitleBlock}>
                  <span className={styles.conflictTitle}>Dữ liệu đã thay đổi gần đây</span>
                  <span className={styles.conflictSubtitle}>Xung đột cập nhật đồng thời</span>
                </div>
                <span className={styles.httpBadge}>HTTP 409</span>
              </div>
              <p className={styles.conflictDesc}>{conflictData.message}</p>
              <button
                type="button"
                className={styles.conflictReloadBtn}
                onClick={handleReloadLatestCategory}
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Đang tải dữ liệu...' : 'Tải lại dữ liệu mới nhất'}
              </button>
            </div>
          )}

          {formError && <div className={styles.formErrorBox}>{formError}</div>}

          <div className={styles.formField}>
            <label className={styles.formLabel}>
              Tên danh mục <span className={styles.requiredMark}>*</span>
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

          <div className={styles.formField}>
            <label className={styles.formLabel}>
              Mô tả danh mục <span className={styles.optionalMark}>(Tùy chọn)</span>
            </label>
            <textarea
              className={styles.formTextarea}
              placeholder="Nhập mô tả chi tiết danh mục hoặc hướng dẫn phân loại nội bộ..."
              value={categoryForm.description}
              onChange={(e) =>
                setCategoryForm((prev) => ({ ...prev, description: e.target.value }))
              }
              disabled={!isAdmin || isSubmitting}
              rows={3}
            />
           
          </div>
        </form>
      </Modal>

      {/* 6. Modal xác nhận ngừng hoạt động / kích hoạt lại danh mục */}
      {isAdmin && (
        <Modal
          isOpen={Boolean(categoryToToggle)}
          onClose={() => {
            if (!isTogglingStatus) setCategoryToToggle(null);
          }}
          title={
            categoryToToggle?.status === 'ACTIVE'
              ? 'Xác nhận ngừng hoạt động danh mục'
              : 'Xác nhận kích hoạt lại danh mục'
          }
          maxWidth="440px"
          footer={
            <>
              <button
                type="button"
                className={modalStyles.cancelBtn}
                onClick={() => setCategoryToToggle(null)}
                disabled={isTogglingStatus}
              >
                Hủy
              </button>
              <button
                type="button"
                className={
                  categoryToToggle?.status === 'ACTIVE'
                    ? modalStyles.dangerBtn || modalStyles.confirmBtn
                    : modalStyles.confirmBtn
                }
                onClick={handleConfirmToggleStatus}
                disabled={isTogglingStatus}
              >
                {isTogglingStatus
                  ? 'Đang xử lý...'
                  : categoryToToggle?.status === 'ACTIVE'
                  ? 'Ngừng hoạt động'
                  : 'Kích hoạt lại'}
              </button>
            </>
          }
        >
          <p style={{ margin: 0, lineHeight: 1.6 }}>
            Bạn có chắc chắn muốn{' '}
            {categoryToToggle?.status === 'ACTIVE'
              ? 'ngừng hoạt động'
              : 'kích hoạt lại'}{' '}
            danh mục <strong>&quot;{categoryToToggle?.name}&quot;</strong>?
            {categoryToToggle?.status === 'ACTIVE' && (
              <>
                {' '}
                Danh mục ngừng hoạt động sẽ không thể gán cho sản phẩm mới; các sản
                phẩm hiện có thuộc danh mục này vẫn giữ nguyên trạng thái.
              </>
            )}
          </p>
        </Modal>
      )}
    </div>
  );
}
