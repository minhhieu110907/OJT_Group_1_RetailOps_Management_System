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
  callRefreshTokenApi,
  ensureCsrfToken,
  getApiErrorMessage,
  getClientToken,
  getUseMock,
  invalidateSession,
  setClientToken,
  setCsrfToken,
  setUseMock,
  setupAxiosAuth,
} from '../api/axiosClient';
import { useToast } from '../components/common';

// 1. Tạo Context lưu trữ thông tin xác thực
const AuthContext = createContext(null);

// 5 Tài khoản mẫu cố định (Seed Accounts) của hệ thống RetailOps v1.0
const INITIAL_USERS = [
  {
    id: 'usr_admin_01',
    name: 'Nguyễn Minh Hiếu',
    email: 'minhhieu19692016@gmail.com',
    password: 'admin123',
    role: 'ADMIN',
    status: 'APPROVED',
  },
  {
    id: 'usr_staff_01',
    name: 'Cao Nguyễn Anh Dương',
    email: 'caoanhnguyenduong@gmail.com',
    password: 'staff123',
    role: 'STAFF',
    status: 'APPROVED',
  },
  {
    id: 'usr_staff_pending',
    name: 'Nguyễn Văn An',
    email: 'staff.pending@retailops.vn',
    password: 'staff123',
    role: 'STAFF',
    status: 'PENDING',
    submittedAt: '09:30 - 07/11/2026 (Asia/Ha_Noi)',
  },
  {
    id: 'usr_staff_rejected_locked',
    name: 'Trần Thị Bình',
    email: 'staff.rejected@retailops.vn',
    password: 'staff123',
    role: 'STAFF',
    status: 'REJECTED',
    rejectSubState: 'LOCKED_24H',
    submittedAt: '15:20 - 07/11/2026 (Asia/Ha_Noi)',
    rejectReason:
      'Email đăng ký chưa nằm trong danh sách phân ca nhân sự tháng 11/2026 tại cửa hàng. Vui lòng xác nhận lại với Cửa hàng trưởng trước khi gửi lại yêu cầu.',
  },
  {
    id: 'usr_staff_rejected_eligible',
    name: 'Lê Hoàng Nam',
    email: 'staff.reapply@retailops.vn',
    password: 'staff123',
    role: 'STAFF',
    status: 'REJECTED',
    rejectSubState: 'ELIGIBLE',
    submittedAt: '08:00 - 06/11/2026 (Asia/Ha_Noi)',
    rejectReason:
      'Thông tin ca trực đăng ký trước đó chưa khớp lịch phân công. Thời gian chờ 24 giờ đã hoàn tất, bạn có thể xác minh và gửi lại yêu cầu xét duyệt.',
  },
];

/**
 * Chuẩn hóa đối tượng user trả về từ FastAPI Backend (`AuthenticatedUser`)
 * sang định dạng thống nhất của giao diện Frontend.
 */
function normalizeBackendUser(rawUser, usersList = []) {
  if (!rawUser) return null;
  const email = (
    rawUser.email ||
    rawUser.email_normalized ||
    ''
  )
    .trim()
    .toLowerCase();

  const matchedLocal = usersList.find(
    (u) => u.email.toLowerCase() === email
  );

  const rawStatus = rawUser.status || 'ACTIVE';
  const mappedStatus =
    rawStatus === 'ACTIVE' ? 'APPROVED' : rawStatus;

  const fallbackName =
    rawUser.role === 'ADMIN'
      ? 'Quản trị viên (Admin)'
      : email
        ? email.split('@')[0]
        : 'Nhân viên RetailOps';

  return {
    id: rawUser.id,
    name: rawUser.name || matchedLocal?.name || fallbackName,
    email,
    role: rawUser.role || 'STAFF',
    status: mappedStatus,
    submittedAt: rawUser.submittedAt || matchedLocal?.submittedAt,
    rejectReason: rawUser.rejectReason || matchedLocal?.rejectReason,
    rejectSubState:
      rawUser.rejectSubState || matchedLocal?.rejectSubState || 'LOCKED_24H',
  };
}

// 2. Tạo Provider bọc ngoài ứng dụng
export function AuthProvider({ children }) {
  const toast = useToast();

  // Danh sách tài khoản tạm thời trong bộ nhớ
  const [usersList, setUsersList] = useState(INITIAL_USERS);

  // Lưu thông tin người dùng và Access Token hoàn toàn trong RAM (React State)
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);

  // Trạng thái kết nối với FastAPI Backend (Docker) & chế độ Mock/Real API
  const [backendOnline, setBackendOnline] = useState(false);
  const [isCheckingBackend, setIsCheckingBackend] = useState(true);
  const [isMockMode, setIsMockMode] = useState(getUseMock());
  const [authInitializing, setAuthInitializing] = useState(true);

  // Hàm đăng xuất: xóa sạch user, vô hiệu hóa session và token trong Context + axiosClient và thông báo Toast
  const logout = useCallback(
    async (isSessionExpired = false) => {
      invalidateSession();
      setAccessToken(null);
      setClientToken(null);
      setCsrfToken(null);
      setUser(null);

      if (!getUseMock()) {
        try {
          await ensureCsrfToken();
          await axiosClient.post('/auth/logout');
        } catch {
          // Bỏ qua lỗi mạng khi gọi logout để luôn dọn sạch trạng thái ở Client
        }
      }

      if (isSessionExpired === true) {
        toast.error('Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.');
      } else {
        toast.info('Đã đăng xuất khỏi hệ thống');
      }
    },
    [toast]
  );

  // Kết nối callback đồng bộ với axiosClient khi ứng dụng Mount
  useEffect(() => {
    setupAxiosAuth({
      onTokenRefreshed: (newToken, refreshedUser) => {
        setAccessToken(newToken);
        if (refreshedUser) {
          setUser((prev) =>
            normalizeBackendUser(refreshedUser, prev ? [prev] : INITIAL_USERS)
          );
        }
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
            try {
              const refreshRes = await callRefreshTokenApi();
              const restoredToken =
                refreshRes?.data?.access_token ||
                refreshRes?.data?.accessToken;
              const restoredUser = refreshRes?.data?.user;
              if (restoredToken && restoredUser) {
                setClientToken(restoredToken);
                setAccessToken(restoredToken);
                setUser(normalizeBackendUser(restoredUser, INITIAL_USERS));
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
        // Giữ vững nguyên tắc Fail-Closed và bảo mật môi trường.
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

  // Cho phép chuyển đổi thủ công giữa chế độ API thật (Backend) và Mock Data trên thanh Header
  const toggleMockMode = useCallback(async () => {
    // Luôn dọn sạch phiên hiện tại khi chuyển đổi chế độ để tránh rò rỉ phiên
    invalidateSession();
    setUser(null);
    setAccessToken(null);

    if (isMockMode) {
      const online = await checkBackendConnection({
        notify: false,
        forceRealIfOnline: true,
      });
      if (online) {
        setUseMock(false);
        setIsMockMode(false);
        toast.success('Đã chuyển sang chế độ API thật (FastAPI Backend).');
      } else {
        toast.warning(
          'Không thể bật API thật vì Backend chưa phản hồi. Đang giữ chế độ Mock.'
        );
      }
    } else {
      setUseMock(true);
      setIsMockMode(true);
      toast.info('Đã chuyển sang chế độ Mock Data (5 tài khoản mẫu).');
    }
  }, [isMockMode, checkBackendConnection, toast]);

  // Hàm đăng nhập: kiểm tra tài khoản, kiểm tra trạng thái hồ sơ (PENDING/REJECTED/APPROVED)
  const login = async (email, password) => {
    const normalizedEmail = (email || '').trim().toLowerCase();

    if (getUseMock()) {
      const foundUser = usersList.find(
        (u) =>
          u.email.toLowerCase() === normalizedEmail && u.password === password
      );

      if (!foundUser) {
        throw new Error('Thông tin đăng nhập không hợp lệ');
      }

      const accountStatus = foundUser.status || 'APPROVED';

      if (
        accountStatus === 'PENDING' ||
        accountStatus === 'PENDING_APPROVAL' ||
        accountStatus === 'REJECTED'
      ) {
        return {
          id: foundUser.id,
          name: foundUser.name,
          email: foundUser.email,
          role: foundUser.role,
          status: accountStatus,
          submittedAt: foundUser.submittedAt,
          rejectReason: foundUser.rejectReason,
          rejectSubState: foundUser.rejectSubState || 'LOCKED_24H',
        };
      }

      const sessionUser = {
        id: foundUser.id,
        name: foundUser.name,
        email: foundUser.email,
        role: foundUser.role,
        status: 'APPROVED',
      };

      const token = `mock-access-token-${foundUser.role.toLowerCase()}-${Date.now()}`;

      setAccessToken(token);
      setClientToken(token);
      setUser(sessionUser);

      toast.success(`Đăng nhập thành công! Xin chào ${sessionUser.name}`);
      return sessionUser;
    }

    // Khi USE_MOCK = false -> Gọi API POST /api/v1/auth/login thật lên FastAPI Backend
    try {
      const response = await axiosClient.post('/auth/login', {
        email: normalizedEmail,
        password,
      });

      const token =
        response?.data?.access_token || response?.data?.accessToken;
      const csrfHeader = response?.headers?.['x-csrf-token'];
      if (csrfHeader) {
        setCsrfToken(csrfHeader);
      }

      const loggedInUser = normalizeBackendUser(
        response?.data?.user,
        []
      );

      if (
        loggedInUser?.status === 'PENDING' ||
        loggedInUser?.status === 'PENDING_APPROVAL' ||
        loggedInUser?.status === 'REJECTED'
      ) {
        return loggedInUser;
      }

      setAccessToken(token);
      setClientToken(token);
      setUser(loggedInUser);

      toast.success(
        `Đăng nhập thành công! Xin chào ${loggedInUser?.name || ''}`
      );
      return loggedInUser;
    } catch (error) {
      // TUYỆT ĐỐI KHÔNG can thiệp hoặc fallback sang mock usersList khi ở Real API mode
      const msg = getApiErrorMessage(error);
      throw new Error(msg || 'Thông tin đăng nhập không chính xác hoặc tài khoản chưa sẵn sàng.');
    }
  };

  // Hàm đăng ký tài khoản mới từ Register.jsx -> gọi POST /api/v1/auth/register khi nối BE
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

    if (getUseMock()) {
      const newUser = {
        id: `usr_staff_${Date.now()}`,
        name: (userData.fullName || 'Nhân viên mới').trim(),
        email: normalizedEmail,
        password: userData.password,
        role: 'STAFF',
        status: userData.status || 'PENDING',
        submittedAt: `${nowFormatted} (Asia/Ha_Noi)`,
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

    // Khi USE_MOCK = false -> Gọi API POST /api/v1/auth/register thật lên FastAPI Backend
    // Backend RegisterRequest có extra="forbid", chỉ nhận { email, password }
    try {
      const res = await axiosClient.post('/auth/register', {
        email: normalizedEmail,
        password: userData.password,
      });

      // Trả thông tin trạng thái để chuyển sang /account-status (PENDING)
      // TUYỆT ĐỐI KHÔNG lưu mật khẩu hoặc tạo user giả trong usersList
      return {
        id: `pending_${Date.now()}`,
        name: (userData.fullName || 'Nhân viên mới').trim(),
        email: normalizedEmail,
        role: 'STAFF',
        status: 'PENDING',
        submittedAt: `${nowFormatted} (Asia/Ha_Noi)`,
        message: res.data?.message,
      };
    } catch (error) {
      const msg = getApiErrorMessage(error);
      throw new Error(msg || 'Không thể gửi yêu cầu đăng ký tới máy chủ.');
    }
  };

  // Hàm đặt lại/đổi mật khẩu cho người dùng
  const resetPassword = (targetEmail, newPassword) => {
    const normalizedEmail = (targetEmail || '').trim().toLowerCase();
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

  // Helper lấy thông tin người dùng mẫu theo email
  const getUserByEmail = (searchEmail) => {
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
        usersList,
        backendOnline,
        isCheckingBackend,
        isMockMode,
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
