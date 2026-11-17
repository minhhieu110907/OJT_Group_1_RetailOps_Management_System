import axiosClient, { getApiErrorMessage } from './axiosClient.js';
import { assertRealApiMode } from './productsApi.js';

export const AI_QUERY_MAX_LENGTH = 4000;
export const AI_QUERY_TIMEOUT_MS = 20000;

/**
 * Validate AIEvidence item from OpenAPI schema:
 * { source: string, period: string | null, summary: string } (additionalProperties: false)
 */
export function validateAiEvidence(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    throw new Error('AIEvidence item must be an object.');
  }
  if (typeof item.source !== 'string' || !item.source.trim()) {
    throw new Error('AIEvidence missing valid source.');
  }
  if (item.period !== null && typeof item.period !== 'string') {
    throw new Error('AIEvidence.period must be string or null.');
  }
  if (typeof item.summary !== 'string' || !item.summary.trim()) {
    throw new Error('AIEvidence missing valid summary.');
  }
  return {
    source: item.source.trim(),
    period: item.period === null ? null : item.period.trim(),
    summary: item.summary.trim(),
  };
}

/**
 * Validate AIAskResponse contract (fail-closed):
 * { answer: string, evidence: AIEvidence[], insufficient_data: boolean }
 */
export function validateAiAskResponse(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('AIAskResponse payload must be an object.');
  }
  if (typeof payload.answer !== 'string' || !payload.answer.trim()) {
    throw new Error('AIAskResponse missing valid answer.');
  }
  if (!Array.isArray(payload.evidence)) {
    throw new Error('AIAskResponse.evidence must be an array.');
  }
  if (typeof payload.insufficient_data !== 'boolean') {
    throw new Error('AIAskResponse.insufficient_data must be a boolean.');
  }

  return {
    answer: payload.answer.trim(),
    evidence: payload.evidence.map(validateAiEvidence),
    insufficient_data: payload.insufficient_data,
  };
}

/**
 * Validate AIAskRequest message before sending to POST /ai/query.
 */
export function validateAiMessageInput(rawMessage) {
  const trimmed = typeof rawMessage === 'string' ? rawMessage.trim() : '';
  if (!trimmed) {
    return {
      isValid: false,
      value: '',
      error: 'Vui lòng nhập câu hỏi kinh doanh trước khi gửi.',
    };
  }
  if (trimmed.length > AI_QUERY_MAX_LENGTH) {
    return {
      isValid: false,
      value: trimmed,
      error: `Câu hỏi không được vượt quá ${AI_QUERY_MAX_LENGTH.toLocaleString('vi-VN')} ký tự.`,
    };
  }
  return {
    isValid: true,
    value: trimmed,
    error: null,
  };
}

/**
 * Map API/network error into canonical AI-04 safe error state.
 * Never exposes internal SQL, secrets, or stack traces.
 */
export function classifyAiError(err) {
  if (err?.isClientValidation) {
    return {
      kind: 'validation',
      status: 422,
      title: 'Câu hỏi chưa hợp lệ',
      message: err.message,
      actionType: 'dismiss',
      retryable: false,
    };
  }

  const status = err?.response?.status ?? null;
  const code = err?.code || '';

  if (status === 401 || status === 403) {
    return {
      kind: 'denied',
      status,
      title: 'Không có quyền truy cập',
      message:
        status === 401
          ? 'Phiên đăng nhập đã hết hạn hoặc chưa được xác thực. Vui lòng đăng nhập lại bằng tài khoản Quản trị viên.'
          : 'Trợ lý AI chỉ dành cho Quản trị viên. Tài khoản hiện tại không được phân quyền truy cập chức năng này.',
      actionType: 'dismiss',
      retryable: false,
    };
  }

  if (status === 429) {
    return {
      kind: 'quota',
      status,
      title: 'Đã đạt giới hạn sử dụng',
      message:
        'Bạn đã gửi quá nhiều yêu cầu trong thời gian ngắn. Vui lòng thử lại sau ít phút.',
      hint: 'Vui lòng thử lại sau ít phút',
      actionType: 'dismiss',
      retryable: false,
    };
  }

  if (
    code === 'ECONNABORTED' ||
    code === 'ETIMEDOUT' ||
    status === 408 ||
    status === 504
  ) {
    return {
      kind: 'timeout',
      status,
      title: 'Quá thời gian chờ',
      message:
        'Yêu cầu vượt quá thời gian phản hồi cho phép nên dữ liệu chưa được tải đầy đủ.',
      actionType: 'retry',
      retryable: true,
    };
  }

  if (status === 400 || status === 422) {
    return {
      kind: 'validation',
      status,
      title: 'Câu hỏi chưa hợp lệ',
      message: getApiErrorMessage(err, 'Câu hỏi không đúng định dạng yêu cầu.'),
      actionType: 'dismiss',
      retryable: false,
    };
  }

  if (status === 503 || status === 502 || status === 404 || !status) {
    return {
      kind: 'unavailable',
      status,
      title: 'Dịch vụ tạm thời không khả dụng',
      message:
        'Hệ thống trợ lý AI đang được bảo trì hoặc kết nối tạm thời bị gián đoạn. Dữ liệu cửa hàng của bạn vẫn an toàn.',
      actionType: 'retry',
      retryable: true,
    };
  }

  return {
    kind: 'error',
    status,
    title: 'Không thể hoàn tất phân tích AI',
    message: getApiErrorMessage(
      err,
      'Đã xảy ra lỗi khi xử lý yêu cầu Trợ lý AI. Vui lòng thử lại.'
    ),
    actionType: 'retry',
    retryable: true,
  };
}

export const aiApi = {
  /**
   * POST /api/v1/ai/query (Real API only, ADMIN-only)
   */
  async ask({ isMockMode = false, message, signal } = {}) {
    assertRealApiMode(isMockMode);

    const check = validateAiMessageInput(message);
    if (!check.isValid) {
      const validationErr = new Error(check.error);
      validationErr.isClientValidation = true;
      throw validationErr;
    }

    const response = await axiosClient.post(
      '/ai/query',
      { message: check.value },
      {
        signal,
        timeout: AI_QUERY_TIMEOUT_MS,
      }
    );

    return validateAiAskResponse(response.data);
  },
};
