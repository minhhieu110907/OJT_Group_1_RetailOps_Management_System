import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Component bảo vệ Route và phân quyền theo vai trò (Role-Based Access Control)
 * @param {Array<string>} allowedRoles - Danh sách vai trò được phép truy cập (VD: ['ADMIN'] hoặc ['ADMIN', 'STAFF'])
 */
export default function ProtectedRoute({ allowedRoles = [], children }) {
  const { user } = useAuth();
  const location = useLocation();

  // 1. Chưa đăng nhập (!user):
  // Điều hướng về /login kèm theo state={{ from: location }} để hỗ trợ quay lại đúng trang sau khi đăng nhập
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 2. Đã đăng nhập nhưng không đủ quyền truy cập vào route này:
  // TUYỆT ĐỐI KHÔNG đăng xuất người dùng -> Điều hướng về màn hình mặc định theo vai trò
  if (allowedRoles.length > 0 && !allowedRoles.includes(user.role)) {
    const fallbackPath = user.role === 'STAFF' ? '/pos' : '/dashboard';
    return <Navigate to={fallbackPath} replace />;
  }

  // 3. Đủ quyền hợp lệ -> Render <Outlet /> (hoặc children nếu được bọc trực tiếp)
  return children ? children : <Outlet />;
}
