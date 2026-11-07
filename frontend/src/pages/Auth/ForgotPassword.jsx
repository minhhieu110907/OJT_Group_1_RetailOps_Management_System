import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  OWASP_FORGOT_PASSWORD_MESSAGE,
  validateEmail,
  validateForgotPasswordForm,
} from '../../utils/validation';
import styles from './Login.module.css';

/**
 * Trang Quên mật khẩu (ForgotPassword)
 * Tuân thủ chuẩn bảo mật OWASP chống dò quét tài khoản (User Enumeration Defense):
 * Dù email có tồn tại trong hệ thống hay không, luôn trả về cùng một thông báo chung.
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState('');
  const [touched, setTouched] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleChange = (e) => {
    const val = e.target.value;
    setEmail(val);
    if (isSubmitted) {
      setIsSubmitted(false);
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
    // Giả lập độ trễ xử lý đồng nhất (tránh Timing Attack dò email)
    await new Promise((resolve) => setTimeout(resolve, 500));
    setIsSubmitting(false);
    setIsSubmitted(true);
  };

  return (
    <div>
      {/* 1. Tiêu đề */}
      <div className={styles.headerSection}>
        <h1 className={styles.title}>Khôi phục mật khẩu</h1>
        <p className={styles.subtitle}>
          Nhập địa chỉ email nhân sự của bạn để nhận hướng dẫn đặt lại mật khẩu.
        </p>
      </div>

      {/* 2. Thông báo chuẩn OWASP chống dò quét tài khoản */}
      {isSubmitted && (
        <div className={styles.successAlert} role="status">
          <span className={styles.successIcon} aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </span>
          <div className={styles.errorBody}>
            <h3 className={styles.successTitle}>Đã tiếp nhận yêu cầu</h3>
            <p className={styles.successDesc}>
              {OWASP_FORGOT_PASSWORD_MESSAGE}
            </p>
          </div>
        </div>
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

