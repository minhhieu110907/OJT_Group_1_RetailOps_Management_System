import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import { getApiErrorMessage } from '../../api/axiosClient';
import { receiptsApi } from '../../api/receiptsApi';
import { suppliersApi } from '../../api/suppliersApi';
import { productsApi } from '../../api/productsApi';
import { useAuth } from '../../context/AuthContext';
import styles from './PurchaseList.module.css';

// Định dạng số tiền kiểu 2.500.000 đ
const formatVND = (amount) => {
  const num = Number(amount) || 0;
  return `${num.toLocaleString('vi-VN')} đ`;
};

// Format ngày: DD/MM/YYYY HH:mm theo đúng múi giờ Asia/Ho_Chi_Minh (GMT+7)
const formatDate = (isoString) => {
  if (!isoString) return '—';
  try {
    const raw = String(isoString).trim();
    // Nếu chuỗi ISO thiếu timezone offset ('Z' hoặc '+07:00'), gắn Z để chuyển thành UTC chuẩn trước khi format
    const utcStr = raw.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(raw)
      ? raw
      : `${raw.replace(' ', 'T')}Z`;
    const d = new Date(utcStr);
    if (Number.isNaN(d.getTime())) return '—';

    const parts = new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(d);

    const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
    return `${map.day}/${map.month}/${map.year} ${map.hour}:${map.minute}`;
  } catch {
    return '—';
  }
};

export default function PurchaseList() {
  const toast = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  // 1. Tab điều hướng trên cùng & Trạng thái lọc
  const [topTab, setTopTab] = useState('RECEIPTS'); // 'RECEIPTS' (Phiếu nhập) | 'HISTORY' (Lịch sử)
  const [activeTab, setActiveTab] = useState('ALL'); // 'ALL' | 'DRAFT' | 'CONFIRMED' | 'CANCELLED' | 'ALL_HISTORY'

  // 2. Bộ lọc & Phân trang (100% Server-side API)
  const [supplierFilter, setSupplierFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [dateRangeType, setDateRangeType] = useState('ALL'); // 'ALL' | '30DAYS' | '7DAYS' | 'TODAY' | 'CUSTOM'
  const [fromDateFilter, setFromDateFilter] = useState('');
  const [toDateFilter, setToDateFilter] = useState('');

  const [data, setData] = useState([]);
  const [draftCount, setDraftCount] = useState(0);
  const [historyCount, setHistoryCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    total: 0,
    totalPages: 1,
  });

  // 3. Dropdown danh sách NCC & Sản phẩm ACTIVE
  const [activeSuppliers, setActiveSuppliers] = useState([]);
  const [activeProducts, setActiveProducts] = useState([]);

  // 4. Phiếu đang chọn & Chi tiết phiếu (Gọi GET /purchase-receipts/:id)
  const [selectedReceiptId, setSelectedReceiptId] = useState(null);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [conflictError, setConflictError] = useState(null); // Lưu thông tin 409

  // 5. Modal Tạo phiếu mới (Create Mode)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createSupplierId, setCreateSupplierId] = useState('');
  const [createLines, setCreateLines] = useState([
    { product_id: '', quantity: 1, unit_cost_vnd: 0 },
  ]);

  // 6. Chế độ chỉnh sửa dòng của DRAFT trong panel chi tiết (Edit Draft Mode)
  const [isEditingDraft, setIsEditingDraft] = useState(false);
  const [editSupplierId, setEditSupplierId] = useState('');
  const [editLines, setEditLines] = useState([]);

  // 7. Modal xác nhận hủy phiếu nhập nháp (PUR-04)
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);

  const requestIdRef = useRef(0);

  // Tải danh mục Master Data: NCC & Sản phẩm ACTIVE (Chỉ bản ghi ACTIVE theo PUR-01, PROD-01)
  useEffect(() => {
    let isMounted = true;
    async function loadMasterData() {
      try {
        const [supRes, prodRes] = await Promise.all([
          suppliersApi.getActiveSuppliers({ page: 1, pageSize: 100 }),
          productsApi.getProducts({ page: 1, pageSize: 100, status: 'ACTIVE' }),
        ]);
        if (isMounted) {
          setActiveSuppliers(supRes.items || []);
          setActiveProducts(prodRes.items || []);
        }
      } catch (err) {
        console.error('Failed to load active suppliers or products:', err);
      }
    }
    loadMasterData();
    return () => {
      isMounted = false;
    };
  }, []);

  // Load danh sách phiếu từ server (GET /api/v1/purchase-receipts)
  const loadReceipts = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);

    try {
      // Nhận diện nếu người dùng nhập mã phiếu (dạng 123 hoặc #123) hoặc tên nhà cung cấp vào ô tìm kiếm
      const trimmedQuery = searchQuery.trim();
      let resolvedSupplierId = supplierFilter ? Number(supplierFilter) : null;

      // Nếu người dùng nhập tìm kiếm tên nhà cung cấp và chưa chọn dropdown NCC cụ thể,
      // tự động ánh xạ tìm nhà cung cấp khớp nhất trong activeSuppliers để truyền supplier_id qua API
      if (!resolvedSupplierId && trimmedQuery) {
        const cleanQuery = trimmedQuery.toLowerCase().replace(/^#/, '');
        const matchedSupplier = activeSuppliers.find(
          (s) => s.name?.toLowerCase().includes(cleanQuery)
        );
        if (matchedSupplier) {
          resolvedSupplierId = matchedSupplier.id;
        }
      }

      // Nếu ở tab Lịch sử và chọn ALL_HISTORY, gọi song song cả CONFIRMED và CANCELLED để gộp đầy đủ lịch sử
      if (topTab === 'HISTORY' && activeTab === 'ALL_HISTORY') {
        const [confirmedRes, cancelledRes] = await Promise.all([
          receiptsApi.list({
            page: pagination.page,
            pageSize: pagination.page_size,
            status: 'CONFIRMED',
            supplierId: resolvedSupplierId,
            fromDate: fromDateFilter,
            toDate: toDateFilter,
          }).catch(() => ({ items: [], total: 0 })),
          receiptsApi.list({
            page: pagination.page,
            pageSize: pagination.page_size,
            status: 'CANCELLED',
            supplierId: resolvedSupplierId,
            fromDate: fromDateFilter,
            toDate: toDateFilter,
          }).catch(() => ({ items: [], total: 0 })),
        ]);

        if (currentRequestId === requestIdRef.current) {
          const merged = [...(confirmedRes.items || []), ...(cancelledRes.items || [])].sort(
            (a, b) => b.id - a.id
          );
          setData(merged);
          setPagination((prev) => ({
            ...prev,
            total: (confirmedRes.total || 0) + (cancelledRes.total || 0),
            totalPages: Math.max(1, Math.ceil(((confirmedRes.total || 0) + (cancelledRes.total || 0)) / pagination.page_size)),
          }));
          return;
        }
      }

      let statusParam = '';
      if (activeTab === 'DRAFT' || activeTab === 'CONFIRMED' || activeTab === 'CANCELLED') {
        statusParam = activeTab;
      } else if (topTab === 'RECEIPTS' && activeTab === 'ALL') {
        statusParam = ''; // Xem tất cả ở tab phiếu nhập
      }

      const res = await receiptsApi.list({
        page: pagination.page,
        pageSize: pagination.page_size,
        status: statusParam,
        supplierId: resolvedSupplierId,
        fromDate: fromDateFilter,
        toDate: toDateFilter,
      });

      if (currentRequestId === requestIdRef.current) {
        setData(res.items || []);
        setPagination((prev) => ({
          ...prev,
          total: res.total || 0,
          totalPages: res.total_pages || 1,
        }));

        // Không tự động set selectedReceiptId khi load danh sách
        // Chỉ load chi tiết khi người dùng chủ động click xem/sửa
        setSelectedReceiptId((prevId) => {
          if (prevId && res.items && res.items.some((r) => r.id === prevId)) return prevId;
          return null;
        });
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        // Nếu Backend chưa có endpoint GET list (404/405), coi danh sách là rỗng và không spam toast lỗi đỏ
        if (err.response?.status === 404 || err.response?.status === 405) {
          setData([]);
          setPagination((prev) => ({ ...prev, total: 0, totalPages: 1 }));
        } else {
          toast.error(getApiErrorMessage(err, 'Không thể tải danh sách phiếu nhập.'));
        }
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [
    topTab,
    activeTab,
    pagination.page,
    pagination.page_size,
    supplierFilter,
    searchQuery,
    activeSuppliers,
    fromDateFilter,
    toDateFilter,
    toast,
  ]);

  useEffect(() => {
    loadReceipts();
  }, [loadReceipts, refreshTrigger]);

  // Load số lượng đếm thống kê cho 2 tab "Phiếu nhập" (DRAFT) và "Lịch sử nhập hàng" (CONFIRMED/CANCELLED)
  useEffect(() => {
    let isMounted = true;
    async function loadCounts() {
      try {
        const [draftRes, historyConfirmedRes, historyCancelledRes] = await Promise.all([
          receiptsApi.list({ page: 1, pageSize: 1, status: 'DRAFT' }).catch(() => ({ total: 0 })),
          receiptsApi.list({ page: 1, pageSize: 1, status: 'CONFIRMED' }).catch(() => ({ total: 0 })),
          receiptsApi.list({ page: 1, pageSize: 1, status: 'CANCELLED' }).catch(() => ({ total: 0 })),
        ]);
        if (isMounted) {
          setDraftCount(draftRes?.total || 0);
          setHistoryCount((historyConfirmedRes?.total || 0) + (historyCancelledRes?.total || 0));
        }
      } catch {
        // im lặng nếu không lấy được đếm
      }
    }
    loadCounts();
    return () => {
      isMounted = false;
    };
  }, [refreshTrigger]);

  // Load chi tiết phiếu nhập chỉ khi Modal Chi tiết ĐANG MỞ và có selectedReceiptId
  const loadReceiptDetail = useCallback(async (receiptId) => {
    if (!receiptId || !isDetailModalOpen) return;
    setIsDetailLoading(true);
    setConflictError(null);
    try {
      const receipt = await receiptsApi.get(receiptId);
      setSelectedReceipt(receipt);
      // Chuẩn bị dữ liệu form chỉnh sửa nếu là DRAFT
      if (receipt.status === 'DRAFT') {
        setEditSupplierId(String(receipt.supplier_id));
        setEditLines(
          receipt.items.map((it) => ({
            product_id: String(it.product_id),
            quantity: it.quantity,
            unit_cost_vnd: it.unit_cost_vnd,
          }))
        );
      } else {
        setIsEditingDraft(false);
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Không thể tải chi tiết phiếu nhập.'));
    } finally {
      setIsDetailLoading(false);
    }
  }, [isDetailModalOpen, toast]);

  // Chỉ gọi API get chi tiết khi người dùng chủ động mở modal chi tiết (isDetailModalOpen === true)
  useEffect(() => {
    if (isDetailModalOpen && selectedReceiptId) {
      loadReceiptDetail(selectedReceiptId);
    } else if (!isDetailModalOpen) {
      setSelectedReceipt(null);
    }
  }, [isDetailModalOpen, selectedReceiptId, loadReceiptDetail]);

  // Thao tác: Mở Modal Tạo phiếu nhập mới (Create Mode)
  const handleOpenCreateModal = () => {
    setCreateSupplierId('');
    setCreateLines([{ product_id: '', quantity: 1, unit_cost_vnd: 0 }]);
    setIsCreateModalOpen(true);
  };

  const handleAddCreateLine = () => {
    setCreateLines((prev) => [...prev, { product_id: '', quantity: 1, unit_cost_vnd: 0 }]);
  };

  const handleRemoveCreateLine = (index) => {
    setCreateLines((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleUpdateCreateLine = (index, field, value) => {
    setCreateLines((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  // Submit Tạo mới bản nháp (POST /api/v1/purchase-receipts)
  const handleSubmitCreateDraft = async (e) => {
    e.preventDefault();
    if (!createSupplierId) {
      toast.error('Vui lòng chọn nhà cung cấp.');
      return;
    }
    if (!createLines || createLines.length === 0) {
      toast.error('Phiếu nhập phải có ít nhất 1 dòng sản phẩm.');
      return;
    }

    setIsActionLoading(true);
    try {
      const created = await receiptsApi.createDraft({
        supplier_id: Number(createSupplierId),
        items: createLines.map((l) => ({
          product_id: Number(l.product_id),
          quantity: Number(l.quantity),
          unit_cost_vnd: Number(l.unit_cost_vnd),
        })),
      });

      toast.success(`Tạo phiếu nhập nháp #${created.id} thành công!`);
      setIsCreateModalOpen(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Lỗi khi tạo phiếu nhập nháp.'));
    } finally {
      setIsActionLoading(false);
    }
  };

  // Thao tác sửa dòng trong DRAFT
  const handleAddEditLine = () => {
    setEditLines((prev) => [...prev, { product_id: '', quantity: 1, unit_cost_vnd: 0 }]);
  };

  const handleRemoveEditLine = (index) => {
    setEditLines((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleUpdateEditLine = (index, field, value) => {
    setEditLines((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  // Thao tác: Lưu bản nháp (PATCH /api/v1/purchase-receipts/:id)
  const handleSaveDraft = async () => {
    if (!selectedReceipt || selectedReceipt.status !== 'DRAFT') return;
    if (!editLines || editLines.length === 0) {
      toast.error('Phiếu nhập phải có ít nhất 1 mặt hàng.');
      return;
    }

    // 1. Kiểm tra dirty-state: nếu không có bất kỳ thay đổi nào so với bản nháp ban đầu thì không bắn API
    const isSupplierChanged = Number(editSupplierId) !== Number(selectedReceipt.supplier_id);
    const originalItems = selectedReceipt.items || [];
    let areLinesChanged = editLines.length !== originalItems.length;

    if (!areLinesChanged) {
      for (let i = 0; i < editLines.length; i++) {
        const cur = editLines[i];
        const orig = originalItems[i];
        if (
          Number(cur.product_id) !== Number(orig.product_id) ||
          Number(cur.quantity) !== Number(orig.quantity) ||
          Number(cur.unit_cost_vnd) !== Number(orig.unit_cost_vnd)
        ) {
          areLinesChanged = true;
          break;
        }
      }
    }

    if (!isSupplierChanged && !areLinesChanged) {
      toast.info('Không có thay đổi nào để lưu.');
      setIsEditingDraft(false);
      setIsDetailModalOpen(false);
      setSelectedReceiptId(null);
      setSelectedReceipt(null);
      return;
    }

    setIsActionLoading(true);
    setConflictError(null);
    try {
      const updated = await receiptsApi.updateDraft(selectedReceipt.id, {
        expected_draft_version: selectedReceipt.draft_version,
        supplier_id: Number(editSupplierId),
        items: editLines.map((l) => ({
          product_id: Number(l.product_id),
          quantity: Number(l.quantity),
          unit_cost_vnd: Number(l.unit_cost_vnd),
        })),
      });

      toast.success(`Đã lưu bản nháp phiếu #${updated.id} (Phiên bản v${updated.draft_version})!`);
      setSelectedReceipt(updated);
      setIsEditingDraft(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      const errMsg = getApiErrorMessage(err, 'Lỗi khi lưu bản nháp.');
      if (err.response?.status === 409) {
        setConflictError(errMsg || 'Phiên bản nháp đã cũ do có người chỉnh sửa. Vui lòng tải lại phiếu.');
      }
      toast.error(errMsg);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Thao tác: Xác nhận phiếu nhập (POST /api/v1/purchase-receipts/:id/confirm)
  const handleConfirmPurchase = async () => {
    if (!selectedReceipt || selectedReceipt.status !== 'DRAFT') return;
    setIsActionLoading(true);
    setConflictError(null);
    try {
      const confirmed = await receiptsApi.confirm(selectedReceipt.id, {
        expected_draft_version: selectedReceipt.draft_version,
      });
      toast.success(`Đã xác nhận phiếu nhập #${confirmed.id} thành công! Kho đã được cập nhật.`);
      setSelectedReceipt(confirmed);
      setIsEditingDraft(false);
      setIsDetailModalOpen(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      const errMsg = getApiErrorMessage(err, 'Lỗi khi xác nhận phiếu nhập.');
      if (err.response?.status === 409) {
        setConflictError(errMsg || 'Phiếu nhập đã được xác nhận hoặc phiên bản nháp đã cũ. Vui lòng tải lại.');
      }
      toast.error(errMsg);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Thao tác: Mở modal xác nhận hủy phiếu nhập nháp (PUR-04)
  const handleOpenCancelModal = () => {
    if (!selectedReceipt || selectedReceipt.status !== 'DRAFT') return;
    setIsCancelModalOpen(true);
  };

  // Xác nhận hủy phiếu nhập từ trong Modal (POST /api/v1/purchase-receipts/:id/cancel)
  const handleConfirmCancelPurchase = async () => {
    if (!selectedReceipt || selectedReceipt.status !== 'DRAFT') return;
    setIsActionLoading(true);
    try {
      const cancelled = await receiptsApi.cancel(selectedReceipt.id, {
        expected_draft_version: selectedReceipt.draft_version,
      });
      toast.error(`Đã hủy phiếu nhập nháp #${cancelled.id}.`);
      setSelectedReceipt(cancelled);
      setIsCancelModalOpen(false);
      setIsDetailModalOpen(false);
      setIsEditingDraft(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Lỗi khi hủy phiếu nhập.'));
    } finally {
      setIsActionLoading(false);
    }
  };

  // Bảng danh sách phiếu nhập
  const columns = useMemo(
    () => [
      {
        key: 'id',
        title: 'MÃ PHIẾU',
        width: '100px',
        render: (row) => {
          const isSelected = selectedReceipt?.id === row.id;
          return (
            <span className={styles.purchaseCode}>
              {isSelected && <span className={styles.activeDot} />}
              <span>#{row.id}</span>
            </span>
          );
        },
      },
      {
        key: 'supplier_name_snapshot',
        title: 'NHÀ CUNG CẤP',
        render: (row) => (
          <span className={styles.supplierNameCell} title={row.supplier_name_snapshot || `NCC ID: ${row.supplier_id}`}>
            {row.supplier_name_snapshot || `NCC #${row.supplier_id}`}
          </span>
        ),
      },
      {
        key: 'items_count',
        title: 'SỐ MẶT HÀNG',
        align: 'center',
        width: '120px',
        render: (row) => {
          const count = Array.isArray(row.items) ? row.items.length : 0;
          return (
            <span style={{ fontWeight: 600, color: '#374151' }}>
              {count} {count > 0 ? 'mặt hàng' : '—'}
            </span>
          );
        },
      },
      {
        key: 'created_at',
        title: 'THỜI GIAN TẠO',
        width: '140px',
        render: (row) => <span className={styles.dateCell}>{formatDate(row.created_at)}</span>,
      },
      {
        key: 'total_vnd',
        title: 'TỔNG TIỀN',
        align: 'right',
        width: '130px',
        render: (row) => (
          <span className={styles.amountCell}>{formatVND(row.total_vnd)}</span>
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI',
        width: '130px',
        align: 'center',
        render: (row) => {
          if (row.status === 'CONFIRMED') {
            return <span className={styles.statusBadgeConfirmed}>Đã nhập</span>;
          }
          if (row.status === 'CANCELLED') {
            return <span className={styles.statusBadgeCancelled}>Đã hủy</span>;
          }
          return <span className={styles.statusBadgeDraft}>Bản nháp (v{row.draft_version})</span>;
        },
      },
      {
        key: 'actions',
        title: 'THAO TÁC',
        align: 'center',
        width: '110px',
        render: (row) => {
          return (
            <button
              type="button"
              className={styles.viewDetailBtn}
              onClick={() => {
                setSelectedReceiptId(row.id);
                setIsDetailModalOpen(true);
              }}
              title="Xem / Thao tác phiếu nhập"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <span>{row.status === 'DRAFT' ? 'Sửa nháp' : 'Chi tiết'}</span>
            </button>
          );
        },
      },
    ],
    [selectedReceipt]
  );

  const startRecord = pagination.total === 0 ? 0 : (pagination.page - 1) * pagination.page_size + 1;
  const endRecord = Math.min(pagination.page * pagination.page_size, pagination.total);

  // Client-side search & View Mode: Đảm bảo khi đang ở tab "Lịch sử nhập hàng", chỉ hiển thị phiếu đã hoàn tất (CONFIRMED / CANCELLED)
  const filteredData = useMemo(() => {
    let list = data;

    // Khi ở tab "Lịch sử nhập hàng" và chọn ALL_HISTORY, lọc bỏ DRAFT
    if (topTab === 'HISTORY') {
      list = list.filter((row) => row.status === 'CONFIRMED' || row.status === 'CANCELLED');
    } else if (topTab === 'RECEIPTS' && activeTab === 'DRAFT') {
      list = list.filter((row) => row.status === 'DRAFT');
    }

    if (!searchQuery.trim()) return list;
    const query = searchQuery.trim().toLowerCase();
    return list.filter((row) => {
      const idMatch = String(row.id).toLowerCase().includes(query) || (`#${row.id}`).includes(query);
      const supplierMatch = (row.supplier_name_snapshot || '').toLowerCase().includes(query);
      return idMatch || supplierMatch;
    });
  }, [data, topTab, activeTab, searchQuery]);

  // Xử lý chuyển tab Top "Phiếu nhập" vs "Lịch sử nhập hàng"
  const handleTopTabChange = (tab) => {
    setTopTab(tab);
    setSelectedReceiptId(null);
    setSelectedReceipt(null);
    setIsDetailModalOpen(false);
    if (tab === 'RECEIPTS') {
      // Tab "Phiếu nhập": chỉ quản lý phiếu DRAFT
      setActiveTab('DRAFT');
    } else {
      // Tab "Lịch sử nhập hàng": mặc định xem tất cả lịch sử (CONFIRMED hoặc CANCELLED)
      setActiveTab('ALL_HISTORY');
    }
    setPagination((prev) => ({ ...prev, page: 1 }));
  };

  // Xử lý chọn khoảng thời gian nhanh (30 ngày gần nhất, 7 ngày, Hôm nay, ...) theo múi giờ Asia/Ho_Chi_Minh
  const handleDateRangePreset = (type) => {
    setDateRangeType(type);
    const now = new Date();
    // Lấy chuỗi YYYY-MM-DD chuẩn theo múi giờ Asia/Ho_Chi_Minh
    const toStr = now.toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });

    if (type === '30DAYS') {
      const from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      setFromDateFilter(from.toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }));
      setToDateFilter(toStr);
    } else if (type === '7DAYS') {
      const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      setFromDateFilter(from.toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }));
      setToDateFilter(toStr);
    } else if (type === 'TODAY') {
      setFromDateFilter(toStr);
      setToDateFilter(toStr);
    } else if (type === 'ALL') {
      setFromDateFilter('');
      setToDateFilter('');
    }
    setPagination((prev) => ({ ...prev, page: 1 }));
  };

  // Quyền: ADMIN-only
  if (!isAdmin) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <h1 className={styles.title}>Quản lý nhập hàng</h1>
            <p className={styles.subtitle}>Chức năng dành riêng cho Quản trị viên (ADMIN).</p>
          </div>
        </div>
        <div className={styles.readOnlyNotice} style={{ color: '#DC2626', backgroundColor: '#FEF2F2' }}>
          Bạn không có quyền truy cập chức năng này. Vui lòng liên hệ Quản trị viên.
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* 1. Header Trang */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>Quản lý nhập hàng</h1>
          <p className={styles.subtitle}>
            Tạo và xử lý phiếu nhập kho từ nhà cung cấp
          </p>
        </div>

        <button
          type="button"
          className={styles.primaryBtn}
          onClick={handleOpenCreateModal}
          disabled={isActionLoading}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>Thêm phiếu nhập</span>
        </button>
      </div>

      {/* 2. Sub-Header: Hai tab "Phiếu nhập" & "Lịch sử nhập hàng" theo mockup */}
      <div className={styles.subHeaderRow}>
        <div className={styles.navTabs}>
          <button
            type="button"
            className={`${styles.navTabBtn} ${topTab === 'RECEIPTS' ? styles.navTabBtnActive : ''}`}
            onClick={() => handleTopTabChange('RECEIPTS')}
          >
            <span>Phiếu nhập</span>
            {draftCount > 0 && <span className={styles.tabCountBadge}>{draftCount}</span>}
          </button>

          <button
            type="button"
            className={`${styles.navTabBtn} ${topTab === 'HISTORY' ? styles.navTabBtnActive : ''}`}
            onClick={() => handleTopTabChange('HISTORY')}
          >
            <span>Lịch sử nhập hàng</span>
            {historyCount > 0 && <span className={styles.tabCountBadgeGray}>{historyCount}</span>}
          </button>
        </div>

        <div className={styles.warehouseHint}>
          Kho áp dụng: <strong>Kho cửa hàng</strong>
        </div>
      </div>

      {/* 3. Thanh tìm kiếm và bộ lọc theo mockup */}
      <div className={styles.filtersRow}>
        {/* Ô tìm kiếm theo mã phiếu, nhà cung cấp */}
        <div className={styles.searchInputWrapper}>
          <svg className={styles.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Tìm theo mã phiếu, nhà cung cấp..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPagination((prev) => ({ ...prev, page: 1 }));
            }}
          />
        </div>

        {/* Dropdown lọc theo Trạng thái (Đồng bộ theo tab Top) */}
        <select
          className={styles.selectBox}
          value={activeTab}
          onChange={(e) => {
            setActiveTab(e.target.value);
            setPagination((prev) => ({ ...prev, page: 1 }));
          }}
        >
          {topTab === 'HISTORY' ? (
            <>
              <option value="ALL_HISTORY">Trạng thái: Tất cả lịch sử</option>
              <option value="CONFIRMED">Trạng thái: Đã nhập </option>
              <option value="CANCELLED">Trạng thái: Đã hủy </option>
            </>
          ) : (
            <>
              <option value="DRAFT">Trạng thái: Bản nháp </option>
              <option value="ALL">Trạng thái: Tất cả trạng thái</option>
            </>
          )}
        </select>

        {/* Dropdown lọc Nhà cung cấp */}
        <select
          className={styles.selectBox}
          value={supplierFilter}
          onChange={(e) => {
            setSupplierFilter(e.target.value);
            setPagination((prev) => ({ ...prev, page: 1 }));
          }}
        >
          <option value="">Nhà cung cấp: Tất cả</option>
          {activeSuppliers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>

        {/* Dropdown chọn khoảng thời gian */}
        <select
          className={styles.selectBox}
          value={dateRangeType}
          onChange={(e) => handleDateRangePreset(e.target.value)}
        >
          <option value="ALL">Thời gian: Toàn bộ</option>
          <option value="30DAYS">Thời gian: 30 ngày gần nhất </option>
          <option value="7DAYS">Thời gian: 7 ngày gần nhất </option>
          <option value="TODAY">Thời gian: Hôm nay </option>
          <option value="CUSTOM">Thời gian: Tùy chỉnh </option>
        </select>

        {/* Khoảng ngày tùy chỉnh nếu chọn CUSTOM */}
        {dateRangeType === 'CUSTOM' && (
          <div className={styles.customDatePopover}>
            <div className={styles.dateInputGroup}>
              <span>Từ:</span>
              <input
                type="date"
                className={styles.dateInput}
                value={fromDateFilter}
                onChange={(e) => {
                  setFromDateFilter(e.target.value);
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              />
            </div>
            <div className={styles.dateInputGroup}>
              <span>Đến:</span>
              <input
                type="date"
                className={styles.dateInput}
                value={toDateFilter}
                onChange={(e) => {
                  setToDateFilter(e.target.value);
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              />
            </div>
          </div>
        )}

        {(supplierFilter ||
          (topTab === 'HISTORY' ? activeTab !== 'ALL_HISTORY' : activeTab !== 'DRAFT') ||
          fromDateFilter ||
          toDateFilter ||
          searchQuery ||
          dateRangeType !== 'ALL') && (
          <button
            type="button"
            className={styles.clearFilterBtn}
            onClick={() => {
              setSupplierFilter('');
              setActiveTab(topTab === 'HISTORY' ? 'ALL_HISTORY' : 'DRAFT');
              setDateRangeType('ALL');
              setFromDateFilter('');
              setToDateFilter('');
              setSearchQuery('');
              setPagination((prev) => ({ ...prev, page: 1 }));
            }}
          >
            Xóa bộ lọc
          </button>
        )}
      </div>

      {/* 4. Bảng danh sách phiếu nhập */}
      <div className={styles.tableCard}>
        <Table
          columns={columns}
          data={filteredData}
          rowKey="id"
          isLoading={isLoading}
          emptyText="Không tìm thấy phiếu nhập nào"
        />

        <div className={styles.paginationBar}>
          <span className={styles.paginationSummary}>
            Hiển thị <strong>{startRecord} - {endRecord}</strong> trên <strong>{pagination.total}</strong> phiếu nhập
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

      {/* 5. Modal Chi tiết & Thao tác Phiếu nhập kho (Tái sử dụng common/Modal) */}
      <Modal
        isOpen={isDetailModalOpen}
        onClose={() => {
          if (!isActionLoading) {
            setIsDetailModalOpen(false);
            setSelectedReceiptId(null);
            setSelectedReceipt(null);
            setIsEditingDraft(false);
            setConflictError(null);
          }
        }}
        title={
          selectedReceipt
            ? `Chi tiết phiếu nhập #${selectedReceipt.id}`
            : 'Chi tiết phiếu nhập kho'
        }
        maxWidth="780px"
        footer={
          selectedReceipt && selectedReceipt.status === 'DRAFT' ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
              <button
                type="button"
                className={modalStyles.dangerBtn}
                onClick={handleOpenCancelModal}
                disabled={isActionLoading}
              >
                Hủy phiếu
              </button>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  className={modalStyles.cancelBtn}
                  onClick={handleSaveDraft}
                  disabled={isActionLoading}
                >
                  {isActionLoading ? 'Đang lưu...' : 'Lưu nháp'}
                </button>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  onClick={handleConfirmPurchase}
                  disabled={isActionLoading}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>{isActionLoading ? 'Đang xử lý...' : 'Xác nhận nhập kho'}</span>
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={() => {
                setIsDetailModalOpen(false);
                setSelectedReceiptId(null);
                setSelectedReceipt(null);
              }}
            >
              Đóng
            </button>
          )
        }
      >
        {isDetailLoading ? (
          <div style={{ padding: '32px 0', textAlign: 'center', color: '#6B7280' }}>
            <span>Đang tải chi tiết phiếu nhập...</span>
          </div>
        ) : selectedReceipt ? (
          <div>
            {/* Header trạng thái */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {selectedReceipt.status === 'CONFIRMED' && (
                  <span className={styles.statusBadgeConfirmed}>(ĐÃ NHẬP)</span>
                )}
                {selectedReceipt.status === 'CANCELLED' && (
                  <span className={styles.statusBadgeCancelled}>(ĐÃ HỦY)</span>
                )}
                {selectedReceipt.status === 'DRAFT' && (
                  <span className={styles.statusBadgeDraft}>BẢN NHÁP </span>
                )}
              </div>
            </div>

            {/* Banner cảnh báo xung đột phiên bản 409 Conflict */}
            {conflictError && (
              <div className={styles.conflictAlert}>
                <strong>Phiên bản đã thay đổi!</strong>
                <span>{conflictError}</span>
                <button
                  type="button"
                  className={styles.reloadBtn}
                  onClick={() => loadReceiptDetail(selectedReceipt.id)}
                >
                  Tải lại phiếu mới nhất
                </button>
              </div>
            )}

            {/* Meta info */}
            <div className={styles.metaInfoRow}>
              <div>
                Tạo lúc: <strong>{formatDate(selectedReceipt.created_at)}</strong>
              </div>
              <div>
                Phiên bản: <strong>v{selectedReceipt.draft_version}</strong>
              </div>
            </div>

            {/* Thông tin NCC & Trạng thái */}
            <div className={styles.infoGrid}>
              <div className={styles.infoBlock}>
                <span className={styles.infoLabel}>NHÀ CUNG CẤP</span>
                {selectedReceipt.status === 'DRAFT' && isEditingDraft ? (
                  <select
                    className={styles.formSelect}
                    value={editSupplierId}
                    onChange={(e) => setEditSupplierId(e.target.value)}
                  >
                    {activeSuppliers.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <>
                    <span className={styles.infoValue}>
                      {selectedReceipt.supplier_name_snapshot || `NCC #${selectedReceipt.supplier_id}`}
                    </span>
                  </>
                )}
              </div>
              <div className={styles.infoBlock}>
                <span className={styles.infoLabel}>TRẠNG THÁI CHỨNG TỪ</span>
                <span className={styles.infoValue}>
                  {selectedReceipt.status === 'CONFIRMED'
                    ? 'ĐÃ XÁC NHẬN'
                    : selectedReceipt.status === 'CANCELLED'
                    ? 'ĐÃ HỦY'
                    : 'BẢN NHÁP'}
                </span>
                {selectedReceipt.closed_at && (
                  <span className={styles.infoSub}>Đóng lúc: {formatDate(selectedReceipt.closed_at)}</span>
                )}
              </div>
            </div>

            {/* Danh sách mặt hàng nhập */}
            <div className={styles.itemsSection}>
              <div className={styles.itemsHeader}>
                <span className={styles.itemsTitle}>
                  DANH SÁCH MẶT HÀNG ({selectedReceipt.items?.length || 0} SẢN PHẨM)
                </span>
                {selectedReceipt.status === 'DRAFT' && !isEditingDraft && (
                  <button
                    type="button"
                    className={styles.addItemLink}
                    onClick={() => {
                      setIsEditingDraft(true);
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                    <span>Chỉnh sửa mặt hàng</span>
                  </button>
                )}
              </div>

              {selectedReceipt.status === 'DRAFT' && isEditingDraft ? (
                // Chế độ chỉnh sửa dòng mặt hàng
                <div>
                  <div className={styles.lineHeaderRow}>
                    <span>Sản phẩm</span>
                    <span>Số lượng</span>
                    <span>Đơn giá nhập (đ)</span>
                    <span></span>
                  </div>

                  {editLines.map((line, idx) => (
                    <div key={idx} className={styles.lineInputRow}>
                      <select
                        className={styles.formSelect}
                        value={line.product_id}
                        onChange={(e) => handleUpdateEditLine(idx, 'product_id', e.target.value)}
                      >
                        <option value="">-- Chọn sản phẩm --</option>
                        {activeProducts.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.sku} - {p.name}
                          </option>
                        ))}
                      </select>

                      <input
                        type="number"
                        min="1"
                        className={styles.formInput}
                        placeholder="Số lượng nhập"
                        value={line.quantity}
                        onChange={(e) => handleUpdateEditLine(idx, 'quantity', e.target.value)}
                      />

                      <input
                        type="number"
                        min="0"
                        className={styles.formInput}
                        placeholder="Đơn giá nhập"
                        value={line.unit_cost_vnd}
                        onChange={(e) => handleUpdateEditLine(idx, 'unit_cost_vnd', e.target.value)}
                      />

                      <button
                        type="button"
                        className={styles.removeLineBtn}
                        onClick={() => handleRemoveEditLine(idx)}
                        disabled={editLines.length <= 1}
                        title="Xóa dòng"
                      >
                        ✕
                      </button>
                    </div>
                  ))}

                  <button
                    type="button"
                    className={styles.addLineBtn}
                    onClick={handleAddEditLine}
                  >
                    + Thêm dòng sản phẩm
                  </button>
                </div>
              ) : (
                // Chế độ xem bảng chi tiết
                <table className={styles.itemsTable}>
                  <thead>
                    <tr>
                      <th>Sản phẩm</th>
                      <th>SL</th>
                      <th>Đơn giá (đ)</th>
                      <th>Thành tiền (đ)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(selectedReceipt.items || []).map((item) => (
                      <tr key={item.product_id}>
                        <td>
                          <div className={styles.itemMainName}>{item.product_name_snapshot}</div>
                          <div className={styles.itemSubSku}>
                            SKU: {item.sku_snapshot}
                          </div>
                        </td>
                        <td className={styles.qtyBadge}>{item.quantity}</td>
                        <td className={styles.unitPrice}>
                          {(item.unit_cost_vnd || 0).toLocaleString('vi-VN')}
                        </td>
                        <td className={styles.lineTotal}>
                          {(item.line_total_vnd || 0).toLocaleString('vi-VN')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Tổng số lượng & Tổng tiền */}
            <div className={styles.summaryBlock}>
              <div className={styles.summaryTotalRow}>
                <span>Tổng tiền phiếu nhập:</span>
                <span className={styles.totalHighlight}>
                  {formatVND(selectedReceipt.total_vnd)}
                </span>
              </div>
            </div>

            {/* Lưu ý khi thao tác */}
            {selectedReceipt.status === 'DRAFT' ? (
              <div className={styles.confirmWarningBox}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, marginTop: 1 }}>
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                <div>
                  <strong>BẢN NHÁP</strong> chưa làm tăng số lượng tồn kho. Khi bấm <strong>xác nhận phiếu</strong>, hệ thống sẽ tăng tồn kho thực tế, khóa bất biến chứng từ và chuyển sang trạng thái <strong>ĐÃ XÁC NHẬN</strong>.
                </div>
              </div>
            ) : (
              <div className={styles.readOnlyNotice}>
                Chứng từ này đã ở trạng thái <strong>{selectedReceipt.status === 'CONFIRMED' ? 'ĐÃ NHẬP KHO' : 'ĐÃ HỦY'}</strong>. Mọi thông tin đã được khóa bất biến và không thể chỉnh sửa hay hủy bỏ.
              </div>
            )}
          </div>
        ) : null}
      </Modal>

      {/* 5. Modal Tạo mới phiếu nhập nháp (Create Mode) */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => !isActionLoading && setIsCreateModalOpen(false)}
        title="Tạo mới phiếu nhập hàng"
        maxWidth="680px"
        footer={
          <>
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={() => setIsCreateModalOpen(false)}
              disabled={isActionLoading}
            >
              Hủy bỏ
            </button>
            <button
              type="button"
              className={modalStyles.confirmBtn}
              onClick={handleSubmitCreateDraft}
              disabled={isActionLoading}
            >
              {isActionLoading ? 'Đang tạo...' : 'Tạo bản nháp'}
            </button>
          </>
        }
      >
        <form onSubmit={handleSubmitCreateDraft}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>
              Nhà cung cấp  <span style={{ color: '#DC2626' }}>*</span>
            </label>
            <select
              className={styles.formSelect}
              value={createSupplierId}
              onChange={(e) => setCreateSupplierId(e.target.value)}
              required
            >
              <option value="">-- Chọn nhà cung cấp --</option>
              {activeSuppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>
              Danh sách sản phẩm nhập <span style={{ color: '#DC2626' }}>*</span>
            </label>

            <div className={styles.lineHeaderRow}>
              <span>Sản phẩm</span>
              <span>Số lượng</span>
              <span>Đơn giá nhập (đ)</span>
              <span></span>
            </div>

            {createLines.map((line, idx) => (
              <div key={idx} className={styles.lineInputRow}>
                <select
                  className={styles.formSelect}
                  value={line.product_id}
                  onChange={(e) => handleUpdateCreateLine(idx, 'product_id', e.target.value)}
                  required
                >
                  <option value="">-- Chọn sản phẩm --</option>
                  {activeProducts.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} - {p.name}
                    </option>
                  ))}
                </select>

                <input
                  type="number"
                  min="1"
                  className={styles.formInput}
                  placeholder="Số lượng nhập"
                  value={line.quantity}
                  onChange={(e) => handleUpdateCreateLine(idx, 'quantity', e.target.value)}
                  required
                />

                <input
                  type="number"
                  min="0"
                  className={styles.formInput}
                  placeholder="Đơn giá nhập"
                  value={line.unit_cost_vnd}
                  onChange={(e) => handleUpdateCreateLine(idx, 'unit_cost_vnd', e.target.value)}
                  required
                />

                <button
                  type="button"
                  className={styles.removeLineBtn}
                  onClick={() => handleRemoveCreateLine(idx)}
                  disabled={createLines.length <= 1}
                  title="Xóa dòng"
                >
                  ✕
                </button>
              </div>
            ))}

            <button
              type="button"
              className={styles.addLineBtn}
              onClick={handleAddCreateLine}
            >
              + Thêm dòng sản phẩm
            </button>
          </div>
        </form>
      </Modal>

      {/* 6. Modal xác nhận hủy phiếu nhập dùng component common/Modal */}
      <Modal
        isOpen={isCancelModalOpen}
        onClose={() => !isActionLoading && setIsCancelModalOpen(false)}
        title="Xác nhận hủy phiếu nhập nháp"
        footer={
          <>
            <button
              type="button"
              className={modalStyles.cancelBtn}
              onClick={() => setIsCancelModalOpen(false)}
              disabled={isActionLoading}
            >
              Quay lại
            </button>
            <button
              type="button"
              className={modalStyles.dangerBtn}
              onClick={handleConfirmCancelPurchase}
              disabled={isActionLoading}
            >
              {isActionLoading ? 'Đang hủy...' : 'Xác nhận hủy phiếu'}
            </button>
          </>
        }
      >
        <p style={{ margin: 0, fontSize: '14px', lineHeight: 1.5, color: '#374151' }}>
          Bạn có chắc chắn muốn hủy bản nháp phiếu nhập{' '}
          <strong style={{ color: '#111827' }}>#{selectedReceipt?.id}</strong>?
          Thao tác này sẽ đánh dấu phiếu thành CANCELLED và không thể khôi phục.
        </p>
      </Modal>
    </div>
  );
}
