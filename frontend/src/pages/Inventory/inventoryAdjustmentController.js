/**
 * Status constants for Inventory Adjustment lifecycle
 */
export const ADJUSTMENT_STATUS = Object.freeze({
  IDLE: 'IDLE',
  SUBMITTING: 'SUBMITTING',
  STALE_VERSION: 'STALE_VERSION',
  AMBIGUOUS: 'AMBIGUOUS',
  RECONCILING: 'RECONCILING',
  AWAITING_ACKNOWLEDGEMENT: 'AWAITING_ACKNOWLEDGEMENT',
});

/**
 * Centralized close guard for the adjustment modal.
 * Pure logic determining if the modal can safely be closed/dismissed.
 * Blocks during SUBMITTING, RECONCILING, AMBIGUOUS, and AWAITING_ACKNOWLEDGEMENT.
 *
 * @param {string} status Current ADJUSTMENT_STATUS
 * @param {any} pendingIntent Active ambiguous intent
 * @returns {boolean} True if the modal is safe to close/dismiss
 */
export function canCloseAdjustmentModal(status, pendingIntent) {
  if (status === ADJUSTMENT_STATUS.SUBMITTING) {
    return false;
  }
  if (status === ADJUSTMENT_STATUS.AMBIGUOUS || Boolean(pendingIntent)) {
    return false;
  }
  if (status === ADJUSTMENT_STATUS.RECONCILING) {
    return false;
  }
  if (status === ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT) {
    return false;
  }
  return true;
}

/**
 * Checks whether an adjustment session currently has an active ambiguous or unacknowledged intent
 * that requires lifecycle protection (e.g. blocking navigation or preserving across unmount).
 *
 * @param {string} status Current ADJUSTMENT_STATUS
 * @param {any} pendingIntent Active ambiguous intent object
 * @returns {boolean}
 */
export function hasUnresolvedAdjustmentIntent(status, pendingIntent) {
  if (status === ADJUSTMENT_STATUS.SUBMITTING) return true;
  if (status === ADJUSTMENT_STATUS.AMBIGUOUS || Boolean(pendingIntent)) return true;
  if (status === ADJUSTMENT_STATUS.RECONCILING && Boolean(pendingIntent)) return true;
  if (status === ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT) return true;
  return false;
}

/**
 * Validates authoritative product inventory response from GET /inventory/{id}.
 * Strictly fail-closed.
 *
 * @param {any} data Response object from server
 * @param {number} expectedProductId Expected product ID
 * @returns {boolean}
 */
export function isValidAuthoritativeInventory(data, expectedProductId) {
  if (!data || typeof data !== 'object') {
    return false;
  }
  if (data.product_id !== expectedProductId) {
    return false;
  }
  if (
    typeof data.quantity !== 'number' ||
    !Number.isInteger(data.quantity) ||
    data.quantity < 0 ||
    data.quantity > 2147483647
  ) {
    return false;
  }
  if (
    typeof data.stock_version !== 'number' ||
    !Number.isInteger(data.stock_version) ||
    data.stock_version < 0
  ) {
    return false;
  }
  return true;
}

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
 * Blocks during submitting, reconciling, ambiguous, awaiting acknowledgement, and stale version states.
 * Also checks No-op vs valid input.
 */
export function canSubmitAdjustment({
  status,
  isValidCounted,
  isReasonValid,
  delta,
}) {
  // If in any non-idle state (submitting, stale, ambiguous, reconciling, awaiting_acknowledgement), submission is locked
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
 * Initial state factory for adjustment modal state.
 */
export function createInitialAdjustmentState() {
  return {
    status: ADJUSTMENT_STATUS.IDLE,
    errorMessage: '',
    conflictData: null,
    ambiguousIntent: null,
    reconciledResult: null,
  };
}

/**
 * Pure transition handler for adjustment modal state.
 * Used directly by InventoryAdjustModal and test suites.
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

    case 'RELOAD_SUCCESS': {
      const fromAmbiguous =
        state.status === ADJUSTMENT_STATUS.AMBIGUOUS ||
        action.payload.previousStatus === ADJUSTMENT_STATUS.AMBIGUOUS ||
        Boolean(state.ambiguousIntent);

      if (fromAmbiguous) {
        // Must gate with AWAITING_ACKNOWLEDGEMENT before unlocking to IDLE
        return {
          ...state,
          status: ADJUSTMENT_STATUS.AWAITING_ACKNOWLEDGEMENT,
          conflictData: null,
          errorMessage: '',
          reconciledResult: action.payload.reconciledResult,
          // Retain ambiguousIntent until user explicitly acknowledges
          ambiguousIntent: state.ambiguousIntent,
        };
      }

      // If came from STALE_VERSION, valid reload clears conflict and returns to IDLE
      return {
        ...state,
        status: ADJUSTMENT_STATUS.IDLE,
        conflictData: null,
        errorMessage: '',
        reconciledResult: action.payload.reconciledResult || null,
        ambiguousIntent: null,
      };
    }

    case 'RELOAD_FAILURE':
      // Preserve current status (AMBIGUOUS or STALE_VERSION) and retain all drafts & intents
      return {
        ...state,
        status:
          state.status === ADJUSTMENT_STATUS.RECONCILING
            ? action.payload.previousStatus
            : state.status,
        errorMessage: action.payload.errorMessage,
      };

    case 'ACKNOWLEDGE_RECONCILIATION':
      return {
        ...state,
        status: ADJUSTMENT_STATUS.IDLE,
        ambiguousIntent: null,
        reconciledResult: null,
        errorMessage: '',
      };

    case 'RESET_PRODUCT':
      return createInitialAdjustmentState();

    default:
      return state;
  }
}

