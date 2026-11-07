import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axiosClient, {
  USE_MOCK,
  setClientToken,
  setupAxiosAuth,
} from '../api/axiosClient';
import { useToast } from '../components/common';

// 1. Tạo Context lưu trữ thông tin xác thực
const AuthContext = createContext(null);

// 2 Tài khoản mẫu cố định (Seed Accounts) của hệ thống RetailOps v1.0
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

// 2. Tạo Provider bọc ngoài ứng dụng
export function AuthProvider({ children }) {
  const toast = useToast();

  // Danh sách tài khoản tạm thời trong bộ nhớ
  const [usersList, setUsersList] = useState(INITIAL_USERS);

  // Lưu thông tin người dùng và Access Token hoàn toàn trong RAM (React State)
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);

  // Hàm đăng xuất: xóa sạch user, xóa token trong Context + axiosClient và thông báo Toast
  const logout = useCallback(
    async (isSessionExpired = false) => {
      if (!USE_MOCK) {
        try {
          await axiosClient.post('/auth/logout');
        } catch {
          // Bỏ qua lỗi mạng khi gọi logout để luôn dọn sạch trạng thái ở Client
        }
      }

      setAccessToken(null);
      setClientToken(null);
      setUser(null);

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
      onTokenRefreshed: (newToken) => setAccessToken(newToken),
      onAuthFailed: () => logout(true),
    });
  }, [logout]);

  // Hàm đăng nhập: kiểm tra tài khoản, kiểm tra trạng thái hồ sơ (PENDING/REJECTED/APPROVED)
  const login = async (email, password) => {
    const normalizedEmail = (email || '').trim().toLowerCase();

    if (USE_MOCK) {
      const foundUser = usersList.find(
        (u) =>
          u.email.toLowerCase() === normalizedEmail && u.password === password
      );

      if (!foundUser) {
        throw new Error('Thông tin đăng nhập không hợp lệ');
      }

      const accountStatus = foundUser.status || 'APPROVED';

      // Nếu tài khoản đang chờ duyệt (PENDING) hoặc bị từ chối (REJECTED):
      // Không cấp Access Token vào phiên, trả về thông tin hồ sơ để Login.jsx điều hướng sang /account-status
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

      // Đồng bộ token vào Context state và biến inMemoryToken của axiosClient
      setAccessToken(token);
      setClientToken(token);
      setUser(sessionUser);

      toast.success(`Đăng nhập thành công! Xin chào ${sessionUser.name}`);
      return sessionUser;
    }

    // Khi USE_MOCK = false -> Gọi API POST /auth/login thật lên Backend
    const response = await axiosClient.post('/auth/login', {
      email: normalizedEmail,
      password,
    });
    const token =
      response?.data?.accessToken || response?.data?.access_token;
    const loggedInUser = response?.data?.user;

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

    toast.success(`Đăng nhập thành công! Xin chào ${loggedInUser?.name || ''}`);
    return loggedInUser;
  };

  // Hàm đăng ký tài khoản mới từ Register.jsx -> khởi tạo với role: 'STAFF' và status: 'PENDING'
  const register = (userData) => {
    const normalizedEmail = (userData.email || '').trim().toLowerCase();
    const nowFormatted = new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date());

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
      const exists = prev.some((u) => u.email.toLowerCase() === normalizedEmail);
      if (exists) {
        return prev.map((u) =>
          u.email.toLowerCase() === normalizedEmail ? newUser : u
        );
      }
      return [...prev, newUser];
    });

    return newUser;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        usersList,
        login,
        register,
        logout,
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
