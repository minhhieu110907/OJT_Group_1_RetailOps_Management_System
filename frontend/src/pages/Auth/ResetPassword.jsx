import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import {
  validateChangePasswordForm,
  validateResetPasswordByTokenForm,
  validateNewPassword,
  validateConfirmPassword,
} from '../../utils/validation';
import styles from './ResetPassword.module.css';

/**
 * Giao diện Đổi/Đặt lại mật khẩu (Trạng thái 4A, 4B, 4C)
 * Tách biệt rõ 2 luồng nghiệp vụ:
 * 1. Đặt lại mật khẩu theo link có mã token từ Quên mật khẩu (/reset-password?token=...&email=...)
 * 2. Đổi mật khẩu trực tiếp của người dùng đã đăng nhập (mở qua Modal có truyền onClose)
 */
export default function ResetPassword({ onClose, defaultEmail }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user, resetPassword, getUserByEmail, isMockMode, canUseMock } =
    useAuth();

  const isMockDemoActive = Boolean(isMockMode && canUseMock);
  const isChangePasswordMode = Boolean(onClose);

  const resetTokenParam = searchParams.get('token') || '';
  const targetEmail = isChangePasswordMode
    ? defaultEmail || user?.email || ''
    : searchParams.get('email') || defaultEmail || '';

  // Chỉ tra cứu mật khẩu mẫu khi đang ở chế độ Mock Demo hợp lệ; tuyệt đối không fallback mật khẩu cứng
  const targetUser =
    isMockDemoActive && targetEmail ? getUserByEmail(targetEmail) : null;
  const actualPassword = isMockDemoActive ? targetUser?.password ?? null : null;

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
    token: '',
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

  // Trạng thái 4A: Form sạch (chưa nhập ký tự nào) -> Vô hiệu hóa nút Cập nhật
  const isFormClean = isChangePasswordMode
    ? !currentPassword.trim() && !newPassword.trim() && !confirmPassword.trim()
    : !newPassword.trim() && !confirmPassword.trim();

  // Xử lý thay đổi Mật khẩu hiện tại:
  const handleCurrentPasswordChange = (e) => {
    const val = e.target.value;
    setCurrentPassword(val);
    if (errors.currentPassword) {
      setErrors((prev) => ({
        ...prev,
        currentPassword: '',
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
      navigate('/login', { replace: true });
    }
  };

  // Xử lý nộp biểu mẫu cập nhật mật khẩu
  const handleSubmit = async (e) => {
    e.preventDefault();

    // Chế độ Real API: Cô lập hoàn toàn, không đọc dữ liệu mẫu và không giả lập cập nhật thành công
    if (!isMockDemoActive) {
      toast.info(
        'Chức năng Đổi / Đặt lại mật khẩu thuộc phạm vi Backend Sprint 2. Hiện chưa có thay đổi mật khẩu nào được thực hiện.'
      );
      return;
    }

    setTouched({
      currentPassword: isChangePasswordMode,
      newPassword: true,
      confirmPassword: true,
    });

    setIsSubmitting(true);
    await new Promise((resolve) => setTimeout(resolve, 400));

    const validationResult = isChangePasswordMode
      ? validateChangePasswordForm(
          {
            currentPassword,
            newPassword,
            confirmPassword,
          },
          actualPassword
        )
      : validateResetPasswordByTokenForm({
          token: resetTokenParam,
          newPassword,
          confirmPassword,
        });

    if (!isChangePasswordMode && !targetUser) {
      validationResult.isValid = false;
      validationResult.errors.token =
        'Không tìm thấy tài khoản mẫu tương ứng với liên kết đặt lại mật khẩu.';
    }

    setErrors((prev) => ({
      ...prev,
      ...validationResult.errors,
    }));

    if (!validationResult.isValid) {
      setIsSubmitting(false);
      return;
    }

    const updated = resetPassword(targetEmail, newPassword);
    setIsSubmitting(false);

    if (!updated) {
      toast.error('Không thể cập nhật mật khẩu trong chế độ hiện tại.');
      return;
    }

    toast.success('Mật khẩu đã được cập nhật (Chế độ Mock Demo).');
    handleClose();
  };

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true">
      <div className={styles.modalCard}>
        {/* 1. Phần Đầu Header Modal */}
        <div className={styles.modalHeader}>
          <div>
            <h2 className={styles.modalTitle}>
              {isChangePasswordMode ? 'Đổi mật khẩu' : 'Đặt lại mật khẩu'}
            </h2>
            <p className={styles.modalSubtitle}>
              {isChangePasswordMode
                ? 'Cập nhật mật khẩu mới cho tài khoản đang đăng nhập'
                : 'Thiết lập mật khẩu mới qua liên kết khôi phục email'}
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

        {/* Thanh ghi chú tài khoản */}
        <div className={styles.accountBar}>
          <span>Tài khoản:</span>
          <span className={styles.accountEmail}>
            {targetEmail || 'Chưa xác định email'}
          </span>
        </div>

        {/* Cảnh báo lộ trình Sprint 2 khi ở chế độ Real API */}
        {!isMockDemoActive && (
          <div className={styles.errorMessage} role="status">
            <span>
              Chức năng {isChangePasswordMode ? 'Đổi mật khẩu' : 'Đặt lại mật khẩu'} qua Backend API thuộc lộ trình <strong>Sprint 2</strong>. Ở chế độ Real API hiện tại, biểu mẫu chỉ phục vụ xem trước giao diện và không thay đổi mật khẩu.
            </span>
          </div>
        )}

        {!isChangePasswordMode && errors.token && (
          <div className={styles.errorMessage} role="alert">
            <span>{errors.token}</span>
          </div>
        )}

        {/* 2. Biểu mẫu đổi / đặt lại mật khẩu */}
        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          {/* Trường 1: Mật khẩu hiện tại * (Chỉ hiển thị ở luồng Đổi mật khẩu của user đã đăng nhập) */}
          {isChangePasswordMode && (
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
          )}

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
              disabled={isSubmitting}
            >
              Hủy
            </button>
            <button
              type="submit"
              className={`${styles.submitBtn} ${
                isSubmitting ? styles.submitBtnLoading : ''
              }`}
              disabled={isFormClean || isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className={styles.spinner} aria-hidden="true" />
                  <span>Đang cập nhật mật khẩu...</span>
                </>
              ) : (
                <>
                  {/* Icon xoay cập nhật tròn theo đúng thiết kế 4A, 4B */}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="23 4 23 10 17 10" />
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                  </svg>
                  <span>Cập nhật mật khẩu</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
