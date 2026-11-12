import axiosClient from './axiosClient.js';
import {
  assertRealApiMode,
  isValidIsoTimestamp,
  validatePaginatedResponse,
} from './productsApi.js';

/**
 * Validate a single NotificationRead DTO from FastAPI Backend (/api/v1/admin/notifications).
 * Contract (backend/app/modules/notifications/schemas.py):
 * - id: positive integer (> 0)
 * - approval_request_id: positive integer (> 0)
 * - created_at: valid UTC ISO-8601 timestamp string
 * - read_at: null or valid UTC ISO-8601 timestamp string
 *
 * Invariant: ERD admin_notifications only stores (id, admin_user_id, approval_request_id, created_at, read_at).
 * Never invent fake PII fields.
 */
export function validateNotificationRead(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    throw new Error('Notification payload must be a non-null object.');
  }

  if (
    typeof item.id !== 'number' ||
    !Number.isInteger(item.id) ||
    item.id <= 0
  ) {
    throw new Error(
      `Schema violation: Notification missing valid positive integer id: ${JSON.stringify(item.id)}`
    );
  }

  if (
    typeof item.approval_request_id !== 'number' ||
    !Number.isInteger(item.approval_request_id) ||
    item.approval_request_id <= 0
  ) {
    throw new Error(
      `Schema violation: Notification #${item.id} missing valid positive integer approval_request_id: ${JSON.stringify(item.approval_request_id)}`
    );
  }

  if (!isValidIsoTimestamp(item.created_at)) {
    throw new Error(
      `Schema violation: Notification #${item.id} has invalid created_at timestamp: ${JSON.stringify(item.created_at)}`
    );
  }

  if (item.read_at !== null && !isValidIsoTimestamp(item.read_at)) {
    throw new Error(
      `Schema violation: Notification #${item.id} has invalid read_at timestamp: ${JSON.stringify(item.read_at)}`
    );
  }

  return {
    id: item.id,
    approval_request_id: item.approval_request_id,
    created_at: item.created_at,
    read_at: item.read_at,
  };
}

/**
 * Validate UnreadCountResponse DTO: { count: int >= 0 }
 */
export function validateUnreadCountResponse(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('UnreadCountResponse payload must be a non-null object.');
  }
  if (
    typeof payload.count !== 'number' ||
    !Number.isInteger(payload.count) ||
    payload.count < 0
  ) {
    throw new Error(
      `Schema violation: UnreadCountResponse "count" must be a non-negative integer, got: ${JSON.stringify(payload.count)}`
    );
  }
  return { count: payload.count };
}

/**
 * Validate MarkAllReadResponse DTO: { updated_count: int >= 0 }
 */
export function validateMarkAllReadResponse(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('MarkAllReadResponse payload must be a non-null object.');
  }
  if (
    typeof payload.updated_count !== 'number' ||
    !Number.isInteger(payload.updated_count) ||
    payload.updated_count < 0
  ) {
    throw new Error(
      `Schema violation: MarkAllReadResponse "updated_count" must be a non-negative integer, got: ${JSON.stringify(payload.updated_count)}`
    );
  }
  return { updated_count: payload.updated_count };
}

/**
 * Format UTC ISO-8601 timestamp into Vietnam business timezone (Asia/Ho_Chi_Minh)
 * matching the approved UI design:
 * - Unread today (first item): "10:24 • Hôm nay (Asia/Ho_Chi_Minh)"
 * - Unread today (other items): "09:15 • Hôm nay"
 * - Yesterday (read): "Hôm qua (03/11/2026)" or "14:20 • Hôm qua (03/11/2026)"
 * - Older dates: "10:24 • 03/11/2026"
 */
export function formatNotificationTimeVN(
  isoString,
  { includeTimezoneLabel = false, isRead = false, nowDate = new Date() } = {}
) {
  if (!isValidIsoTimestamp(isoString)) {
    return '';
  }

  const normalizedIso =
    /Z|[+-]\d{2}:?\d{2}$/.test(isoString.trim())
      ? isoString.trim()
      : `${isoString.trim().replace(' ', 'T')}Z`;

  const date = new Date(normalizedIso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  const vnPartsFormatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  const getPartsMap = (d) => {
    const parts = vnPartsFormatter.formatToParts(d);
    const map = {};
    for (const p of parts) {
      if (p.type !== 'literal') map[p.type] = p.value;
    }
    return map;
  };

  const target = getPartsMap(date);
  const current = getPartsMap(nowDate);

  const timeStr = `${target.hour}:${target.minute}`;
  const dateStr = `${target.day}/${target.month}/${target.year}`;

  const targetDayUtc = Date.UTC(
    Number(target.year),
    Number(target.month) - 1,
    Number(target.day)
  );
  const currentDayUtc = Date.UTC(
    Number(current.year),
    Number(current.month) - 1,
    Number(current.day)
  );
  const diffDays = Math.round((currentDayUtc - targetDayUtc) / 86400000);

  if (diffDays === 0) {
    return includeTimezoneLabel
      ? `${timeStr} • Hôm nay (Asia/Ho_Chi_Minh)`
      : `${timeStr} • Hôm nay`;
  }

  if (diffDays === 1) {
    return isRead
      ? `Hôm qua (${dateStr})`
      : `${timeStr} • Hôm qua (${dateStr})`;
  }

  return isRead ? dateStr : `${timeStr} • ${dateStr}`;
}

/**
 * Admin In-App Notifications API Service (AUTH-05 / T3C9BA4).
 * Connects strictly to FastAPI Backend /api/v1/admin/notifications.
 * Never falls back to Mock data.
 */
export const notificationsApi = {
  /**
   * GET /api/v1/admin/notifications
   */
  async getNotifications({
    isMockMode,
    page = 1,
    pageSize = 20,
    unreadOnly = false,
  } = {}) {
    assertRealApiMode(isMockMode);

    const params = {
      page,
      page_size: pageSize,
      unread_only: Boolean(unreadOnly),
    };

    const response = await axiosClient.get('/admin/notifications', { params });
    return validatePaginatedResponse(response.data, validateNotificationRead, {
      minPageSize: 1,
      maxPageSize: 100,
    });
  },

  /**
   * GET /api/v1/admin/notifications/unread-count
   */
  async getUnreadCount({ isMockMode } = {}) {
    assertRealApiMode(isMockMode);

    const response = await axiosClient.get('/admin/notifications/unread-count');
    return validateUnreadCountResponse(response.data);
  },

  /**
   * PATCH /api/v1/admin/notifications/{id}/read
   * Backend requires strict empty JSON body {} (EmptyPatchRequest extra="forbid").
   */
  async markAsRead({ isMockMode, id } = {}) {
    assertRealApiMode(isMockMode);

    const numericId = Number(id);
    if (!Number.isInteger(numericId) || numericId <= 0) {
      throw new Error('ID thông báo không hợp lệ.');
    }

    const response = await axiosClient.patch(
      `/admin/notifications/${numericId}/read`,
      {}
    );
    return validateNotificationRead(response.data);
  },

  /**
   * PATCH /api/v1/admin/notifications/read-all
   * Backend requires strict empty JSON body {} (EmptyPatchRequest extra="forbid").
   */
  async markAllAsRead({ isMockMode } = {}) {
    assertRealApiMode(isMockMode);

    const response = await axiosClient.patch(
      '/admin/notifications/read-all',
      {}
    );
    return validateMarkAllReadResponse(response.data);
  },
};

export default notificationsApi;
