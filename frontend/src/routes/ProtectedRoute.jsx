import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Component bảo vệ Route và phân quyền theo vai trò (Role-Based Access Control)
 * @param {Array<string>} allowedRoles - Danh sách vai trò được phép truy cập (VD: ['ADMIN'] hoặc ['ADMIN', 'STAFF'])
 */
export default function ProtectedRoute({ allowedRoles = [], children }) {
  const { user, authInitializing } = useAuth();
  const location = useLocation();

  // 1. Đang kiểm tra kết nối / khôi phục phiên từ Cookie khi vừa tải lại trang (F5):
  // Giữ màn hình chờ, TUYỆT ĐỐI KHÔNG chuyển hướng sớm về /login tránh hiệu ứng giật màn hình
  if (authInitializing) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#f8fafc',
          gap: '12px',
        }}
      >
        <div
          style={{
            width: '36px',
            height: '36px',
            border: '3px solid #6366f1',
            borderTopColor: 'transparent',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }}
        />
        <p style={{ fontSize: '14px', color: '#64748b', fontWeight: 500 }}>
          Đang khôi phục phiên đăng nhập...
        </p>
      </div>
    );
  }

  // 2. Chưa đăng nhập (!user):
  // Điều hướng về /login kèm theo state={{ from: location }} để hỗ trợ quay lại đúng trang sau khi đăng nhập
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 3. Tài khoản chưa được duyệt (PENDING/REJECTED):
  // Chuyển hướng sang màn hình trạng thái hồ sơ /account-status
  if (
    user.status === 'PENDING' ||
    user.status === 'PENDING_APPROVAL' ||
    user.status === 'REJECTED'
  ) {
    return <Navigate to="/account-status" state={user} replace />;
  }

  // 4. Đã đăng nhập nhưng không đủ quyền truy cập vào route này:
  // TUYỆT ĐỐI KHÔNG đăng xuất người dùng -> Điều hướng về màn hình mặc định theo vai trò
  if (allowedRoles.length > 0 && !allowedRoles.includes(user.role)) {
    const fallbackPath = user.role === 'STAFF' ? '/pos' : '/dashboard';
    return <Navigate to={fallbackPath} replace />;
  }

  // 5. Đủ quyền hợp lệ -> Render <Outlet /> (hoặc children nếu được bọc trực tiếp)
  return children ? children : <Outlet />;
}
