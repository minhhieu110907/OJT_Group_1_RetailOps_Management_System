import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import axiosClient, {
  beginLoginAttempt,
  callLogoutApi,
  canCommitLoginAttempt,
  commitLoginSession,
  getApiErrorMessage,
  getClientToken,
  getCsrfToken,
  getSessionGeneration,
  getUseMock,
  invalidateSession,
  isLogoutInProgress,
  isMockAllowed,
  normalizeBackendUser,
  runHealthCheck,
  setupAxiosAuth,
  transitionAuthMode,
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
    submittedAt: '09:30 - 07/11/2026',
  },
  {
    id: 'usr_staff_rejected_locked',
    name: 'Nhân viên Từ chối Tạm khóa (Demo)',
    email: 'rejected.locked@retailops.local',
    password: 'DemoPassword123',
    role: 'STAFF',
    status: 'REJECTED',
    rejectSubState: 'LOCKED_24H',
    submittedAt: '15:20 - 07/11/2026',
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
    submittedAt: '08:00 - 06/11/2026',
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
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  // Hàm đăng xuất (FIX-04, Hardening FIX-01, FIX-03):
  // - Chụp snapshot token/CSRF trước khi hủy phiên local để gửi request revoke hợp lệ lên Server.
  // - Vô hiệu hóa ngay lập tức phiên ở Client (tăng session generation, chặn mọi request/refresh cũ).
  // - Bật cờ `isLoggingOut` để ngăn mọi login race trong khi server revoke đang xử lý.
  // - Chuẩn hóa kết quả trả về `{ serverRevoked, localOnly }` là Single Source of Truth cho toàn bộ ứng dụng.
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
        return { serverRevoked: false, localOnly: true, sessionExpired: true };
      }

      if (wasMock) {
        toast.info('Đã đăng xuất khỏi chế độ mô phỏng (Mock).');
        return { serverRevoked: true, localOnly: false, isMock: true };
      }

      setIsLoggingOut(true);
      try {
        const result = await callLogoutApi({
          accessToken: tokenSnapshot,
          csrfToken: csrfSnapshot,
        });

        if (result.revoked) {
          toast.info('Đã đăng xuất khỏi hệ thống.');
          return { serverRevoked: true, localOnly: false };
        } else {
          toast.warning(
            'Đã kết thúc phiên trên thiết bị này, nhưng chưa xác nhận được hủy phiên trên máy chủ.'
          );
          return { serverRevoked: false, localOnly: true };
        }
      } finally {
        setIsLoggingOut(false);
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
      onSessionInvalidated: ({ isMockMode: nextMockMode }) => {
        setAccessToken(null);
        setUser(null);
        setIsMockMode(Boolean(nextMockMode && isMockAllowed()));
      },
    });
  }, [logout]);

  // Kiểm tra kết nối tới FastAPI Backend (`/api/v1/health`) và tùy chọn khôi phục phiên lúc khởi động (FIX-02):
  // - Health check chỉ xác nhận trạng thái kết nối, TUYỆT ĐỐI KHÔNG tự ý đổi chế độ Mock <-> Real.
  // - Không ghi đè phiên hợp lệ hiện có và không khôi phục cookie trong một callback đã lỗi thời.
  const checkBackendConnection = useCallback(
    async ({ notify = false, allowSessionRestore = false } = {}) => {
      await Promise.resolve();
      setIsCheckingBackend(true);
      try {
        const result = await runHealthCheck({
          allowSessionRestore,
          onRestoredSession: ({
            accessToken: restoredToken,
            user: restoredUser,
            generation,
          }) => {
            if (generation === getSessionGeneration() && !getUseMock()) {
              setAccessToken(restoredToken);
              setUser(restoredUser);
            }
          },
        });

        setBackendOnline(Boolean(result.online));

        if (result.online) {
          if (notify) {
            toast.success(
              getUseMock() && isMockAllowed()
                ? 'FastAPI Backend đang trực tuyến (Hệ thống hiện giữ chế độ Mock Demo).'
                : 'Đã kết nối thành công với FastAPI Backend! Hệ thống đang dùng API thật (/api/v1).'
            );
          }
          return true;
        }

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

  // Tự động kiểm tra kết nối Backend và thử khôi phục phiên từ Cookie ngay khi mở ứng dụng
  useEffect(() => {
    const timer = setTimeout(() => {
      checkBackendConnection({ notify: false, allowSessionRestore: true });
    }, 0);
    return () => clearTimeout(timer);
  }, [checkBackendConnection]);

  // Chuyển đổi thủ công giữa chế độ API thật và Mock Data qua cơ chế transition duy nhất (FIX-02):
  // Chỉ được phép khi isMockAllowed() === true (Development + VITE_USE_MOCK=true)
  const toggleMockMode = useCallback(async () => {
    if (!isMockAllowed()) {
      transitionAuthMode(false);
      setIsMockMode(false);
      setUser(null);
      setAccessToken(null);
      toast.warning(
        'Chế độ Mock đã bị khóa trong môi trường hiện tại. Hệ thống bắt buộc sử dụng API thật.'
      );
      return false;
    }

    const targetMock = !getUseMock();
    const transition = transitionAuthMode(targetMock);
    setUser(null);
    setAccessToken(null);
    setIsMockMode(transition.isMockMode);

    if (!transition.isMockMode) {
      const online = await checkBackendConnection({
        notify: false,
        allowSessionRestore: false,
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

    toast.info('Đã chuyển sang chế độ Mock Demo (Dữ liệu mẫu phát triển).');
    return true;
  }, [checkBackendConnection, toast]);

  // Hàm đăng nhập có bảo vệ Session Generation, Attempt ID & Logout Race Guard (FIX-01)
  const login = async (email, password) => {
    if (isLoggingOut || isLogoutInProgress()) {
      throw new Error(
        'Đang hoàn tất quá trình đăng xuất. Vui lòng đợi trong giây lát trước khi đăng nhập lại.'
      );
    }

    const normalizedEmail = (email || '').trim().toLowerCase();
    const loginAttempt = beginLoginAttempt();

    if (loginAttempt.isMock) {
      const foundUser = usersList.find(
        (u) =>
          u.email.toLowerCase() === normalizedEmail && u.password === password
      );

      if (!foundUser) {
        throw new Error('Thông tin đăng nhập không hợp lệ');
      }

      if (!canCommitLoginAttempt(loginAttempt)) {
        throw new Error(
          'Phiên đăng nhập hoặc chế độ xác thực đã thay đổi. Vui lòng thử lại.'
        );
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
      const commitResult = commitLoginSession(loginAttempt, {
        accessToken: token,
        csrfToken: null,
        user: sessionUser,
      });

      if (!commitResult.committed) {
        throw new Error(
          'Phiên đăng nhập hoặc chế độ xác thực đã thay đổi. Vui lòng thử lại.'
        );
      }

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

      // FIX-01: Nếu trong lúc chờ phản hồi, người dùng đã đổi mode, logout hoặc có lần login mới hơn ->
      // Từ chối ngay, TUYỆT ĐỐI KHÔNG ghi đè phiên mới hoặc hiển thị thông báo thành công.
      if (!canCommitLoginAttempt(loginAttempt)) {
        throw new Error(
          'Phiên đăng nhập hoặc chế độ xác thực đã thay đổi. Vui lòng thử lại.'
        );
      }

      const token =
        response?.data?.access_token || response?.data?.accessToken;
      const csrfHeader = response?.headers?.['x-csrf-token'] || null;
      const loggedInUser = normalizeBackendUser(response?.data?.user);

      if (!loggedInUser) {
        if (canCommitLoginAttempt(loginAttempt)) {
          invalidateSession();
          setAccessToken(null);
          setUser(null);
        }
        throw new Error(
          'Dữ liệu người dùng từ máy chủ không hợp lệ hoặc thiếu trường bắt buộc.'
        );
      }

      if (
        loggedInUser.status === 'PENDING' ||
        loggedInUser.status === 'PENDING_APPROVAL' ||
        loggedInUser.status === 'REJECTED'
      ) {
        if (!canCommitLoginAttempt(loginAttempt)) {
          throw new Error(
            'Phiên đăng nhập hoặc chế độ xác thực đã thay đổi. Vui lòng thử lại.'
          );
        }
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
        if (canCommitLoginAttempt(loginAttempt)) {
          invalidateSession();
          setAccessToken(null);
          setUser(null);
        }
        throw new Error('Máy chủ không cấp phiên xác thực hợp lệ.');
      }

      const commitResult = commitLoginSession(loginAttempt, {
        accessToken: token,
        csrfToken: csrfHeader,
        user: loggedInUser,
      });

      if (!commitResult.committed) {
        throw new Error(
          'Phiên đăng nhập hoặc chế độ xác thực đã thay đổi. Vui lòng thử lại.'
        );
      }

      setAccessToken(token);
      setUser(loggedInUser);

      toast.success(
        `Đăng nhập thành công! Xin chào ${loggedInUser.name || ''}`
      );
      return loggedInUser;
    } catch (error) {
      // TUYỆT ĐỐI KHÔNG can thiệp hoặc fallback sang mock usersList khi ở Real API mode
      const msg = getApiErrorMessage(error) || error?.message;
      const authError = new Error(
        msg ||
          'Thông tin đăng nhập không chính xác hoặc tài khoản chưa sẵn sàng.'
      );
      if (error?.response?.data?.code) {
        authError.code = error.response.data.code;
      }
      throw authError;
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
        submittedAt: nowFormatted,
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
        submittedAt: nowFormatted,
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
        isLoggingOut,
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
