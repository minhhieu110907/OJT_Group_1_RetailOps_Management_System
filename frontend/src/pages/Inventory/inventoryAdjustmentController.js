/**
 * Status constants for Inventory Adjustment lifecycle
 */
export const ADJUSTMENT_STATUS = Object.freeze({
  IDLE: 'IDLE',
  SUBMITTING: 'SUBMITTING',
  STALE_VERSION: 'STALE_VERSION',
  AMBIGUOUS: 'AMBIGUOUS',
  RECONCILING: 'RECONCILING',
});

/**
 * Classifies an adjustment error response.
 * @param {any} err Axios error or standard Error
 * @returns {{ type: 'STALE_VERSION' | 'AMBIGUOUS' | 'CONFIRMED_ERROR', details: any, message: string }}
 */
export function classifyAdjustmentError(err) {
  const errStatus = err?.response?.status;
  const errCode = err?.response?.data?.code;

  if (errStatus === 409 && errCode === 'STALE_STOCK_VERSION') {
    return {
      type: ADJUSTMENT_STATUS.STALE_VERSION,
      details: err?.response?.data?.details || {},
      message: err?.response?.data?.message || 'Phiên bản tồn kho đã thay đổi trên máy chủ.',
    };
  }

  // Ambiguous: Network drop, timeout (ECONNABORTED), or Server 500 error after mutation dispatch
  const isNetworkOrTimeout = !err?.response || err?.code === 'ECONNABORTED';
  const isServerError = typeof errStatus === 'number' && errStatus >= 500;

  if (isNetworkOrTimeout || isServerError) {
    return {
      type: ADJUSTMENT_STATUS.AMBIGUOUS,
      details: {},
      message:
        'Kết nối máy chủ bị gián đoạn, quá thời gian chờ hoặc máy chủ gặp sự cố trong khi xử lý yêu cầu. Kết quả điều chỉnh chưa thể xác minh trên hệ thống. Vui lòng đối soát dữ liệu tồn kho authoritative trước khi thực hiện giao dịch mới.',
    };
  }

  return {
    type: 'CONFIRMED_ERROR',
    details: {},
    message: err?.response?.data?.message || err?.message || 'Không thể điều chỉnh tồn kho.',
  };
}

/**
 * Determines whether the user is permitted to submit a new adjustment POST.
 * Blocks during submitting, reconciling, ambiguous, and stale version states.
 * Also checks No-op vs valid input.
 */
export function canSubmitAdjustment({
  status,
  isValidCounted,
  isReasonValid,
  delta,
}) {
  // If in any non-idle state (submitting, stale, ambiguous, reconciling), submission is locked
  if (status !== ADJUSTMENT_STATUS.IDLE) {
    return false;
  }

  if (!isValidCounted) {
    return false;
  }

  // No-op (delta === 0) allows submission to trigger toast and close without forcing 10-char reason
  if (delta === 0) {
    return true;
  }

  return isReasonValid;
}

/**
 * Pure transition handler for adjustment modal state.
 */
export function reduceAdjustmentState(state, action) {
  switch (action.type) {
    case 'START_SUBMIT':
      return {
        ...state,
        status: ADJUSTMENT_STATUS.SUBMITTING,
        errorMessage: '',
      };

    case 'SUBMIT_STALE_VERSION':
      return {
        ...state,
        status: ADJUSTMENT_STATUS.STALE_VERSION,
        conflictData: action.payload,
        errorMessage: '',
      };

    case 'SUBMIT_AMBIGUOUS':
      return {
        ...state,
        status: ADJUSTMENT_STATUS.AMBIGUOUS,
        conflictData: null,
        errorMessage: action.payload.message,
        ambiguousIntent: action.payload.intent,
        reconciledResult: null,
      };

    case 'SUBMIT_CONFIRMED_ERROR':
      return {
        ...state,
        status: ADJUSTMENT_STATUS.IDLE,
        conflictData: null,
        errorMessage: action.payload.message,
      };

    case 'START_RELOAD':
      return {
        ...state,
        status: ADJUSTMENT_STATUS.RECONCILING,
        errorMessage: '',
      };

    case 'RELOAD_SUCCESS':
      return {
        ...state,
        status: ADJUSTMENT_STATUS.IDLE,
        conflictData: null,
        errorMessage: '',
        reconciledResult: action.payload.reconciledResult || null,
        ambiguousIntent: null,
      };

    case 'RELOAD_FAILURE':
      // Preserve current status (AMBIGUOUS or STALE_VERSION)
      return {
        ...state,
        status: state.status === ADJUSTMENT_STATUS.RECONCILING ? action.payload.previousStatus : state.status,
        errorMessage: action.payload.errorMessage,
      };

    case 'RESET_PRODUCT':
      return {
        status: ADJUSTMENT_STATUS.IDLE,
        conflictData: null,
        errorMessage: '',
        ambiguousIntent: null,
        reconciledResult: null,
      };

    default:
      return state;
  }
}
