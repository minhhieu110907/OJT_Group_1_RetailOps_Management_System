import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import {
  validateChangePasswordForm,
  validateCurrentPassword,
  validateNewPassword,
  validateConfirmPassword,
} from '../../utils/validation';
import styles from './ResetPassword.module.css';

/**
 * Giao diện Đổi/Đặt lại mật khẩu (Trạng thái 4A, 4B, 4C)
 * Phục vụ cả:
 * 1. Đặt lại mật khẩu theo link có mã token từ Quên mật khẩu (/reset-password?token=...&email=...)
 * 2. Đổi mật khẩu trực tiếp trong ứng dụng
 */
export default function ResetPassword({ onClose, defaultEmail }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user, resetPassword, getUserByEmail } = useAuth();

  // Xác định email tài khoản cần đặt lại: Ưu tiên URL params -> defaultEmail -> User hiện tại -> fallback mẫu
  const targetEmail =
    searchParams.get('email') ||
    defaultEmail ||
    user?.email ||
    'caoanhnguyenduong@gmail.com';

  // Lấy mật khẩu thực tế trong dữ liệu mẫu để đối soát kiểm tra mật khẩu hiện tại
  const targetUser = getUserByEmail(targetEmail);
  const actualPassword = targetUser?.password || 'staff123';

  // State các ô nhập liệu
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // State hiển thị/ẩn mật khẩu (Mặc định ẩn)
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // State lưu trữ lỗi validation cụ thể từng trường (Trạng thái 4B)
  const [errors, setErrors] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });

  const [touched, setTouched] = useState({
    currentPassword: false,
    newPassword: false,
    confirmPassword: false,
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmittedSuccess, setIsSubmittedSuccess] = useState(false);

  // Trạng thái 4A: Form sạch (chưa nhập ký tự nào) -> Vô hiệu hóa nút Cập nhật
  const isFormClean =
    !currentPassword.trim() &&
    !newPassword.trim() &&
    !confirmPassword.trim();

  // Xử lý thay đổi Mật khẩu hiện tại
  const handleCurrentPasswordChange = (e) => {
    const val = e.target.value;
    setCurrentPassword(val);
    if (touched.currentPassword) {
      setErrors((prev) => ({
        ...prev,
        currentPassword: validateCurrentPassword(val, actualPassword),
      }));
    }
  };

  // Xử lý thay đổi Mật khẩu mới
  const handleNewPasswordChange = (e) => {
    const val = e.target.value;
    setNewPassword(val);
    if (touched.newPassword) {
      setErrors((prev) => ({
        ...prev,
        newPassword: validateNewPassword(val),
      }));
    }
    if (touched.confirmPassword && confirmPassword) {
      setErrors((prev) => ({
        ...prev,
        confirmPassword: validateConfirmPassword(val, confirmPassword),
      }));
    }
  };

  // Xử lý thay đổi Xác nhận mật khẩu mới
  const handleConfirmPasswordChange = (e) => {
    const val = e.target.value;
    setConfirmPassword(val);
    if (touched.confirmPassword) {
      setErrors((prev) => ({
        ...prev,
        confirmPassword: validateConfirmPassword(newPassword, val),
      }));
    }
  };

  // Đóng Modal hoặc chuyển hướng về trang Đăng nhập
  const handleClose = () => {
    if (onClose) {
      onClose();
    } else {
      navigate('/login');
    }
  };

  // Xử lý nộp biểu mẫu cập nhật mật khẩu
  const handleSubmit = async (e) => {
    e.preventDefault();

    setTouched({
      currentPassword: true,
      newPassword: true,
      confirmPassword: true,
    });

    // Thực hiện kiểm tra lỗi toàn diện
    const validationResult = validateChangePasswordForm(
      {
        currentPassword,
        newPassword,
        confirmPassword,
      },
      actualPassword
    );

    setErrors(validationResult.errors);

    // Trạng thái 4B: Nếu có lỗi validation -> Giữ nguyên form, hiển thị lỗi viền đỏ và text cảnh báo
    if (!validationResult.isValid) {
      return;
    }

    setIsSubmitting(true);
    await new Promise((resolve) => setTimeout(resolve, 350));

    // Cập nhật mật khẩu mới vào AuthContext
    resetPassword(targetEmail, newPassword);

    setIsSubmitting(false);
    // Trạng thái 4C: Đóng form hoàn toàn và kích hoạt thông báo Toast thành công
    setIsSubmittedSuccess(true);
    toast.success('Mật khẩu đã được cập nhật.');

    // Chuyển hướng về trang Đăng nhập để người dùng trải nghiệm mật khẩu mới
    setTimeout(() => {
      handleClose();
    }, 1200);
  };

  // Trạng thái 4C: Form đã đóng, chỉ còn hiển thị thông báo Toast trên màn hình
  if (isSubmittedSuccess) {
    return null;
  }

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true">
      <div className={styles.modalCard}>
        {/* 1. Phần Đầu Header Modal */}
        <div className={styles.modalHeader}>
          <div>
            <h2 className={styles.modalTitle}>Đổi mật khẩu</h2>
            <p className={styles.modalSubtitle}>
              Cập nhật mật khẩu mới để bảo vệ tài khoản của bạn
            </p>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={handleClose}
            aria-label="Đóng"
            title="Đóng"
          >
            ✕
          </button>
        </div>

        {/* Thanh ghi chú tài khoản hỗ trợ test */}
        <div className={styles.accountBar}>
          <span>Tài khoản:</span>
          <span className={styles.accountEmail}>{targetEmail}</span>
        </div>

        {/* 2. Biểu mẫu đổi mật khẩu */}
        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          {/* Trường 1: Mật khẩu hiện tại * */}
          <div className={styles.fieldGroup}>
            <label htmlFor="current-password" className={styles.label}>
              Mật khẩu hiện tại <span className={styles.required}>*</span>
            </label>
            <div className={styles.inputWrapper}>
              <input
                id="current-password"
                type={showCurrent ? 'text' : 'password'}
                placeholder="Nhập mật khẩu hiện tại"
                value={currentPassword}
                onChange={handleCurrentPasswordChange}
                onBlur={() => {
                  setTouched((t) => ({ ...t, currentPassword: true }));
                  setErrors((prev) => ({
                    ...prev,
                    currentPassword: validateCurrentPassword(
                      currentPassword,
                      actualPassword
                    ),
                  }));
                }}
                className={`${styles.input} ${
                  errors.currentPassword ? styles.inputError : ''
                }`}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className={styles.eyeBtn}
                onClick={() => setShowCurrent((prev) => !prev)}
                aria-label={
                  showCurrent ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'
                }
              >
                {showCurrent ? (
                  /* Icon Eye mở */
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                ) : (
                  /* Icon Eye gạch chéo */
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                )}
              </button>
            </div>
            {errors.currentPassword && (
              <div className={styles.errorMessage} role="alert">
                <span className={styles.errorIcon} aria-hidden="true">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                </span>
                <span>{errors.currentPassword}</span>
              </div>
            )}
          </div>

          {/* Trường 2: Mật khẩu mới * */}
          <div className={styles.fieldGroup}>
            <label htmlFor="new-password" className={styles.label}>
              Mật khẩu mới <span className={styles.required}>*</span>
            </label>
            <div className={styles.inputWrapper}>
              <input
                id="new-password"
                type={showNew ? 'text' : 'password'}
                placeholder="Nhập mật khẩu mới"
                value={newPassword}
                onChange={handleNewPasswordChange}
                onBlur={() => {
                  setTouched((t) => ({ ...t, newPassword: true }));
                  setErrors((prev) => ({
                    ...prev,
                    newPassword: validateNewPassword(newPassword),
                  }));
                }}
                className={`${styles.input} ${
                  errors.newPassword ? styles.inputError : ''
                }`}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className={styles.eyeBtn}
                onClick={() => setShowNew((prev) => !prev)}
                aria-label={showNew ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
              >
                {showNew ? (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                ) : (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                )}
              </button>
            </div>
            <p className={styles.helperText}>
              Tối thiểu 8 ký tự, bao gồm chữ hoa, chữ thường và ít nhất một chữ số. (Gợi ý: Thêm ký tự đặc biệt để tăng độ bảo mật)
            </p>
            {errors.newPassword && (
              <div className={styles.errorMessage} role="alert">
                <span className={styles.errorIcon} aria-hidden="true">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                </span>
                <span>{errors.newPassword}</span>
              </div>
            )}
          </div>

          {/* Trường 3: Xác nhận mật khẩu mới * */}
          <div className={styles.fieldGroup}>
            <label htmlFor="confirm-new-password" className={styles.label}>
              Xác nhận mật khẩu mới <span className={styles.required}>*</span>
            </label>
            <div className={styles.inputWrapper}>
              <input
                id="confirm-new-password"
                type={showConfirm ? 'text' : 'password'}
                placeholder="Nhập lại mật khẩu mới"
                value={confirmPassword}
                onChange={handleConfirmPasswordChange}
                onBlur={() => {
                  setTouched((t) => ({ ...t, confirmPassword: true }));
                  setErrors((prev) => ({
                    ...prev,
                    confirmPassword: validateConfirmPassword(
                      newPassword,
                      confirmPassword
                    ),
                  }));
                }}
                className={`${styles.input} ${
                  errors.confirmPassword ? styles.inputError : ''
                }`}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className={styles.eyeBtn}
                onClick={() => setShowConfirm((prev) => !prev)}
                aria-label={
                  showConfirm ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'
                }
              >
                {showConfirm ? (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                ) : (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                )}
              </button>
            </div>
            {errors.confirmPassword && (
              <div className={styles.errorMessage} role="alert">
                <span className={styles.errorIcon} aria-hidden="true">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                </span>
                <span>{errors.confirmPassword}</span>
              </div>
            )}
          </div>

          {/* 3. Hàng nút thao tác Hủy và Cập nhật mật khẩu */}
          <div className={styles.actionsRow}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={handleClose}
            >
              Hủy
            </button>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={isFormClean || isSubmitting}
            >
              {isSubmitting ? (
                <span className={styles.spinner} aria-hidden="true" />
              ) : (
                /* Icon xoay cập nhật tròn theo đúng thiết kế 4A, 4B */
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
              )}
              <span>Cập nhật mật khẩu</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
