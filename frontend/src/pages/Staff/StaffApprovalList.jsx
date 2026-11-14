import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Modal, Pagination, useToast } from '../../components/common';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import { getApiErrorMessage } from '../../api/axiosClient';
import {
  formatApprovalDateTimeVN,
  getEmailInitials,
  parsePositiveApprovalId,
  staffApprovalsApi,
  validateRejectReason,
} from '../../api/staffApprovalsApi';
import {
  canUserCloseApprovalModal,
  executeStaffApprovalDecision,
} from './staffApprovalModalHelpers';
import styles from './StaffApprovalList.module.css';

const STATUS_TABS = [
  { key: 'PENDING', label: 'Chờ duyệt' },
  { key: 'APPROVED', label: 'Đã duyệt' },
  { key: 'REJECTED', label: 'Đã từ chối' },
];

export default function StaffApprovalList() {
  const { isMockMode, canUseMock } = useAuth();
  const toast = useToast();
  const [urlSearchParams, setUrlSearchParams] = useSearchParams();

  const isMock = Boolean(isMockMode && canUseMock);

  // 1. State bộ lọc, tìm kiếm & phân trang
  const [activeStatus, setActiveStatus] = useState('PENDING');
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(!isMock);
  const [loadError, setLoadError] = useState('');
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [lastUpdatedLabel, setLastUpdatedLabel] = useState('Vừa xong');

  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    total: 0,
    totalPages: 1,
  });

  // Đếm số lượng theo từng tab trạng thái từ API thật
  const [tabCounts, setTabCounts] = useState({
    PENDING: 0,
    APPROVED: 0,
    REJECTED: 0,
  });

  // 2. State Modal xem chi tiết & xử lý phê duyệt / từ chối
  const [selectedApproval, setSelectedApproval] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [modalError, setModalError] = useState('');
  const [isModalStale, setIsModalStale] = useState(false);
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);

  const requestIdRef = useRef(0);
  const deepLinkGenRef = useRef(0);
  const lastFetchedCountsRefreshRef = useRef(-1);
  const isDecisionPendingRef = useRef(false);
  const reasonInputRef = useRef(null);

  const targetRequestIdParam = urlSearchParams.get('approval_request_id');

  // Tải danh sách yêu cầu duyệt nhân viên + đồng bộ số lượng từng tab (chỉ fetch 3 tab counts khi khởi tạo hoặc refresh)
  useEffect(() => {
    if (isMock) return undefined;

    const currentReqId = ++requestIdRef.current;
    const shouldFetchCounts =
      lastFetchedCountsRefreshRef.current !== refreshTrigger;

    const requests = [
      staffApprovalsApi.getApprovals({
        isMockMode: isMock,
        status: activeStatus,
        page: pagination.page,
        pageSize: pagination.page_size,
      }),
    ];

    if (shouldFetchCounts) {
      requests.push(
        staffApprovalsApi.getApprovals({
          isMockMode: isMock,
          status: 'PENDING',
          page: 1,
          pageSize: 1,
        }),
        staffApprovalsApi.getApprovals({
          isMockMode: isMock,
          status: 'APPROVED',
          page: 1,
          pageSize: 1,
        }),
        staffApprovalsApi.getApprovals({
          isMockMode: isMock,
          status: 'REJECTED',
          page: 1,
          pageSize: 1,
        })
      );
    }

    Promise.all(requests)
      .then(([mainPage, pendingRes, approvedRes, rejectedRes]) => {
        if (currentReqId !== requestIdRef.current) return;

        const fetchedItems = mainPage.items || [];
        const total = mainPage.total || 0;
        const totalPages = Math.max(
          1,
          Math.ceil(total / (mainPage.page_size || pagination.page_size))
        );

        setItems(fetchedItems);
        setPagination((prev) => ({
          ...prev,
          page: mainPage.page,
          page_size: mainPage.page_size,
          total,
          totalPages,
        }));

        if (shouldFetchCounts && pendingRes && approvedRes && rejectedRes) {
          lastFetchedCountsRefreshRef.current = refreshTrigger;
          setTabCounts({
            PENDING: pendingRes.total || 0,
            APPROVED: approvedRes.total || 0,
            REJECTED: rejectedRes.total || 0,
          });
        } else {
          setTabCounts((prev) => ({
            ...prev,
            [activeStatus]: total,
          }));
        }
        setLoadError('');

        const nowTime = new Intl.DateTimeFormat('vi-VN', {
          timeZone: 'Asia/Ho_Chi_Minh',
          hour: '2-digit',
          minute: '2-digit',
        }).format(new Date());
        setLastUpdatedLabel(`Lúc ${nowTime}`);
      })
      .catch((error) => {
        if (currentReqId !== requestIdRef.current) return;
        const status = error?.response?.status;
        if (status === 403) {
          setLoadError(
            'Bạn không có quyền truy cập danh sách xét duyệt nhân viên (HTTP 403 — Chỉ dành cho Quản trị viên ACTIVE).'
          );
        } else if (status === 401) {
          setLoadError(
            'Phiên đăng nhập đã hết hạn hoặc không hợp lệ (HTTP 401). Vui lòng đăng nhập lại.'
          );
        } else {
          setLoadError(
            getApiErrorMessage(error) ||
              'Không thể tải danh sách xét duyệt nhân viên từ máy chủ.'
          );
        }
      })
      .finally(() => {
        if (currentReqId === requestIdRef.current) {
          setIsLoading(false);
        }
      });

    return () => {
      requestIdRef.current += 1;
    };
  }, [
    activeStatus,
    isMock,
    pagination.page,
    pagination.page_size,
    refreshTrigger,
  ]);

  // Xử lý deep-link ?approval_request_id=<id> (tìm trên trang hiện tại hoặc tìm có giới hạn across statuses/pages)
  useEffect(() => {
    if (isMock || !targetRequestIdParam || isLoading || loadError) {
      return undefined;
    }

    const parsedId = parsePositiveApprovalId(targetRequestIdParam);
    const currentDeepLinkGen = ++deepLinkGenRef.current;

    if (!parsedId) {
      Promise.resolve().then(() => {
        if (currentDeepLinkGen !== deepLinkGenRef.current) return;
        toast.warning('Mã hồ sơ trên đường dẫn không hợp lệ.');
        const nextParams = new URLSearchParams(urlSearchParams);
        nextParams.delete('approval_request_id');
        setUrlSearchParams(nextParams, { replace: true });
      });
      return () => {
        deepLinkGenRef.current += 1;
      };
    }

    if (selectedApproval?.id === parsedId) {
      return undefined;
    }

    staffApprovalsApi
      .findApprovalByIdBounded({
        isMockMode: isMock,
        approvalId: parsedId,
        currentItems: items,
        activeStatus,
        maxPagesPerStatus: 3,
        pageSize: 50,
      })
      .then((found) => {
        if (currentDeepLinkGen !== deepLinkGenRef.current) return;

        if (!found) {
          toast.warning(
            `Không tìm thấy hồ sơ #${parsedId} trong hàng đợi xét duyệt gần đây.`
          );
          const nextParams = new URLSearchParams(urlSearchParams);
          nextParams.delete('approval_request_id');
          setUrlSearchParams(nextParams, { replace: true });
          return;
        }

        if (found.status !== activeStatus) {
          setActiveStatus(found.status);
          setPagination((prev) => ({ ...prev, page: 1 }));
        }

        setSelectedApproval(found.item);
        setRejectReason(found.item.decision_reason || '');
        setIsModalStale(false);
        setModalError('');
      })
      .catch((error) => {
        if (currentDeepLinkGen !== deepLinkGenRef.current) return;
        const status = error?.response?.status;
        if (status === 401 || status === 403) {
          return;
        }
        toast.error(
          getApiErrorMessage(error) ||
            `Không thể mở hồ sơ #${parsedId} từ liên kết thông báo.`
        );
      });

    return () => {
      deepLinkGenRef.current += 1;
    };
  }, [
    activeStatus,
    isLoading,
    isMock,
    items,
    loadError,
    selectedApproval?.id,
    setUrlSearchParams,
    targetRequestIdParam,
    toast,
    urlSearchParams,
  ]);

  // Lọc theo từ khóa tìm kiếm trên trang hiện tại dựa trên các trường thực tế từ API (Email, Mã hồ sơ, User ID, Lần gửi, Lý do)
  const filteredItems = useMemo(() => {
    const trimmed = keyword.trim().toLowerCase();
    if (!trimmed) return items;

    return items.filter((item) => {
      const searchableText = [
        item.email || '',
        `hồ sơ nhân viên #${item.id}`,
        `reg-${item.id}`,
        `#${item.id}`,
        `user #${item.user_id}`,
        `${item.user_id}`,
        `lần #${item.attempt_no}`,
        item.status || '',
        item.decision_reason || '',
      ]
        .join(' ')
        .toLowerCase();
      return searchableText.includes(trimmed);
    });
  }, [items, keyword]);

  // Chuyển tab trạng thái (Chờ duyệt / Đã duyệt / Đã từ chối)
  const handleSelectStatusTab = (nextStatus) => {
    if (nextStatus === activeStatus) return;
    setIsLoading(true);
    setLoadError('');
    setActiveStatus(nextStatus);
    setPagination((prev) => ({ ...prev, page: 1 }));
  };

  // Làm mới dữ liệu thủ công
  const handleRefresh = useCallback(() => {
    setIsLoading(true);
    setLoadError('');
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  // Đổi trang phân trang
  const handlePageChange = (nextPage) => {
    setIsLoading(true);
    setLoadError('');
    setPagination((prev) => ({ ...prev, page: nextPage }));
  };

  // Mở Modal khi bấm vào thẻ hồ sơ của nhân viên bất kỳ
  const handleOpenDetailModal = (item) => {
    setSelectedApproval(item);
    setRejectReason(item.decision_reason || '');
    setIsModalStale(false);
    setModalError('');
  };

  // Đóng Modal nội bộ (dùng cho cả programmatic close sau khi POST thành công và user close sau khi qua guard)
  const closeDetailModalProgrammatic = useCallback(() => {
    deepLinkGenRef.current += 1;
    setSelectedApproval(null);
    setRejectReason('');
    setIsModalStale(false);
    setModalError('');
    if (urlSearchParams.has('approval_request_id')) {
      const nextParams = new URLSearchParams(urlSearchParams);
      nextParams.delete('approval_request_id');
      setUrlSearchParams(nextParams, { replace: true });
    }
  }, [setUrlSearchParams, urlSearchParams]);

  // Đóng Modal do người dùng thao tác (X, nút Đóng, Escape hoặc click nền mờ) — bị chặn khi đang gửi POST
  const handleCloseDetailModal = () => {
    if (
      !canUserCloseApprovalModal({
        isSubmittingDecision,
        isDecisionPending: isDecisionPendingRef.current,
      })
    ) {
      return;
    }
    closeDetailModalProgrammatic();
  };

  // Xử lý Phê duyệt (Chấp nhận) hồ sơ Staff — POST /api/v1/staff-approvals/{id}/approve
  const handleApproveStaff = () =>
    executeStaffApprovalDecision({
      action: 'approve',
      isMockMode: isMock,
      selectedApproval,
      isModalStale,
      isDecisionPendingRef,
      staffApprovalsApi,
      getApiErrorMessage,
      setIsSubmittingDecision,
      setModalError,
      setIsModalStale,
      onSuccessToast: (approval) => {
        const targetEmail = approval.email || `User #${approval.user_id}`;
        toast.success(
          `Đã chấp nhận phê duyệt tài khoản ${targetEmail} (Hồ sơ #${approval.id} • Trạng thái: ACTIVE).`
        );
      },
      closeModalProgrammatic: closeDetailModalProgrammatic,
      onRefresh: handleRefresh,
    });

  // Xử lý Từ chối hồ sơ Staff — POST /api/v1/staff-approvals/{id}/reject
  const handleRejectStaff = () =>
    executeStaffApprovalDecision({
      action: 'reject',
      isMockMode: isMock,
      selectedApproval,
      isModalStale,
      isDecisionPendingRef,
      rejectReason,
      validateRejectReason,
      staffApprovalsApi,
      getApiErrorMessage,
      setIsSubmittingDecision,
      setModalError,
      setIsModalStale,
      onInvalidReason: () => {
        if (reasonInputRef.current) {
          reasonInputRef.current.focus();
        }
      },
      onSuccessToast: (approval) => {
        const targetEmail = approval.email || `User #${approval.user_id}`;
        toast.info(
          `Đã từ chối hồ sơ đăng ký của ${targetEmail} (Hồ sơ #${approval.id}).`
        );
      },
      closeModalProgrammatic: closeDetailModalProgrammatic,
      onRefresh: handleRefresh,
    });

  const statusSummaryLabel =
    activeStatus === 'PENDING'
      ? 'đang chờ quyết định'
      : activeStatus === 'APPROVED'
      ? 'đã được phê duyệt'
      : 'đã bị từ chối';

  return (
    <div className={styles.container}>
      {/* Cảnh báo nếu đang ở chế độ Mock */}
      {isMock && (
        <div className={styles.mockWarningBanner} role="alert">
          <div className={styles.mockWarningTitle}>
            <span>
              Chế độ Mock Demo không được hỗ trợ trong Duyệt tài khoản nhân viên
            </span>
          </div>
          <p>
            Module Duyệt tài khoản nhân viên kết nối trực tiếp với API thật
            (/api/v1/staff-approvals) và không sử dụng dữ liệu mẫu.
          </p>
        </div>
      )}

      {/* 1. Header trang (Cấu trúc đồng bộ với Quản lý sản phẩm) */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <div className={styles.titleRow}>
            <h1 className={styles.title}>Duyệt tài khoản nhân viên</h1>
            <span className={styles.authCodeBadge}>AUTH-01 &amp; AUTH-03</span>
          </div>
          <p className={styles.subtitle}>
            Hàng đợi xét duyệt hồ sơ đăng ký tài khoản nhân viên (Staff) • Quyền
            Admin
          </p>
        </div>

        <div className={styles.headerActions}>
          <div className={styles.policyBadge}>
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
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <polyline points="9 12 11 14 15 10" />
            </svg>
            <span>
              Quy chuẩn: Cấp quyền duy nhất <strong>STAFF</strong> (1 cửa hàng,
              1 kho)
            </span>
          </div>

          <button
            type="button"
            className={styles.refreshBtn}
            onClick={handleRefresh}
            disabled={isLoading || isMock}
          >
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
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
            <span>Làm mới</span>
          </button>
        </div>
      </div>

      {/* 2. Thanh Bộ lọc & Tab trạng thái hài hòa, cân đối */}
      <div className={styles.filterBar}>
        <div
          className={styles.statusTabs}
          role="tablist"
          aria-label="Lọc theo trạng thái phê duyệt"
        >
          {STATUS_TABS.map((tab) => {
            const isActive = activeStatus === tab.key;
            const count = tabCounts[tab.key] ?? 0;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`${styles.statusTabBtn} ${
                  isActive ? styles.statusTabBtnActive : ''
                }`}
                onClick={() => handleSelectStatusTab(tab.key)}
              >
                <span>{tab.label}</span>
                <span
                  className={`${styles.tabCountBadge} ${
                    isActive ? styles.tabCountBadgeActive : ''
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

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
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Tìm trong trang hiện tại (email, mã hồ sơ, User ID)..."
            aria-label="Tìm trong trang hiện tại"
            className={styles.searchInput}
          />
        </div>
      </div>

      {/* 3. Dòng tóm tắt số lượng & thời gian cập nhật */}
      <div className={styles.summaryStrip}>
        <span>
          {keyword.trim() ? (
            <>
              Khớp <strong>{filteredItems.length}</strong>/{items.length} hồ sơ
              trên trang hiện tại (Tổng mục: <strong>{pagination.total}</strong>
              )
            </>
          ) : (
            <>
              Hiển thị <strong>{items.length}</strong>/{pagination.total} hồ sơ{' '}
              {statusSummaryLabel}
            </>
          )}
        </span>
        <span className={styles.summaryRight}>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <span>Cập nhật: {lastUpdatedLabel}</span>
        </span>
      </div>

      {/* 4. Danh sách hồ sơ từ API thật (/api/v1/staff-approvals) */}
      {isLoading ? (
        <div className={styles.stateCard}>
          <h3 className={styles.stateTitle}>
            Đang tải danh sách hồ sơ nhân viên...
          </h3>
          <p className={styles.stateDesc}>
            Hệ thống đang đồng bộ dữ liệu thực tế từ máy chủ RetailOps.
          </p>
        </div>
      ) : loadError ? (
        <div className={styles.stateCard} role="alert">
          <h3 className={styles.stateTitle}>Không thể tải danh sách hồ sơ</h3>
          <p className={styles.errorText}>{loadError}</p>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={handleRefresh}
          >
            Thử lại
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className={styles.stateCard}>
          <h3 className={styles.stateTitle}>
            Chưa có hồ sơ nhân viên nào trong mục này
          </h3>
          <p className={styles.stateDesc}>
            Khi có nhân viên mới gửi yêu cầu đăng ký tài khoản tại trang
            /register, hồ sơ sẽ xuất hiện tại đây để Quản trị viên xét duyệt.
          </p>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className={styles.stateCard}>
          <h3 className={styles.stateTitle}>
            Không tìm thấy hồ sơ khớp từ khóa trên trang hiện tại
          </h3>
          <p className={styles.stateDesc}>
            Tìm kiếm chỉ lọc trong {items.length} hồ sơ của trang đang hiển thị.
            Hãy thử chuyển trang hoặc xóa từ khóa tìm kiếm.
          </p>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={() => setKeyword('')}
          >
            Xóa từ khóa tìm kiếm
          </button>
        </div>
      ) : (
        <div className={styles.cardList}>
          {filteredItems.map((item) => {
            const isSelected = selectedApproval?.id === item.id;
            const initials = getEmailInitials(item.email);

            return (
              <button
                key={item.id}
                type="button"
                className={`${styles.staffCard} ${
                  isSelected ? styles.staffCardSelected : ''
                }`}
                onClick={() => handleOpenDetailModal(item)}
              >
                <div className={styles.cardTopRow}>
                  <div className={styles.applicantIdentity}>
                    <div
                      className={`${styles.avatarCircle} ${
                        item.status !== 'PENDING'
                          ? styles.avatarCircleNeutral
                          : ''
                      }`}
                    >
                      {initials}
                    </div>

                    <div className={styles.applicantTexts}>
                      <div className={styles.applicantNameRow}>
                        <span className={styles.applicantName}>
                          {item.email}
                        </span>
                        <span className={styles.requestCodePill}>
                          ID: REG-{item.id} • Lần #{item.attempt_no}
                        </span>
                      </div>
                      <span className={styles.applicantEmail}>
                        Email đăng ký: {item.email} • Mã tài khoản User #
                        {item.user_id} • Yêu cầu #{item.id}
                      </span>
                    </div>
                  </div>

                  {item.status === 'PENDING' ? (
                    <span className={styles.statusPillPending}>
                      <span
                        className={styles.statusDotPending}
                        aria-hidden="true"
                      />
                      <span>PENDING</span>
                    </span>
                  ) : item.status === 'APPROVED' ? (
                    <span className={styles.statusPillApproved}>
                      <span aria-hidden="true">✓</span>
                      <span>APPROVED</span>
                    </span>
                  ) : (
                    <span className={styles.statusPillRejected}>
                      <span aria-hidden="true">✕</span>
                      <span>REJECTED</span>
                    </span>
                  )}
                </div>

                <div className={styles.cardDivider} />

                <div className={styles.cardBottomRow}>
                  <span className={styles.timeInfo}>
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                    <span>
                      Thời gian gửi:{' '}
                      <strong>
                        {formatApprovalDateTimeVN(item.requested_at)}
                      </strong>
                    </span>
                  </span>

                  <div className={styles.cardBottomRight}>
                    <span className={styles.storeScopeLabel}>
                      Cửa hàng RetailOps (duy nhất)
                    </span>
                    <span className={styles.viewProfileLink}>
                      <span>Xem hồ sơ</span>
                      <span aria-hidden="true">→</span>
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* 5. Phân trang chuẩn */}
      {!isLoading && !loadError && pagination.total > 0 && (
        <Pagination
          currentPage={pagination.page}
          totalPages={pagination.totalPages}
          totalItems={pagination.total}
          pageSize={pagination.page_size}
          onPageChange={handlePageChange}
        />
      )}

      {/* 6. Ghi chú quy chuẩn AUTH-01 */}
      <div className={styles.complianceNotice}>
        <span className={styles.complianceIcon} aria-hidden="true">
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
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        </span>
        <span>
          Chỉ tài khoản đăng ký qua luồng nội bộ được
          hiển thị tại đây. Đảm bảo nhân viên đã ký hợp đồng thử việc trước khi
          cấp mã truy cập.
        </span>
      </div>

      {/* 7. Modal Chi tiết hồ sơ nhân viên (Có nút X góc phải & bấm ra ngoài để thoát, có nút Từ chối & Chấp nhận) */}
      <Modal
        isOpen={Boolean(selectedApproval)}
        onClose={handleCloseDetailModal}
        title="Chi tiết hồ sơ đăng ký nhân viên"
        maxWidth="580px"
        footer={
          selectedApproval ? (
            <>
              <button
                type="button"
                className={modalStyles.cancelBtn}
                onClick={handleCloseDetailModal}
                disabled={isSubmittingDecision}
              >
                Đóng
              </button>

              {selectedApproval.status === 'PENDING' && !isModalStale && (
                <>
                  <button
                    type="button"
                    className={styles.rejectModalBtn}
                    onClick={handleRejectStaff}
                    disabled={isSubmittingDecision}
                  >
                    <span>
                      {isSubmittingDecision ? 'Đang xử lý...' : 'Từ chối'}
                    </span>
                  </button>

                  <button
                    type="button"
                    className={styles.approveModalBtn}
                    onClick={handleApproveStaff}
                    disabled={isSubmittingDecision}
                  >
                    <span>
                      {isSubmittingDecision ? 'Đang xử lý...' : 'Chấp nhận'}
                    </span>
                  </button>
                </>
              )}
            </>
          ) : null
        }
      >
        {selectedApproval && (
          <div className={styles.modalContentWrapper}>
            {/* Dòng mã hồ sơ & trạng thái */}
            <div className={styles.modalSubheader}>
              <span className={styles.modalRecordIdBadge}>
                ID: REG-{selectedApproval.id} • User #{selectedApproval.user_id}
              </span>

              {selectedApproval.status === 'PENDING' ? (
                <span className={styles.statusPillPending}>
                  <span
                    className={styles.statusDotPending}
                    aria-hidden="true"
                  />
                  <span>PENDING</span>
                </span>
              ) : selectedApproval.status === 'APPROVED' ? (
                <span className={styles.statusPillApproved}>
                  <span aria-hidden="true">✓</span>
                  <span>APPROVED</span>
                </span>
              ) : (
                <span className={styles.statusPillRejected}>
                  <span aria-hidden="true">✕</span>
                  <span>REJECTED</span>
                </span>
              )}
            </div>

            {/* Khối 1: HỒ SƠ ỨNG VIÊN (Thuần 100% trường từ API ApprovalListItemRead) */}
            <div className={styles.sectionBox}>
              <div className={styles.sectionHeaderRow}>
                <h3 className={styles.sectionTitle}>HỒ SƠ ỨNG VIÊN</h3>
                <span className={styles.sectionTag}>Hồ sơ đăng ký nội bộ</span>
              </div>

              <div className={styles.infoGrid}>
                <div className={styles.infoField}>
                  <span className={styles.infoLabel}>Email đăng ký</span>
                  <span className={styles.infoValue}>
                    {selectedApproval.email}
                  </span>
                </div>

                <div className={styles.infoField}>
                  <span className={styles.infoLabel}>Thời điểm nộp đơn</span>
                  <span className={styles.infoValue}>
                    {formatApprovalDateTimeVN(selectedApproval.requested_at)}
                  </span>
                </div>

                <div className={styles.infoField}>
                  <span className={styles.infoLabel}>Mã yêu cầu xét duyệt</span>
                  <span className={styles.infoValue}>
                    REG-{selectedApproval.id} (#{selectedApproval.id})
                  </span>
                </div>

                <div className={styles.infoField}>
                  <span className={styles.infoLabel}>
                    Mã tài khoản (User ID) • Lần gửi
                  </span>
                  <span className={styles.infoValue}>
                    User #{selectedApproval.user_id} • Lần #
                    {selectedApproval.attempt_no}
                  </span>
                </div>

                {selectedApproval.decided_by && (
                  <div className={styles.infoField}>
                    <span className={styles.infoLabel}>
                      Người xử lý quyết định
                    </span>
                    <span className={styles.infoValue}>
                      Admin #{selectedApproval.decided_by}
                    </span>
                  </div>
                )}

                {selectedApproval.decided_at && (
                  <div className={styles.infoField}>
                    <span className={styles.infoLabel}>
                      Thời điểm xử lý quyết định
                    </span>
                    <span className={styles.infoValue}>
                      {formatApprovalDateTimeVN(selectedApproval.decided_at)}
                    </span>
                  </div>
                )}

                <div className={styles.infoFieldFull}>
                  <span className={styles.infoLabel}>Phạm vi áp dụng</span>
                  <span className={styles.scopeValueRow}>
                    <svg
                      className={styles.scopeIcon}
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                      <polyline points="9 22 9 12 15 12 15 22" />
                    </svg>
                    <span>Một cửa hàng &amp; một kho lưu trữ duy nhất</span>
                  </span>
                </div>
              </div>

              {selectedApproval.status === 'REJECTED' &&
                selectedApproval.decision_reason && (
                  <div className={styles.rejectionReasonBox}>
                    <strong>Lý do từ chối đã ghi nhận:</strong>{' '}
                    {selectedApproval.decision_reason}
                  </div>
                )}
            </div>

            {/* Khối 2: VAI TRÒ HỆ THỐNG SẼ CẤP */}
            <div className={styles.sectionBox}>
              <div className={styles.sectionHeaderRow}>
                <h3 className={styles.sectionTitle}>
                  VAI TRÒ HỆ THỐNG SẼ CẤP
                </h3>
                <span className={styles.sectionTag}>Cố định (AUTH-01)</span>
              </div>

              <div className={styles.roleBox}>
                <div className={styles.roleBoxHeader}>
                  <span className={styles.roleBoxTitle}>
                    <span>Nhân viên bán hàng (Staff)</span>
                  </span>
                  <span className={styles.roleCodePill}>ROLE_STAFF</span>
                </div>

                <p className={styles.roleDescParagraph}>
                  <strong>Quyền hạn được cấp:</strong> Bán hàng tại quầy (POS),
                  tra cứu &amp; xem chi tiết sản phẩm, xem tồn kho hiện tại, xem
                  biến động kho đã lọc (không hiển thị giá vốn/giá nhập/lý do
                  nội bộ), xem danh sách &amp; chi tiết đơn hàng.
                </p>

                <p className={styles.roleDescParagraph}>
                  <strong>Không có quyền:</strong> Tổng quan/Báo cáo quản trị,
                  Phân tích (Analytics), Trợ lý AI, Quản lý nhập hàng, Nhà cung
                  cấp hoặc Quản lý nhân viên.
                </p>

                <p className={styles.roleNoteText}>
                  * Lưu ý: Quyền hạn được thiết lập cố định theo quy chuẩn hệ
                  thống V1.0, không phân quyền theo ca hay chi nhánh.
                </p>
              </div>
            </div>

            {/* Khối 3: Lý do từ chối (Khi hồ sơ đang ở trạng thái PENDING và chưa bị stale) */}
            {selectedApproval.status === 'PENDING' && !isModalStale && (
              <div className={styles.decisionFormSection}>
                <label
                  htmlFor="staff-reject-reason"
                  className={styles.reasonLabel}
                >
                  Lý do từ chối hồ sơ{' '}
                  <span className={styles.reasonHint}>
                    (Chỉ bắt buộc khi bấm nút &quot;Từ chối&quot; — tối đa 500
                    ký tự)
                  </span>
                </label>
                <textarea
                  id="staff-reject-reason"
                  ref={reasonInputRef}
                  className={styles.reasonTextarea}
                  value={rejectReason}
                  onChange={(e) => {
                    setRejectReason(e.target.value);
                    if (modalError) setModalError('');
                  }}
                  maxLength={500}
                  placeholder="Nhập lý do từ chối nếu không chấp nhận hồ sơ này..."
                  disabled={isSubmittingDecision}
                />
              </div>
            )}

            {modalError && (
              <div className={styles.modalErrorAlert} role="alert">
                {modalError}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
