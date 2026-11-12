import axiosClient from './axiosClient.js';
import {
  assertRealApiMode,
  isValidIsoTimestamp,
  validatePaginatedResponse,
} from './productsApi.js';

export const ALLOWED_APPROVAL_STATUSES = ['PENDING', 'APPROVED', 'REJECTED'];

/**
 * Strictly parse a positive integer approval request ID from URL/query params.
 * Returns positive integer or null if invalid.
 */
export function parsePositiveApprovalId(rawValue) {
  if (typeof rawValue === 'number') {
    return Number.isSafeInteger(rawValue) && rawValue > 0 ? rawValue : null;
  }
  if (typeof rawValue !== 'string') {
    return null;
  }
  const trimmed = rawValue.trim();
  if (!/^[1-9]\d*$/.test(trimmed)) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/**
 * Validate a single ApprovalRead DTO from FastAPI Backend (/api/v1/staff-approvals).
 * Contract (backend/app/modules/auth/schemas.py):
 * - id: positive integer (> 0)
 * - user_id: positive integer (> 0)
 * - attempt_no: positive integer (>= 1)
 * - status: 'PENDING' | 'APPROVED' | 'REJECTED'
 * - requested_at: valid UTC ISO-8601 timestamp string
 * - decided_by: null or positive integer (> 0)
 * - decided_at: null or valid UTC ISO-8601 timestamp string
 * - decision_reason: null or string
 */
export function validateApprovalRead(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    throw new Error('ApprovalRead payload must be a non-null object.');
  }

  if (
    typeof item.id !== 'number' ||
    !Number.isInteger(item.id) ||
    item.id <= 0
  ) {
    throw new Error(
      `Schema violation: ApprovalRead missing valid positive integer id: ${JSON.stringify(item.id)}`
    );
  }

  if (
    typeof item.user_id !== 'number' ||
    !Number.isInteger(item.user_id) ||
    item.user_id <= 0
  ) {
    throw new Error(
      `Schema violation: ApprovalRead #${item.id} missing valid positive integer user_id: ${JSON.stringify(item.user_id)}`
    );
  }

  if (
    typeof item.attempt_no !== 'number' ||
    !Number.isInteger(item.attempt_no) ||
    item.attempt_no < 1
  ) {
    throw new Error(
      `Schema violation: ApprovalRead #${item.id} missing valid attempt_no: ${JSON.stringify(item.attempt_no)}`
    );
  }

  if (!ALLOWED_APPROVAL_STATUSES.includes(item.status)) {
    throw new Error(
      `Schema violation: ApprovalRead #${item.id} has invalid status: ${JSON.stringify(item.status)}`
    );
  }

  if (!isValidIsoTimestamp(item.requested_at)) {
    throw new Error(
      `Schema violation: ApprovalRead #${item.id} has invalid requested_at timestamp: ${JSON.stringify(item.requested_at)}`
    );
  }

  if (
    item.decided_by !== null &&
    (typeof item.decided_by !== 'number' ||
      !Number.isInteger(item.decided_by) ||
      item.decided_by <= 0)
  ) {
    throw new Error(
      `Schema violation: ApprovalRead #${item.id} has invalid decided_by: ${JSON.stringify(item.decided_by)}`
    );
  }

  if (item.decided_at !== null && !isValidIsoTimestamp(item.decided_at)) {
    throw new Error(
      `Schema violation: ApprovalRead #${item.id} has invalid decided_at timestamp: ${JSON.stringify(item.decided_at)}`
    );
  }

  if (
    item.decision_reason !== null &&
    typeof item.decision_reason !== 'string'
  ) {
    throw new Error(
      `Schema violation: ApprovalRead #${item.id} has invalid decision_reason: ${JSON.stringify(item.decision_reason)}`
    );
  }

  return {
    id: item.id,
    user_id: item.user_id,
    attempt_no: item.attempt_no,
    status: item.status,
    requested_at: item.requested_at,
    decided_by: item.decided_by,
    decided_at: item.decided_at,
    decision_reason: item.decision_reason,
  };
}

/**
 * Validate a single ApprovalListItemRead DTO from GET /api/v1/staff-approvals.
 * Contract (backend/app/modules/auth/schemas.py & contracts/openapi.yaml):
 * Extends ApprovalRead with required `email` (from users.email_normalized).
 * Note: POST /approve and POST /reject return ApprovalRead (without email).
 */
export function validateApprovalListItemRead(item) {
  const base = validateApprovalRead(item);

  if (typeof item.email !== 'string' || !item.email.trim().includes('@')) {
    throw new Error(
      `Schema violation: ApprovalListItemRead #${item.id} missing valid email: ${JSON.stringify(item.email)}`
    );
  }

  return {
    ...base,
    email: item.email.trim(),
  };
}

/**
 * Derive 2-letter avatar initials from a Staff email address (e.g. "binh.nv@retailops.vn" -> "BN").
 */
export function getEmailInitials(email) {
  if (typeof email !== 'string' || !email.trim()) {
    return 'NV';
  }
  const localPart = email.trim().split('@')[0] || '';
  const tokens = localPart.split(/[._-]+/).filter(Boolean);
  if (tokens.length >= 2) {
    return `${tokens[0][0]}${tokens[tokens.length - 1][0]}`.toUpperCase();
  }
  if (localPart.length >= 2) {
    return localPart.slice(0, 2).toUpperCase();
  }
  if (localPart.length === 1) {
    return localPart.toUpperCase();
  }
  return 'NV';
}

/**
 * Validate rejection reason according to RejectRequest schema (1..500 non-whitespace chars).
 */
export function validateRejectReason(reason) {
  if (typeof reason !== 'string') {
    return {
      isValid: false,
      normalized: '',
      error: 'Vui lòng nhập lý do từ chối hồ sơ.',
    };
  }
  const normalized = reason.trim();
  if (normalized.length < 1) {
    return {
      isValid: false,
      normalized: '',
      error: 'Lý do từ chối không được để trống hoặc chỉ chứa khoảng trắng.',
    };
  }
  if (normalized.length > 500) {
    return {
      isValid: false,
      normalized,
      error: 'Lý do từ chối không được vượt quá 500 ký tự.',
    };
  }
  return {
    isValid: true,
    normalized,
    error: '',
  };
}

/**
 * Format UTC ISO-8601 timestamp into Vietnam business timezone: "15:20 • 04/11/2026"
 */
export function formatApprovalDateTimeVN(isoString) {
  if (!isValidIsoTimestamp(isoString)) {
    return '—';
  }

  const normalizedIso = /Z|[+-]\d{2}:?\d{2}$/.test(isoString.trim())
    ? isoString.trim()
    : `${isoString.trim().replace(' ', 'T')}Z`;

  const date = new Date(normalizedIso);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  const formatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  const parts = formatter.formatToParts(date);
  const map = {};
  for (const p of parts) {
    if (p.type !== 'literal') {
      map[p.type] = p.value;
    }
  }

  return `${map.hour}:${map.minute} • ${map.day}/${map.month}/${map.year}`;
}

/**
 * Staff Approvals API Service (AUTH-03 / T04A61F / T04A6F3).
 * Connects strictly to FastAPI Backend /api/v1/staff-approvals.
 * Zero mock fallback.
 */
export const staffApprovalsApi = {
  /**
   * GET /api/v1/staff-approvals
   */
  async getApprovals({
    isMockMode,
    status = '',
    page = 1,
    pageSize = 10,
  } = {}) {
    assertRealApiMode(isMockMode);

    const params = {
      page,
      page_size: pageSize,
    };

    if (status && ALLOWED_APPROVAL_STATUSES.includes(status)) {
      params.status = status;
    }

    const response = await axiosClient.get('/staff-approvals', { params });
    return validatePaginatedResponse(
      response.data,
      validateApprovalListItemRead,
      {
        minPageSize: 1,
        maxPageSize: 100,
      }
    );
  },

  /**
   * POST /api/v1/staff-approvals/{id}/approve
   */
  async approveStaff({ isMockMode, id } = {}) {
    assertRealApiMode(isMockMode);

    const numericId = Number(id);
    if (!Number.isInteger(numericId) || numericId <= 0) {
      throw new Error('Mã yêu cầu phê duyệt không hợp lệ.');
    }

    const response = await axiosClient.post(
      `/staff-approvals/${numericId}/approve`
    );
    return validateApprovalRead(response.data);
  },

  /**
   * POST /api/v1/staff-approvals/{id}/reject
   * Body: { reason: string (1..500 chars) }
   */
  async rejectStaff({ isMockMode, id, reason } = {}) {
    assertRealApiMode(isMockMode);

    const numericId = Number(id);
    if (!Number.isInteger(numericId) || numericId <= 0) {
      throw new Error('Mã yêu cầu phê duyệt không hợp lệ.');
    }

    const reasonCheck = validateRejectReason(reason);
    if (!reasonCheck.isValid) {
      throw new Error(reasonCheck.error);
    }

    const response = await axiosClient.post(
      `/staff-approvals/${numericId}/reject`,
      { reason: reasonCheck.normalized }
    );
    return validateApprovalRead(response.data);
  },

  /**
   * Bounded deep-link lookup for /staff?approval_request_id=<id> when backend has no GET /staff-approvals/{id}.
   * Checks currentItems first (0 requests), then searches across statuses with strict page cap.
   */
  async findApprovalByIdBounded({
    isMockMode,
    approvalId,
    currentItems = [],
    activeStatus = 'PENDING',
    maxPagesPerStatus = 3,
    pageSize = 50,
  } = {}) {
    assertRealApiMode(isMockMode);

    const targetId = parsePositiveApprovalId(approvalId);
    if (!targetId) {
      return null;
    }

    if (Array.isArray(currentItems)) {
      const localMatch = currentItems.find((item) => item?.id === targetId);
      if (localMatch) {
        return {
          item: localMatch,
          status: localMatch.status,
          page: null,
          fromCurrentPage: true,
        };
      }
    }

    const orderedStatuses = ALLOWED_APPROVAL_STATUSES.includes(activeStatus)
      ? [
          activeStatus,
          ...ALLOWED_APPROVAL_STATUSES.filter((s) => s !== activeStatus),
        ]
      : [...ALLOWED_APPROVAL_STATUSES];

    for (const status of orderedStatuses) {
      for (let page = 1; page <= maxPagesPerStatus; page += 1) {
        const res = await this.getApprovals({
          isMockMode,
          status,
          page,
          pageSize,
        });
        const matched = res.items.find((item) => item.id === targetId);
        if (matched) {
          return {
            item: matched,
            status,
            page,
            fromCurrentPage: false,
          };
        }
        if (res.items.length === 0 || page * pageSize >= res.total) {
          break;
        }
      }
    }

    return null;
  },
};
