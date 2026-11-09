import axios from 'axios';

/**
 * ============================================================================
 * CẤU HÌNH TRUNG TÂM MẠNG & BẢO MẬT PHIÊN (RetailOps v1.0)
 * ============================================================================
 * - USE_MOCK = false: Gọi trực tiếp các endpoint thật của FastAPI Backend (`/api/v1/auth/*`).
 * - USE_MOCK = true: Chế độ giả lập tại Client khi chưa bật Docker Backend.
 *   Hệ thống tự động phát hiện trạng thái Backend qua `/api/v1/health` và cho phép
 *   chuyển đổi trực tiếp trên giao diện.
 */
export let USE_MOCK = true;

export function setUseMock(value) {
  USE_MOCK = Boolean(value);
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
    const detail = error.response.data?.detail || error.response.data?.message;
    if (typeof detail === 'string' && detail.trim().length > 0) {
      return detail;
    }
    if (status >= 500) {
      return 'Máy chủ FastAPI phản hồi lỗi kết nối hoặc dịch vụ tạm thời chưa sẵn sàng. Hãy đảm bảo Backend đang chạy tại cổng đã cấu hình.';
    }
    return `Máy chủ trả về trạng thái không mong đợi (HTTP ${status}).`;
  }

  return 'Không thể kết nối tới FastAPI Backend. Hãy kiểm tra dịch vụ Backend và cấu hình Vite proxy.';
}

// ============================================================================
// 1. QUẢN LÝ ACCESS TOKEN & CSRF TOKEN TRONG BỘ NHỚ RAM (IN-MEMORY)
// Tuyệt đối KHÔNG lưu vào localStorage hay sessionStorage để chống tấn công XSS
// ============================================================================
let inMemoryToken = null;
let inMemoryCsrfToken = null;

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
 * Phục vụ các mutation yêu cầu bảo vệ CSRF (`POST /auth/refresh`, `POST /auth/logout`).
 */
export async function ensureCsrfToken() {
  if (inMemoryCsrfToken) {
    return inMemoryCsrfToken;
  }
  try {
    const response = await axios.get(`${BASE_URL}/auth/csrf`, {
      withCredentials: true,
      headers: inMemoryToken
        ? { Authorization: `Bearer ${inMemoryToken}` }
        : {},
    });
    const token =
      response?.data?.csrf_token || response?.headers?.['x-csrf-token'] || null;
    if (token) {
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
  withCredentials: true, // Tự động đính kèm HttpOnly Refresh Cookie & CSRF Cookie
});

export const apiClient = axiosClient;

// ============================================================================
// 4. HÀM GỌI REFRESH TOKEN ĐỘC LẬP (TRÁNH INFINITE LOOP)
// Sử dụng `axios.post` gốc (KHÔNG đi qua axiosClient) để nếu /auth/refresh
// trả về 401 thì không bị Response Interceptor bắt lại gây vòng lặp vô tận.
// ============================================================================
export async function callRefreshTokenApi() {
  if (USE_MOCK) {
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve({
          data: {
            access_token: `mock-refreshed-token-${Date.now()}`,
          },
        });
      }, 600);
    });
  }

  // Đảm bảo có X-CSRF-Token theo đúng yêu cầu của Backend (/api/v1/auth/refresh)
  const csrfToken = inMemoryCsrfToken || (await ensureCsrfToken());

  const response = await axios.post(
    `${BASE_URL}/auth/refresh`,
    {},
    {
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
      },
      withCredentials: true,
    }
  );

  const nextCsrf = response?.headers?.['x-csrf-token'];
  if (nextCsrf) {
    setCsrfToken(nextCsrf);
  }

  return response;
}

// ============================================================================
// 5. REQUEST INTERCEPTOR: ĐÍNH KÈM BEARER TOKEN & X-CSRF-TOKEN VÀO HEADER
// ============================================================================
axiosClient.interceptors.request.use(
  (config) => {
    config.headers = config.headers || {};
    if (inMemoryToken) {
      config.headers.Authorization = `Bearer ${inMemoryToken}`;
    }
    if (inMemoryCsrfToken) {
      config.headers['X-CSRF-Token'] = inMemoryCsrfToken;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ============================================================================
// 6. RESPONSE INTERCEPTOR & HÀNG ĐỢI MUTEX (SINGLE-FLIGHT REFRESH KHI GẶP 401)
// ============================================================================
let isRefreshing = false;
let failedQueue = [];

/**
 * Giải phóng hoặc từ chối toàn bộ các request đang nằm chờ trong failedQueue
 */
function processQueue(error, token = null) {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else {
      promise.resolve(token);
    }
  });
  failedQueue = [];
}

axiosClient.interceptors.response.use(
  (response) => {
    // Tự động lưu X-CSRF-Token nếu Backend trả về trong response header (ví dụ sau /auth/login)
    const csrfHeader = response?.headers?.['x-csrf-token'];
    if (csrfHeader) {
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

    // Nếu không có config của request gốc hoặc không phải lỗi 401 -> Trả lỗi ngay
    if (!originalRequest || status !== 401) {
      return Promise.reject(error);
    }

    // 2. Bỏ qua logic refresh cho các route xác thực ban đầu
    const requestUrl = originalRequest.url || '';
    const isInitialAuthRoute =
      requestUrl.includes('/auth/login') ||
      requestUrl.includes('/auth/register') ||
      requestUrl.includes('/auth/refresh') ||
      requestUrl.includes('/auth/csrf');

    if (isInitialAuthRoute || originalRequest._retry) {
      return Promise.reject(error);
    }

    // 3. Xử lý đồng thời (Single-Flight Concurrency):
    // Nếu đang có 1 tiến trình refresh chạy, đẩy các request 401 đến sau vào failedQueue
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then((newToken) => {
          originalRequest.headers = originalRequest.headers || {};
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return axiosClient(originalRequest);
        })
        .catch((queueError) => Promise.reject(queueError));
    }

    // Đánh dấu request đầu tiên kích hoạt luồng làm mới token
    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const response = await callRefreshTokenApi();
      const newAccessToken =
        response?.data?.access_token || response?.data?.accessToken;

      if (!newAccessToken) {
        throw new Error('Không nhận được access_token mới từ API refresh');
      }

      // Kịch bản Refresh THÀNH CÔNG:
      // a) Lưu token mới vào biến cục bộ inMemoryToken
      setClientToken(newAccessToken);

      // b) Báo cho AuthContext cập nhật state accessToken (và user nếu có)
      if (authCallbacks.onTokenRefreshed) {
        authCallbacks.onTokenRefreshed(newAccessToken, response?.data?.user);
      }

      // c) Giải phóng toàn bộ các request đang chờ trong hàng đợi
      processQueue(null, newAccessToken);

      // d) Gắn token mới vào request gốc và thực hiện gọi lại (retry)
      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
      return axiosClient(originalRequest);
    } catch (refreshError) {
      // Kịch bản Refresh THẤT BẠI (Phiên hết hạn hoàn toàn):
      // a) Hủy toàn bộ hàng đợi đang chờ
      processQueue(refreshError, null);

      // b) Xóa sạch token trong RAM
      setClientToken(null);
      setCsrfToken(null);

      // c) Gọi callback để AuthContext thực hiện logout() và điều hướng về /login
      if (authCallbacks.onAuthFailed) {
        authCallbacks.onAuthFailed();
      }

      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default axiosClient;
