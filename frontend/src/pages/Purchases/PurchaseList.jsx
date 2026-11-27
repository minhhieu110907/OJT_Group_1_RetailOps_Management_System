import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  useInRouterContext,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import {
  CustomDatePicker,
  CustomSelect,
  Modal,
  Pagination,
  Table,
  useToast,
} from '../../components/common';
import PrintablePurchaseReceipt from '../../components/purchases/PrintablePurchaseReceipt';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import { getApiErrorMessage } from '../../api/axiosClient';
import {
  MAX_HISTORY_MERGE_WINDOW,
  createConfirmIntentTracker,
  createDetailRequestGuard,
  parseReceiptSearchInput,
  receiptsApi,
} from '../../api/receiptsApi';
import { suppliersApi } from '../../api/suppliersApi';
import { productsApi } from '../../api/productsApi';
import { useAuth } from '../../context/AuthContext';
import { buildPrefillDraftState } from '../../utils/reorderSuggestions';
import { downloadStyledExcelRows } from '../../utils/csvDownload';
import {
  MAX_EXPORT_ROWS,
  buildPurchaseReceiptExportRows,
  collectPurchaseReceiptsForExport,
  formatPurchaseExportMessage,
} from '../../utils/exportReportHelpers';
import {
  filterProductsBySupplierCategories,
  findAutoFillSupplierForProduct,
  resetIncompatibleProductLines,
} from '../../utils/purchaseSupplierLinkUtils';
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
    const utcStr =
      raw.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(raw)
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

function PurchaseRouterStateConsumer({ onPrefillDraft, onOpenReceiptId }) {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const state = location?.state;
    if (!state || typeof state !== 'object') return;

    let consumed = false;
    if (state.prefillDraft && typeof state.prefillDraft === 'object') {
      onPrefillDraft(state.prefillDraft);
      consumed = true;
    } else if (state.openReceiptId !== undefined && state.openReceiptId !== null) {
      onOpenReceiptId(state.openReceiptId);
      consumed = true;
    }

    if (consumed) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location, navigate, onPrefillDraft, onOpenReceiptId]);

  return null;
}

export default function PurchaseList() {
  const toast = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const inRouter = useInRouterContext();

  // 1. Tab điều hướng trên cùng & Trạng thái lọc
  const [topTab, setTopTab] = useState('RECEIPTS'); // 'RECEIPTS' (Phiếu nhập) | 'HISTORY' (Lịch sử)
  const [activeTab, setActiveTab] = useState('DRAFT'); // 'DRAFT' | 'ALL' | 'CONFIRMED' | 'CANCELLED' | 'ALL_HISTORY'

  // 2. Bộ lọc & Phân trang (100% Server-side API, không lọc cục bộ sau phân trang)
  const [supplierFilter, setSupplierFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [searchValidationError, setSearchValidationError] = useState('');
  const [dateRangeType, setDateRangeType] = useState('ALL'); // 'ALL' | '30DAYS' | '7DAYS' | 'TODAY' | 'CUSTOM'
  const [fromDateFilter, setFromDateFilter] = useState('');
  const [toDateFilter, setToDateFilter] = useState('');

  const [data, setData] = useState([]);
  const [listError, setListError] = useState('');
  const [isHistoryWindowCapped, setIsHistoryWindowCapped] = useState(false);
  const [draftCount, setDraftCount] = useState(null);
  const [historyCount, setHistoryCount] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExportingExcel, setIsExportingExcel] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const hasLoadedListOnceRef = useRef(false);
  const pendingOpenReceiptIdRef = useRef(null);

  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    total: 0,
    totalPages: 1,
  });

  // 3. Master Data: Danh sách NCC & Sản phẩm ACTIVE (bounded + server-side search)
  const [activeSuppliers, setActiveSuppliers] = useState([]);
  const [suppliersMeta, setSuppliersMeta] = useState({ total: 0, isTruncated: false });
  const [activeProducts, setActiveProducts] = useState([]);
  const [productsMeta, setProductsMeta] = useState({ total: 0, isTruncated: false });
  const [knownProductsById, setKnownProductsById] = useState({});
  const [productSearchTerm, setProductSearchTerm] = useState('');
  const [debouncedProductSearch, setDebouncedProductSearch] = useState('');
  const [isMasterDataLoading, setIsMasterDataLoading] = useState(false);
  const [masterDataError, setMasterDataError] = useState('');
  const [masterDataTrigger, setMasterDataTrigger] = useState(0);

  // 4. Phiếu đang chọn & Chi tiết phiếu (Gọi GET /purchase-receipts/:id với generation guard)
  const [selectedReceiptId, setSelectedReceiptId] = useState(null);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [detailRetryTrigger, setDetailRetryTrigger] = useState(0);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [conflictError, setConflictError] = useState(null);

  // 5. Modal Tạo phiếu mới (Create Mode)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createSupplierId, setCreateSupplierId] = useState('');
  const [createLines, setCreateLines] = useState([
    { product_id: '', quantity: 1, unit_cost_vnd: 0 },
  ]);
  const [showAllProductsInReceipt, setShowAllProductsInReceipt] = useState(false);

  // 6. Chế độ chỉnh sửa dòng của DRAFT trong panel chi tiết (Edit Draft Mode)
  const [isEditingDraft, setIsEditingDraft] = useState(false);
  const [editSupplierId, setEditSupplierId] = useState('');
  const [editLines, setEditLines] = useState([]);

  // 7. Modal xác nhận hủy phiếu nhập nháp (PUR-04)
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);

  // Guards chống race condition, stale response và double-submit
  const requestIdRef = useRef(0);
  const masterDataRequestIdRef = useRef(0);
  const productSearchRequestIdRef = useRef(0);
  const detailGuardRef = useRef(createDetailRequestGuard());
  const confirmIntentRef = useRef(createConfirmIntentTracker());
  const actionMutationLockRef = useRef(false);

  // Debounce ô tìm kiếm mã phiếu (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Debounce ô tìm kiếm sản phẩm trong Modal Tạo/Sửa (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedProductSearch(productSearchTerm.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [productSearchTerm]);

  // Tải danh mục Master Data: NCC ACTIVE (bounded multi-page) & Sản phẩm ACTIVE trang đầu
  useEffect(() => {
    if (!isAdmin) return undefined;
    const currentReqId = ++masterDataRequestIdRef.current;

    const fetchMasterData = async () => {
      setIsMasterDataLoading(true);
      setMasterDataError('');
      try {
        const [supRes, prodRes] = await Promise.all([
          suppliersApi.getActiveSuppliers({
            page: 1,
            pageSize: 100,
            fetchAll: true,
            maxPages: 10,
          }),
          productsApi.getProducts({
            page: 1,
            pageSize: 100,
            status: 'ACTIVE',
            fetchAll: true,
            maxPages: 10,
          }),
        ]);

        if (currentReqId === masterDataRequestIdRef.current) {
          const suppliers = supRes.items || [];
          const products = prodRes.items || [];
          setActiveSuppliers(suppliers);
          setSuppliersMeta({
            total: supRes.total || suppliers.length,
            isTruncated: Boolean(supRes.isTruncated),
          });
          setActiveProducts(products);
          setProductsMeta({
            total: prodRes.total || products.length,
            isTruncated: (prodRes.total || 0) > products.length,
          });
          setKnownProductsById((prev) => {
            const next = { ...prev };
            products.forEach((p) => {
              next[p.id] = p;
            });
            return next;
          });
        }
      } catch (err) {
        if (currentReqId === masterDataRequestIdRef.current) {
          setMasterDataError(
            getApiErrorMessage(
              err,
              'Không thể tải danh sách nhà cung cấp hoặc sản phẩm đang hoạt động.'
            )
          );
        }
      } finally {
        if (currentReqId === masterDataRequestIdRef.current) {
          setIsMasterDataLoading(false);
        }
      }
    };

    fetchMasterData();
    return () => {
      masterDataRequestIdRef.current += 1;
    };
  }, [isAdmin, masterDataTrigger]);

  // Tìm kiếm sản phẩm ACTIVE phía server khi người dùng gõ từ khóa trong Modal Tạo/Sửa
  useEffect(() => {
    if (!isAdmin || (!isCreateModalOpen && !isEditingDraft)) return undefined;
    const currentReqId = ++productSearchRequestIdRef.current;

    const searchActiveProducts = async () => {
      try {
        const prodRes = await productsApi.getProducts({
          page: 1,
          pageSize: 100,
          status: 'ACTIVE',
          keyword: debouncedProductSearch,
          fetchAll: false,
        });
        if (currentReqId === productSearchRequestIdRef.current) {
          const items = prodRes.items || [];
          setActiveProducts(items);
          setProductsMeta({
            total: prodRes.total || items.length,
            isTruncated: (prodRes.total || 0) > items.length,
          });
          setKnownProductsById((prev) => {
            const next = { ...prev };
            items.forEach((p) => {
              next[p.id] = p;
            });
            return next;
          });
        }
      } catch (err) {
        if (currentReqId === productSearchRequestIdRef.current) {
          toast.error(
            getApiErrorMessage(err, 'Không thể tìm kiếm danh sách sản phẩm.')
          );
        }
      }
    };

    searchActiveProducts();
    return () => {
      productSearchRequestIdRef.current += 1;
    };
  }, [isAdmin, isCreateModalOpen, isEditingDraft, debouncedProductSearch, toast]);

  const reloadMasterData = useCallback(() => {
    setMasterDataTrigger((prev) => prev + 1);
  }, []);

  // Hợp nhất danh sách sản phẩm đang hiển thị từ kết quả tìm kiếm + các sản phẩm đã được chọn ở các dòng
  const selectableProducts = useMemo(() => {
    const map = new Map();
    activeProducts.forEach((p) => {
      map.set(Number(p.id), p);
    });
    const selectedIds = [
      ...createLines.map((l) => Number(l.product_id)),
      ...editLines.map((l) => Number(l.product_id)),
    ].filter((id) => Number.isInteger(id) && id > 0);

    selectedIds.forEach((id) => {
      if (!map.has(id) && knownProductsById[id]) {
        map.set(id, knownProductsById[id]);
      }
    });
    return Array.from(map.values());
  }, [activeProducts, createLines, editLines, knownProductsById]);

  // Load danh sách phiếu từ server (GET /api/v1/purchase-receipts hoặc GET /api/v1/purchase-receipts/:id)
  useEffect(() => {
    if (!isAdmin) return undefined;
    const currentRequestId = ++requestIdRef.current;

    const fetchReceiptsList = async () => {
      setIsLoading(true);
      setListError('');
      setSearchValidationError('');
      setIsHistoryWindowCapped(false);

      const resolvedSupplierId = supplierFilter ? Number(supplierFilter) : null;
      const parsedSearch = parseReceiptSearchInput(debouncedSearchQuery);

      // Nếu người dùng nhập chuỗi không phải Mã phiếu hợp lệ (VD: gõ tên NCC vào ô mã phiếu),
      // không được lọc cục bộ 1 trang hay đoán từ 100 NCC đầu tiên -> thông báo rõ ràng và dừng.
      if (parsedSearch.mode === 'UNSUPPORTED_QUERY' || parsedSearch.mode === 'INVALID_ID') {
        if (currentRequestId === requestIdRef.current) {
          setSearchValidationError(parsedSearch.error);
          setData([]);
          setPagination((prev) => ({
            ...prev,
            total: 0,
            totalPages: 1,
          }));
          setIsLoading(false);
        }
        return;
      }

      try {
        // Trường hợp 1: Tra cứu toàn cục theo Mã phiếu chính xác qua GET /purchase-receipts/{id}
        if (parsedSearch.mode === 'EXACT_ID') {
          const exactRes = await receiptsApi.findByExactId(parsedSearch.receiptId, {
            pageSize: pagination.page_size,
            topTab,
            activeTab,
            supplierId: resolvedSupplierId,
            fromDate: fromDateFilter,
            toDate: toDateFilter,
          });

          if (currentRequestId === requestIdRef.current) {
            setData(exactRes.items);
            setPagination((prev) => ({
              ...prev,
              page: 1,
              total: exactRes.total,
              totalPages: exactRes.total_pages,
            }));
          }
          return;
        }

        // Trường hợp 2: Tab Lịch sử nhập hàng với ALL_HISTORY (CONFIRMED + CANCELLED)
        // Gộp có kiểm soát theo (created_at DESC, id DESC) và cắt đúng page_size dòng/trang, fail-closed khi lỗi.
        if (topTab === 'HISTORY' && activeTab === 'ALL_HISTORY') {
          const historyRes = await receiptsApi.listHistory({
            page: pagination.page,
            pageSize: pagination.page_size,
            supplierId: resolvedSupplierId,
            fromDate: fromDateFilter,
            toDate: toDateFilter,
          });

          if (currentRequestId === requestIdRef.current) {
            setData(historyRes.items || []);
            setIsHistoryWindowCapped(Boolean(historyRes.is_window_capped));
            setPagination((prev) => ({
              ...prev,
              total: historyRes.effective_total ?? historyRes.total ?? 0,
              totalPages: historyRes.total_pages || 1,
            }));
          }
          return;
        }

        // Trường hợp 3: Lọc theo 1 trạng thái cụ thể (DRAFT, CONFIRMED, CANCELLED) hoặc ALL
        let statusParam = '';
        if (
          activeTab === 'DRAFT' ||
          activeTab === 'CONFIRMED' ||
          activeTab === 'CANCELLED'
        ) {
          statusParam = activeTab;
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
        }
      } catch (err) {
        if (currentRequestId === requestIdRef.current) {
          // Fail-closed: tuyệt đối không biến lỗi 404/405/429/5xx/network ở API danh sách thành mảng rỗng giả
          const errMsg =
            err?.code === 'ERR_HISTORY_WINDOW_EXCEEDED'
              ? err.message
              : getApiErrorMessage(err, 'Không thể tải danh sách phiếu nhập.');
          setData([]);
          setPagination((prev) => ({
            ...prev,
            total: 0,
            totalPages: 1,
          }));
          setListError(errMsg);
        }
      } finally {
        if (currentRequestId === requestIdRef.current) {
          setIsLoading(false);
          hasLoadedListOnceRef.current = true;
          const pendingId = Number(pendingOpenReceiptIdRef.current);
          if (Number.isInteger(pendingId) && pendingId > 0) {
            pendingOpenReceiptIdRef.current = null;
            setSelectedReceiptId(pendingId);
            setSelectedReceipt(null);
            setDetailError('');
            setConflictError(null);
            setIsEditingDraft(false);
            setIsDetailLoading(true);
            setIsDetailModalOpen(true);
          }
        }
      }
    };

    fetchReceiptsList();

    return () => {
      requestIdRef.current += 1;
    };
  }, [
    isAdmin,
    topTab,
    activeTab,
    pagination.page,
    pagination.page_size,
    supplierFilter,
    debouncedSearchQuery,
    fromDateFilter,
    toDateFilter,
    refreshTrigger,
  ]);

  // Load số lượng đếm thống kê cho 2 tab "Phiếu nhập" (DRAFT) và "Lịch sử nhập hàng" (CONFIRMED + CANCELLED)
  // Không nuốt lỗi từng phần để tránh hiển thị số tổng sai lệch khi 1 request bị lỗi
  useEffect(() => {
    if (!isAdmin) return undefined;
    let isMounted = true;
    async function loadCounts() {
      try {
        const [draftRes, historyConfirmedRes, historyCancelledRes] = await Promise.all([
          receiptsApi.list({ page: 1, pageSize: 1, status: 'DRAFT' }),
          receiptsApi.list({ page: 1, pageSize: 1, status: 'CONFIRMED' }),
          receiptsApi.list({ page: 1, pageSize: 1, status: 'CANCELLED' }),
        ]);
        if (isMounted) {
          setDraftCount(draftRes.total);
          setHistoryCount(historyConfirmedRes.total + historyCancelledRes.total);
        }
      } catch {
        if (isMounted) {
          setDraftCount(null);
          setHistoryCount(null);
        }
      }
    }
    loadCounts();
    return () => {
      isMounted = false;
    };
  }, [isAdmin, refreshTrigger]);

  // Đóng Modal Chi tiết & vô hiệu hóa mọi request chi tiết cũ đang chạy
  const handleCloseDetailModal = useCallback(() => {
    if (actionMutationLockRef.current || isActionLoading) return;
    detailGuardRef.current.invalidate();
    setIsDetailModalOpen(false);
    setSelectedReceiptId(null);
    setSelectedReceipt(null);
    setIsDetailLoading(false);
    setDetailError('');
    setIsEditingDraft(false);
    setConflictError(null);
  }, [isActionLoading]);

  // Mở Modal Chi tiết cho 1 phiếu nhập cụ thể (xóa ngay dữ liệu phiếu cũ để tránh hiển thị nhầm chứng từ)
  const handleOpenDetailModal = useCallback((receiptId) => {
    const id = Number(receiptId);
    if (!Number.isInteger(id) || id <= 0) return;
    setSelectedReceiptId(id);
    setSelectedReceipt(null);
    setDetailError('');
    setConflictError(null);
    setIsEditingDraft(false);
    setIsDetailLoading(true);
    setIsDetailModalOpen(true);
  }, []);

  // T3C9F16 — Nhận state.prefillDraft từ trang Trợ lý AI để mở sẵn Modal Tạo mới phiếu nhập
  // Dùng chung bộ validation buildPrefillDraftState (không âm thầm ép giá trị lỗi về 1 hoặc 0)
  const handleApplyPrefillDraft = useCallback(
    (prefillDraft) => {
      if (!prefillDraft || typeof prefillDraft !== 'object') return;

      const rawItems = Array.isArray(prefillDraft.items) ? prefillDraft.items : [];
      const selectedIds = rawItems.map((it) => it?.product_id);
      const { prefillDraft: validatedPrefill, error } = buildPrefillDraftState({
        supplierId:
          prefillDraft.supplier_id !== undefined && prefillDraft.supplier_id !== null
            ? prefillDraft.supplier_id
            : '',
        rows: rawItems,
        selectedIds,
      });

      if (error || !validatedPrefill) {
        toast.error(error || 'Dữ liệu khởi tạo phiếu nhập nháp không hợp lệ.');
        return;
      }

      setKnownProductsById((prev) => {
        const next = { ...prev };
        validatedPrefill.items.forEach((it) => {
          next[it.product_id] = {
            id: it.product_id,
            sku: it.sku,
            name: it.name,
          };
        });
        return next;
      });

      setCreateSupplierId(
        validatedPrefill.supplier_id ? String(validatedPrefill.supplier_id) : ''
      );
      setCreateLines(
        validatedPrefill.items.map((it) => ({
          product_id: String(it.product_id),
          quantity: it.quantity,
          unit_cost_vnd: it.unit_cost_vnd,
        }))
      );
      setProductSearchTerm('');
      setIsCreateModalOpen(true);
    },
    [toast]
  );

  // T3C9F16 — Nhận state.openReceiptId từ trang Trợ lý AI để tự mở chi tiết phiếu nháp sau khi tải danh sách
  const handleApplyOpenReceiptId = useCallback(
    (receiptId) => {
      const id = Number(receiptId);
      if (!Number.isInteger(id) || id <= 0) return;
      setTopTab('RECEIPTS');
      setActiveTab('DRAFT');
      if (hasLoadedListOnceRef.current && !isLoading) {
        pendingOpenReceiptIdRef.current = null;
        handleOpenDetailModal(id);
      } else {
        pendingOpenReceiptIdRef.current = id;
      }
    },
    [handleOpenDetailModal, isLoading]
  );

  useEffect(() => {
    const detailGuard = detailGuardRef.current;
    return () => {
      pendingOpenReceiptIdRef.current = null;
      hasLoadedListOnceRef.current = false;
      detailGuard.invalidate();
    };
  }, []);

  // Theo dõi tab hiện tại để phát hiện phiếu nháp đã chuyển trạng thái khi người dùng bấm Xem chi tiết
  const activeTabRef = useRef(activeTab);
  activeTabRef.current = activeTab;

  // Load chi tiết phiếu nhập chỉ khi Modal Chi tiết ĐANG MỞ và khớp generation guard
  useEffect(() => {
    const detailGuard = detailGuardRef.current;
    if (!isDetailModalOpen || !selectedReceiptId) {
      detailGuard.invalidate();
      return undefined;
    }

    const targetReceiptId = Number(selectedReceiptId);
    const reqId = detailGuard.begin(targetReceiptId);

    const fetchDetail = async () => {
      setIsDetailLoading(true);
      setDetailError('');
      setConflictError(null);

      try {
        const receipt = await receiptsApi.get(targetReceiptId);
        if (!detailGuard.isCurrent(reqId, targetReceiptId)) {
          return;
        }

        setSelectedReceipt(receipt);
        if (receipt.status === 'DRAFT') {
          setEditSupplierId(String(receipt.supplier_id));
          setEditLines(
            receipt.items.map((it) => ({
              product_id: String(it.product_id),
              quantity: it.quantity,
              unit_cost_vnd: it.unit_cost_vnd,
            }))
          );
          setKnownProductsById((prev) => {
            const next = { ...prev };
            receipt.items.forEach((it) => {
              if (!next[it.product_id]) {
                next[it.product_id] = {
                  id: it.product_id,
                  sku: it.sku_snapshot,
                  name: it.product_name_snapshot,
                };
              }
            });
            return next;
          });
        } else {
          setIsEditingDraft(false);
          if (activeTabRef.current === 'DRAFT') {
            setConflictError(
              receipt.status === 'CONFIRMED'
                ? `Phiếu nhập #${receipt.id} đã được xác nhận ở phiên làm việc khác. Danh sách đã được cập nhật.`
                : `Phiếu nhập #${receipt.id} đã bị hủy ở phiên làm việc khác. Danh sách đã được cập nhật.`
            );
            setRefreshTrigger((prev) => prev + 1);
          }
        }
      } catch (err) {
        if (!detailGuard.isCurrent(reqId, targetReceiptId)) {
          return;
        }
        const errMsg = getApiErrorMessage(err, 'Không thể tải chi tiết phiếu nhập.');
        setSelectedReceipt(null);
        setDetailError(errMsg);
        toast.error(errMsg);
      } finally {
        if (detailGuard.isCurrent(reqId, targetReceiptId)) {
          setIsDetailLoading(false);
        }
      }
    };

    fetchDetail();

    return () => {
      detailGuard.invalidate();
    };
  }, [isDetailModalOpen, selectedReceiptId, detailRetryTrigger, toast]);

  const handleRetryDetail = useCallback(() => {
    if (selectedReceiptId) {
      setDetailRetryTrigger((prev) => prev + 1);
    }
  }, [selectedReceiptId]);

  const handleRetryList = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
    if (masterDataError) {
      reloadMasterData();
    }
  }, [masterDataError, reloadMasterData]);

  // Thao tác: Mở Modal Tạo phiếu nhập mới (Create Mode)
  const handleOpenCreateModal = () => {
    setCreateSupplierId('');
    setCreateLines([{ product_id: '', quantity: 1, unit_cost_vnd: 0 }]);
    setProductSearchTerm('');
    setShowAllProductsInReceipt(false);
    setIsCreateModalOpen(true);
  };

  const supplierById = useMemo(() => {
    const map = new Map();
    activeSuppliers.forEach((s) => map.set(Number(s.id), s));
    return map;
  }, [activeSuppliers]);

  const productById = useMemo(() => {
    const map = new Map();
    selectableProducts.forEach((p) => map.set(Number(p.id), p));
    return map;
  }, [selectableProducts]);

  const createSelectedSupplier = useMemo(
    () => (createSupplierId ? supplierById.get(Number(createSupplierId)) || null : null),
    [createSupplierId, supplierById]
  );

  const editSelectedSupplier = useMemo(
    () => (editSupplierId ? supplierById.get(Number(editSupplierId)) || null : null),
    [editSupplierId, supplierById]
  );

  const createFilteredProducts = useMemo(
    () =>
      filterProductsBySupplierCategories({
        products: selectableProducts,
        selectedSupplier: createSelectedSupplier,
        selectedProductIds: createLines.map((l) => l.product_id),
        showAllProducts: showAllProductsInReceipt,
      }),
    [selectableProducts, createSelectedSupplier, createLines, showAllProductsInReceipt]
  );

  const editFilteredProducts = useMemo(
    () =>
      filterProductsBySupplierCategories({
        products: selectableProducts,
        selectedSupplier: editSelectedSupplier,
        selectedProductIds: editLines.map((l) => l.product_id),
        showAllProducts: showAllProductsInReceipt,
      }),
    [selectableProducts, editSelectedSupplier, editLines, showAllProductsInReceipt]
  );

  const handleCreateSupplierChange = (nextSupplierId) => {
    setCreateSupplierId(nextSupplierId);
    const nextSupplier = nextSupplierId ? supplierById.get(Number(nextSupplierId)) || null : null;
    setCreateLines((prev) =>
      resetIncompatibleProductLines({
        lines: prev,
        selectedSupplier: nextSupplier,
        productById,
        showAllProducts: showAllProductsInReceipt,
      })
    );
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
    if (field === 'product_id' && value && !createSupplierId) {
      const pickedProduct = productById.get(Number(value));
      const matchedSupplier = findAutoFillSupplierForProduct({
        suppliers: activeSuppliers,
        product: pickedProduct,
        currentSupplierId: createSupplierId,
      });
      if (matchedSupplier) {
        setCreateSupplierId(String(matchedSupplier.id));
        toast.info(`Đã tự động chọn nhà cung cấp "${matchedSupplier.name}" theo danh mục sản phẩm.`);
      }
    }
  };

  // Submit Tạo mới bản nháp (POST /api/v1/purchase-receipts)
  const handleSubmitCreateDraft = async (e) => {
    e.preventDefault();
    if (actionMutationLockRef.current || isActionLoading) return;
    if (masterDataError) {
      toast.error('Dữ liệu nhà cung cấp/sản phẩm chưa sẵn sàng. Vui lòng thử tải lại trước khi tạo phiếu.');
      return;
    }
    if (!createSupplierId) {
      toast.error('Vui lòng chọn nhà cung cấp.');
      return;
    }
    if (!createLines || createLines.length === 0) {
      toast.error('Phiếu nhập phải có ít nhất 1 dòng sản phẩm.');
      return;
    }

    actionMutationLockRef.current = true;
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
      actionMutationLockRef.current = false;
      setIsActionLoading(false);
    }
  };

  // Thao tác sửa dòng trong DRAFT
  const handleEditSupplierChange = (nextSupplierId) => {
    setEditSupplierId(nextSupplierId);
    const nextSupplier = nextSupplierId ? supplierById.get(Number(nextSupplierId)) || null : null;
    setEditLines((prev) =>
      resetIncompatibleProductLines({
        lines: prev,
        selectedSupplier: nextSupplier,
        productById,
        showAllProducts: showAllProductsInReceipt,
      })
    );
  };

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
    if (
      actionMutationLockRef.current ||
      isActionLoading ||
      isDetailLoading ||
      !selectedReceipt ||
      selectedReceipt.id !== selectedReceiptId ||
      selectedReceipt.status !== 'DRAFT'
    ) {
      return;
    }
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
      handleCloseDetailModal();
      return;
    }

    const targetId = selectedReceipt.id;
    const expectedVersion = selectedReceipt.draft_version;
    actionMutationLockRef.current = true;
    setIsActionLoading(true);
    setConflictError(null);
    try {
      const updated = await receiptsApi.updateDraft(targetId, {
        expected_draft_version: expectedVersion,
        supplier_id: Number(editSupplierId),
        items: editLines.map((l) => ({
          product_id: Number(l.product_id),
          quantity: Number(l.quantity),
          unit_cost_vnd: Number(l.unit_cost_vnd),
        })),
      });

      // Khi phiên bản nháp thay đổi, xóa intent confirm cũ để lần confirm tiếp theo sinh key mới theo version mới
      confirmIntentRef.current.clearIntent(targetId);

      toast.success(`Đã lưu bản nháp phiếu #${updated.id} (Phiên bản ${updated.draft_version})!`);
      if (detailGuardRef.current.getActiveReceiptId() === targetId) {
        setSelectedReceipt(updated);
        setIsEditingDraft(false);
      }
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      const errMsg = getApiErrorMessage(err, 'Lỗi khi lưu bản nháp.');
      if (err.response?.status === 409) {
        setConflictError(
          errMsg || 'Phiên bản nháp đã cũ do có người chỉnh sửa. Vui lòng tải lại phiếu.'
        );
      }
      toast.error(errMsg);
    } finally {
      actionMutationLockRef.current = false;
      setIsActionLoading(false);
    }
  };

  // Thao tác: Xác nhận phiếu nhập (POST /api/v1/purchase-receipts/:id/confirm) với Intent-level Idempotency
  const handleConfirmPurchase = async () => {
    if (
      actionMutationLockRef.current ||
      confirmIntentRef.current.isInFlight() ||
      isActionLoading ||
      isDetailLoading ||
      !selectedReceipt ||
      selectedReceipt.id !== selectedReceiptId ||
      selectedReceipt.status !== 'DRAFT'
    ) {
      return;
    }

    const targetId = selectedReceipt.id;
    const expectedVersion = selectedReceipt.draft_version;
    actionMutationLockRef.current = true;
    setIsActionLoading(true);
    setConflictError(null);

    try {
      const result = await confirmIntentRef.current.executeConfirm(
        targetId,
        expectedVersion,
        {
          confirmFn: (id, opts) =>
            receiptsApi.confirm(id, { ...opts, notifyEmail: true }),
        }
      );

      if (result.outcome === 'IGNORED_IN_FLIGHT') {
        return;
      }

      if (result.outcome === 'CONFIRMED') {
        const confirmedReceipt = result.receipt;
        toast.success(
          `Đã xác nhận phiếu nhập #${confirmedReceipt.id} thành công! Kho đã được cập nhật.`
        );
        setSelectedReceipt(confirmedReceipt);
        setIsEditingDraft(false);
        detailGuardRef.current.invalidate();
        setIsDetailModalOpen(false);
        setSelectedReceiptId(null);
        setRefreshTrigger((prev) => prev + 1);
        return;
      }

      if (result.outcome === 'RECONCILED_CONFIRMED') {
        const confirmedReceipt = result.receipt;
        const reconciledMsg = `Phiếu nhập #${confirmedReceipt.id} đã được xác nhận ở phiên làm việc khác. Dữ liệu đã được đồng bộ lại.`;
        toast.info(reconciledMsg);
        if (detailGuardRef.current.getActiveReceiptId() === targetId) {
          setSelectedReceipt(confirmedReceipt);
          setIsEditingDraft(false);
          setConflictError(reconciledMsg);
        }
        setRefreshTrigger((prev) => prev + 1);
        return;
      }

      if (result.outcome === 'CONFLICT_STALE') {
        const errMsg = getApiErrorMessage(
          result.error,
          'Phiếu nhập đã được thay đổi hoặc đã chuyển trạng thái. Đã đồng bộ lại dữ liệu mới nhất.'
        );
        if (
          result.receipt &&
          detailGuardRef.current.getActiveReceiptId() === targetId
        ) {
          setSelectedReceipt(result.receipt);
          if (result.receipt.status === 'DRAFT') {
            setEditSupplierId(String(result.receipt.supplier_id));
            setEditLines(
              result.receipt.items.map((it) => ({
                product_id: String(it.product_id),
                quantity: it.quantity,
                unit_cost_vnd: it.unit_cost_vnd,
              }))
            );
          } else {
            setIsEditingDraft(false);
          }
        }
        setConflictError(errMsg);
        toast.error(errMsg);
        setRefreshTrigger((prev) => prev + 1);
      }
    } catch (err) {
      const errMsg = getApiErrorMessage(err, 'Lỗi khi xác nhận phiếu nhập.');
      if (err.response?.status === 409) {
        setConflictError(
          errMsg || 'Yêu cầu xác nhận đang được xử lý hoặc có xung đột phiên bản.'
        );
      }
      toast.error(errMsg);
    } finally {
      actionMutationLockRef.current = false;
      setIsActionLoading(false);
    }
  };

  // Thao tác: Mở modal xác nhận hủy phiếu nhập nháp (PUR-04)
  const handleOpenCancelModal = () => {
    if (
      actionMutationLockRef.current ||
      isActionLoading ||
      isDetailLoading ||
      !selectedReceipt ||
      selectedReceipt.id !== selectedReceiptId ||
      selectedReceipt.status !== 'DRAFT'
    ) {
      return;
    }
    setIsCancelModalOpen(true);
  };

  // Xác nhận hủy phiếu nhập từ trong Modal (POST /api/v1/purchase-receipts/:id/cancel)
  const handleConfirmCancelPurchase = async () => {
    if (
      actionMutationLockRef.current ||
      isActionLoading ||
      isDetailLoading ||
      !selectedReceipt ||
      selectedReceipt.id !== selectedReceiptId ||
      selectedReceipt.status !== 'DRAFT'
    ) {
      return;
    }

    const targetId = selectedReceipt.id;
    const expectedVersion = selectedReceipt.draft_version;
    actionMutationLockRef.current = true;
    setIsActionLoading(true);
    try {
      const cancelled = await receiptsApi.cancel(targetId, {
        expected_draft_version: expectedVersion,
      });
      confirmIntentRef.current.clearIntent(targetId);
      toast.error(`Đã hủy phiếu nhập nháp #${cancelled.id}.`);
      setSelectedReceipt(cancelled);
      setIsCancelModalOpen(false);
      detailGuardRef.current.invalidate();
      setIsDetailModalOpen(false);
      setSelectedReceiptId(null);
      setIsEditingDraft(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      const errMsg = getApiErrorMessage(err, 'Lỗi khi hủy phiếu nhập.');
      if (err.response?.status === 409) {
        setIsCancelModalOpen(false);
        let latestReceipt = null;
        try {
          latestReceipt = await receiptsApi.get(targetId);
        } catch {
          // Fallback: giữ trạng thái hiện có và vẫn hiển thị cảnh báo xung đột
        }
        if (
          latestReceipt &&
          detailGuardRef.current.getActiveReceiptId() === targetId
        ) {
          setSelectedReceipt(latestReceipt);
          if (latestReceipt.status === 'DRAFT') {
            setEditSupplierId(String(latestReceipt.supplier_id));
            setEditLines(
              latestReceipt.items.map((it) => ({
                product_id: String(it.product_id),
                quantity: it.quantity,
                unit_cost_vnd: it.unit_cost_vnd,
              }))
            );
          } else {
            setIsEditingDraft(false);
          }
        }
        const conflictMsg =
          latestReceipt?.status === 'CONFIRMED'
            ? `Phiếu nhập #${targetId} đã được xác nhận ở phiên làm việc khác. Dữ liệu đã được đồng bộ lại.`
            : latestReceipt?.status === 'CANCELLED'
            ? `Phiếu nhập #${targetId} đã bị hủy ở phiên làm việc khác. Dữ liệu đã được đồng bộ lại.`
            : errMsg || 'Phiên bản nháp đã thay đổi hoặc phiếu đã được xử lý. Dữ liệu đã được đồng bộ lại.';
        setConflictError(conflictMsg);
        setRefreshTrigger((prev) => prev + 1);
      }
      toast.error(errMsg);
    } finally {
      actionMutationLockRef.current = false;
      setIsActionLoading(false);
    }
  };

  // Bảng danh sách phiếu nhập
  const columns = useMemo(
    () => [
      {
        key: 'id',
        title: 'MÃ PHIẾU',
        width: '9%',
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
        width: '24%',
        render: (row) => (
          <span
            className={styles.supplierNameCell}
            title={row.supplier_name_snapshot || `NCC ID: ${row.supplier_id}`}
          >
            {row.supplier_name_snapshot || `NCC #${row.supplier_id}`}
          </span>
        ),
      },
      {
        key: 'items_count',
        title: 'SỐ MẶT HÀNG',
        align: 'center',
        width: '14%',
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
        width: '16%',
        render: (row) => <span className={styles.dateCell}>{formatDate(row.created_at)}</span>,
      },
      {
        key: 'total_vnd',
        title: 'TỔNG TIỀN',
        align: 'right',
        width: '13%',
        render: (row) => (
          <span className={styles.amountCell}>{formatVND(row.total_vnd)}</span>
        ),
      },
      {
        key: 'status',
        title: 'TRẠNG THÁI',
        width: '12%',
        align: 'center',
        render: (row) => {
          if (row.status === 'CONFIRMED') {
            return <span className={styles.statusBadgeConfirmed}>Đã nhập</span>;
          }
          if (row.status === 'CANCELLED') {
            return <span className={styles.statusBadgeCancelled}>Đã hủy</span>;
          }
          return (
            <span className={styles.statusBadgeDraft}>
              Bản nháp ({row.draft_version})
            </span>
          );
        },
      },
      {
        key: 'actions',
        title: 'THAO TÁC',
        align: 'center',
        width: '12%',
        render: (row) => (
          <button
            type="button"
            className={styles.viewDetailBtn}
            onClick={() => handleOpenDetailModal(row.id)}
            title="Xem / Thao tác phiếu nhập"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            <span>{row.status === 'DRAFT' ? 'Sửa nháp' : 'Chi tiết'}</span>
          </button>
        ),
      },
    ],
    [handleOpenDetailModal, selectedReceipt]
  );

  // startRecord và endRecord tính trực tiếp từ tập dữ liệu trang hiện tại và tổng bản ghi khớp bộ lọc
  const startRecord =
    pagination.total === 0 || data.length === 0
      ? 0
      : (pagination.page - 1) * pagination.page_size + 1;
  const endRecord =
    pagination.total === 0 || data.length === 0
      ? 0
      : Math.min(startRecord + data.length - 1, pagination.total);

  // Xử lý chuyển tab Top "Phiếu nhập" vs "Lịch sử nhập hàng"
  const handleTopTabChange = (tab) => {
    detailGuardRef.current.invalidate();
    setTopTab(tab);
    setSelectedReceiptId(null);
    setSelectedReceipt(null);
    setIsDetailModalOpen(false);
    setIsDetailLoading(false);
    setDetailError('');
    if (tab === 'RECEIPTS') {
      setActiveTab('DRAFT');
    } else {
      setActiveTab('ALL_HISTORY');
    }
    setPagination((prev) => ({ ...prev, page: 1 }));
  };

  // Xử lý chọn khoảng thời gian nhanh theo múi giờ Asia/Ho_Chi_Minh
  const handleDateRangePreset = (type) => {
    setDateRangeType(type);
    const now = new Date();
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

  const handleExportExcel = useCallback(async () => {
    if (!isAdmin || isExportingExcel) return;
    setIsExportingExcel(true);
    try {
      const exportResult = await collectPurchaseReceiptsForExport({
        topTab,
        activeTab,
        supplierFilter,
        debouncedSearchQuery,
        fromDateFilter,
        toDateFilter,
        receiptsApi,
        maxRows: MAX_EXPORT_ROWS,
      });

      if (exportResult.validationError) {
        toast.warning(exportResult.validationError);
        return;
      }

      if (exportResult.items.length === 0) {
        toast.warning('Không có dữ liệu phiếu nhập để xuất Excel.');
        return;
      }

      const rows = buildPurchaseReceiptExportRows(exportResult.items, formatDate);
      await downloadStyledExcelRows(
        rows,
        `purchase_receipts_${activeTab.toLowerCase()}.xlsx`
      );

      const notice = formatPurchaseExportMessage(exportResult, MAX_EXPORT_ROWS);
      if (notice.severity === 'warning') {
        toast.warning(notice.message);
      } else {
        toast.success(notice.message);
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Không thể xuất Excel danh sách phiếu nhập.'));
    } finally {
      setIsExportingExcel(false);
    }
  }, [
    isAdmin,
    isExportingExcel,
    topTab,
    activeTab,
    supplierFilter,
    debouncedSearchQuery,
    fromDateFilter,
    toDateFilter,
    toast,
  ]);

  // Quyền: ADMIN-only
  if (!isAdmin) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <h1 className={styles.title}>Quản lý nhập hàng</h1>
            <p className={styles.subtitle}>
              Chức năng dành riêng cho Quản trị viên.
            </p>
          </div>
        </div>
        <div
          className={styles.readOnlyNotice}
          style={{ color: '#DC2626', backgroundColor: '#FEF2F2' }}
        >
          Bạn không có quyền truy cập chức năng này. Vui lòng liên hệ Quản trị viên.
        </div>
      </div>
    );
  }

  const isDetailActionDisabled =
    isActionLoading ||
    isDetailLoading ||
    !selectedReceipt ||
    selectedReceipt.id !== selectedReceiptId ||
    Boolean(detailError);

  return (
    <div className={styles.container}>
      {inRouter && (
        <PurchaseRouterStateConsumer
          onPrefillDraft={handleApplyPrefillDraft}
          onOpenReceiptId={handleApplyOpenReceiptId}
        />
      )}
      {/* 1. Header Trang */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>Quản lý nhập hàng</h1>
          <p className={styles.subtitle}>
            Tạo và xử lý phiếu nhập kho từ nhà cung cấp
          </p>
        </div>

        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.exportExcelBtn}
            onClick={handleExportExcel}
            disabled={isExportingExcel || isLoading || data.length === 0}
          >
            {isExportingExcel ? 'Đang xuất...' : 'Xuất Excel'}
          </button>
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={handleOpenCreateModal}
            disabled={isActionLoading}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Thêm phiếu nhập</span>
          </button>
        </div>
      </div>

      {/* Cảnh báo lỗi tải Master Data (NCC / Sản phẩm) — ẩn khi đã có banner lỗi danh sách chính để tránh trùng lặp */}
      {masterDataError && !listError && (
        <div className={styles.conflictAlert} role="alert" style={{ marginBottom: '12px' }}>
          <span>{masterDataError}</span>
          <button
            type="button"
            className={styles.reloadBtn}
            onClick={reloadMasterData}
            disabled={isMasterDataLoading}
          >
            {isMasterDataLoading ? 'Đang tải...' : 'Thử lại'}
          </button>
        </div>
      )}

      {/* 2. Sub-Header: Hai tab "Phiếu nhập" & "Lịch sử nhập hàng" */}
      <div className={styles.subHeaderRow}>
        <div className={styles.navTabs}>
          <button
            type="button"
            className={`${styles.navTabBtn} ${
              topTab === 'RECEIPTS' ? styles.navTabBtnActive : ''
            }`}
            onClick={() => handleTopTabChange('RECEIPTS')}
          >
            <span>Phiếu nhập</span>
            {typeof draftCount === 'number' && draftCount > 0 && (
              <span className={styles.tabCountBadge}>{draftCount}</span>
            )}
          </button>

          <button
            type="button"
            className={`${styles.navTabBtn} ${
              topTab === 'HISTORY' ? styles.navTabBtnActive : ''
            }`}
            onClick={() => handleTopTabChange('HISTORY')}
          >
            <span>Lịch sử nhập hàng</span>
            {typeof historyCount === 'number' && historyCount > 0 && (
              <span className={styles.tabCountBadgeGray}>{historyCount}</span>
            )}
          </button>
        </div>

        <div className={styles.warehouseHint}>
          Kho áp dụng: <strong>Kho cửa hàng</strong>
        </div>
      </div>

      {/* 3. Thanh tìm kiếm và bộ lọc */}
      <div className={styles.filtersRow}>
        {/* Ô tìm kiếm chính xác theo mã phiếu (GET /purchase-receipts/{id}) */}
        <div className={styles.searchInputWrapper}>
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
            placeholder="Tìm theo mã phiếu (VD: 12 hoặc #12)..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPagination((prev) => ({ ...prev, page: 1 }));
            }}
          />
        </div>

        {/* Dropdown lọc theo Trạng thái */}
        <CustomSelect
          ariaLabel="Lọc theo trạng thái phiếu nhập"
          value={activeTab}
          onChange={(e) => {
            setActiveTab(e.target.value);
            setPagination((prev) => ({ ...prev, page: 1 }));
          }}
          options={
            topTab === 'HISTORY'
              ? [
                  { value: 'ALL_HISTORY', label: 'Trạng thái: Tất cả lịch sử' },
                  { value: 'CONFIRMED', label: 'Trạng thái: Đã nhập' },
                  { value: 'CANCELLED', label: 'Trạng thái: Đã hủy' },
                ]
              : [
                  { value: 'DRAFT', label: 'Trạng thái: Bản nháp' },
                  { value: 'ALL', label: 'Trạng thái: Tất cả trạng thái' },
                ]
          }
        />

        {/* Dropdown lọc Nhà cung cấp (truyền supplier_id lên Backend) */}
        <CustomSelect
          ariaLabel="Lọc theo nhà cung cấp"
          value={supplierFilter}
          searchPlaceholder="Tìm nhà cung cấp..."
          onChange={(e) => {
            setSupplierFilter(e.target.value);
            setPagination((prev) => ({ ...prev, page: 1 }));
          }}
          title={
            suppliersMeta.isTruncated
              ? `Đang hiển thị ${activeSuppliers.length}/${suppliersMeta.total} nhà cung cấp đang hoạt động đầu tiên`
              : 'Lọc theo nhà cung cấp'
          }
          options={[
            { value: '', label: 'Nhà cung cấp: Tất cả' },
            ...activeSuppliers.map((s) => ({
              value: String(s.id),
              label: s.name,
            })),
          ]}
        />

        {/* Dropdown chọn khoảng thời gian + nút Xóa bộ lọc */}
        <div className={styles.dateAndClearRow}>
          <CustomSelect
            ariaLabel="Lọc theo khoảng thời gian"
            value={dateRangeType}
            onChange={(e) => handleDateRangePreset(e.target.value)}
            options={[
              { value: 'ALL', label: 'Thời gian: Toàn bộ' },
              { value: '30DAYS', label: 'Thời gian: 30 ngày gần nhất' },
              { value: '7DAYS', label: 'Thời gian: 7 ngày gần nhất' },
              { value: 'TODAY', label: 'Thời gian: Hôm nay' },
              { value: 'CUSTOM', label: 'Thời gian: Tùy chỉnh' },
            ]}
          />

          {dateRangeType === 'CUSTOM' && (
            <div className={styles.customDatePopover}>
              <CustomDatePicker
                prefixLabel="Từ:"
                placeholder="Chọn ngày"
                ariaLabel="Từ ngày"
                max={toDateFilter || undefined}
                value={fromDateFilter}
                onChange={(e) => {
                  setFromDateFilter(e.target.value);
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              />
              <CustomDatePicker
                prefixLabel="Đến:"
                placeholder="Chọn ngày"
                ariaLabel="Đến ngày"
                min={fromDateFilter || undefined}
                value={toDateFilter}
                onChange={(e) => {
                  setToDateFilter(e.target.value);
                  setPagination((prev) => ({ ...prev, page: 1 }));
                }}
              />
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
                setDebouncedSearchQuery('');
                setSearchValidationError('');
                setPagination((prev) => ({ ...prev, page: 1 }));
              }}
            >
              Xóa bộ lọc
            </button>
          )}
        </div>
      </div>

      {/* Thông báo hướng dẫn nếu người dùng nhập chữ thay vì Mã phiếu vào ô tra cứu mã phiếu */}
      {searchValidationError && (
        <div className={styles.readOnlyNotice} role="status" style={{ marginBottom: '12px' }}>
          {searchValidationError}
        </div>
      )}

      {/* Thông báo nếu tổng lịch sử vượt cửa sổ gộp an toàn (MAX_HISTORY_MERGE_WINDOW) */}
      {isHistoryWindowCapped && (
        <div className={styles.readOnlyNotice} role="status" style={{ marginBottom: '12px' }}>
          Đang hiển thị tối đa {MAX_HISTORY_MERGE_WINDOW} phiếu lịch sử gần nhất ở chế độ gộp trạng thái. Vui lòng chọn trạng thái <strong>Đã nhập</strong> / <strong>Đã hủy</strong> hoặc lọc theo khoảng thời gian để tra cứu sâu hơn.
        </div>
      )}

      {/* Banner lỗi tải danh sách phiếu nhập (Fail-closed + Retry) */}
      {listError && (
        <div className={styles.conflictAlert} role="alert" style={{ marginBottom: '12px' }}>
          <strong>Lỗi tải danh sách phiếu nhập:</strong>
          <span>{listError}</span>
          <button
            type="button"
            className={styles.reloadBtn}
            onClick={handleRetryList}
            disabled={isLoading}
          >
            Thử lại
          </button>
        </div>
      )}

      {/* 4. Bảng danh sách phiếu nhập */}
      <div className={styles.tableCard}>
        <Table
          columns={columns}
          data={data}
          rowKey="id"
          isLoading={isLoading}
          emptyText={
            listError
              ? 'Không thể hiển thị dữ liệu do lỗi kết nối API. Vui lòng bấm "Thử lại".'
              : 'Không tìm thấy phiếu nhập nào'
          }
        />

        <div className={styles.paginationBar}>
          <span className={styles.paginationSummary}>
            Hiển thị <strong>{startRecord} - {endRecord}</strong> trên{' '}
            <strong>{pagination.total}</strong> phiếu nhập
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

      {/* 5. Modal Chi tiết & Thao tác Phiếu nhập kho */}
      {isDetailModalOpen &&
        selectedReceipt &&
        selectedReceipt.id === selectedReceiptId &&
        !isDetailLoading &&
        !detailError && <PrintablePurchaseReceipt receipt={selectedReceipt} />}
      <Modal
        isOpen={isDetailModalOpen}
        onClose={handleCloseDetailModal}
        title={
          selectedReceipt && selectedReceipt.id === selectedReceiptId
            ? `Chi tiết phiếu nhập #${selectedReceipt.id}`
            : selectedReceiptId
            ? `Chi tiết phiếu nhập #${selectedReceiptId}`
            : 'Chi tiết phiếu nhập kho'
        }
        maxWidth="780px"
        footer={
          selectedReceipt &&
          selectedReceipt.id === selectedReceiptId &&
          selectedReceipt.status === 'DRAFT' &&
          !isDetailLoading &&
          !detailError ? (
            <div className={styles.detailModalFooterRow}>
              <button
                type="button"
                className={modalStyles.dangerBtn}
                onClick={handleOpenCancelModal}
                disabled={isDetailActionDisabled}
              >
                Hủy phiếu
              </button>
              <div className={styles.detailModalFooterActions}>
                <button
                  type="button"
                  className={modalStyles.cancelBtn}
                  onClick={() => {
                    if (typeof window !== 'undefined' && typeof window.print === 'function') {
                      window.print();
                    }
                  }}
                  data-testid="purchase-print-btn"
                >
                  In phiếu nhập
                </button>
                <button
                  type="button"
                  className={modalStyles.cancelBtn}
                  onClick={handleSaveDraft}
                  disabled={isDetailActionDisabled}
                >
                  {isActionLoading ? 'Đang lưu...' : 'Lưu nháp'}
                </button>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  onClick={handleConfirmPurchase}
                  disabled={isDetailActionDisabled}
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
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>
                    {isActionLoading ? 'Đang xử lý...' : 'Xác nhận nhập kho'}
                  </span>
                </button>
              </div>
            </div>
          ) : (
            <div className={styles.detailModalFooterActions}>
              {selectedReceipt &&
                selectedReceipt.id === selectedReceiptId &&
                !isDetailLoading &&
                !detailError && (
                  <button
                    type="button"
                    className={modalStyles.cancelBtn}
                    onClick={() => {
                      if (typeof window !== 'undefined' && typeof window.print === 'function') {
                        window.print();
                      }
                    }}
                    data-testid="purchase-print-btn"
                  >
                    In phiếu nhập
                  </button>
                )}
              <button
                type="button"
                className={modalStyles.cancelBtn}
                onClick={handleCloseDetailModal}
                disabled={isActionLoading}
              >
                Đóng
              </button>
            </div>
          )
        }
      >
        {isDetailLoading ? (
          <div className={styles.detailLoadingState}>
            <span>Đang tải chi tiết phiếu nhập...</span>
          </div>
        ) : detailError ? (
          <div className={styles.conflictAlert} role="alert">
            <strong>Không thể tải chi tiết phiếu nhập</strong>
            <span>{detailError}</span>
            <button
              type="button"
              className={styles.reloadBtn}
              onClick={handleRetryDetail}
            >
              Thử lại
            </button>
          </div>
        ) : selectedReceipt && selectedReceipt.id === selectedReceiptId ? (
          <div className={styles.detailModalContent}>
            {/* Banner cảnh báo xung đột phiên bản 409 Conflict */}
            {conflictError && (
              <div className={styles.conflictAlert} role="alert">
                <strong>Phiên bản đã thay đổi!</strong>
                <span>{conflictError}</span>
                <button
                  type="button"
                  className={styles.reloadBtn}
                  onClick={handleRetryDetail}
                >
                  Tải lại phiếu mới nhất
                </button>
              </div>
            )}

            {/* Khung tóm tắt chứng từ */}
            <div className={styles.detailMetaCard}>
              <div className={styles.detailMetaTopRow}>
                <div className={styles.detailStatusGroup}>
                  {selectedReceipt.status === 'CONFIRMED' && (
                    <span className={styles.statusBadgeConfirmed}>Đã nhập kho</span>
                  )}
                  {selectedReceipt.status === 'CANCELLED' && (
                    <span className={styles.statusBadgeCancelled}>Đã hủy</span>
                  )}
                  {selectedReceipt.status === 'DRAFT' && (
                    <span className={styles.statusBadgeDraft}>Bản nháp</span>
                  )}
                  <span className={styles.detailVersionPill}>
                    Phiên bản #{selectedReceipt.draft_version}
                  </span>
                </div>
                <span className={styles.detailTimestamp}>
                  Tạo lúc: <strong>{formatDate(selectedReceipt.created_at)}</strong>
                </span>
              </div>

              <div className={styles.infoGrid}>
                <div className={styles.infoBlock}>
                  <span className={styles.infoLabel}>NHÀ CUNG CẤP</span>
                  {selectedReceipt.status === 'DRAFT' && isEditingDraft ? (
                    <CustomSelect
                      fullWidth
                      value={editSupplierId}
                      searchPlaceholder="Tìm nhà cung cấp..."
                      onChange={(e) => handleEditSupplierChange(e.target.value)}
                      options={[
                        ...(!activeSuppliers.some(
                          (s) => Number(s.id) === Number(selectedReceipt.supplier_id)
                        )
                          ? [
                              {
                                value: String(selectedReceipt.supplier_id),
                                label:
                                  selectedReceipt.supplier_name_snapshot ||
                                  `NCC #${selectedReceipt.supplier_id}`,
                              },
                            ]
                          : []),
                        ...activeSuppliers.map((s) => ({
                          value: String(s.id),
                          label: s.name,
                        })),
                      ]}
                    />
                  ) : (
                    <span className={styles.infoValue}>
                      {selectedReceipt.supplier_name_snapshot ||
                        `NCC #${selectedReceipt.supplier_id}`}
                    </span>
                  )}
                </div>
                <div className={styles.infoBlock}>
                  <span className={styles.infoLabel}>KHO ÁP DỤNG</span>
                  <span className={styles.infoValue}>Kho cửa hàng</span>
                  {selectedReceipt.closed_at && (
                    <span className={styles.infoSub}>
                      Đóng lúc: {formatDate(selectedReceipt.closed_at)}
                    </span>
                  )}
                </div>
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
                      setProductSearchTerm('');
                      setShowAllProductsInReceipt(false);
                      setIsEditingDraft(true);
                    }}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                    >
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                    <span>Chỉnh sửa mặt hàng</span>
                  </button>
                )}
              </div>

              {selectedReceipt.status === 'DRAFT' && isEditingDraft ? (
                <div>
                  {editSelectedSupplier?.category_ids?.length > 0 && (
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px',
                        marginBottom: '8px',
                        fontSize: '12px',
                      }}
                    >
                      <span style={{ color: 'var(--color-text-secondary, #64748b)' }}>
                        {showAllProductsInReceipt
                          ? `Đang hiển thị tất cả ${selectableProducts.length} sản phẩm`
                          : `Đang lọc ${editFilteredProducts.length} sản phẩm theo danh mục của nhà cung cấp`}
                      </span>
                      <button
                        type="button"
                        className={styles.addItemLink}
                        onClick={() => setShowAllProductsInReceipt((prev) => !prev)}
                      >
                        {showAllProductsInReceipt ? 'Lọc theo NCC' : 'Hiện tất cả SP'}
                      </button>
                    </div>
                  )}

                  <div className={styles.lineHeaderRow}>
                    <span>Sản phẩm</span>
                    <span>Số lượng</span>
                    <span>Đơn giá nhập (đ)</span>
                    <span></span>
                  </div>

                  {editLines.map((line, idx) => (
                    <div key={idx} className={styles.lineInputRow}>
                      <div className={`${styles.lineField} ${styles.lineFieldProduct}`}>
                        <span className={styles.mobileFieldLabel}>Sản phẩm</span>
                        <CustomSelect
                          fullWidth
                          value={line.product_id}
                          searchPlaceholder="Tìm theo SKU hoặc tên SP..."
                          onChange={(e) =>
                            handleUpdateEditLine(idx, 'product_id', e.target.value)
                          }
                          options={[
                            { value: '', label: '-- Chọn sản phẩm --' },
                            ...editFilteredProducts.map((p) => ({
                              value: String(p.id),
                              label: `${p.sku} - ${p.name}`,
                            })),
                          ]}
                        />
                      </div>

                      <div className={styles.lineField}>
                        <span className={styles.mobileFieldLabel}>Số lượng</span>
                        <input
                          type="number"
                          min="1"
                          className={styles.formInput}
                          placeholder="Số lượng nhập"
                          value={line.quantity}
                          onChange={(e) =>
                            handleUpdateEditLine(idx, 'quantity', e.target.value)
                          }
                        />
                      </div>

                      <div className={styles.lineField}>
                        <span className={styles.mobileFieldLabel}>Đơn giá nhập (đ)</span>
                        <input
                          type="number"
                          min="0"
                          className={styles.formInput}
                          placeholder="Đơn giá nhập"
                          value={line.unit_cost_vnd}
                          onChange={(e) =>
                            handleUpdateEditLine(idx, 'unit_cost_vnd', e.target.value)
                          }
                        />
                      </div>

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
                <div className={styles.itemsTableWrap}>
                  <table className={styles.itemsTable}>
                    <thead>
                      <tr>
                        <th style={{ width: '46%' }}>Sản phẩm</th>
                        <th style={{ width: '12%', textAlign: 'center' }}>SL</th>
                        <th style={{ width: '20%' }}>Đơn giá (đ)</th>
                        <th style={{ width: '22%' }}>Thành tiền (đ)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedReceipt.items || []).map((item) => (
                        <tr key={item.product_id}>
                          <td>
                            <div className={styles.itemMainName}>
                              {item.product_name_snapshot}
                            </div>
                            <div className={styles.itemSubSku}>
                              SKU: {item.sku_snapshot}
                            </div>
                          </td>
                          <td className={styles.qtyBadge} style={{ textAlign: 'center' }}>
                            {item.quantity}
                          </td>
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
                </div>
              )}
            </div>

            {/* Tổng số lượng & Tổng tiền */}
            <div className={styles.summaryBlock}>
              <div className={styles.summaryRow}>
                <span>
                  Tổng số lượng nhập (
                  {(selectedReceipt.items || []).reduce(
                    (sum, item) => sum + (Number(item.quantity) || 0),
                    0
                  )}{' '}
                  sản phẩm)
                </span>
                <strong>{selectedReceipt.items?.length || 0} mặt hàng</strong>
              </div>
              <div className={styles.summaryTotalRow}>
                <span>Tổng tiền phiếu nhập</span>
                <span className={styles.totalHighlight}>
                  {formatVND(selectedReceipt.total_vnd)}
                </span>
              </div>
            </div>

            {/* Lưu ý khi thao tác */}
            {selectedReceipt.status === 'DRAFT' ? (
              <div className={styles.confirmWarningBox}>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  style={{ flexShrink: 0, marginTop: 1 }}
                >
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                <div>
                  <strong>BẢN NHÁP</strong> chưa làm tăng số lượng tồn kho. Khi bấm{' '}
                  <strong>xác nhận phiếu</strong>, hệ thống sẽ tăng tồn kho thực tế,
                  khóa bất biến chứng từ và chuyển sang trạng thái{' '}
                  <strong>ĐÃ NHẬP</strong>.
                </div>
              </div>
            ) : (
              <div className={styles.readOnlyNotice}>
                Chứng từ này đã ở trạng thái{' '}
                <strong>
                  {selectedReceipt.status === 'CONFIRMED' ? 'ĐÃ NHẬP' : 'ĐÃ HỦY'}
                </strong>
                . Mọi thông tin đã được khóa bất biến và không thể chỉnh sửa hay hủy
                bỏ.
              </div>
            )}
          </div>
        ) : null}
      </Modal>

      {/* 6. Modal Tạo mới phiếu nhập nháp (Create Mode) */}
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
              type="submit"
              form="create-purchase-receipt-form"
              className={modalStyles.confirmBtn}
              disabled={isActionLoading || Boolean(masterDataError) || isMasterDataLoading}
            >
              {isActionLoading ? 'Đang tạo...' : 'Tạo bản nháp'}
            </button>
          </>
        }
      >
        <form id="create-purchase-receipt-form" onSubmit={handleSubmitCreateDraft}>
          {suppliersMeta.isTruncated && (
            <div className={styles.readOnlyNotice} style={{ marginBottom: '12px' }}>
              Đang hiển thị {activeSuppliers.length}/{suppliersMeta.total} nhà cung cấp đang hoạt động đầu tiên.
            </div>
          )}

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>
              Nhà cung cấp <span style={{ color: '#DC2626' }}>*</span>
            </label>
            <CustomSelect
              fullWidth
              value={createSupplierId}
              searchPlaceholder="Tìm nhà cung cấp..."
              onChange={(e) => handleCreateSupplierChange(e.target.value)}
              required
              options={[
                { value: '', label: '-- Chọn nhà cung cấp --' },
                ...activeSuppliers.map((s) => ({
                  value: String(s.id),
                  label: s.name,
                })),
              ]}
            />
          </div>

          <div className={styles.formGroup}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
              }}
            >
              <label className={styles.formLabel}>
                Danh sách sản phẩm nhập <span style={{ color: '#DC2626' }}>*</span>
              </label>
              {createSelectedSupplier?.category_ids?.length > 0 && (
                <button
                  type="button"
                  className={styles.addItemLink}
                  onClick={() => setShowAllProductsInReceipt((prev) => !prev)}
                >
                  {showAllProductsInReceipt
                    ? `Lọc theo NCC (${createFilteredProducts.length})`
                    : `Hiện tất cả SP (${selectableProducts.length})`}
                </button>
              )}
            </div>

            <div className={styles.lineHeaderRow}>
              <span>Sản phẩm</span>
              <span>Số lượng</span>
              <span>Đơn giá nhập (đ)</span>
              <span></span>
            </div>

            {createLines.map((line, idx) => (
              <div key={idx} className={styles.lineInputRow}>
                <div className={`${styles.lineField} ${styles.lineFieldProduct}`}>
                  <span className={styles.mobileFieldLabel}>Sản phẩm</span>
                  <CustomSelect
                    fullWidth
                    value={line.product_id}
                    searchPlaceholder="Tìm theo SKU hoặc tên SP..."
                    onChange={(e) =>
                      handleUpdateCreateLine(idx, 'product_id', e.target.value)
                    }
                    required
                    options={[
                      { value: '', label: '-- Chọn sản phẩm --' },
                      ...createFilteredProducts.map((p) => ({
                        value: String(p.id),
                        label: `${p.sku} - ${p.name}`,
                      })),
                    ]}
                  />
                </div>

                <div className={styles.lineField}>
                  <span className={styles.mobileFieldLabel}>Số lượng</span>
                  <input
                    type="number"
                    min="1"
                    className={styles.formInput}
                    placeholder="Số lượng nhập"
                    value={line.quantity}
                    onChange={(e) =>
                      handleUpdateCreateLine(idx, 'quantity', e.target.value)
                    }
                    required
                  />
                </div>

                <div className={styles.lineField}>
                  <span className={styles.mobileFieldLabel}>Đơn giá nhập (đ)</span>
                  <input
                    type="number"
                    min="0"
                    className={styles.formInput}
                    placeholder="Đơn giá nhập"
                    value={line.unit_cost_vnd}
                    onChange={(e) =>
                      handleUpdateCreateLine(idx, 'unit_cost_vnd', e.target.value)
                    }
                    required
                  />
                </div>

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

      {/* 7. Modal xác nhận hủy phiếu nhập dùng component common/Modal */}
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
              disabled={isDetailActionDisabled}
            >
              {isActionLoading ? 'Đang hủy...' : 'Xác nhận hủy phiếu'}
            </button>
          </>
        }
      >
        <p style={{ margin: 0, fontSize: '14px', lineHeight: 1.5, color: 'var(--color-neutral, #242A30)' }}>
          Bạn có chắc chắn muốn hủy bản nháp phiếu nhập{' '}
          <strong style={{ color: 'var(--color-neutral, #111827)' }}>#{selectedReceipt?.id}</strong>?
          Thao tác này sẽ đánh dấu phiếu thành CANCELLED và không thể khôi phục.
        </p>
      </Modal>
    </div>
  );
}
