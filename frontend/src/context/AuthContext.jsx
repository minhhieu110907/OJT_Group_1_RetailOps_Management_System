import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import axios from 'axios';
import axiosClient, {
  BASE_URL,
  callLogoutApi,
  callRefreshTokenApi,
  getApiErrorMessage,
  getClientToken,
  getCsrfToken,
  getSessionGeneration,
  getUseMock,
  invalidateSession,
  isMockAllowed,
  normalizeBackendUser,
  setUseMock,
  setupAxiosAuth,
  startAuthenticatedSession,
} from '../api/axiosClient';
import { useToast } from '../components/common';

// 1. Tạo Context lưu trữ thông tin xác thực
const AuthContext = createContext(null);

// 5 Tài khoản mẫu không nhạy cảm (Synthetic Demo Accounts) chỉ dùng trong môi trường DEV khi bật Mock
const INITIAL_USERS = [
  {
    id: 'usr_admin_demo',
    name: 'Quản trị viên Demo',
    email: 'admin.demo@retailops.local',
    password: 'DemoPassword123',
    role: 'ADMIN',
    status: 'APPROVED',
  },
  {
    id: 'usr_staff_demo',
    name: 'Nhân viên Bán hàng Demo',
    email: 'staff.demo@retailops.local',
    password: 'DemoPassword123',
    role: 'STAFF',
    status: 'APPROVED',
  },
  {
    id: 'usr_staff_pending',
    name: 'Nhân viên Chờ duyệt (Demo)',
    email: 'pending.demo@retailops.local',
    password: 'DemoPassword123',
    role: 'STAFF',
    status: 'PENDING',
    submittedAt: '09:30 - 07/11/2026 (Asia/Ha_Noi)',
  },
  {
    id: 'usr_staff_rejected_locked',
    name: 'Nhân viên Từ chối Tạm khóa (Demo)',
    email: 'rejected.locked@retailops.local',
    password: 'DemoPassword123',
    role: 'STAFF',
    status: 'REJECTED',
    rejectSubState: 'LOCKED_24H',
    submittedAt: '15:20 - 07/11/2026 (Asia/Ha_Noi)',
    rejectReason:
      'Email đăng ký chưa nằm trong danh sách nhân sự tại cửa hàng. Vui lòng xác nhận lại với Quản trị viên trước khi gửi lại yêu cầu.',
  },
  {
    id: 'usr_staff_rejected_eligible',
    name: 'Nhân viên Đủ điều kiện Gửi lại (Demo)',
    email: 'rejected.eligible@retailops.local',
    password: 'DemoPassword123',
    role: 'STAFF',
    status: 'REJECTED',
    rejectSubState: 'ELIGIBLE',
    submittedAt: '08:00 - 06/11/2026 (Asia/Ha_Noi)',
    rejectReason:
      'Thông tin đăng ký trước đó chưa khớp hồ sơ nội bộ. Thời gian chờ 24 giờ đã hoàn tất, bạn có thể xác minh và gửi lại yêu cầu xét duyệt.',
  },
];

// 2. Tạo Provider bọc ngoài ứng dụng
export function AuthProvider({ children }) {
  const toast = useToast();
  const canUseMock = isMockAllowed();

  // Danh sách tài khoản mẫu trong bộ nhớ (chỉ hiệu lực khi canUseMock && isMockMode)
  const [usersList, setUsersList] = useState(INITIAL_USERS);

  // Lưu thông tin người dùng và Access Token hoàn toàn trong RAM (React State)
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);

  // Trạng thái kết nối với FastAPI Backend & chế độ Mock/Real API
  const [backendOnline, setBackendOnline] = useState(false);
  const [isCheckingBackend, setIsCheckingBackend] = useState(true);
  const [isMockMode, setIsMockMode] = useState(() =>
    canUseMock ? getUseMock() : false
  );
  const [authInitializing, setAuthInitializing] = useState(true);

  // Hàm đăng xuất (FIX-04):
  // - Chụp snapshot token/CSRF trước khi hủy phiên local để gửi request revoke hợp lệ lên Server.
  // - Vô hiệu hóa ngay lập tức phiên ở Client (tăng session generation, chặn mọi request/refresh cũ).
  // - Phân biệt rõ trường hợp Server xác nhận revoke (204) và trường hợp chỉ đóng được phiên trên thiết bị.
  const logout = useCallback(
    async (isSessionExpired = false) => {
      const tokenSnapshot = getClientToken();
      const csrfSnapshot = getCsrfToken();
      const wasMock = getUseMock() && isMockAllowed();

      invalidateSession();
      setAccessToken(null);
      setUser(null);

      if (isSessionExpired === true) {
        toast.error('Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.');
        return;
      }

      if (wasMock) {
        toast.info('Đã đăng xuất khỏi chế độ mô phỏng (Mock).');
        return;
      }

      const result = await callLogoutApi({
        accessToken: tokenSnapshot,
        csrfToken: csrfSnapshot,
      });

      if (result.revoked) {
        toast.info('Đã đăng xuất khỏi hệ thống.');
      } else {
        toast.warning(
          'Đã kết thúc phiên trên thiết bị này, nhưng chưa xác nhận được hủy phiên trên máy chủ.'
        );
      }
    },
    [toast]
  );

  // Kết nối callback đồng bộ với axiosClient khi ứng dụng Mount
  useEffect(() => {
    setupAxiosAuth({
      onTokenRefreshed: (newToken, refreshedUser, refreshGen) => {
        if (refreshGen !== getSessionGeneration()) {
          return;
        }
        if (refreshedUser !== undefined) {
          const normalized = normalizeBackendUser(refreshedUser);
          if (!normalized || normalized.status !== 'APPROVED') {
            invalidateSession();
            setAccessToken(null);
            setUser(null);
            return;
          }
          setUser(normalized);
        }
        setAccessToken(newToken);
      },
      onAuthFailed: () => logout(true),
    });
  }, [logout]);

  // Kiểm tra kết nối tới FastAPI Backend (`/api/v1/health`) và tự động khôi phục phiên nếu có Cookie
  const checkBackendConnection = useCallback(
    async ({ notify = false, forceRealIfOnline = false } = {}) => {
      await Promise.resolve();
      setIsCheckingBackend(true);
      try {
        const res = await axios.get(`${BASE_URL}/health`, {
          timeout: 2500,
        });
        const isHealthy =
          res.status === 200 &&
          (res.data?.status === 'ok' || res.data?.status === 'healthy');

        if (isHealthy) {
          setBackendOnline(true);
          if (forceRealIfOnline) {
            setUseMock(false);
            setIsMockMode(false);
          }
          if (notify) {
            toast.success(
              'Đã kết nối thành công với FastAPI Backend! Hệ thống đang dùng API thật (/api/v1).'
            );
          }

          // Thử khôi phục phiên đăng nhập từ HttpOnly Refresh Cookie (nếu người dùng vừa bấm F5)
          if (!getUseMock() && !getClientToken()) {
            const restoreGen = getSessionGeneration();
            try {
              const refreshRes = await callRefreshTokenApi(restoreGen);
              if (restoreGen !== getSessionGeneration()) {
                return true;
              }
              const restoredToken =
                refreshRes?.data?.access_token ||
                refreshRes?.data?.accessToken;
              const restoredCsrf =
                refreshRes?.headers?.['x-csrf-token'] || null;
              const restoredUser = normalizeBackendUser(
                refreshRes?.data?.user
              );

              if (
                restoredToken &&
                typeof restoredToken === 'string' &&
                restoredUser &&
                restoredUser.status === 'APPROVED'
              ) {
                startAuthenticatedSession(restoredToken, restoredCsrf);
                setAccessToken(restoredToken);
                setUser(restoredUser);
              } else {
                invalidateSession();
                setAccessToken(null);
                setUser(null);
              }
            } catch {
              // Không có cookie phiên cũ hoặc phiên đã hết hạn -> giữ trạng thái chưa đăng nhập
            }
          }
          return true;
        }
        throw new Error('Unhealthy');
      } catch {
        setBackendOnline(false);
        // TUYỆT ĐỐI KHÔNG tự động chuyển USE_MOCK sang true khi kiểm tra thất bại!
        if (notify) {
          toast.warning(
            'Không thể kết nối tới FastAPI Backend. Vui lòng kiểm tra lại dịch vụ Backend.'
          );
        }
        return false;
      } finally {
        setIsCheckingBackend(false);
        setAuthInitializing(false);
      }
    },
    [toast]
  );

  // Tự động kiểm tra kết nối Backend ngay khi mở ứng dụng
  useEffect(() => {
    const timer = setTimeout(() => {
      checkBackendConnection({ notify: false });
    }, 0);
    return () => clearTimeout(timer);
  }, [checkBackendConnection]);

  // Chuyển đổi thủ công giữa chế độ API thật và Mock Data:
  // Chỉ được phép khi isMockAllowed() === true (Development + VITE_USE_MOCK=true)
  const toggleMockMode = useCallback(async () => {
    if (!isMockAllowed()) {
      setUseMock(false);
      setIsMockMode(false);
      toast.warning(
        'Chế độ Mock đã bị khóa trong môi trường hiện tại. Hệ thống bắt buộc sử dụng API thật.'
      );
      return false;
    }

    // Luôn hủy phiên hiện tại khi chuyển đổi chế độ để không mang theo user/token cũ
    invalidateSession();
    setUser(null);
    setAccessToken(null);

    if (isMockMode) {
      setUseMock(false);
      setIsMockMode(false);
      const online = await checkBackendConnection({
        notify: false,
        forceRealIfOnline: true,
      });
      if (online) {
        toast.success('Đã chuyển sang chế độ API thật (FastAPI Backend).');
      } else {
        toast.warning(
          'Đã chuyển sang chế độ API thật, nhưng hiện chưa kết nối được FastAPI Backend.'
        );
      }
      return false;
    }

    const enabled = setUseMock(true);
    setIsMockMode(enabled);
    if (enabled) {
      toast.info('Đã chuyển sang chế độ Mock Demo (Dữ liệu mẫu phát triển).');
    }
    return enabled;
  }, [isMockMode, checkBackendConnection, toast]);

  // Hàm đăng nhập
  const login = async (email, password) => {
    const normalizedEmail = (email || '').trim().toLowerCase();

    if (getUseMock() && isMockAllowed()) {
      const foundUser = usersList.find(
        (u) =>
          u.email.toLowerCase() === normalizedEmail && u.password === password
      );

      if (!foundUser) {
        throw new Error('Thông tin đăng nhập không hợp lệ');
      }

      const accountStatus = foundUser.status || 'PENDING';

      if (
        accountStatus === 'PENDING' ||
        accountStatus === 'PENDING_APPROVAL' ||
        accountStatus === 'REJECTED'
      ) {
        invalidateSession();
        setAccessToken(null);
        setUser(null);
        return {
          id: foundUser.id,
          name: foundUser.name,
          email: foundUser.email,
          role: foundUser.role,
          status: accountStatus,
          submittedAt: foundUser.submittedAt,
          rejectReason: foundUser.rejectReason,
          rejectSubState: foundUser.rejectSubState || 'LOCKED_24H',
          isMock: true,
        };
      }

      const sessionUser = {
        id: foundUser.id,
        name: foundUser.name,
        email: foundUser.email,
        role: foundUser.role,
        status: 'APPROVED',
        isMock: true,
      };

      const token = `mock-access-token-${foundUser.role.toLowerCase()}-${Date.now()}`;

      startAuthenticatedSession(token, null);
      setAccessToken(token);
      setUser(sessionUser);

      toast.success(
        `Đăng nhập thành công (Mock Demo)! Xin chào ${sessionUser.name}`
      );
      return sessionUser;
    }

    // Khi ở Real API Mode -> Gọi API POST /api/v1/auth/login thật lên FastAPI Backend
    try {
      const response = await axiosClient.post('/auth/login', {
        email: normalizedEmail,
        password,
      });

      const token =
        response?.data?.access_token || response?.data?.accessToken;
      const csrfHeader = response?.headers?.['x-csrf-token'] || null;
      const loggedInUser = normalizeBackendUser(response?.data?.user);

      if (!loggedInUser) {
        invalidateSession();
        setAccessToken(null);
        setUser(null);
        throw new Error(
          'Dữ liệu người dùng từ máy chủ không hợp lệ hoặc thiếu trường bắt buộc.'
        );
      }

      if (
        loggedInUser.status === 'PENDING' ||
        loggedInUser.status === 'PENDING_APPROVAL' ||
        loggedInUser.status === 'REJECTED'
      ) {
        invalidateSession();
        setAccessToken(null);
        setUser(null);
        return loggedInUser;
      }

      if (
        loggedInUser.status !== 'APPROVED' ||
        !token ||
        typeof token !== 'string'
      ) {
        invalidateSession();
        setAccessToken(null);
        setUser(null);
        throw new Error('Máy chủ không cấp phiên xác thực hợp lệ.');
      }

      startAuthenticatedSession(token, csrfHeader);
      setAccessToken(token);
      setUser(loggedInUser);

      toast.success(
        `Đăng nhập thành công! Xin chào ${loggedInUser.name || ''}`
      );
      return loggedInUser;
    } catch (error) {
      // TUYỆT ĐỐI KHÔNG can thiệp hoặc fallback sang mock usersList khi ở Real API mode
      const msg = getApiErrorMessage(error);
      throw new Error(
        msg ||
          'Thông tin đăng nhập không chính xác hoặc tài khoản chưa sẵn sàng.'
      );
    }
  };

  // Hàm đăng ký tài khoản mới (FIX-05)
  const register = async (userData) => {
    const normalizedEmail = (userData.email || '').trim().toLowerCase();
    const nowFormatted = new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date());

    if (getUseMock() && isMockAllowed()) {
      const newUser = {
        id: `usr_staff_mock_${Date.now()}`,
        name: (userData.fullName || 'Nhân viên mẫu').trim(),
        email: normalizedEmail,
        password: userData.password,
        role: 'STAFF',
        status: userData.status || 'PENDING',
        submittedAt: `${nowFormatted} (Asia/Ha_Noi)`,
        isMock: true,
      };

      setUsersList((prev) => {
        const exists = prev.some(
          (u) => u.email.toLowerCase() === normalizedEmail
        );
        if (exists) {
          return prev.map((u) =>
            u.email.toLowerCase() === normalizedEmail ? newUser : u
          );
        }
        return [...prev, newUser];
      });

      return newUser;
    }

    // Real API Mode -> Gọi POST /api/v1/auth/register (chỉ gửi { email, password } theo extra="forbid")
    try {
      const res = await axiosClient.post('/auth/register', {
        email: normalizedEmail,
        password: userData.password,
      });

      // Backend trả HTTP 202 {"message": "..."} chung chống dò quét email:
      // Không sinh User ID giả, không khẳng định chắc chắn tài khoản đã được tạo mới ở trạng thái PENDING,
      // và không lưu mật khẩu hay user vào RAM.
      return {
        accepted: true,
        isMock: false,
        status: 'SUBMITTED',
        fullName: (userData.fullName || '').trim(),
        email: normalizedEmail,
        submittedAt: `${nowFormatted} (Asia/Ha_Noi)`,
        message:
          res?.data?.message ||
          'Nếu thông tin đăng ký hợp lệ, Quản trị viên sẽ xem xét yêu cầu của bạn.',
      };
    } catch (error) {
      const msg = getApiErrorMessage(error);
      throw new Error(msg || 'Không thể gửi yêu cầu đăng ký tới máy chủ.');
    }
  };

  // Hàm đặt lại/đổi mật khẩu: Chỉ cho phép trong chế độ Mock Demo khi được phép (FIX-03)
  const resetPassword = (targetEmail, newPassword) => {
    if (!getUseMock() || !isMockAllowed()) {
      return false;
    }
    const normalizedEmail = (targetEmail || '').trim().toLowerCase();
    if (!normalizedEmail || !newPassword) {
      return false;
    }
    setUsersList((prev) =>
      prev.map((u) => {
        if (u.email.toLowerCase() === normalizedEmail) {
          return { ...u, password: newPassword };
        }
        return u;
      })
    );
    return true;
  };

  // Helper lấy thông tin người dùng mẫu theo email: Cô lập hoàn toàn khỏi Real API mode
  const getUserByEmail = (searchEmail) => {
    if (!getUseMock() || !isMockAllowed()) {
      return null;
    }
    const normalizedEmail = (searchEmail || '').trim().toLowerCase();
    return (
      usersList.find((u) => u.email.toLowerCase() === normalizedEmail) || null
    );
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        usersList: canUseMock && isMockMode ? usersList : [],
        backendOnline,
        isCheckingBackend,
        isMockMode: canUseMock && isMockMode,
        canUseMock,
        authInitializing,
        checkBackendConnection,
        toggleMockMode,
        login,
        register,
        logout,
        resetPassword,
        getUserByEmail,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// 3. Custom Hook giúp lấy nhanh dữ liệu từ AuthContext ở bất kỳ component nào
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth phải được sử dụng bên trong <AuthProvider>');
  }
  return context;
}
