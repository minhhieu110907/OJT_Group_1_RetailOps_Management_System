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
      const generation = invalidateSession();
      if (authCallbacks.onSessionInvalidated) {
        authCallbacks.onSessionInvalidated({
          isMockMode: false,
          generation,
        });
      }
    }
    return false;
  }
  const next = Boolean(value);
  if (USE_MOCK !== next) {
    USE_MOCK = next;
    const generation = invalidateSession();
    if (authCallbacks.onSessionInvalidated) {
      authCallbacks.onSessionInvalidated({
        isMockMode: USE_MOCK,
        generation,
      });
    }
  }
  return USE_MOCK;
}

/**
 * Chuyển đổi chế độ xác thực (Mock <-> Real) qua một điểm điều phối duy nhất (FIX-02).
 * Luôn hủy phiên hiện hành, xóa token/CSRF và đồng bộ trạng thái với AuthContext.
 */
export function transitionAuthMode(
  targetMockMode,
  runtimeEnv = import.meta.env
) {
  const allowed = isMockAllowed(runtimeEnv);
  const nextMock = allowed ? Boolean(targetMockMode) : false;
  USE_MOCK = nextMock;
  const generation = invalidateSession();
  if (authCallbacks.onSessionInvalidated) {
    authCallbacks.onSessionInvalidated({
      isMockMode: USE_MOCK,
      generation,
    });
  }
  return {
    isMockMode: USE_MOCK,
    allowed,
    generation,
  };
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
let latestLoginAttemptId = 0;
let activeLogoutPromise = null;
let isRefreshing = false;
let activeRefreshGeneration = -1;
let failedQueue = [];

let authTransport = axios;

export function setAuthTransport(customTransport) {
  authTransport = customTransport || axios;
  activeLogoutPromise = null;
}

export function getSessionGeneration() {
  return currentSessionGeneration;
}

export function isLogoutInProgress() {
  return activeLogoutPromise !== null;
}

/**
 * Tạo đối tượng lỗi chuẩn khi phát hiện request/response thuộc phiên làm việc cũ (FIX-03).
 */
export function createStaleSessionError(
  config = null,
  message = 'Yêu cầu hoặc phản hồi thuộc phiên làm việc cũ đã bị từ chối.'
) {
  const err = new Error(message);
  err.code = 'ERR_STALE_SESSION';
  err.isStaleSession = true;
  if (config) {
    err.config = config;
  }
  return err;
}

/**
 * Đánh giá chính sách phát lại (replay policy) sau khi làm mới token (FIX-02 Hardening):
 * - Giữ automatic retry tối đa một lần cho các request GET/HEAD/OPTIONS phù hợp.
 * - Với POST/PATCH/PUT/DELETE, mặc định KHÔNG tự động replay (fail-closed).
 * - Chỉ cho phép replay mutation nếu endpoint đã được xác minh hỗ trợ idempotency contract
 *   trong `VERIFIED_IDEMPOTENT_MUTATION_ENDPOINTS` VÀ caller đã tự tạo `Idempotency-Key` trước đó.
 * - Tuyệt đối không tự sinh idempotency key tại response interceptor.
 */
const SAFE_IDEMPOTENT_READ_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

/**
 * Danh sách endpoint mutation đã được Backend xác minh hỗ trợ Idempotency contract.
 * Các endpoint Checkout, Receipt Confirm, Cancel Order và Inventory Adjustment chưa có contract
 * hoàn chỉnh trong source hiện tại nên mặc định danh sách là fail-closed.
 */
export const VERIFIED_IDEMPOTENT_MUTATION_ENDPOINTS = new Set();

export function registerVerifiedIdempotentEndpoint(endpointOrPattern) {
  if (endpointOrPattern) {
    VERIFIED_IDEMPOTENT_MUTATION_ENDPOINTS.add(endpointOrPattern);
  }
}

export function unregisterVerifiedIdempotentEndpoint(endpointOrPattern) {
  VERIFIED_IDEMPOTENT_MUTATION_ENDPOINTS.delete(endpointOrPattern);
}

export function clearVerifiedIdempotentEndpoints() {
  VERIFIED_IDEMPOTENT_MUTATION_ENDPOINTS.clear();
}

export function isEndpointVerifiedForIdempotency(url) {
  if (!url || typeof url !== 'string') return false;
  const cleanPath = url.split('?')[0];
  for (const pattern of VERIFIED_IDEMPOTENT_MUTATION_ENDPOINTS) {
    if (typeof pattern === 'string' && (cleanPath === pattern || cleanPath.endsWith(pattern))) {
      return true;
    }
    if (pattern instanceof RegExp && pattern.test(cleanPath)) {
      return true;
    }
  }
  return false;
}

export function isSafeToReplayRequest(config) {
  if (!config || typeof config !== 'object') {
    return false;
  }
  const method = String(config.method || 'GET').trim().toUpperCase();
  if (SAFE_IDEMPOTENT_READ_METHODS.has(method)) {
    return true;
  }

  // Fail-closed cho toàn bộ mutation (POST, PUT, PATCH, DELETE):
  // Chỉ replay nếu endpoint thuộc danh sách được xác minh VÀ caller đã chủ động gắn Idempotency-Key
  const requestUrl = config.url || '';
  if (!isEndpointVerifiedForIdempotency(requestUrl)) {
    return false;
  }

  const headers = config.headers || {};
  const idempotencyKey =
    headers['Idempotency-Key'] ||
    headers['idempotency-key'] ||
    headers['X-Idempotency-Key'] ||
    headers['x-idempotency-key'];
  if (typeof idempotencyKey === 'string' && idempotencyKey.trim().length > 0) {
    return true;
  }
  return false;
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
        createStaleSessionError(
          null,
          'Yêu cầu thuộc phiên làm việc cũ đã bị hủy bỏ.'
        )
      );
    } else {
      entry.resolve(token);
    }
  });
}

/**
 * Hủy bỏ phiên hiện tại, tăng generation và giải phóng hàng đợi chờ refresh.
 * Ngăn mọi request, login attempt hoặc refresh cũ hồi sinh phiên hoặc ghi đè phiên mới.
 */
export function invalidateSession() {
  currentSessionGeneration += 1;
  latestLoginAttemptId += 1;
  inMemoryToken = null;
  inMemoryCsrfToken = null;
  isRefreshing = false;
  activeRefreshGeneration = -1;
  processQueue(
    createStaleSessionError(
      null,
      'Phiên làm việc đã bị hủy hoặc người dùng đã đăng xuất.'
    ),
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
  latestLoginAttemptId += 1;
  inMemoryToken = accessToken || null;
  inMemoryCsrfToken = csrfToken || null;
  isRefreshing = false;
  activeRefreshGeneration = -1;
  processQueue(
    createStaleSessionError(
      null,
      'Phiên làm việc đã chuyển sang phiên xác thực mới.'
    ),
    null,
    -1
  );
  return currentSessionGeneration;
}

/**
 * Ghi nhận ngữ cảnh tại thời điểm bắt đầu một yêu cầu đăng nhập (FIX-01).
 */
export function beginLoginAttempt(runtimeEnv = import.meta.env) {
  latestLoginAttemptId += 1;
  return {
    attemptId: latestLoginAttemptId,
    generation: currentSessionGeneration,
    isMock: Boolean(USE_MOCK && isMockAllowed(runtimeEnv)),
  };
}

/**
 * Kiểm tra xem một yêu cầu đăng nhập đang chờ còn hợp lệ để ghi nhận trạng thái hay không (FIX-01).
 */
export function canCommitLoginAttempt(attempt, runtimeEnv = import.meta.env) {
  if (!attempt || typeof attempt !== 'object') {
    return false;
  }
  if (isLogoutInProgress()) {
    return false;
  }
  const currentIsMock = Boolean(USE_MOCK && isMockAllowed(runtimeEnv));
  return (
    attempt.attemptId === latestLoginAttemptId &&
    attempt.generation === currentSessionGeneration &&
    attempt.isMock === currentIsMock
  );
}

/**
 * Xác nhận và khởi tạo phiên đăng nhập nếu và chỉ nếu login attempt vẫn còn hợp lệ (FIX-01).
 */
export function commitLoginSession(
  attempt,
  { accessToken, csrfToken = null, user = null } = {},
  runtimeEnv = import.meta.env
) {
  if (!canCommitLoginAttempt(attempt, runtimeEnv)) {
    return { committed: false, reason: 'STALE_LOGIN_ATTEMPT' };
  }
  const generation = startAuthenticatedSession(accessToken, csrfToken);
  return {
    committed: true,
    generation,
    accessToken: inMemoryToken,
    csrfToken: inMemoryCsrfToken,
    user,
  };
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
  onSessionInvalidated: null,
};

export function setupAxiosAuth({
  onTokenRefreshed,
  onAuthFailed,
  onSessionInvalidated,
} = {}) {
  authCallbacks = {
    onTokenRefreshed:
      typeof onTokenRefreshed === 'function' ? onTokenRefreshed : null,
    onAuthFailed: typeof onAuthFailed === 'function' ? onAuthFailed : null,
    onSessionInvalidated:
      typeof onSessionInvalidated === 'function' ? onSessionInvalidated : null,
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
 * Đồng thời quản lý khóa `activeLogoutPromise` để ngăn chặn race condition với login mới (FIX-01)
 * và gom các lệnh logout đồng thời (concurrent logout).
 */
export async function callLogoutApi({
  accessToken = null,
  csrfToken = null,
} = {}) {
  if (USE_MOCK && isMockAllowed()) {
    return { revoked: true, isMock: true };
  }

  if (activeLogoutPromise) {
    return activeLogoutPromise;
  }

  activeLogoutPromise = (async () => {
    try {
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
    } finally {
      activeLogoutPromise = null;
    }
  })();

  return activeLogoutPromise;
}

/**
 * Kiểm tra kết nối tới FastAPI Backend (`/api/v1/health`) và tùy chọn khôi phục phiên từ Cookie (FIX-02):
 * - TUYỆT ĐỐI KHÔNG tự ý thay đổi chế độ Mock <-> Real khi thực hiện health check.
 * - Chỉ khôi phục phiên từ cookie khi `allowSessionRestore === true`, đang ở Real API mode,
 *   chưa có accessToken trong RAM và thế hệ phiên chưa thay đổi.
 */
export async function runHealthCheck({
  allowSessionRestore = false,
  onRestoredSession = null,
} = {}) {
  const startGeneration = currentSessionGeneration;
  const startIsMock = Boolean(USE_MOCK && isMockAllowed());

  try {
    const res = await authTransport.get(`${BASE_URL}/health`, {
      timeout: 2500,
    });
    const isHealthy =
      res?.status === 200 &&
      (res?.data?.status === 'ok' || res?.data?.status === 'healthy');

    if (!isHealthy) {
      return { online: false, restored: false };
    }

    // Chỉ thử khôi phục phiên từ HttpOnly Refresh Cookie khi được phép (lúc khởi động app)
    // và khi mode/session generation không hề thay đổi trong lúc chờ /health.
    if (
      allowSessionRestore &&
      !startIsMock &&
      !getUseMock() &&
      !inMemoryToken &&
      startGeneration === currentSessionGeneration
    ) {
      try {
        const refreshRes = await callRefreshTokenApi(startGeneration);
        if (
          startGeneration !== currentSessionGeneration ||
          getUseMock() ||
          inMemoryToken
        ) {
          return { online: true, restored: false, stale: true };
        }

        const restoredToken =
          refreshRes?.data?.access_token || refreshRes?.data?.accessToken;
        const restoredCsrf = refreshRes?.headers?.['x-csrf-token'] || null;
        const restoredUser = normalizeBackendUser(refreshRes?.data?.user);

        if (
          restoredToken &&
          typeof restoredToken === 'string' &&
          restoredUser &&
          restoredUser.status === 'APPROVED'
        ) {
          const newGen = startAuthenticatedSession(restoredToken, restoredCsrf);
          if (typeof onRestoredSession === 'function') {
            onRestoredSession({
              accessToken: restoredToken,
              csrfToken: restoredCsrf,
              user: restoredUser,
              generation: newGen,
            });
          }
          return {
            online: true,
            restored: true,
            user: restoredUser,
            accessToken: restoredToken,
          };
        }
      } catch {
        // Không có cookie phiên cũ hoặc phiên đã hết hạn -> giữ nguyên trạng thái chưa đăng nhập
      }
    }

    return { online: true, restored: false };
  } catch {
    return { online: false, restored: false };
  }
}

// ============================================================================
// 5. REQUEST INTERCEPTOR: GẮN SESSION GENERATION, BEARER TOKEN & X-CSRF-TOKEN
// ============================================================================
axiosClient.interceptors.request.use(
  (config) => {
    config.headers = config.headers || {};

    const requestUrl = config.url || '';
    const isPublicOrAuthBootstrapRoute =
      requestUrl.includes('/auth/login') ||
      requestUrl.includes('/auth/register') ||
      requestUrl.includes('/auth/logout') ||
      requestUrl.includes('/health');

    // FIX-01: Ngăn login mới trong khi server logout đang pending để chống race condition xóa refresh cookie
    if (requestUrl.includes('/auth/login') && isLogoutInProgress()) {
      return Promise.reject(
        new Error(
          'Không thể gửi yêu cầu đăng nhập trong khi đang xử lý đăng xuất máy chủ.'
        )
      );
    }

    // Nếu là request retry: kiểm tra chặt thế hệ phiên và chính sách replay an toàn (FIX-03, FIX-04)
    if (config._retry) {
      if (
        typeof config._sessionGeneration !== 'number' ||
        config._sessionGeneration !== currentSessionGeneration ||
        !inMemoryToken
      ) {
        return Promise.reject(
          createStaleSessionError(
            config,
            'Hủy retry request do phiên làm việc đã thay đổi.'
          )
        );
      }
      if (!isSafeToReplayRequest(config)) {
        const replayErr = new Error(
          'Chặn tự động phát lại (replay) cho request thay đổi dữ liệu không có bảo đảm idempotency.'
        );
        replayErr.config = config;
        replayErr.isReplayBlocked = true;
        replayErr.code = 'ERR_UNSAFE_MUTATION_REPLAY';
        return Promise.reject(replayErr);
      }
    } else {
      if (typeof config._sessionGeneration !== 'number') {
        config._sessionGeneration = currentSessionGeneration;
      }
      const isAuthenticatedRequest =
        Boolean(inMemoryToken) && !isPublicOrAuthBootstrapRoute;
      config._hadAuthToken = isAuthenticatedRequest;
      config._isSessionBound = isAuthenticatedRequest;
      config._sentWithToken = isAuthenticatedRequest ? inMemoryToken : null;
    }

    if (inMemoryToken && !isPublicOrAuthBootstrapRoute) {
      config.headers.Authorization = `Bearer ${inMemoryToken}`;
    } else if (config.headers.Authorization && !isPublicOrAuthBootstrapRoute) {
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
// 6. RESPONSE INTERCEPTOR, STALE RESPONSE ISOLATION & SINGLE-FLIGHT REFRESH
// ============================================================================
axiosClient.interceptors.response.use(
  (response) => {
    const cfg = response?.config;
    const reqGen = cfg?._sessionGeneration;
    const requestUrl = cfg?.url || '';
    const isSessionBound = Boolean(cfg?._isSessionBound || cfg?._hadAuthToken);

    // FIX-03: Nếu là request gắn với phiên xác thực nhưng thế hệ phiên đã thay đổi
    // hoặc phiên hiện tại đã bị hủy -> Từ chối trả dữ liệu của phiên cũ cho caller.
    if (
      isSessionBound &&
      (typeof reqGen !== 'number' ||
        reqGen !== currentSessionGeneration ||
        !inMemoryToken)
    ) {
      return Promise.reject(
        createStaleSessionError(
          cfg,
          'Phản hồi thành công thuộc phiên làm việc cũ đã bị từ chối.'
        )
      );
    }

    const csrfHeader = response?.headers?.['x-csrf-token'];
    if (
      csrfHeader &&
      !requestUrl.includes('/auth/login') &&
      (typeof reqGen !== 'number' || reqGen === currentSessionGeneration)
    ) {
      setCsrfToken(csrfHeader);
    }
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    const status = error.response?.status;

    // FIX-03: Đánh dấu rõ lỗi thuộc phiên cũ nếu generation đã thay đổi
    if (
      originalRequest &&
      (originalRequest._isSessionBound || originalRequest._hadAuthToken) &&
      typeof originalRequest._sessionGeneration === 'number' &&
      originalRequest._sessionGeneration !== currentSessionGeneration
    ) {
      error.isStaleSession = true;
      error.code = error.code || 'ERR_STALE_SESSION';
      return Promise.reject(error);
    }

    // 1. Phân biệt rạch ròi lỗi 403 Forbidden:
    // Người dùng đã đăng nhập nhưng không đủ quyền -> Trả lỗi ngay, KHÔNG đăng xuất
    if (status === 403) {
      return Promise.reject(error);
    }

    if (!originalRequest || status !== 401) {
      return Promise.reject(error);
    }

    // 2. Bỏ qua logic refresh cho các route xác thực hoặc request đã retry (tối đa 1 lần)
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

    // 4. FIX-04: Ngăn chặn gọi refresh dư thừa khi response 401 đến muộn sau khi token đã được rotate
    const sentToken = originalRequest._sentWithToken;
    if (sentToken && inMemoryToken && sentToken !== inMemoryToken) {
      if (!isSafeToReplayRequest(originalRequest)) {
        error.isReplayBlocked = true;
        error.code = error.code || 'ERR_UNSAFE_MUTATION_REPLAY';
        return Promise.reject(error);
      }
      if (requestGeneration !== currentSessionGeneration || !inMemoryToken) {
        return Promise.reject(
          createStaleSessionError(
            originalRequest,
            'Phiên làm việc đã thay đổi trước khi retry request.'
          )
        );
      }
      originalRequest._retry = true;
      originalRequest._sessionGeneration = currentSessionGeneration;
      originalRequest._sentWithToken = inMemoryToken;
      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${inMemoryToken}`;
      return axiosClient(originalRequest);
    }

    // 5. Xử lý đồng thời (Single-Flight Concurrency) trong cùng một thế hệ phiên:
    if (isRefreshing && activeRefreshGeneration === requestGeneration) {
      return new Promise((resolve, reject) => {
        failedQueue.push({
          resolve,
          reject,
          generation: requestGeneration,
        });
      })
        .then((newToken) => {
          if (requestGeneration !== currentSessionGeneration || !inMemoryToken) {
            return Promise.reject(
              createStaleSessionError(
                originalRequest,
                'Phiên làm việc đã thay đổi, hủy retry request cũ.'
              )
            );
          }
          if (!isSafeToReplayRequest(originalRequest)) {
            error.isReplayBlocked = true;
            error.code = error.code || 'ERR_UNSAFE_MUTATION_REPLAY';
            return Promise.reject(error);
          }
          originalRequest._retry = true;
          originalRequest._sessionGeneration = currentSessionGeneration;
          originalRequest._sentWithToken = newToken;
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
        throw createStaleSessionError(
          originalRequest,
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
        throw createStaleSessionError(
          originalRequest,
          'Phiên làm việc bị đóng do dữ liệu xác thực trả về không hợp lệ.'
        );
      }

      processQueue(null, newAccessToken, requestGeneration);

      // FIX-04: Kiểm tra chính sách replay an toàn trước khi phát lại request gốc
      if (!isSafeToReplayRequest(originalRequest)) {
        error.isReplayBlocked = true;
        error.code = error.code || 'ERR_UNSAFE_MUTATION_REPLAY';
        return Promise.reject(error);
      }

      originalRequest._sessionGeneration = currentSessionGeneration;
      originalRequest._sentWithToken = newAccessToken;
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
