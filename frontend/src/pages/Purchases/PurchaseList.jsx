import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Pagination, Table, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import { getApiErrorMessage } from '../../api/axiosClient';
import { purchasesApi } from '../../api/purchasesApi';
import styles from './PurchaseList.module.css';

// Định dạng số tiền kiểu 2.500.000 đ
const formatVND = (amount) => {
  const num = Number(amount) || 0;
  return `${num.toLocaleString('vi-VN')} đ`;
};

// Format ngày: DD/MM/YYYY
const formatDate = (isoString) => {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) return '—';
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    return `${day}/${month}/${year}`;
  } catch {
    return '—';
  }
};

export default function PurchaseList() {
  const toast = useToast();

  // 1. Tab điều hướng trên cùng: 'DRAFTS' (Phiếu nhập) | 'HISTORY' (Lịch sử nhập hàng)
  const [activeTab, setActiveTab] = useState('DRAFTS');

  // 2. Tìm kiếm, bộ lọc & phân trang
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  const [data, setData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [stats, setStats] = useState({
    draftsCount: 0,
    historyCount: 0,
  });

  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 5,
    total: 0,
    totalPages: 1,
  });

  // 3. Phiếu đang được chọn để xem chi tiết ở cột bên phải
  const [selectedPurchase, setSelectedPurchase] = useState(null);
  const [isActionLoading, setIsActionLoading] = useState(false);

  // 4. Modal xác nhận hủy / xóa phiếu nhập nháp (PUR-04)
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);

  const requestIdRef = useRef(0);

  // Debounce tìm kiếm
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim());
      setPagination((prev) => ({ ...prev, page: 1 }));
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Load danh sách phiếu (100% server-side API, không filter client)
  const loadPurchases = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);

    try {
      if (activeTab === 'DRAFTS') {
        const res = await purchasesApi.getPurchaseDrafts({
          page: pagination.page,
          pageSize: pagination.page_size,
          search: debouncedSearch,
          status: statusFilter,
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
              draftsCount: res.total || 0,
            }));
          }
          // Tự động chọn dòng đầu tiên hoặc giữ nguyên dòng đang chọn
          if (res.items && res.items.length > 0) {
            setSelectedPurchase((prev) => {
              if (!prev) return res.items[0];
              const match = res.items.find((p) => p.id === prev.id);
              return match || res.items[0];
            });
          } else {
            setSelectedPurchase(null);
          }
        }
      } else {
        const res = await purchasesApi.getPurchaseHistory({
          page: pagination.page,
          pageSize: pagination.page_size,
          search: debouncedSearch,
        });

        if (currentRequestId === requestIdRef.current) {
          setData(res.items || []);
          setPagination((prev) => ({
            ...prev,
            total: res.total || 0,
            totalPages: res.totalPages || 1,
          }));
          setStats((prev) => ({
            ...prev,
            historyCount: res.total || 0,
          }));
          if (res.items && res.items.length > 0) {
            setSelectedPurchase(res.items[0]);
          } else {
            setSelectedPurchase(null);
          }
        }
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        toast.error(getApiErrorMessage(err, 'Không thể tải danh sách phiếu nhập.'));
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [activeTab, pagination.page, pagination.page_size, debouncedSearch, statusFilter, toast]);

  useEffect(() => {
    loadPurchases();
  }, [loadPurchases, refreshTrigger]);

  // Thao tác: Xác nhận phiếu nhập (PUR-03)
  const handleConfirmPurchase = async () => {
    if (!selectedPurchase) return;
    setIsActionLoading(true);
    try {
      await purchasesApi.confirmPurchase(selectedPurchase.id);
      toast.success(`Đã xác nhận phiếu nhập ${selectedPurchase.code} thành công! Kho đã được cập nhật.`);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Lỗi khi xác nhận phiếu nhập.'));
    } finally {
      setIsActionLoading(false);
    }
  };

  // Thao tác: Mở modal xác nhận hủy phiếu nhập nháp (PUR-04)
  const handleOpenCancelModal = () => {
    if (!selectedPurchase) return;
    setIsCancelModalOpen(true);
  };

  // Xác nhận hủy phiếu nhập từ trong Modal
  const handleConfirmCancelPurchase = async () => {
    if (!selectedPurchase) return;
    setIsActionLoading(true);
    try {
      await purchasesApi.cancelPurchase(selectedPurchase.id);
      toast.success(`Đã hủy phiếu nhập nháp ${selectedPurchase.code}.`);
      setIsCancelModalOpen(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Lỗi khi hủy phiếu nhập.'));
    } finally {
      setIsActionLoading(false);
    }
  };

  // Thao tác: Lưu phiếu nhập (PUR-02)
  const handleSaveDraft = async () => {
    if (!selectedPurchase) return;
    setIsActionLoading(true);
    try {
      await purchasesApi.savePurchase(selectedPurchase.id, selectedPurchase);
      toast.success(`Đã lưu bản nháp phiếu ${selectedPurchase.code}!`);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Lỗi khi lưu bản nháp.'));
    } finally {
      setIsActionLoading(false);
    }
  };

  // Thao tác: Tạo phiếu nhập mới
  const handleCreateNewPurchase = async () => {
    setIsActionLoading(true);
    try {
      const created = await purchasesApi.createPurchase({
        supplier_id: 5,
        supplier_name: 'Công ty Dầu ăn Tường An',
        items: [
          {
            id: Date.now(),
            product_id: 15,
            product_name: 'Dầu ăn Tường An 1L',
            sku: 'SP0005',
            packaging: 'Thùng 12 chai',
            quantity: 20,
            unit_price_vnd: 45000,
            total_vnd: 900000,
          },
        ],
      });
      toast.success(`Đã tạo phiếu nhập nháp ${created.code || ''}!`);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      toast.error(getApiErrorMessage(err, 'Lỗi tạo phiếu nhập mới.'));
    } finally {
      setIsActionLoading(false);
    }
  };

  // Cột cho Bảng danh sách phiếu nhập (dùng component common/Table)
  const columns = useMemo(
    () => [
      {
        key: 'code',
        title: 'MÃ PHIẾU',
        width: '120px',
        render: (row) => {
          const isSelected = selectedPurchase?.id === row.id;
          return (
            <span className={styles.purchaseCode}>
              {isSelected && <span className={styles.activeDot} />}
              <span>{row.code}</span>
            </span>
          );
        },
      },
      {
        key: 'supplier_name',
        title: 'NHÀ CUNG CẤP',
        render: (row) => (
          <span className={styles.supplierNameCell} title={row.supplier_name}>
            {row.supplier_name}
          </span>
        ),
      },
      {
        key: 'created_at',
        title: 'NGÀY TẠO',
        width: '110px',
        render: (row) => <span className={styles.dateCell}>{formatDate(row.created_at)}</span>,
      },
      {
        key: 'items_count',
        title: 'SỐ MẶT HÀNG',
        align: 'center',
        width: '120px',
        render: (row) => (
          <span className={styles.itemCountCell}>{row.items_count} sản phẩm</span>
        ),
      },
      {
        key: 'total_amount_vnd',
        title: 'TỔNG TIỀN',
        align: 'right',
        width: '130px',
        render: (row) => (
          <span className={styles.amountCell}>{formatVND(row.total_amount_vnd)}</span>
        ),
      },
      {
        key: 'actions',
        title: 'THAO TÁC',
        align: 'center',
        width: '110px',
        render: (row) => {
          const isSelected = selectedPurchase?.id === row.id;
          return (
            <button
              type="button"
              className={`${styles.viewDetailBtn} ${isSelected ? styles.viewDetailBtnActive : ''}`}
              onClick={() => setSelectedPurchase(row)}
              title="Xem chi tiết phiếu nhập"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <span>{isSelected ? 'Đang xem' : 'Chi tiết'}</span>
            </button>
          );
        },
      },
    ],
    [selectedPurchase]
  );

  const startRecord = pagination.total === 0 ? 0 : (pagination.page - 1) * pagination.page_size + 1;
  const endRecord = Math.min(pagination.page * pagination.page_size, pagination.total);

  return (
    <div className={styles.container}>
      {/* 1. Header Trang */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 className={styles.title}>Quản lý nhập hàng</h1>
          <p className={styles.subtitle}>
            Quản lý phiếu nhập kho từ nhà cung cấp cho cửa hàng
          </p>
        </div>

        <button
          type="button"
          className={styles.primaryBtn}
          onClick={handleCreateNewPurchase}
          disabled={isActionLoading}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>Tạo phiếu nhập</span>
        </button>
      </div>

      {/* 2. Sub-header Navigation Tabs */}
      <div className={styles.subHeaderRow}>
        <div className={styles.navTabs}>
          <button
            type="button"
            className={`${styles.navTabBtn} ${activeTab === 'DRAFTS' ? styles.navTabBtnActive : ''}`}
            onClick={() => {
              setActiveTab('DRAFTS');
              setPagination((prev) => ({ ...prev, page: 1 }));
            }}
          >
            <span>Phiếu nhập</span>
            <span className={styles.tabCountBadge}>{stats.draftsCount}</span>
          </button>
          <button
            type="button"
            className={`${styles.navTabBtn} ${activeTab === 'HISTORY' ? styles.navTabBtnActive : ''}`}
            onClick={() => {
              setActiveTab('HISTORY');
              setPagination((prev) => ({ ...prev, page: 1 }));
            }}
          >
            <span>Lịch sử nhập hàng</span>
            <span className={styles.tabCountBadgeGray}>{stats.historyCount.toLocaleString()}</span>
          </button>
        </div>

        <div className={styles.warehouseHint}>
          Kho áp dụng: <strong>Kho cửa hàng</strong>
        </div>
      </div>

      {/* 3. Thanh tìm kiếm và bộ lọc */}
      <div className={styles.filtersRow}>
        <div className={styles.searchBox}>
          <svg className={styles.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Tìm theo mã phiếu, nhà cung cấp..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <select
          className={styles.selectBox}
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPagination((prev) => ({ ...prev, page: 1 }));
          }}
        >
          <option value="ALL">Trạng thái: Tất cả</option>
          <option value="DRAFT">Bản nháp (DRAFT)</option>
          <option value="CONFIRMED">Đã nhập (CONFIRMED)</option>
        </select>

        <button
          type="button"
          className={styles.timeFilterBtn}
          onClick={() => toast.info('Thời gian lọc: 30 ngày gần nhất')}
        >
          <span>Thời gian: 30 ngày gần nhất</span>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
        </button>
      </div>

      {/* 4. Bố cục 2 Cột Split Layout */}
      <div className={styles.splitLayout}>
        {/* CỘT TRÁI: Bảng danh sách phiếu (sử dụng common/Table và common/Pagination) */}
        <div className={styles.leftCard}>
          <Table
            columns={columns}
            data={data}
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

        {/* CỘT PHẢI: Khung chi tiết phiếu đang được chọn */}
        {selectedPurchase ? (
          <div className={styles.rightPanel}>
            {/* Header chi tiết */}
            <div className={styles.detailHeader}>
              <div>
                <div className={styles.detailTitleRow}>
                  <h2 className={styles.detailTitle}>Chi tiết phiếu: {selectedPurchase.code}</h2>
                  <span className={styles.badgeDraft}>
                    {selectedPurchase.status === 'CONFIRMED' ? 'Đã nhập (CONFIRMED)' : 'Bản nháp (DRAFT)'}
                  </span>
                </div>
              </div>

              <button
                type="button"
                className={styles.deleteIconBtn}
                onClick={handleOpenCancelModal}
                title="Hủy phiếu nhập"
                aria-label="Hủy phiếu"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
              </button>
            </div>

            {/* Meta info */}
            <div className={styles.metaInfoRow}>
              <div>
                Được tạo: <strong>{formatDate(selectedPurchase.created_at)}</strong> bởi <strong>{selectedPurchase.created_by_name || 'Admin'}</strong>
              </div>
              <div>
                Phiên bản nháp: <strong>v{selectedPurchase.draft_version}</strong> (draft_version: {selectedPurchase.draft_version})
              </div>
            </div>

            {/* Thông tin NCC & Kho */}
            <div className={styles.infoGrid}>
              <div className={styles.infoBlock}>
                <span className={styles.infoLabel}>NHÀ CUNG CẤP</span>
                <span className={styles.infoValue}>{selectedPurchase.supplier_name}</span>
                <span className={styles.infoSub}>Mã NCC: {selectedPurchase.supplier_code}</span>
              </div>
              <div className={styles.infoBlock}>
                <span className={styles.infoLabel}>KHO TIẾP NHẬN</span>
                <span className={styles.infoValue}>{selectedPurchase.warehouse_name}</span>
                <span className={styles.infoSub}>Quản lý tồn kho đơn điểm</span>
              </div>
            </div>

            {/* Danh sách mặt hàng nhập */}
            <div className={styles.itemsSection}>
              <div className={styles.itemsHeader}>
                <span className={styles.itemsTitle}>
                  DANH SÁCH SẢN PHẨM ({selectedPurchase.items?.length || 0} MẶT HÀNG)
                </span>
                <button
                  type="button"
                  className={styles.addItemLink}
                  onClick={() => toast.info('Mở hộp thoại chọn sản phẩm thêm vào phiếu')}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  <span>Thêm mặt hàng</span>
                </button>
              </div>

              <table className={styles.itemsTable}>
                <thead>
                  <tr>
                    <th>Mặt hàng</th>
                    <th>SL</th>
                    <th>Đơn giá (đ)</th>
                    <th>Thành tiền (đ)</th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedPurchase.items || []).map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className={styles.itemMainName}>{item.product_name}</div>
                        <div className={styles.itemSubSku}>
                          SKU: {item.sku} • {item.packaging}
                        </div>
                      </td>
                      <td className={styles.qtyBadge}>{item.quantity}</td>
                      <td className={styles.unitPrice}>
                        {(item.unit_price_vnd || 0).toLocaleString('vi-VN')}
                      </td>
                      <td className={styles.lineTotal}>
                        {(item.total_vnd || 0).toLocaleString('vi-VN')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Tổng số lượng & Tổng tiền */}
            <div className={styles.summaryBlock}>
              <div className={styles.summaryRow}>
                <span>Tổng số lượng nhập:</span>
                <strong>{selectedPurchase.total_quantity} sản phẩm</strong>
              </div>
              <div className={styles.summaryTotalRow}>
                <span>Tổng tiền nhập:</span>
                <span className={styles.totalHighlight}>
                  {formatVND(selectedPurchase.total_amount_vnd)}
                </span>
              </div>
            </div>

            {/* Lưu ý khi xác nhận PUR-03 */}
            <div className={styles.confirmWarningBox}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, marginTop: 1 }}>
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <div>
                <strong>Lưu ý:</strong> Khi xác nhận, hệ thống sẽ kiểm tra phiên bản nháp mới nhất, cập nhật tăng tồn kho thực tế và chuyển trạng thái phiếu sang <strong>ĐÃ NHẬP (CONFIRMED)</strong>. Phiếu đã xác nhận sẽ không thể chỉnh sửa hay hủy bỏ.
              </div>
            </div>

            {/* Các nút bấm thao tác */}
            <div className={styles.detailFooter}>
              <button
                type="button"
                className={styles.cancelDraftBtn}
                onClick={handleOpenCancelModal}
                disabled={isActionLoading}
              >
                Hủy phiếu nhập
              </button>
              <button
                type="button"
                className={styles.saveDraftBtn}
                onClick={handleSaveDraft}
                disabled={isActionLoading}
              >
                Lưu nháp
              </button>
              <button
                type="button"
                className={styles.confirmBtn}
                onClick={handleConfirmPurchase}
                disabled={isActionLoading}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span>Xác nhận phiếu</span>
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.rightPanel} style={{ alignItems: 'center', justifyContent: 'center', minHeight: '300px', color: '#6B7280' }}>
            <span>Chọn một phiếu nhập từ bảng bên trái để xem chi tiết</span>
          </div>
        )}
      </div>

      {/* 5. Modal xác nhận hủy phiếu nhập dùng component common/Modal */}
      <Modal
        isOpen={isCancelModalOpen}
        onClose={() => !isActionLoading && setIsCancelModalOpen(false)}
        title="Xác nhận hủy phiếu nhập"
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
          <strong style={{ color: '#111827' }}>{selectedPurchase?.code}</strong> của nhà cung cấp{' '}
          <strong style={{ color: '#111827' }}>{selectedPurchase?.supplier_name}</strong>?
        </p>
      </Modal>
    </div>
  );
}

