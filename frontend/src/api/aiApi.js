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
      retryable: false,
    };
  }

  const status = err?.response?.status ?? null;
  const code = err?.code || '';

  if (status === 401 || status === 403) {
    return {
      kind: 'denied',
      status,
      title: 'Không có quyền truy cập Trợ lý AI',
      message:
        status === 401
          ? 'Phiên đăng nhập đã hết hạn hoặc chưa được xác thực. Vui lòng đăng nhập lại bằng tài khoản ADMIN.'
          : 'Chỉ tài khoản Quản trị viên (ADMIN) mới được phép sử dụng Trợ lý AI.',
      retryable: false,
    };
  }

  if (status === 429) {
    return {
      kind: 'quota',
      status,
      title: 'Vượt giới hạn lượt hỏi tạm thời',
      message:
        getApiErrorMessage(err, '') ||
        'Hệ thống Trợ lý AI đang tạm giới hạn tần suất truy vấn (HTTP 429). Vui lòng đợi ít phút rồi thử lại.',
      retryable: true,
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
      title: 'Yêu cầu phân tích AI quá thời gian chờ',
      message:
        'Truy vấn vượt quá thời gian xử lý cho phép. Vui lòng thử đặt câu hỏi ngắn gọn, rõ khoảng thời gian hơn hoặc thử lại.',
      retryable: true,
    };
  }

  if (status === 400 || status === 422) {
    return {
      kind: 'validation',
      status,
      title: 'Dữ liệu câu hỏi không hợp lệ',
      message: getApiErrorMessage(err, 'Câu hỏi không đúng định dạng yêu cầu.'),
      retryable: false,
    };
  }

  if (status === 503 || status === 502 || status === 404 || !status) {
    return {
      kind: 'unavailable',
      status,
      title: 'Dịch vụ Trợ lý AI tạm thời chưa sẵn sàng',
      message:
        status === 404
          ? 'Endpoint Trợ lý AI (/api/v1/ai/query) chưa được kích hoạt trên máy chủ Backend.'
          : 'Không thể kết nối tới dịch vụ Trợ lý AI lúc này. Vui lòng thử lại sau.',
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
