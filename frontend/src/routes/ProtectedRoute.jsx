import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { evaluateRouteAccess } from '../api/axiosClient';
import { useAuth } from '../context/AuthContext';

/**
 * Component bảo vệ Route và phân quyền theo vai trò (Role-Based Access Control)
 * @param {Array<string>} allowedRoles - Danh sách vai trò được phép truy cập (VD: ['ADMIN'] hoặc ['ADMIN', 'STAFF'])
 */
export default function ProtectedRoute({ allowedRoles = [], children }) {
  const { user, accessToken, authInitializing } = useAuth();
  const location = useLocation();

  const decision = evaluateRouteAccess({
    user,
    accessToken,
    authInitializing,
    allowedRoles,
  });

  if (decision.action === 'WAIT') {
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

  if (decision.action === 'REDIRECT_ACCOUNT_STATUS') {
    return <Navigate to="/account-status" state={user} replace />;
  }

  if (decision.action === 'REDIRECT_LOGIN') {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (decision.action === 'REDIRECT_ROLE_HOME') {
    return <Navigate to={decision.to} replace />;
  }

  return children ? children : <Outlet />;
}
