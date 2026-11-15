export const VN_TIMEZONE = 'Asia/Ho_Chi_Minh';
export const STAFF_CANCEL_WINDOW_MS = 15 * 60 * 1000;

/**
 * Format an ISO timestamp in Asia/Ho_Chi_Minh timezone (HH:mm:ss - dd/MM/yyyy).
 */
export function formatOrderDateTimeVN(isoString) {
  if (!isoString) return '—';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return '—';

  const timePart = new Intl.DateTimeFormat('vi-VN', {
    timeZone: VN_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);

  const datePart = new Intl.DateTimeFormat('vi-VN', {
    timeZone: VN_TIMEZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);

  return `${timePart} • ${datePart}`;
}

/**
 * Format short HH:mm in Asia/Ho_Chi_Minh timezone.
 */
export function formatOrderTimeShortVN(isoString) {
  if (!isoString) return '—';
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return '—';

  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: VN_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

/**
 * Normalize order search query so "#108" or " #108 " sends "108" to match numeric order_id on backend.
 */
export function normalizeOrderSearchQuery(rawSearch) {
  if (typeof rawSearch !== 'string') return '';
  const trimmed = rawSearch.trim();
  if (!trimmed) return '';
  const hashDigitsMatch = /^#(\d+)$/.exec(trimmed);
  if (hashDigitsMatch) {
    return hashDigitsMatch[1];
  }
  return trimmed;
}

/**
 * Format table created-time label in Asia/Ho_Chi_Minh timezone.
 * If same VN business day and within 60 minutes, includes "(X phút trước)".
 */
export function formatOrderCreatedCellVN(isoString, nowMs = Date.now()) {
  if (!isoString) return { primary: '—', secondary: '' };
  const date = new Date(isoString);
  const soldMs = date.getTime();
  if (Number.isNaN(soldMs)) return { primary: '—', secondary: '' };

  const timeShort = formatOrderTimeShortVN(isoString);
  const sameDay =
    getVietnamBusinessDateKey(soldMs) === getVietnamBusinessDateKey(nowMs);

  if (sameDay) {
    const diffMinutes = Math.floor((nowMs - soldMs) / 60000);
    if (diffMinutes >= 0 && diffMinutes < 1) {
      return { primary: timeShort, secondary: '(Vừa xong)' };
    }
    if (diffMinutes >= 1 && diffMinutes < 60) {
      return { primary: timeShort, secondary: `(${diffMinutes} phút trước)` };
    }
    return { primary: timeShort, secondary: '' };
  }

  const datePart = new Intl.DateTimeFormat('vi-VN', {
    timeZone: VN_TIMEZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);

  return { primary: timeShort, secondary: datePart };
}

/**
 * Return YYYY-MM-DD business date key in Asia/Ho_Chi_Minh timezone.
 */
export function getVietnamBusinessDateKey(dateInput = new Date()) {
  const date = dateInput instanceof Date ? dateInput : new Date(dateInput);
  if (Number.isNaN(date.getTime())) return '';

  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: VN_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);

  const map = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${map.year}-${map.month}-${map.day}`;
}

/**
 * UI-level cancel eligibility check (mirrors backend policy; backend remains authoritative):
 * - Only COMPLETED orders can be cancelled.
 * - ADMIN: same Asia/Ho_Chi_Minh business day.
 * - STAFF: same Asia/Ho_Chi_Minh business day, own order (created_by === user.id), within 15 minutes of sold_at.
 */
export function evaluateCancelOrderEligibility({
  order,
  user,
  nowMs = Date.now(),
}) {
  if (!order || !user) {
    return { canCancel: false, reason: 'MISSING_CONTEXT', remainingMinutes: 0 };
  }

  if (order.status !== 'COMPLETED') {
    return { canCancel: false, reason: 'NOT_COMPLETED', remainingMinutes: 0 };
  }

  const soldMs = Date.parse(order.sold_at || '');
  if (!Number.isFinite(soldMs)) {
    return { canCancel: false, reason: 'INVALID_SOLD_AT', remainingMinutes: 0 };
  }

  const sameBusinessDay =
    getVietnamBusinessDateKey(soldMs) === getVietnamBusinessDateKey(nowMs);
  if (!sameBusinessDay) {
    return { canCancel: false, reason: 'DIFFERENT_BUSINESS_DAY', remainingMinutes: 0 };
  }

  if (user.role === 'ADMIN') {
    return { canCancel: true, reason: null, remainingMinutes: null };
  }

  if (order.created_by !== user.id) {
    return { canCancel: false, reason: 'NOT_OWNER', remainingMinutes: 0 };
  }

  const elapsedMs = nowMs - soldMs;
  if (elapsedMs < 0 || elapsedMs > STAFF_CANCEL_WINDOW_MS) {
    return { canCancel: false, reason: 'WINDOW_EXPIRED', remainingMinutes: 0 };
  }

  const remainingMinutes = Math.max(
    1,
    Math.ceil((STAFF_CANCEL_WINDOW_MS - elapsedMs) / 60000)
  );
  return { canCancel: true, reason: null, remainingMinutes };
}

/**
 * Classify POST /orders/{id}/cancel errors into:
 * - 'INELIGIBLE' (Lỗi 1: Không đủ điều kiện hủy đơn — 403 or 409 policy refusal)
 * - 'DATA_CHANGED' (Lỗi 2: Dữ liệu đơn hàng bị thay đổi — 409 already cancelled / state changed)
 * - 'AMBIGUOUS' (timeout / network drop / 5xx / REQUEST_IN_PROGRESS)
 * - 'DEFINITE_FAILURE' (validation / 401 replay block / other 4xx)
 */
export function classifyCancelOrderError(error) {
  if (!error) {
    return {
      outcome: 'DEFINITE_FAILURE',
      message: 'Không thể hủy đơn hàng. Vui lòng thử lại.',
    };
  }

  if (
    error.isClientValidation ||
    error.code === 'ERR_MOCK_NOT_SUPPORTED' ||
    error.isReplayBlocked ||
    error.code === 'ERR_UNSAFE_MUTATION_REPLAY'
  ) {
    return {
      outcome: 'DEFINITE_FAILURE',
      message:
        error.isReplayBlocked || error.code === 'ERR_UNSAFE_MUTATION_REPLAY'
          ? 'Phiên đăng nhập vừa hết hạn nên hệ thống không tự gửi lại yêu cầu hủy đơn. Vui lòng thử lại.'
          : error.message || 'Dữ liệu yêu cầu hủy đơn không hợp lệ.',
    };
  }

  const status = error.response?.status;
  const apiCode = error.response?.data?.code || '';
  const apiMessage = error.response?.data?.message || '';
  const apiDetails = error.response?.data?.details || null;

  if (apiCode === 'REQUEST_IN_PROGRESS') {
    return {
      outcome: 'AMBIGUOUS',
      apiCode,
      message:
        apiMessage ||
        'Yêu cầu hủy đơn trước vẫn đang được máy chủ xử lý. Vui lòng kiểm tra lại trạng thái đơn hàng.',
    };
  }

  if (
    !error.response ||
    error.code === 'ECONNABORTED' ||
    error.code === 'ETIMEDOUT' ||
    error.code === 'ERR_NETWORK' ||
    (typeof status === 'number' && status >= 500)
  ) {
    return {
      outcome: 'AMBIGUOUS',
      apiCode,
      message:
        'Chưa xác định được kết quả hủy đơn do mất kết nối hoặc quá thời gian chờ. Vui lòng kiểm tra lại trạng thái đơn.',
    };
  }

  // Lỗi 2: Dữ liệu đơn hàng bị thay đổi (đã hủy ở thiết bị / cửa sổ khác)
  if (
    status === 409 &&
    (apiCode === 'INVALID_STATE' ||
      apiCode === 'ORDER_ALREADY_CANCELLED' ||
      apiCode === 'INVALID_ORDER_STATE' ||
      apiCode === 'ORDER_STATE_CONFLICT' ||
      apiCode === 'CONFLICT')
  ) {
    return {
      outcome: 'DATA_CHANGED',
      apiCode,
      details: apiDetails,
      message:
        apiMessage ||
        'Đơn hàng đã được hủy trước đó ở phiên làm việc khác. Tồn kho chỉ được hoàn trả một lần duy nhất.',
    };
  }

  // Lỗi 1: Không đủ điều kiện hủy đơn (403 Forbidden hoặc 409 quá hạn 15 phút / khác ngày / khác người tạo)
  if (
    (status === 403 && apiCode !== 'CSRF_REJECTED') ||
    (status === 409 &&
      (apiCode === 'CANCEL_WINDOW_EXPIRED' ||
        apiCode === 'CANCEL_NOT_ALLOWED' ||
        apiCode === 'DIFFERENT_BUSINESS_DAY' ||
        apiCode === 'FORBIDDEN'))
  ) {
    return {
      outcome: 'INELIGIBLE',
      apiCode,
      details: apiDetails,
      message:
        apiMessage ||
        'Đơn hàng đã quá hạn 15 phút cho phép nhân viên hủy trực tiếp hoặc không thuộc quyền hủy của tài khoản hiện tại.',
    };
  }

  return {
    outcome: 'DEFINITE_FAILURE',
    apiCode,
    details: apiDetails,
    message:
      apiMessage ||
      error.message ||
      'Không thể hủy đơn hàng. Vui lòng kiểm tra lại.',
  };
}
