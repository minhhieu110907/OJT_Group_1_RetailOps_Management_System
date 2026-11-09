import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import styles from './AccountStatus.module.css';

// Hàm lấy giờ hiện tại theo chuẩn múi giờ Asia/Ha_Noi (HH:mm)
function getHaNoiCurrentTime() {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date());
}

// Dữ liệu hồ sơ mẫu không nhạy cảm khi truy cập trực tiếp /account-status
const FALLBACK_PROFILE = {
  fullName: 'Nhân viên Mẫu (Chưa xác thực)',
  email: 'nhanvien.demo@retailops.local',
  submittedAt: '09:30 - 07/11/2026 (Asia/Ha_Noi)',
  rejectReason:
    'Hồ sơ chưa đáp ứng điều kiện phân ca nhân sự tại cửa hàng. Vui lòng liên hệ Quản trị viên để biết thêm chi tiết.',
};

export default function AccountStatus() {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const { isMockMode, canUseMock, checkBackendConnection } = useAuth();
  const isMockDemoActive = Boolean(isMockMode && canUseMock);

  // Lấy dữ liệu truyền từ Register.jsx / Login.jsx qua location.state hoặc dùng fallback
  const incomingState = location.state || {};
  const isUnverifiedSubmission =
    !isMockDemoActive &&
    (incomingState.isUnverifiedSubmission !== false ||
      incomingState.status === 'SUBMITTED' ||
      !incomingState.status);

  const profile = {
    fullName: incomingState.fullName || FALLBACK_PROFILE.fullName,
    email: incomingState.email || FALLBACK_PROFILE.email,
    submittedAt: incomingState.submittedAt || FALLBACK_PROFILE.submittedAt,
    rejectReason: incomingState.rejectReason || FALLBACK_PROFILE.rejectReason,
  };

  // Trạng thái chính của hồ sơ: 'PENDING' | 'APPROVED' | 'REJECTED'
  // Chuẩn hóa tương thích với Backend enum (PENDING_APPROVAL / SUBMITTED -> PENDING, ACTIVE -> APPROVED)
  const rawStatus = incomingState.status;
  const initialStatus =
    rawStatus === 'PENDING_APPROVAL' || rawStatus === 'SUBMITTED'
      ? 'PENDING'
      : rawStatus === 'ACTIVE'
      ? 'APPROVED'
      : rawStatus || 'PENDING';
  const [status, setStatus] = useState(initialStatus);

  // Trạng thái con của mục Gửi lại khi REJECTED:
  // - 'LOCKED_24H' (Mặc định khi lần đầu mở: Tạm khóa trong vòng 24h)
  // - 'ELIGIBLE' (Sau 24h: Đủ điều kiện gửi lại)
  const [rejectSubState] = useState(incomingState.rejectSubState || 'LOCKED_24H');

  // Cờ xác minh quyền kiểm soát tài khoản (ở trạng thái REJECTED - Đủ điều kiện)
  const [isAccountVerified, setIsAccountVerified] = useState(false);

  // Thời gian cập nhật lần cuối (HH:mm Asia/Ha_Noi)
  const [lastUpdated, setLastUpdated] = useState(() => getHaNoiCurrentTime());

  // Hiệu ứng loading khi bấm kiểm tra trạng thái
  const [isChecking, setIsChecking] = useState(false);

  // Khối lỗi kết nối máy chủ (Ẩn ở chế độ bình thường, chỉ hiện khi gặp lỗi mạng/máy chủ)
  const [hasConnectionError, setHasConnectionError] = useState(
    Boolean(incomingState.hasConnectionError)
  );

  // Xử lý bấm nút kiểm tra trạng thái phê duyệt
  const handleCheckStatus = async () => {
    // Chế độ Real API: Không giả lập kiểm tra trạng thái phê duyệt từ Backend vì không có public endpoint
    if (!isMockDemoActive) {
      toast.info(
        'Hệ thống bảo mật không công khai trạng thái tài khoản khi chưa xác thực. Vui lòng thử đăng nhập tại trang Đăng nhập hoặc liên hệ Quản trị viên.'
      );
      return;
    }

    setIsChecking(true);
    await new Promise((resolve) => setTimeout(resolve, 400));
    setIsChecking(false);
    setLastUpdated(getHaNoiCurrentTime());
    setHasConnectionError(false);

    if (status === 'PENDING') {
      toast.info(
        'Chế độ Mock Demo: Hồ sơ mẫu vẫn đang ở trạng thái chờ Quản trị viên xét duyệt.'
      );
    }
  };

  // Xử lý bấm nút "Thử lại kết nối" trên Error Banner (Chỉ kiểm tra kết nối /api/v1/health, tách biệt với trạng thái phê duyệt)
  const handleRetryConnection = async () => {
    setIsChecking(true);
    if (!isMockDemoActive) {
      const isOnline = await checkBackendConnection();
      setIsChecking(false);
      setLastUpdated(getHaNoiCurrentTime());
      if (isOnline) {
        setHasConnectionError(false);
        toast.success('Đã khôi phục kết nối máy chủ thành công.');
      } else {
        setHasConnectionError(true);
        toast.error('Chưa thể kết nối lại máy chủ FastAPI. Vui lòng kiểm tra dịch vụ Backend.');
      }
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 400));
    setIsChecking(false);
    setLastUpdated(getHaNoiCurrentTime());
    setHasConnectionError(false);
    toast.success('Đã khôi phục kết nối máy chủ thành công (Chế độ Mock Demo).');
  };

  // Xử lý gửi lại yêu cầu xét duyệt khi ở trạng thái REJECTED (Đủ điều kiện)
  const handleResubmitRequest = async () => {
    if (!isAccountVerified) {
      toast.warning(
        'Vui lòng bấm "Xác minh quyền kiểm soát tài khoản" trước khi gửi lại yêu cầu.'
      );
      return;
    }

    if (!isMockDemoActive) {
      toast.info(
        'Chức năng gửi lại yêu cầu tự động thuộc phạm vi phát triển tiếp theo. Vui lòng liên hệ Quản trị viên để được mở lại hồ sơ.'
      );
      return;
    }

    setIsChecking(true);
    await new Promise((resolve) => setTimeout(resolve, 400));
    setIsChecking(false);
    setLastUpdated(getHaNoiCurrentTime());
    setStatus('PENDING');
    toast.success('Đã gửi lại yêu cầu xét duyệt hồ sơ thành công (Chế độ Mock Demo)!');
  };

  // Xác định class viền cho thẻ Card duy nhất
  const cardVariantClass =
    status === 'APPROVED'
      ? styles.cardApproved
      : status === 'REJECTED'
      ? styles.cardRejected
      : styles.cardPending;

  return (
    <div className={styles.statusWrapper}>
      {/* 1. Góc trên cùng bên phải: Nhãn Cập nhật lần cuối (Asia/Ha_Noi) */}
      <div className={styles.topMetaRow}>
        <span className={styles.lastUpdatedTag}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <span>Cập nhật lần cuối: {lastUpdated} (Asia/Ha_Noi)</span>
        </span>
      </div>

      {/* 2. Khối lỗi kết nối (Error Banner - chỉ hiển thị khi gặp lỗi mạng/máy chủ) */}
      {hasConnectionError && (
        <div className={styles.connectionErrorBanner} role="alert">
          <div className={styles.connectionErrorLeft}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <span>Máy chủ tạm thời gián đoạn (Thử lại sau ít phút)</span>
          </div>
          <button
            type="button"
            className={styles.retryConnectBtn}
            onClick={handleRetryConnection}
            disabled={isChecking}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            <span>Thử lại kết nối</span>
          </button>
        </div>
      )}

      {/* 3. DUY NHẤT 1 THẺ CARD TRUNG TÂM ĐẠI DIỆN TRẠNG THÁI HIỆN TẠI */}
      <div className={`${styles.statusCard} ${cardVariantClass}`}>
        {/* ===================================================================
         * BIẾN THỂ 1: ĐANG CHỜ PHÊ DUYỆT / ĐÃ TIẾP NHẬN YÊU CẦU (PENDING - Card viền vàng cam)
         * =================================================================== */}
        {status === 'PENDING' && (
          <>
            <div className={styles.badgeRow}>
              <span className={`${styles.statusBadge} ${styles.badgePending}`}>
                <span className={`${styles.dot} ${styles.dotAmber}`} />
                <span>
                  {isUnverifiedSubmission
                    ? 'Đã tiếp nhận yêu cầu'
                    : 'Đang chờ phê duyệt'}
                </span>
              </span>
            </div>

            <div className={styles.headerBlock}>
              <h1 className={styles.stateTitle}>
                {isUnverifiedSubmission
                  ? 'Yêu cầu đăng ký đã được ghi nhận'
                  : 'Hồ sơ đã được tiếp nhận'}
              </h1>
              <p className={styles.stateDesc}>
                {isUnverifiedSubmission
                  ? 'Nếu thông tin đăng ký hợp lệ và email chưa tồn tại trên hệ thống, Quản trị viên sẽ xem xét phê duyệt tài khoản của bạn trước khi cấp quyền truy cập POS.'
                  : 'Tài khoản chưa được kích hoạt quyền truy cập vào các tính năng bán hàng hoặc kho. Quản trị viên đang xem xét hồ sơ của bạn.'}
              </p>
            </div>

            <div className={styles.infoTable}>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Họ tên</span>
                <span className={styles.infoValue}>{profile.fullName}</span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Email đăng ký</span>
                <span className={styles.infoValue}>{profile.email}</span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Thời điểm gửi</span>
                <span className={styles.infoValue}>{profile.submittedAt}</span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Vai trò dự kiến</span>
                <span className={styles.rolePill}>Nhân viên (STAFF)</span>
              </div>
            </div>

            <div className={styles.mailNoteBox}>
              <span className={styles.noteIcon} aria-hidden="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                </svg>
              </span>
              <span>
                {isMockDemoActive
                  ? 'Chế độ Mock Demo: Hệ thống mô phỏng thông báo khi có quyết định từ Quản trị viên.'
                  : 'Vì lý do bảo mật chống dò tìm tài khoản, hệ thống không công khai trạng thái phê duyệt khi chưa đăng nhập. Vui lòng chờ thông báo từ Quản trị viên hoặc thử đăng nhập lại sau.'}
              </span>
            </div>

            <div className={styles.actionButtons}>
              {isMockDemoActive ? (
                <button
                  type="button"
                  className={styles.primaryActionBtn}
                  onClick={handleCheckStatus}
                  disabled={isChecking}
                >
                  {isChecking ? (
                    <>
                      <span className={styles.spinner} aria-hidden="true" />
                      <span>Đang kiểm tra trạng thái (Mock)...</span>
                    </>
                  ) : (
                    <>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="23 4 23 10 17 10" />
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                      </svg>
                      <span>Kiểm tra lại trạng thái (Mock)</span>
                    </>
                  )}
                </button>
              ) : (
                <button
                  type="button"
                  className={styles.primaryActionBtn}
                  onClick={() => navigate('/login')}
                >
                  <span>Thử đăng nhập tại quầy POS</span>
                </button>
              )}

              <button
                type="button"
                className={styles.secondaryActionBtn}
                onClick={() => navigate('/login')}
              >
                <span>Quay lại đăng nhập</span>
              </button>
            </div>
          </>
        )}

        {/* ===================================================================
         * BIẾN THỂ 2: ĐÃ KÍCH HOẠT THÀNH CÔNG (APPROVED - Card viền xanh lá)
         * =================================================================== */}
        {status === 'APPROVED' && (
          <>
            <div className={styles.badgeRow}>
              <span className={`${styles.statusBadge} ${styles.badgeApproved}`}>
                <span className={`${styles.dot} ${styles.dotGreen}`} />
                <span>Đã kích hoạt thành công</span>
              </span>
            </div>

            <div className={styles.headerBlock}>
              <h1 className={styles.stateTitle}>Chào mừng bạn gia nhập!</h1>
              <p className={styles.stateDesc}>
                Quản trị viên đã phê duyệt yêu cầu của bạn. Tài khoản đã sẵn sàng
                đăng nhập để bắt đầu ca làm việc tại quầy POS.
              </p>
            </div>

            <div className={styles.infoTable}>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Họ tên</span>
                <span className={styles.infoValue}>{profile.fullName}</span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Tài khoản</span>
                <span className={styles.infoValue}>{profile.email}</span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Vai trò hệ thống</span>
                <span className={styles.rolePill}>STAFF</span>
              </div>
              <div className={styles.infoRow}>
                <span className={styles.infoLabel}>Quyền hạn</span>
                <span className={styles.infoValue}>
                  Bán hàng POS, tra cứu tồn
                </span>
              </div>
            </div>

            <div className={styles.greenNoteBox}>
              <span className={styles.noteIcon} aria-hidden="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </span>
              <span>
                Bạn có thể sử dụng email và mật khẩu đã đăng ký để đăng nhập ngay
                bây giờ.
              </span>
            </div>

            <div className={styles.actionButtons}>
              <button
                type="button"
                className={styles.primaryActionBtn}
                onClick={() => navigate('/login')}
              >
                <span>Đến trang đăng nhập -&gt;</span>
              </button>
            </div>
          </>
        )}

        {/* ===================================================================
         * BIẾN THỂ 3: YÊU CẦU BỊ TỪ CHỐI (REJECTED - Card viền đỏ)
         * =================================================================== */}
        {status === 'REJECTED' && (
          <>
            <div className={styles.badgeRow}>
              <span className={`${styles.statusBadge} ${styles.badgeRejected}`}>
                <span className={`${styles.dot} ${styles.dotRed}`} />
                <span>Yêu cầu bị từ chối</span>
              </span>
            </div>

            <div className={styles.headerBlock}>
              <h1 className={styles.stateTitle}>Hồ sơ chưa được phê duyệt</h1>
              <p className={styles.stateDesc}>
                Yêu cầu cấp quyền chưa được duyệt dựa trên quy định quản lý nhân
                sự của cửa hàng.
              </p>
            </div>

            {/* Khung lý do từ chối viền đứt màu đỏ nhạt */}
            <div className={styles.rejectReasonBox}>
              <span className={styles.rejectReasonLabel}>
                Lý do từ Quản trị viên:
              </span>
              <p className={styles.rejectReasonText}>{profile.rejectReason}</p>
            </div>

            {/* Mục Gửi lại yêu cầu (2 trạng thái con: Tạm khóa 24h & Đủ điều kiện) */}
            <div className={styles.resubmitSection}>
              {rejectSubState === 'LOCKED_24H' ? (
                <>
                  <div className={styles.resubmitHeader}>
                    <span className={styles.resubmitTitle}>
                      Gửi lại yêu cầu xét duyệt
                    </span>
                    <span className={styles.subBadgeLocked}>Tạm khóa</span>
                  </div>
                  <p className={styles.resubmitDesc}>
                    Để tránh quá tải hệ thống phê duyệt (Rate Limit), mỗi tài
                    khoản chỉ được phép gửi lại yêu cầu sau 24 giờ kể từ thời điểm
                    từ chối.
                  </p>
                  <div className={styles.cooldownTag}>
                    Có thể gửi lại sau: 15:20 - 08/11/2026 (Asia/Ha_Noi)
                  </div>
                  <button
                    type="button"
                    className={styles.primaryActionBtn}
                    disabled
                  >
                    <span>Gửi lại yêu cầu</span>
                  </button>
                </>
              ) : (
                <>
                  <div className={styles.resubmitHeader}>
                    <span className={styles.resubmitTitle}>
                      Gửi lại yêu cầu xét duyệt
                    </span>
                    <span className={styles.subBadgeEligible}>Đủ điều kiện</span>
                  </div>
                  <p className={styles.resubmitDesc}>
                    Thời gian chờ 24 giờ đã hoàn tất. Vui lòng xác minh quyền kiểm
                    soát tài khoản trước khi gửi lại hồ sơ cho Quản trị viên.
                  </p>
                  <button
                    type="button"
                    className={`${styles.verifyControlBtn} ${
                      isAccountVerified ? styles.verifyControlActive : ''
                    }`}
                    onClick={() => {
                      setIsAccountVerified((prev) => {
                        const next = !prev;
                        if (next) {
                          toast.success(
                            'Đã xác minh quyền kiểm soát tài khoản thành công.'
                          );
                        }
                        return next;
                      });
                    }}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    </svg>
                    <span>
                      {isAccountVerified
                        ? 'Đã xác minh quyền kiểm soát tài khoản ✓'
                        : 'Xác minh quyền kiểm soát tài khoản'}
                    </span>
                  </button>

                  <button
                    type="button"
                    className={styles.primaryActionBtn}
                    onClick={handleResubmitRequest}
                    disabled={isChecking}
                  >
                    {isChecking ? (
                      <>
                        <span className={styles.spinner} aria-hidden="true" />
                        <span>Đang gửi lại yêu cầu...</span>
                      </>
                    ) : (
                      <span>Gửi lại yêu cầu xét duyệt</span>
                    )}
                  </button>
                </>
              )}
            </div>

            <div className={styles.actionButtons}>
              <button
                type="button"
                className={styles.secondaryActionBtn}
                onClick={() =>
                  toast.info(
                    'Vui lòng liên hệ trực tiếp Cửa hàng trưởng hoặc Quản trị viên ca trực để được hỗ trợ.'
                  )
                }
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                </svg>
                <span>Liên hệ Quản trị viên</span>
              </button>
            </div>
          </>
        )}
      </div>

    </div>
  );
}
