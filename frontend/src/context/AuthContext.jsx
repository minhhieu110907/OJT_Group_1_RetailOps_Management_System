import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axiosClient, {
  USE_MOCK,
  callRefreshTokenApi,
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
  },
  {
    id: 'usr_staff_01',
    name: 'Cao Nguyễn Anh Dương',
    email: 'caoanhnguyenduong@gmail.com',
    password: 'staff123',
    role: 'STAFF',
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
  const [isInitializing, setIsInitializing] = useState(!USE_MOCK);

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

  // Silent Refresh khi ứng dụng khởi chạy lần đầu (F5 / Reload) ở chế độ Backend thật
  useEffect(() => {
    if (USE_MOCK) {
      return;
    }

    let isMounted = true;

    async function bootstrapSession() {
      try {
        const response = await callRefreshTokenApi();
        const newToken =
          response?.data?.accessToken || response?.data?.access_token;
        const sessionUser = response?.data?.user;

        if (isMounted && newToken) {
          setAccessToken(newToken);
          setClientToken(newToken);
          if (sessionUser) {
            setUser({
              ...sessionUser,
              name: sessionUser.name || sessionUser.full_name || sessionUser.email,
            });
          }
        }
      } catch {
        // Chưa có phiên hoặc refresh cookie hết hạn -> coi như khách chưa đăng nhập
        if (isMounted) {
          setAccessToken(null);
          setClientToken(null);
          setUser(null);
        }
      } finally {
        if (isMounted) {
          setIsInitializing(false);
        }
      }
    }

    bootstrapSession();

    return () => {
      isMounted = false;
    };
  }, []);

  // Hàm đăng nhập: kiểm tra tài khoản, lưu user + accessToken và đồng bộ setClientToken(token)
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

      const sessionUser = {
        id: foundUser.id,
        name: foundUser.name,
        email: foundUser.email,
        role: foundUser.role,
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
    const rawUser = response?.data?.user;
    const loggedInUser = rawUser
      ? {
          ...rawUser,
          name: rawUser.name || rawUser.full_name || rawUser.email,
        }
      : null;

    setAccessToken(token);
    setClientToken(token);
    setUser(loggedInUser);

    toast.success(`Đăng nhập thành công! Xin chào ${loggedInUser?.name || ''}`);
    return loggedInUser;
  };

  // Hàm đăng ký tài khoản mới từ Register.jsx -> đẩy vào usersList với role: 'STAFF'
  const register = (userData) => {
    const normalizedEmail = (userData.email || '').trim().toLowerCase();

    const newUser = {
      id: `usr_staff_${Date.now()}`,
      name: (userData.fullName || 'Nhân viên mới').trim(),
      email: normalizedEmail,
      password: userData.password,
      role: 'STAFF',
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
        isInitializing,
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
