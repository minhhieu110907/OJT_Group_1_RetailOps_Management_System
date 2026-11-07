import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import {
  validateEmail,
  validateLoginForm,
  validateLoginPassword,
} from '../../utils/validation';
import styles from './Login.module.css';

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [fieldErrors, setFieldErrors] = useState({
    email: '',
    password: '',
  });
  const [touched, setTouched] = useState({
    email: false,
    password: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Nếu người dùng đã đăng nhập sẵn (APPROVED) thì tự động điều hướng theo vai trò
  if (user) {
    return (
      <Navigate
        to={user.role === 'ADMIN' ? '/dashboard' : '/pos'}
        replace
      />
    );
  }

  // Kiểm tra lỗi từng trường
  const validateSingleField = (name, value) => {
    if (name === 'email') return validateEmail(value);
    if (name === 'password') return validateLoginPassword(value);
    return '';
  };

  // Khi người dùng gõ ký tự -> ẩn thông báo lỗi chung và cập nhật validate nếu trường đã chạm (touched)
  const handleChange = (e) => {
    const { name, value } = e.target;
    if (hasError) {
      setHasError(false);
    }

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));

    if (touched[name]) {
      setFieldErrors((prev) => ({
        ...prev,
        [name]: validateSingleField(name, value),
      }));
    }
  };

  // Khi rời chuột khỏi ô input (onBlur) -> Hiển thị lỗi ngay dưới ô input
  const handleBlur = (e) => {
    const { name, value } = e.target;
    setTouched((prev) => ({
      ...prev,
      [name]: true,
    }));
    setFieldErrors((prev) => ({
      ...prev,
      [name]: validateSingleField(name, value),
    }));
  };

  // Xử lý submit form đăng nhập
  const handleSubmit = async (e) => {
    e.preventDefault();
    setHasError(false);

    // 1. Validate toàn bộ form trước khi gửi
    const { isValid, errors } = validateLoginForm(formData);
    setTouched({ email: true, password: true });
    setFieldErrors(errors);

    if (!isValid) {
      return;
    }

    setIsSubmitting(true);
    await new Promise((resolve) => setTimeout(resolve, 600));

    try {
      const loggedInUser = await login(formData.email, formData.password);

      // 2. Nếu tài khoản có trạng thái PENDING hoặc REJECTED -> Chuyển sang /account-status
      if (
        loggedInUser?.status === 'PENDING' ||
        loggedInUser?.status === 'PENDING_APPROVAL' ||
        loggedInUser?.status === 'REJECTED'
      ) {
        navigate('/account-status', {
          replace: true,
          state: {
            status: loggedInUser.status,
            fullName: loggedInUser.name,
            email: loggedInUser.email,
            submittedAt: loggedInUser.submittedAt,
            rejectReason: loggedInUser.rejectReason,
            rejectSubState: loggedInUser.rejectSubState,
          },
        });
        return;
      }

      // 3. Tài khoản APPROVED -> Điều hướng vào không gian làm việc theo vai trò
      navigate(loggedInUser.role === 'ADMIN' ? '/dashboard' : '/pos', {
        replace: true,
      });
    } catch {
      setHasError(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      {/* 1. Tiêu đề & Giới thiệu */}
      <div className={styles.headerSection}>
        <h1 className={styles.title}>Đăng nhập</h1>
        <p className={styles.subtitle}>
          Truy cập không gian làm việc của quản trị viên hoặc nhân viên bán hàng.
        </p>
      </div>

      {/* 2. Hộp cảnh báo lỗi màu đỏ (Chỉ xuất hiện khi xác thực thất bại) */}
      {hasError && (
        <div className={styles.errorAlert} role="alert">
          <span className={styles.errorIcon} aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </span>
          <div className={styles.errorBody}>
            <h3 className={styles.errorTitle}>Thông tin đăng nhập không hợp lệ</h3>
            <p className={styles.errorDesc}>
              Email hoặc mật khẩu không chính xác. Vui lòng kiểm tra lại thông tin và thử lại.
            </p>
          </div>
        </div>
      )}

      {/* 3. Form nhập Email & Mật khẩu */}
      <form onSubmit={handleSubmit} className={styles.form} noValidate>
        {/* Trường 1: EMAIL ĐĂNG NHẬP * */}
        <div className={styles.fieldGroup}>
          <label htmlFor="email" className={styles.label}>
            EMAIL ĐĂNG NHẬP <span className={styles.required}>*</span>
          </label>
          <div className={styles.inputWrapper}>
            <span className={styles.leftIcon} aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="4" width="20" height="16" rx="2" />
                <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
              </svg>
            </span>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="an.nguyen@retailops.vn"
              className={`${styles.input} ${
                fieldErrors.email ? styles.inputError : ''
              }`}
              autoComplete="email"
              aria-invalid={Boolean(fieldErrors.email)}
              required
            />
          </div>
          {fieldErrors.email ? (
            <span className={styles.fieldError} role="alert">
              {fieldErrors.email}
            </span>
          ) : (
            <span className={styles.helperText}>
              Sử dụng email nhân viên đã được kích hoạt trong hệ thống.
            </span>
          )}
        </div>

        {/* Trường 2: MẬT KHẨU * */}
        <div className={styles.fieldGroup}>
          <div className={styles.labelRow}>
            <label htmlFor="password" className={styles.label}>
              MẬT KHẨU <span className={styles.required}>*</span>
            </label>
            <Link to="/forgot-password" className={styles.forgotLink}>
              Quên mật khẩu?
            </Link>
          </div>
          <div className={styles.inputWrapper}>
            <span className={styles.leftIcon} aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </span>
            <input
              type={showPassword ? 'text' : 'password'}
              id="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="••••••••••••"
              className={`${styles.input} ${styles.inputWithRightIcon} ${
                fieldErrors.password ? styles.inputError : ''
              }`}
              autoComplete="current-password"
              aria-invalid={Boolean(fieldErrors.password)}
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              className={styles.eyeBtn}
              aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
              title={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
            >
              {showPassword ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
          {fieldErrors.password && (
            <span className={styles.fieldError} role="alert">
              {fieldErrors.password}
            </span>
          )}
        </div>

        {/* 4. Nút bấm Đăng nhập & Trạng thái Loading */}
        <button
          type="submit"
          className={styles.submitBtn}
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              <span>Đang xác thực phiên...</span>
            </>
          ) : (
            <>
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                <polyline points="10 17 15 12 10 7" />
                <line x1="15" y1="12" x2="3" y2="12" />
              </svg>
              <span>Đăng nhập</span>
            </>
          )}
        </button>
      </form>

      {/* 5. Liên kết chuyển sang trang Đăng ký */}
      <div className={styles.cardFooter}>
        <span>Chưa có tài khoản nhân viên? </span>
        <Link to="/register" className={styles.registerLink}>
          <span>Đăng ký tài khoản Staff</span>
          <span aria-hidden="true">-&gt;</span>
        </Link>
      </div>
    </div>
  );
}
