import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import {
  OWASP_FORGOT_PASSWORD_MESSAGE,
  validateEmail,
  validateForgotPasswordForm,
} from '../../utils/validation';
import styles from './Login.module.css';

/**
 * Trang Quên mật khẩu (ForgotPassword - FIX-03):
 * - Real API mode: Không tự tạo reset token giả và không báo đã gửi email khi Backend Sprint 1 chưa có endpoint.
 * - Mock Demo mode: Cho phép mô phỏng luồng đặt lại mật khẩu phục vụ demo UI.
 */
export default function ForgotPassword() {
  const { isMockMode, canUseMock } = useAuth();
  const isMockActive = Boolean(isMockMode && canUseMock);

  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState('');
  const [touched, setTouched] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [resetToken, setResetToken] = useState('');

  const handleChange = (e) => {
    const val = e.target.value;
    setEmail(val);
    if (isSubmitted) {
      setIsSubmitted(false);
      setResetToken('');
    }
    if (touched) {
      setEmailError(validateEmail(val));
    }
  };

  const handleBlur = () => {
    setTouched(true);
    setEmailError(validateEmail(email));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setTouched(true);

    const { isValid, errors } = validateForgotPasswordForm({ email });
    setEmailError(errors.email);

    if (!isValid) {
      return;
    }

    setIsSubmitting(true);
    await new Promise((resolve) => setTimeout(resolve, 300));

    if (isMockActive) {
      setResetToken(`mock-token-${Date.now()}`);
    } else {
      setResetToken('');
    }

    setIsSubmitting(false);
    setIsSubmitted(true);
  };

  return (
    <div>
      {/* 1. Tiêu đề */}
      <div className={styles.headerSection}>
        <h1 className={styles.title}>Khôi phục mật khẩu</h1>
        <p className={styles.subtitle}>
          Nhập địa chỉ email nhân sự của bạn để yêu cầu đặt lại mật khẩu.
        </p>
      </div>

      {/* 2. Kết quả xử lý: Phân tách rõ Real API Placeholder (Sprint 2) và Mock Demo */}
      {isSubmitted && !isMockActive && (
        <div className={styles.errorAlert} role="status">
          <span className={styles.errorIcon} aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </span>
          <div className={styles.errorBody}>
            <h3 className={styles.errorTitle}>
              Chức năng đang phát triển (Sprint 2 Placeholder)
            </h3>
            <p className={styles.errorDesc}>
              Dịch vụ gửi email khôi phục mật khẩu tự động thuộc phạm vi Sprint 2 và hiện chưa được kích hoạt trên máy chủ. Chưa có email hay mã khôi phục nào được gửi đi. Vui lòng liên hệ Quản trị viên cửa hàng để được hỗ trợ trực tiếp.
            </p>
          </div>
        </div>
      )}

      {isSubmitted && isMockActive && (
        <>
          <div className={styles.successAlert} role="status">
            <span className={styles.successIcon} aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </span>
            <div className={styles.errorBody}>
              <h3 className={styles.successTitle}>
                Đã tiếp nhận yêu cầu (Mô phỏng Mock Demo)
              </h3>
              <p className={styles.successDesc}>
                {OWASP_FORGOT_PASSWORD_MESSAGE}
              </p>
            </div>
          </div>

          {/* Mô phỏng Hộp thư Email chỉ hiển thị khi ở chế độ Mock Demo được phép */}
          <div className={styles.emailSimBox}>
            <div className={styles.emailSimHeader}>
              <span className={styles.emailSimBadge}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
                Hộp thư mô phỏng (Mock Demo - Sprint 2)
              </span>
              <span className={styles.emailSimTo}>{email}</span>
            </div>
            <p className={styles.emailSimDesc}>
              Chế độ Mock Demo đã tạo liên kết đặt lại mật khẩu mẫu. Bấm vào nút bên dưới để mở giao diện Đặt lại mật khẩu qua Email Token:
            </p>
            <div>
              <Link
                to={`/reset-password?email=${encodeURIComponent(
                  email
                )}&token=${encodeURIComponent(resetToken)}`}
                className={styles.emailSimAction}
              >
                <span>Mở liên kết đặt lại mật khẩu (Demo)</span>
                <span aria-hidden="true">→</span>
              </Link>
            </div>
            <p className={styles.emailSimTip}>
              * Lưu ý: Đây là luồng mô phỏng UI tại Client, không tác động tới cơ sở dữ liệu Backend.
            </p>
          </div>
        </>
      )}

      {/* 3. Biểu mẫu nhập Email */}
      <form onSubmit={handleSubmit} className={styles.form} noValidate>
        <div className={styles.fieldGroup}>
          <label htmlFor="forgot-email" className={styles.label}>
            EMAIL ĐĂNG KÝ <span className={styles.required}>*</span>
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
              id="forgot-email"
              name="email"
              value={email}
              onChange={handleChange}
              onBlur={handleBlur}
              placeholder="an.nguyen@retailops.vn"
              className={`${styles.input} ${
                emailError ? styles.inputError : ''
              }`}
              autoComplete="email"
              aria-invalid={Boolean(emailError)}
              required
            />
          </div>
          {emailError ? (
            <span className={styles.fieldError} role="alert">
              {emailError}
            </span>
          ) : (
            <span className={styles.helperText}>
              Hệ thống bảo mật thông tin theo tiêu chuẩn chống dò quét tài khoản OWASP.
            </span>
          )}
        </div>

        <button
          type="submit"
          className={styles.submitBtn}
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              <span>Đang xử lý yêu cầu...</span>
            </>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
              <span>Gửi liên kết đặt lại mật khẩu</span>
            </>
          )}
        </button>
      </form>

      {/* 4. Liên kết quay lại Đăng nhập */}
      <div className={styles.cardFooter}>
        <span>Đã nhớ mật khẩu? </span>
        <Link to="/login" className={styles.registerLink}>
          <span>Quay lại đăng nhập</span>
          <span aria-hidden="true">-&gt;</span>
        </Link>
      </div>
    </div>
  );
}

