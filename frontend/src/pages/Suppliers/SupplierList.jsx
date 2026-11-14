import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import { getApiErrorMessage } from '../../api/axiosClient';
import {
  suppliersApi,
  normalizeSupplierSnapshot,
  detectSupplierChanges,
} from '../../api/suppliersApi';
import {
  hydrateSupplierPhoneField,
  parseAndValidateSupplierPhone,
} from '../../utils/phoneUtils';
import SupplierPhoneInput from './SupplierPhoneInput';
import styles from './SupplierList.module.css';

// Component hiển thị tag trạng thái chuẩn thiết kế
function SupplierStatusBadge({ status, inModal = false }) {
  const isActive = status === 'ACTIVE';
  const inactiveBg = inModal ? '#FEF2F2' : '#F3F4F6';
  const inactiveColor = inModal ? '#DC2626' : '#4B5563';
  const inactiveBorder = inModal ? '#FECACA' : '#E5E7EB';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 10px',
        borderRadius: '9999px',
        fontSize: '12.5px',
        fontWeight: '500',
        backgroundColor: isActive ? '#DCFCE7' : inactiveBg,
        color: isActive ? '#166534' : inactiveColor,
        border: `1px solid ${isActive ? '#BBF7D0' : inactiveBorder}`,
      }}
    >
      {isActive ? 'Đang hợp tác' : 'Ngừng hợp tác'}
    </span>
  );
}

// Format ngày tạo: DD/MM/YYYY HH:mm (ICT)
function formatCreatedAt(isoString) {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) return '—';
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return (
      <div>
        <div>{`${day}/${month}/${year}`}</div>
        <div style={{ fontSize: '12px', color: '#6B7280' }}>{`${hours}:${minutes} (ICT)`}</div>
      </div>
    );
  } catch {
    return '—';
  }
}

const INITIAL_SUPPLIER_FORM = {
  id: null,
  name: '',
  contact_phone: '',
  contact_email: '',
  status: 'ACTIVE',
};

export default function SupplierList() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const toast = useToast();

  // 1. State tìm kiếm, lọc & phân trang
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [data, setData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isForbidden, setIsForbidden] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    total: 0,
    totalPages: 1,
  });

  // 2. State Modal Chi tiết / Thêm / Cập nhật
  const supplierFormId = useId();
  const isSubmittingRef = useRef(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState('create'); // 'create' | 'edit'
  const [supplierForm, setSupplierForm] = useState(INITIAL_SUPPLIER_FORM);
  const [phoneCountry, setPhoneCountry] = useState('VN');
  const [phoneNationalInput, setPhoneNationalInput] = useState('');
  const [phoneError, setPhoneError] = useState('');
  const [initialSnapshot, setInitialSnapshot] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  // Chống race condition
  const requestIdRef = useRef(0);

  // Debounce tìm kiếm
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim());
      setPagination((prev) => ({ ...prev, page: 1 }));
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Load danh sách nhà cung cấp
  const loadSuppliers = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);

    try {
      setIsForbidden(false);
      const res = await suppliersApi.getSuppliers({
        page: pagination.page,
        pageSize: pagination.page_size,
        status: statusFilter || undefined,
        search: debouncedSearch || undefined,
      });

      if (currentRequestId === requestIdRef.current) {
        setData(res.items);
        setPagination((prev) => ({
          ...prev,
          total: res.total,
          totalPages: res.totalPages,
        }));
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        if (err?.response?.status === 403) {
          setIsForbidden(true);
        }
        const errorMsg = getApiErrorMessage(err, 'Không thể tải danh sách nhà cung cấp.');
        toast.error(errorMsg);
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [pagination.page, pagination.page_size, statusFilter, debouncedSearch, toast]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers, refreshTrigger]);

  // Xử lý mở modal thêm mới (chỉ ADMIN)
  const handleOpenCreateModal = () => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên (ADMIN) mới có quyền thêm nhà cung cấp.');
      return;
    }
    setModalMode('create');
    setSupplierForm({ ...INITIAL_SUPPLIER_FORM });
    setPhoneCountry('VN');
    setPhoneNationalInput('');
    setPhoneError('');
    setInitialSnapshot(null);
    setFormError('');
    setIsModalOpen(true);
  };

  // Xử lý mở modal xem chi tiết / cập nhật (chỉ ADMIN)
  const handleOpenEditModal = useCallback((supplier) => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên (ADMIN) mới có quyền chỉnh sửa nhà cung cấp.');
      return;
    }
    setModalMode('edit');
    const snapshot = normalizeSupplierSnapshot(supplier);
    const hydratedPhone = hydrateSupplierPhoneField(snapshot.contact_phone);
    setSupplierForm({
      id: snapshot.id,
      name: snapshot.name,
      contact_phone: snapshot.contact_phone || '',
      contact_email: snapshot.contact_email || '',
      status: snapshot.status,
    });
    setPhoneCountry(hydratedPhone.countryIso);
    setPhoneNationalInput(hydratedPhone.nationalInput);
    setPhoneError('');
    setInitialSnapshot(snapshot);
    setFormError('');
    setIsModalOpen(true);
  }, [isAdmin, toast]);

  const handleCloseModal = () => {
    if (isSubmitting) return;
    setIsModalOpen(false);
    setFormError('');
    setPhoneError('');
  };

  // Đồng bộ giá trị số điện thoại quốc gia -> E.164 trong supplierForm
  const syncPhoneField = useCallback(
    (nextNationalInput, nextCountryIso, shouldValidate = false) => {
      const validation = parseAndValidateSupplierPhone(nextNationalInput, nextCountryIso);
      setPhoneNationalInput(nextNationalInput);
      setPhoneCountry(nextCountryIso);

      setSupplierForm((prev) => ({
        ...prev,
        contact_phone: !nextNationalInput.trim()
          ? ''
          : validation.isValid
            ? validation.e164
            : nextNationalInput.trim(),
      }));

      if (shouldValidate || phoneError) {
        setPhoneError(
          !nextNationalInput.trim() || validation.isValid ? '' : validation.error
        );
      }
    },
    [phoneError]
  );

  const handlePhoneInputChange = (nextValue) => {
    syncPhoneField(nextValue, phoneCountry, false);
  };

  const handlePhoneCountryChange = (nextCountryIso, pastedNationalInput) => {
    const nextInput =
      pastedNationalInput !== undefined ? pastedNationalInput : phoneNationalInput;
    const hasValue = Boolean(nextInput.trim());
    syncPhoneField(nextInput, nextCountryIso, hasValue);
  };

  const handlePhoneBlur = () => {
    if (!phoneNationalInput.trim()) {
      setPhoneError('');
      return;
    }
    const validation = parseAndValidateSupplierPhone(phoneNationalInput, phoneCountry);
    setPhoneError(validation.isValid ? '' : validation.error);
  };

  // Đảo trạng thái tạm thời trong form modal (chưa lưu xuống database cho đến khi bấm "Lưu thay đổi")
  const handleToggleStatus = () => {
    if (!isAdmin) {
      toast.error('Chỉ Quản trị viên (ADMIN) mới có quyền thay đổi trạng thái đối tác.');
      return;
    }
    if (isSubmitting || modalMode !== 'edit' || !supplierForm.id) return;
    setSupplierForm((prev) => ({
      ...prev,
      status: prev.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE',
    }));
  };

  // Submit form (Thêm mới hoặc Cập nhật - chỉ ADMIN)
  const handleSubmitForm = async (e) => {
    if (e && typeof e.preventDefault === 'function') {
      e.preventDefault();
    }
    if (!isAdmin) {
      const msg = 'Chỉ Quản trị viên (ADMIN) mới có quyền thực hiện thao tác này.';
      setFormError(msg);
      toast.error(msg);
      return;
    }
    if (isSubmittingRef.current) {
      return;
    }

    const trimmedName = supplierForm.name.trim();
    if (!trimmedName) {
      setFormError('Tên nhà cung cấp là bắt buộc.');
      return;
    }
    if (trimmedName.length > 160) {
      setFormError('Tên nhà cung cấp không được vượt quá 160 ký tự.');
      return;
    }

    const phoneValidation = parseAndValidateSupplierPhone(
      phoneNationalInput,
      phoneCountry
    );
    if (!phoneValidation.isValid) {
      setPhoneError(phoneValidation.error);
      return;
    }
    setPhoneError('');
    const normalizedPhone = phoneValidation.e164;

    const trimmedEmail = supplierForm.contact_email?.trim() || null;
    if (trimmedEmail) {
      if (trimmedEmail.length > 254) {
        setFormError('Email không được vượt quá 254 ký tự.');
        return;
      }
      const emailRegex = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
      if (!emailRegex.test(trimmedEmail)) {
        setFormError('Email kinh doanh không đúng định dạng.');
        return;
      }
    }

    // Với edit mode: kiểm tra dirty state theo Decision Matrix
    let changes = null;
    if (modalMode === 'edit') {
      changes = detectSupplierChanges(
        { ...supplierForm, contact_phone: normalizedPhone || '' },
        initialSnapshot
      );
      if (!changes.hasInfoChanges && !changes.hasStatusChange) {
        toast.info('Không có thay đổi nào để lưu.');
        setIsModalOpen(false);
        return;
      }
    }

    setFormError('');
    isSubmittingRef.current = true;
    setIsSubmitting(true);

    try {
      if (modalMode === 'create') {
        await suppliersApi.createSupplier({
          name: trimmedName,
          contact_email: trimmedEmail,
          contact_phone: normalizedPhone,
        });
        toast.success('Thêm nhà cung cấp mới thành công.');
        setIsModalOpen(false);
        setRefreshTrigger((prev) => prev + 1);
      } else {
        const { hasInfoChanges, hasStatusChange, normalizedPayload } = changes;
        let infoUpdated = false;

        // 1. Gửi PATCH thông tin nếu có thay đổi
        if (hasInfoChanges) {
          await suppliersApi.updateSupplier(supplierForm.id, {
            name: normalizedPayload.name,
            contact_email: normalizedPayload.contact_email,
            contact_phone: normalizedPayload.contact_phone,
          });
          infoUpdated = true;
        }

        // 2. Gửi PATCH trạng thái nếu có thay đổi
        if (hasStatusChange) {
          try {
            await suppliersApi.updateSupplierStatus(supplierForm.id, normalizedPayload.status);
          } catch (statusErr) {
            // Xử lý Partial Failure: Thông tin đã lưu nhưng trạng thái thất bại
            if (infoUpdated) {
              const statusErrMsg = getApiErrorMessage(
                statusErr,
                'Không thể cập nhật trạng thái đối tác.'
              );
              let syncWarning = '';

              try {
                // Thử đồng bộ lại dữ liệu backend thực tế
                const latestSupplier = await suppliersApi.getSupplier(supplierForm.id);
                const newSnapshot = normalizeSupplierSnapshot(latestSupplier);
                const rehydratedPhone = hydrateSupplierPhoneField(newSnapshot.contact_phone);
                setInitialSnapshot(newSnapshot);
                setSupplierForm({
                  id: newSnapshot.id,
                  name: newSnapshot.name,
                  contact_phone: newSnapshot.contact_phone || '',
                  contact_email: newSnapshot.contact_email || '',
                  status: newSnapshot.status,
                });
                setPhoneCountry(rehydratedPhone.countryIso);
                setPhoneNationalInput(rehydratedPhone.nationalInput);
                setPhoneError('');
                syncWarning = `Thông tin nhà cung cấp đã được lưu thành công, nhưng cập nhật trạng thái thất bại: ${statusErrMsg}. Giao diện đã được đồng bộ với dữ liệu máy chủ.`;
              } catch {
                syncWarning = `Cảnh báo: Thông tin nhà cung cấp đã được lưu một phần trên hệ thống, nhưng cập nhật trạng thái thất bại (${statusErrMsg}) và không thể tải lại dữ liệu mới nhất. Vui lòng kiểm tra lại trước khi tiếp tục.`;
              }

              setFormError(syncWarning);
              toast.error(syncWarning);
              setRefreshTrigger((prev) => prev + 1);
              return; // Giữ modal mở để người dùng kiểm tra
            }
            throw statusErr;
          }
        }

        toast.success('Cập nhật thông tin nhà cung cấp thành công.');
        setIsModalOpen(false);
        setRefreshTrigger((prev) => prev + 1);
      }
    } catch (err) {
      const errorMsg = getApiErrorMessage(
        err,
        modalMode === 'create'
          ? 'Không thể tạo nhà cung cấp.'
          : 'Không thể cập nhật nhà cung cấp.'
      );
      setFormError(errorMsg);
      toast.error(errorMsg);
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  // Định nghĩa các cột cho Table component từ common
  const columns = useMemo(() => {
    const cols = [
      {
        key: 'name',
        title: 'TÊN NHÀ CUNG CẤP',
        width: isAdmin ? '28%' : '34%',
        render: (row) => (
          <div className={styles.supplierNameCol}>
            <span className={styles.supplierNameText}>{row.name}</span>
            <span className={styles.supplierCodeText}>
              Mã NCC: NCC-{String(row.id).padStart(5, '0')}
            </span>
          </div>
        ),
      },
      {
        key: 'contact_phone',
        title: 'SỐ ĐIỆN THOẠI',
        width: '16%',
        render: (row) => row.contact_phone || '—',
      },
      {
        key: 'contact_email',
        title: 'EMAIL',
        width: '20%',
        render: (row) => row.contact_email || '—',
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI',
        width: '16%',
        render: (row) => <SupplierStatusBadge status={row.status} />,
      },
      {
        key: 'created_at',
        title: 'NGÀY TẠO',
        width: isAdmin ? '10%' : '14%',
        render: (row) => formatCreatedAt(row.created_at),
      },
    ];

    if (isAdmin) {
      cols.push({
        key: 'actions',
        title: 'THAO TÁC',
        width: '10%',
        align: 'right',
        render: (row) => (
          <div className={styles.actionCell} style={{ justifyContent: 'flex-end' }}>
            <button
              type="button"
              className={styles.editRowBtn}
              onClick={(e) => {
                e.stopPropagation();
                handleOpenEditModal(row);
              }}
            >
              Cập nhật
            </button>
          </div>
        ),
      });
    }

    return cols;
  }, [isAdmin, handleOpenEditModal]);

  return (
    <div className={styles.container}>
      {/* 1. Header trang */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>Quản lý nhà cung cấp</h1>
          <p className={styles.subtitle}>
            Quản lý đối tác cung ứng cho hoạt động nhập hàng · Một kho duy nhất
          </p>
        </div>
        {isAdmin && (
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={handleOpenCreateModal}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Thêm nhà cung cấp
          </button>
        )}
      </div>

      {isForbidden && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#FEF2F2',
            border: '1px solid #FCA5A5',
            borderRadius: '8px',
            color: '#991B1B',
            marginBottom: '16px',
            fontSize: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>
            <strong>Truy cập bị giới hạn (403):</strong> Bạn không có quyền Quản trị viên (ADMIN) để thao tác trên danh mục nhà cung cấp.
          </span>
        </div>
      )}

      {/* 3. Thanh tìm kiếm & lọc */}
      <div className={styles.filterBar}>
        <div className={styles.filterLeft}>
          <div className={styles.searchBox}>
            <svg
              className={styles.searchIcon}
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
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Tìm kiếm theo tên đối tác, mã NCC..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <select
            className={styles.statusSelect}
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPagination((prev) => ({ ...prev, page: 1 }));
            }}
          >
            <option value="">Tất cả trạng thái</option>
            <option value="ACTIVE">Đang hợp tác</option>
            <option value="INACTIVE">Ngừng hợp tác</option>
          </select>
        </div>

        <div className={styles.totalBadge}>
          Tổng số: <strong>{pagination.total} đối tác</strong>
        </div>
      </div>

      {/* 4. Nội dung: Bảng bên trái + Drawer bên phải khi mở */}
      <div className={styles.contentLayout}>
        <div className={styles.tableSection}>
          <Table
            columns={columns}
            data={data}
            rowKey="id"
            isLoading={isLoading}
            emptyText="Không tìm thấy nhà cung cấp nào."
          />

          {/* Phân trang dùng common Pagination */}
          <div className={styles.tableFooter}>
            <span className={styles.pageInfo}>
              Hiển thị{' '}
              {pagination.total === 0
                ? '0'
                : `${(pagination.page - 1) * pagination.page_size + 1} - ${Math.min(
                  pagination.page * pagination.page_size,
                  pagination.total
                )}`}{' '}
              trong tổng số {pagination.total} đối tác
            </span>
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

      {/* 5. Modal Thêm / Cập nhật nhà cung cấp */}
      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={
          modalMode === 'create'
            ? 'Thêm nhà cung cấp'
            : 'Chi tiết nhà cung cấp'
        }
        maxWidth="520px"
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
                form={supplierFormId}
                className={modalStyles.confirmBtn}
                disabled={!isAdmin || isSubmitting}
              >
                {isSubmitting
                  ? 'Đang xử lý...'
                  : modalMode === 'create'
                    ? 'Thêm nhà cung cấp'
                    : 'Lưu thay đổi'}
              </button>
            )}
          </>
        }
      >
        <form
          id={supplierFormId}
          onSubmit={handleSubmitForm}
          className={styles.modalForm}
        >
          {formError && <div className={styles.formErrorBox}>{formError}</div>}

          {/* Tên nhà cung cấp */}
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>
              Tên nhà cung cấp <span className={styles.requiredMark}>*</span>
            </label>
            <input
              type="text"
              className={styles.formInput}
              placeholder="Nhập tên nhà cung cấp..."
              value={supplierForm.name}
              onChange={(e) =>
                setSupplierForm((prev) => ({ ...prev, name: e.target.value }))
              }
              maxLength={160}
              disabled={!isAdmin || isSubmitting}
              required
              autoFocus
            />
            <span className={styles.formSubtext}>
              Tên pháp nhân chính xác để hiển thị trên chứng từ nhập kho.
            </span>
          </div>

          {/* Số điện thoại */}
          <div className={styles.formGroup}>
            <div className={styles.labelRow}>
              <label className={styles.formLabel}>Số điện thoại liên hệ</label>
              <span className={styles.optionalBadge}>Tùy chọn</span>
            </div>
            <SupplierPhoneInput
              countryIso={phoneCountry}
              value={phoneNationalInput}
              error={phoneError}
              disabled={!isAdmin || isSubmitting}
              onChange={handlePhoneInputChange}
              onCountryChange={handlePhoneCountryChange}
              onBlur={handlePhoneBlur}
            />
          </div>

          {/* Email */}
          <div className={styles.formGroup}>
            <div className={styles.labelRow}>
              <label className={styles.formLabel}>Email kinh doanh</label>
              <span className={styles.optionalBadge}>Tùy chọn</span>
            </div>
            <div className={styles.formInputWrapper}>
              <svg
                className={styles.inputIcon}
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
              <input
                type="email"
                className={`${styles.formInput} ${styles.formInputWithIcon}`}
                placeholder="Ví dụ: contact@supplier.vn"
                value={supplierForm.contact_email}
                onChange={(e) =>
                  setSupplierForm((prev) => ({
                    ...prev,
                    contact_email: e.target.value,
                  }))
                }
                maxLength={254}
                disabled={!isAdmin || isSubmitting}
              />
            </div>
          </div>

          {/* Tình trạng đối tác (chỉ hiện khi xem chi tiết / cập nhật) */}
          {modalMode === 'edit' && (
            <div className={styles.statusCard}>
              <div className={styles.statusCardRow}>
                <span className={styles.statusCardLabel}>Tình trạng đối tác</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <SupplierStatusBadge status={supplierForm.status} inModal />
                  {isAdmin && (
                    <button
                      type="button"
                      className={styles.statusToggleBtn}
                      onClick={handleToggleStatus}
                      disabled={isSubmitting}
                    >
                      {supplierForm.status === 'ACTIVE'
                        ? 'Ngừng hợp tác'
                        : 'Kích hoạt lại'}
                    </button>
                  )}
                </div>
              </div>
              <p className={styles.statusCardDesc}>
                {supplierForm.status === 'ACTIVE'
                  ? 'Khi vô hiệu hóa, nhà cung cấp này sẽ không hiển thị tại mục chọn đối tác của màn hình Lập phiếu nhập kho mới.'
                  : 'Nhà cung cấp đang ở trạng thái ngừng hợp tác. Kích hoạt lại để cho phép tạo phiếu nhập mới.'}
              </p>
            </div>
          )}
        </form>
      </Modal>

      <div className={styles.bottomDisclaimer}>
        RetailOps V1.0 · Cấu hình Đơn Kho Thực Nghiệm · Dữ liệu được bảo chứng toàn vẹn giao dịch
      </div>
    </div>
  );
}
