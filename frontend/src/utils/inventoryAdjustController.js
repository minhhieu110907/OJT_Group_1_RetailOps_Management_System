import {
  MAX_STOCK_QUANTITY,
  generateSecureIdempotencyKey,
  inventoryApi,
} from '../api/inventoryApi.js';
import { getApiErrorMessage } from '../api/axiosClient.js';

/**
 * Các trạng thái điều phối của Inventory Adjust Modal (FSM light)
 */
export const ADJUST_MODAL_STATES = Object.freeze({
  IDLE: 'IDLE',
  SUBMITTING: 'SUBMITTING',
  STALE_VERSION: 'STALE_VERSION',
  AMBIGUOUS: 'AMBIGUOUS',
  RECONCILING: 'RECONCILING',
});

/**
 * Phân loại kết quả/lỗi từ API POST /inventory/{product_id}/adjustments
 * Trả về:
 * - 'SUCCESS': mutation đã hoàn tất
 * - 'STALE_VERSION': 409 STALE_STOCK_VERSION
 * - 'AMBIGUOUS': timeout, network failure, ECONNABORTED, 502/503/504 hoặc 500 sau khi request đã gửi
 * - 'DEFINITE_FAILURE': 400, 401, 403, 422...
 */
export function classifyAdjustError(err) {
  if (!err) {
    return {
      type: 'DEFINITE_FAILURE',
      message: 'Lỗi không xác định.',
      details: null,
    };
  }

  const status = err?.response?.status;
  const code = err?.response?.data?.code;

  if (status === 409 && code === 'STALE_STOCK_VERSION') {
    const errorDetails = err?.response?.data?.details || {};
    return {
      type: 'STALE_VERSION',
      expectedVersion: errorDetails.expected_stock_version,
      actualVersion: errorDetails.current_stock_version,
      message: err?.response?.data?.message || 'Phiên bản tồn kho đã thay đổi trên máy chủ.',
      details: errorDetails,
    };
  }

  // Ambiguous network outcome: không có response (network drop), timeout, ECONNABORTED, hoặc gateway 502/503/504
  const isNetworkOrTimeout =
    !err?.response ||
    err?.code === 'ECONNABORTED' ||
    err?.message?.includes?.('timeout') ||
    status === 502 ||
    status === 503 ||
    status === 504;

  if (isNetworkOrTimeout) {
    return {
      type: 'AMBIGUOUS',
      message:
        'Kết nối máy chủ bị gián đoạn hoặc quá thời gian phản hồi. Kết quả điều chỉnh chưa thể xác minh trên hệ thống. ' +
        'Yêu cầu đối soát tồn kho trước khi gửi giao dịch mới.',
      details: err?.response?.data || null,
    };
  }

  return {
    type: 'DEFINITE_FAILURE',
    message: getApiErrorMessage(err, 'Không thể điều chỉnh tồn kho.'),
    details: err?.response?.data || null,
  };
}

/**
 * Kiểm tra xem người dùng có thể gửi yêu cầu điều chỉnh không.
 * Khóa hoàn toàn khi đang SUBMITTING, RECONCILING, AMBIGUOUS (chưa đối soát) hoặc STALE_VERSION.
 */
export function canSubmitAdjustment({
  modalState,
  isValidCounted,
  isReasonValid,
  isNoOp,
}) {
  if (
    modalState === ADJUST_MODAL_STATES.SUBMITTING ||
    modalState === ADJUST_MODAL_STATES.RECONCILING ||
    modalState === ADJUST_MODAL_STATES.AMBIGUOUS ||
    modalState === ADJUST_MODAL_STATES.STALE_VERSION
  ) {
    return false;
  }

  if (isNoOp) return true;
  return Boolean(isValidCounted && isReasonValid);
}

/**
 * Controller thuần túy xử lý Submit Adjustment
 * Dùng trực tiếp bởi InventoryAdjustModal và Test suite
 */
export async function executeAdjustmentSubmit({
  product,
  countedQty,
  reason,
  modalState,
  savedIntent,
  onSuccess,
}) {
  const currentQty = Number(product?.quantity) || 0;
  const currentVersion = Number(product?.stock_version) || 0;

  const trimmedQty = String(countedQty || '').trim();
  const parsedCounted = trimmedQty === '' ? NaN : Number(trimmedQty);
  const isValidCounted =
    !Number.isNaN(parsedCounted) &&
    Number.isInteger(parsedCounted) &&
    parsedCounted >= 0 &&
    parsedCounted <= MAX_STOCK_QUANTITY;

  const delta = isValidCounted ? parsedCounted - currentQty : 0;
  const isNoOp = isValidCounted && delta === 0;
  const trimmedReason = String(reason || '').trim();
  const isReasonValid = trimmedReason.length >= 10 && trimmedReason.length <= 250;

  if (!canSubmitAdjustment({ modalState, isValidCounted, isReasonValid, isNoOp })) {
    return {
      executed: false,
      blocked: true,
      reason: 'SUBMISSION_BLOCKED_OR_INVALID',
    };
  }

  if (isNoOp) {
    return {
      executed: true,
      isNoOp: true,
      message: 'Số đếm trùng với tồn kho đang hiển thị. Không có yêu cầu điều chỉnh nào được gửi.',
    };
  }

  // Tạo khóa bảo mật giao dịch (hoặc dùng lại intent nếu có chính sách retry cùng key)
  const intentKey = savedIntent?.idempotencyKey || generateSecureIdempotencyKey();
  const intentPayload = {
    productId: product.product_id,
    countedQuantity: parsedCounted,
    expectedStockVersion: currentVersion,
    reason: trimmedReason,
    idempotencyKey: intentKey,
  };

  try {
    const response = await inventoryApi.adjustInventory(intentPayload);
    if (onSuccess) {
      onSuccess(response);
    }
    return {
      executed: true,
      success: true,
      response,
      nextState: ADJUST_MODAL_STATES.IDLE,
    };
  } catch (err) {
    const classification = classifyAdjustError(err);
    if (classification.type === 'STALE_VERSION') {
      return {
        executed: true,
        success: false,
        nextState: ADJUST_MODAL_STATES.STALE_VERSION,
        conflictData: {
          expectedVersion: classification.expectedVersion ?? currentVersion,
          actualVersion: classification.actualVersion ?? 'Chưa xác định',
          detailsMsg: classification.message,
        },
        errorMessage: '',
      };
    }

    if (classification.type === 'AMBIGUOUS') {
      return {
        executed: true,
        success: false,
        nextState: ADJUST_MODAL_STATES.AMBIGUOUS,
        savedIntent: intentPayload,
        conflictData: null,
        errorMessage: classification.message,
      };
    }

    return {
      executed: true,
      success: false,
      nextState: ADJUST_MODAL_STATES.IDLE,
      conflictData: null,
      errorMessage: classification.message,
    };
  }
}

/**
 * Controller thuần túy xử lý Reload để đối soát authoritative inventory
 * Dùng trực tiếp bởi InventoryAdjustModal và Test suite
 */
export async function executeAdjustmentReload({
  productId,
  onReloadLatest,
}) {
  if (!onReloadLatest || !productId) {
    throw new Error('Thiếu thông tin nạp tồn kho mới nhất.');
  }

  const latest = await onReloadLatest(productId);
  return latest;
}
