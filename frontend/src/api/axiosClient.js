import axios from 'axios';

/**
 * ============================================================================
 * CẤU HÌNH TRUNG TÂM MẠNG & BẢO MẬT PHIÊN (RetailOps v1.0)
 * ============================================================================
 * Bảo mật Mock Isolation (FIX-01):
 * - Production build BẮT BUỘC dùng Real API (`isMockAllowed() === false`).
 * - Development mặc định dùng Real API; chỉ cho phép bật Mock khi chạy ở
 *   môi trường DEV và cấu hình tường minh `VITE_USE_MOCK=true`.
 */
export function isMockAllowed(runtimeEnv = import.meta.env) {
  if (!runtimeEnv || typeof runtimeEnv !== 'object') {
    return false;
  }
  const isDevEnvironment =
    runtimeEnv.DEV === true &&
    runtimeEnv.PROD !== true &&
    runtimeEnv.MODE !== 'production';
  const isExplicitlyEnabled =
    String(runtimeEnv.VITE_USE_MOCK || '')
      .trim()
      .toLowerCase() === 'true';
  return Boolean(isDevEnvironment && isExplicitlyEnabled);
}

export let USE_MOCK = isMockAllowed();

export function setUseMock(value, runtimeEnv = import.meta.env) {
  if (!isMockAllowed(runtimeEnv)) {
    if (USE_MOCK) {
      USE_MOCK = false;
      invalidateSession();
    }
    return false;
  }
  const next = Boolean(value);
  if (USE_MOCK !== next) {
    USE_MOCK = next;
    invalidateSession();
  }
  return USE_MOCK;
}

export function getUseMock() {
  return USE_MOCK;
}

export const BASE_URL = import.meta.env?.VITE_API_BASE_URL || '/api/v1';

const DEFAULT_TIMEOUT_MS = 10000;
const parsedTimeout = Number.parseInt(import.meta.env?.VITE_API_TIMEOUT, 10);
const timeout =
  Number.isFinite(parsedTimeout) && parsedTimeout > 0
    ? parsedTimeout
    : DEFAULT_TIMEOUT_MS;

export function getApiErrorMessage(error) {
  if (axios.isCancel(error)) {
    return '';
  }

  if (error?.code === 'ECONNABORTED') {
    return 'Yêu cầu tới máy chủ quá thời gian chờ. Vui lòng kiểm tra kết nối và thử lại.';
  }

  if (error?.response) {
    const status = error.response.status;
    const detail = error.response.data?.message || error.response.data?.detail;
    if (typeof detail === 'string' && detail.trim().length > 0) {
      return detail;
    }
    if (status >= 500) {
      return 'Máy chủ FastAPI phản hồi lỗi kết nối hoặc dịch vụ tạm thời chưa sẵn sàng.';
    }
    return `Máy chủ trả về trạng thái không mong đợi (HTTP ${status}).`;
  }

  return 'Không thể kết nối tới FastAPI Backend. Hãy kiểm tra dịch vụ Backend và cấu hình Vite proxy.';
}

// ============================================================================
// 1. QUẢN LÝ ACCESS TOKEN, CSRF TOKEN & SESSION GENERATION TRONG BỘ NHỚ RAM
// Tuyệt đối KHÔNG lưu vào localStorage hay sessionStorage để chống tấn công XSS
// ============================================================================
let inMemoryToken = null;
let inMemoryCsrfToken = null;
let currentSessionGeneration = 0;
let isRefreshing = false;
let activeRefreshGeneration = -1;
let failedQueue = [];

let authTransport = axios;

export function setAuthTransport(customTransport) {
  authTransport = customTransport || axios;
}

export function getSessionGeneration() {
  return currentSessionGeneration;
}

/**
 * Giải phóng hoặc từ chối các request đang chờ trong hàng đợi của đúng phiên chỉ định
 */
function processQueue(
  error,
  token = null,
  expectedGeneration = currentSessionGeneration
) {
  const queueSnapshot = failedQueue;
  failedQueue = [];
  queueSnapshot.forEach((entry) => {
    if (error) {
      entry.reject(error);
    } else if (
      entry.generation !== expectedGeneration ||
      expectedGeneration !== currentSessionGeneration
    ) {
      entry.reject(
        new Error('Yêu cầu thuộc phiên làm việc cũ đã bị hủy bỏ.')
      );
    } else {
      entry.resolve(token);
    }
  });
}

/**
 * Hủy bỏ phiên hiện tại, tăng generation và giải phóng hàng đợi chờ refresh.
 * Ngăn mọi request hoặc refresh cũ hồi sinh phiên hoặc ghi đè phiên mới.
 */
export function invalidateSession() {
  currentSessionGeneration += 1;
  inMemoryToken = null;
  inMemoryCsrfToken = null;
  isRefreshing = false;
  activeRefreshGeneration = -1;
  processQueue(
    new Error('Phiên làm việc đã bị hủy hoặc người dùng đã đăng xuất.'),
    null,
    -1
  );
  return currentSessionGeneration;
}

/**
 * Tạo ranh giới phiên xác thực mới khi đăng nhập hoặc khôi phục phiên thành công.
 */
export function startAuthenticatedSession(accessToken, csrfToken = null) {
  currentSessionGeneration += 1;
  inMemoryToken = accessToken || null;
  inMemoryCsrfToken = csrfToken || null;
  isRefreshing = false;
  activeRefreshGeneration = -1;
  processQueue(
    new Error('Phiên làm việc đã chuyển sang phiên xác thực mới.'),
    null,
    -1
  );
  return currentSessionGeneration;
}

export function setClientToken(token) {
  inMemoryToken = token || null;
}

export function getClientToken() {
  return inMemoryToken;
}

export function setCsrfToken(token) {
  inMemoryCsrfToken = token || null;
}

export function getCsrfToken() {
  return inMemoryCsrfToken;
}

/**
 * Lấy CSRF Token từ Backend (`GET /api/v1/auth/csrf`) nếu trong RAM chưa có.
 * Có kiểm tra session generation để không ghi đè trạng thái của phiên khác.
 */
export async function ensureCsrfToken(
  expectedGeneration = currentSessionGeneration
) {
  if (expectedGeneration !== currentSessionGeneration) {
    return null;
  }
  if (inMemoryCsrfToken) {
    return inMemoryCsrfToken;
  }
  const tokenSnapshot = inMemoryToken;
  try {
    const response = await authTransport.get(`${BASE_URL}/auth/csrf`, {
      timeout,
      withCredentials: true,
      headers: tokenSnapshot
        ? { Authorization: `Bearer ${tokenSnapshot}` }
        : {},
    });
    if (expectedGeneration !== currentSessionGeneration) {
      return null;
    }
    const token =
      response?.data?.csrf_token ||
      response?.headers?.['x-csrf-token'] ||
      null;
    if (token && typeof token === 'string') {
      inMemoryCsrfToken = token;
    }
    return inMemoryCsrfToken;
  } catch {
    return null;
  }
}

// ============================================================================
// 2. ĐĂNG KÝ CALLBACK ĐỒNG BỘ VỚI AUTHCONTEXT (TRÁNH CIRCULAR DEPENDENCY)
// ============================================================================
let authCallbacks = {
  onTokenRefreshed: null,
  onAuthFailed: null,
};

export function setupAxiosAuth({ onTokenRefreshed, onAuthFailed } = {}) {
  authCallbacks = {
    onTokenRefreshed:
      typeof onTokenRefreshed === 'function' ? onTokenRefreshed : null,
    onAuthFailed: typeof onAuthFailed === 'function' ? onAuthFailed : null,
  };
}

// ============================================================================
// 3. KHỞI TẠO AXIOS INSTANCE CHÍNH CHO TOÀN ỨNG DỤNG
// ============================================================================
const axiosClient = axios.create({
  baseURL: BASE_URL,
  timeout,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
  withCredentials: true,
});

export const apiClient = axiosClient;

// ============================================================================
// 4. HÀM GỌI REFRESH TOKEN & LOGOUT ĐỘC LẬP (TRÁNH INFINITE LOOP)
// ============================================================================
export async function callRefreshTokenApi(
  expectedGeneration = currentSessionGeneration
) {
  if (USE_MOCK && isMockAllowed()) {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        if (expectedGeneration !== currentSessionGeneration) {
          reject(new Error('Phiên làm việc đã thay đổi trong lúc refresh.'));
          return;
        }
        resolve({
          data: {
            access_token: `mock-refreshed-token-${Date.now()}`,
          },
        });
      }, 100);
    });
  }

  const csrfToken =
    inMemoryCsrfToken || (await ensureCsrfToken(expectedGeneration));

  if (expectedGeneration !== currentSessionGeneration) {
    throw new Error('Phiên làm việc đã thay đổi trước khi gọi refresh.');
  }

  const response = await authTransport.post(
    `${BASE_URL}/auth/refresh`,
    {},
    {
      timeout,
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
      },
      withCredentials: true,
    }
  );

  if (expectedGeneration !== currentSessionGeneration) {
    throw new Error('Phiên làm việc đã thay đổi sau khi gọi refresh.');
  }

  const nextCsrf = response?.headers?.['x-csrf-token'];
  if (nextCsrf && expectedGeneration === currentSessionGeneration) {
    setCsrfToken(nextCsrf);
  }

  return response;
}

/**
 * Gửi yêu cầu hủy phiên lên Server (`POST /api/v1/auth/logout`) sử dụng snapshot
 * của phiên vừa đóng, không ghi lại bất kỳ token nào vào RAM.
 */
export async function callLogoutApi({
  accessToken = null,
  csrfToken = null,
} = {}) {
  if (USE_MOCK && isMockAllowed()) {
    return { revoked: true, isMock: true };
  }

  let csrfToUse = csrfToken;
  if (!csrfToUse) {
    try {
      const csrfRes = await authTransport.get(`${BASE_URL}/auth/csrf`, {
        timeout,
        withCredentials: true,
        headers: accessToken
          ? { Authorization: `Bearer ${accessToken}` }
          : {},
      });
      csrfToUse =
        csrfRes?.data?.csrf_token ||
        csrfRes?.headers?.['x-csrf-token'] ||
        null;
    } catch {
      csrfToUse = null;
    }
  }

  if (!csrfToUse) {
    return { revoked: false, reason: 'CSRF_UNAVAILABLE' };
  }

  try {
    const response = await authTransport.post(
      `${BASE_URL}/auth/logout`,
      {},
      {
        timeout,
        withCredentials: true,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToUse,
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
      }
    );
    const revoked = response?.status === 204 || response?.status === 200;
    return { revoked };
  } catch (error) {
    return { revoked: false, error };
  }
}

// ============================================================================
// 5. REQUEST INTERCEPTOR: GẮN SESSION GENERATION, BEARER TOKEN & X-CSRF-TOKEN
// ============================================================================
axiosClient.interceptors.request.use(
  (config) => {
    config.headers = config.headers || {};

    // Nếu là request retry nhưng phiên đã thay đổi -> chặn ngay trước khi gửi
    if (
      config._retry &&
      typeof config._sessionGeneration === 'number' &&
      config._sessionGeneration !== currentSessionGeneration
    ) {
      return Promise.reject(
        new Error('Hủy retry request do phiên làm việc đã thay đổi.')
      );
    }

    if (typeof config._sessionGeneration !== 'number') {
      config._sessionGeneration = currentSessionGeneration;
    }
    config._hadAuthToken = Boolean(inMemoryToken);

    if (inMemoryToken) {
      config.headers.Authorization = `Bearer ${inMemoryToken}`;
    } else if (config.headers.Authorization) {
      delete config.headers.Authorization;
    }

    if (inMemoryCsrfToken) {
      config.headers['X-CSRF-Token'] = inMemoryCsrfToken;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ============================================================================
// 6. RESPONSE INTERCEPTOR & HÀNG ĐỢI SINGLE-FLIGHT REFRESH KHI GẶP 401
// ============================================================================
axiosClient.interceptors.response.use(
  (response) => {
    const reqGen = response?.config?._sessionGeneration;
    const csrfHeader = response?.headers?.['x-csrf-token'];
    if (
      csrfHeader &&
      (typeof reqGen !== 'number' || reqGen === currentSessionGeneration)
    ) {
      setCsrfToken(csrfHeader);
    }
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    const status = error.response?.status;

    // 1. Phân biệt rạch ròi lỗi 403 Forbidden:
    // Người dùng đã đăng nhập nhưng không đủ quyền -> Trả lỗi ngay, KHÔNG đăng xuất
    if (status === 403) {
      return Promise.reject(error);
    }

    if (!originalRequest || status !== 401) {
      return Promise.reject(error);
    }

    // 2. Bỏ qua logic refresh cho các route xác thực hoặc request đã retry
    const requestUrl = originalRequest.url || '';
    const isAuthLifecycleRoute =
      requestUrl.includes('/auth/login') ||
      requestUrl.includes('/auth/register') ||
      requestUrl.includes('/auth/refresh') ||
      requestUrl.includes('/auth/csrf') ||
      requestUrl.includes('/auth/logout');

    if (isAuthLifecycleRoute || originalRequest._retry) {
      return Promise.reject(error);
    }

    // 3. Kiểm tra cô lập thế hệ phiên (Session Generation Isolation):
    // Nếu request được gửi từ phiên cũ hoặc khi chưa đăng nhập -> Từ chối ngay,
    // TUYỆT ĐỐI KHÔNG refresh hoặc retry bằng token của phiên mới.
    const requestGeneration = originalRequest._sessionGeneration;
    if (
      typeof requestGeneration !== 'number' ||
      requestGeneration !== currentSessionGeneration ||
      !originalRequest._hadAuthToken ||
      !inMemoryToken
    ) {
      return Promise.reject(error);
    }

    // 4. Xử lý đồng thời (Single-Flight Concurrency) trong cùng một thế hệ phiên:
    if (isRefreshing && activeRefreshGeneration === requestGeneration) {
      return new Promise((resolve, reject) => {
        failedQueue.push({
          resolve,
          reject,
          generation: requestGeneration,
        });
      })
        .then((newToken) => {
          if (requestGeneration !== currentSessionGeneration) {
            return Promise.reject(
              new Error('Phiên làm việc đã thay đổi, hủy retry request cũ.')
            );
          }
          originalRequest._retry = true;
          originalRequest._sessionGeneration = currentSessionGeneration;
          originalRequest.headers = originalRequest.headers || {};
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return axiosClient(originalRequest);
        })
        .catch((queueError) => Promise.reject(queueError));
    }

    // Đánh dấu request đầu tiên của phiên hiện hành kích hoạt luồng làm mới token
    originalRequest._retry = true;
    isRefreshing = true;
    activeRefreshGeneration = requestGeneration;

    try {
      const response = await callRefreshTokenApi(requestGeneration);

      if (requestGeneration !== currentSessionGeneration) {
        throw new Error(
          'Phiên làm việc đã bị hủy hoặc thay đổi trong khi đang làm mới token.'
        );
      }

      const newAccessToken =
        response?.data?.access_token || response?.data?.accessToken;

      if (!newAccessToken || typeof newAccessToken !== 'string') {
        throw new Error('Không nhận được access_token hợp lệ từ API refresh');
      }

      setClientToken(newAccessToken);

      if (authCallbacks.onTokenRefreshed) {
        authCallbacks.onTokenRefreshed(
          newAccessToken,
          response?.data?.user,
          requestGeneration
        );
      }

      // Nếu callback phát hiện thông tin user vi phạm contract và đã hủy phiên:
      if (requestGeneration !== currentSessionGeneration) {
        throw new Error(
          'Phiên làm việc bị đóng do dữ liệu xác thực trả về không hợp lệ.'
        );
      }

      processQueue(null, newAccessToken, requestGeneration);

      originalRequest._sessionGeneration = currentSessionGeneration;
      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
      return axiosClient(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null, requestGeneration);

      // Chỉ xóa trạng thái và gọi onAuthFailed nếu vẫn đang ở đúng thế hệ phiên của refresh này
      if (requestGeneration === currentSessionGeneration) {
        invalidateSession();
        if (authCallbacks.onAuthFailed) {
          authCallbacks.onAuthFailed();
        }
      }

      return Promise.reject(refreshError);
    } finally {
      if (activeRefreshGeneration === requestGeneration) {
        isRefreshing = false;
        activeRefreshGeneration = -1;
      }
    }
  }
);

// ============================================================================
// 7. DEFENSIVE USER NORMALIZATION & ROUTE ACCESS EVALUATION (FAIL-CLOSED)
// ============================================================================
const VALID_ROLES = new Set(['ADMIN', 'STAFF']);
const VALID_BACKEND_STATUSES = new Set([
  'ACTIVE',
  'APPROVED',
  'PENDING_APPROVAL',
  'PENDING',
  'REJECTED',
]);

/**
 * Chuẩn hóa đối tượng user trả về từ FastAPI Backend (`AuthenticatedUser`)
 * theo cơ chế Fail-Closed (FIX-07):
 * - Bắt buộc có `id`, `email_normalized`/`email`, `role` hợp lệ và `status` hợp lệ.
 * - Tuyệt đối KHÔNG mặc định `status = ACTIVE` hay `role = STAFF` khi thiếu dữ liệu.
 * - Không trộn dữ liệu từ `usersList` của Mock vào đối tượng xác thực của Backend.
 */
export function normalizeBackendUser(rawUser) {
  if (!rawUser || typeof rawUser !== 'object') {
    return null;
  }

  const rawId = rawUser.id;
  const hasValidId =
    (typeof rawId === 'number' && Number.isInteger(rawId) && rawId > 0) ||
    (typeof rawId === 'string' && rawId.trim().length > 0);
  if (!hasValidId) {
    return null;
  }

  const email = String(rawUser.email_normalized || rawUser.email || '')
    .trim()
    .toLowerCase();
  if (!email || !email.includes('@')) {
    return null;
  }

  const role =
    typeof rawUser.role === 'string' ? rawUser.role.trim().toUpperCase() : '';
  if (!VALID_ROLES.has(role)) {
    return null;
  }

  const rawStatus =
    typeof rawUser.status === 'string'
      ? rawUser.status.trim().toUpperCase()
      : '';
  if (!VALID_BACKEND_STATUSES.has(rawStatus)) {
    return null;
  }

  const mappedStatus =
    rawStatus === 'ACTIVE'
      ? 'APPROVED'
      : rawStatus === 'PENDING_APPROVAL'
        ? 'PENDING'
        : rawStatus;

  const fallbackName =
    role === 'ADMIN'
      ? 'Quản trị viên (Admin)'
      : email.split('@')[0] || 'Nhân viên RetailOps';

  return {
    id: rawId,
    name:
      typeof rawUser.name === 'string' && rawUser.name.trim()
        ? rawUser.name.trim()
        : fallbackName,
    email,
    role,
    status: mappedStatus,
    rawStatus,
    submittedAt: rawUser.submittedAt || null,
    rejectReason: rawUser.rejectReason || null,
    rejectSubState: rawUser.rejectSubState || 'LOCKED_24H',
  };
}

/**
 * Đánh giá quyền truy cập route theo nguyên tắc Fail-Closed (FIX-07).
 */
export function evaluateRouteAccess({
  user,
  accessToken,
  authInitializing,
  allowedRoles = [],
}) {
  if (authInitializing) {
    return { action: 'WAIT' };
  }

  if (!user || typeof user !== 'object') {
    return { action: 'REDIRECT_LOGIN' };
  }

  if (
    user.status === 'PENDING' ||
    user.status === 'PENDING_APPROVAL' ||
    user.status === 'REJECTED'
  ) {
    return { action: 'REDIRECT_ACCOUNT_STATUS' };
  }

  const isApproved =
    user.status === 'APPROVED' || user.status === 'ACTIVE';
  const hasValidRole = VALID_ROLES.has(user.role);
  const hasValidToken =
    typeof accessToken === 'string' && accessToken.trim().length > 0;

  if (!isApproved || !hasValidRole || !hasValidToken) {
    return { action: 'REDIRECT_LOGIN' };
  }

  if (
    Array.isArray(allowedRoles) &&
    allowedRoles.length > 0 &&
    !allowedRoles.includes(user.role)
  ) {
    const fallbackPath = user.role === 'STAFF' ? '/pos' : '/dashboard';
    return {
      action: 'REDIRECT_ROLE_HOME',
      to: fallbackPath,
      target: fallbackPath,
    };
  }

  return { action: 'ALLOW' };
}

export default axiosClient;
