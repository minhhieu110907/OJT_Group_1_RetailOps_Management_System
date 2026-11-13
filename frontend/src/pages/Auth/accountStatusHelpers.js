/**
 * Pure behavioral helpers for AccountStatus.jsx to ensure Real API mode
 * never trusts location.state as verification/eligibility proof, never
 * defaults to a fake 24h lock without Backend data, and never fakes
 * account control verification.
 */

export function deriveRejectSubState({ isMockDemoActive, incomingState }) {
  if (!isMockDemoActive) {
    return 'UNAVAILABLE';
  }
  return incomingState?.rejectSubState === 'ELIGIBLE' ? 'ELIGIBLE' : 'LOCKED_24H';
}

export function evaluateAccountVerificationClick({
  isMockDemoActive,
  prevVerified,
}) {
  if (!isMockDemoActive) {
    return {
      nextVerified: false,
      toastType: 'info',
      message:
        'Chế độ Real API chưa hỗ trợ xác minh trực tuyến tại trang này. Vui lòng liên hệ Quản trị viên để được hỗ trợ mở lại hồ sơ.',
    };
  }

  const nextVerified = !prevVerified;
  if (nextVerified) {
    return {
      nextVerified: true,
      toastType: 'success',
      message:
        'Đã xác minh quyền kiểm soát tài khoản thành công (Chế độ Mock Demo).',
    };
  }

  return {
    nextVerified: false,
    toastType: null,
    message: null,
  };
}

export function evaluateResubmitAction({
  isMockDemoActive,
  isAccountVerified,
}) {
  if (!isMockDemoActive) {
    return {
      allowed: false,
      nextStatus: null,
      toastType: 'info',
      message:
        'Chức năng gửi lại yêu cầu tự động thuộc phạm vi phát triển tiếp theo. Vui lòng liên hệ Quản trị viên để được mở lại hồ sơ.',
    };
  }

  if (!isAccountVerified) {
    return {
      allowed: false,
      nextStatus: null,
      toastType: 'warning',
      message:
        'Vui lòng bấm "Xác minh quyền kiểm soát tài khoản" trước khi gửi lại yêu cầu.',
    };
  }

  return {
    allowed: true,
    nextStatus: 'PENDING',
    toastType: 'success',
    message:
      'Đã gửi lại yêu cầu xét duyệt hồ sơ thành công (Chế độ Mock Demo)!',
  };
}
