import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../components/common';
import styles from './Register.module.css';

export default function Register() {
  const { user, register } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
  });

  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Nếu đã đăng nhập sẵn thì điều hướng vào không gian làm việc
  if (user) {
    return (
      <Navigate
        to={user.role === 'ADMIN' ? '/dashboard' : '/pos'}
        replace
      />
    );
  }

  const handleChange = (e) => {
    const { name, value } = e.target;
    if (errorMsg) setErrorMsg('');
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!formData.fullName.trim() || !formData.email.trim() || !formData.password) {
      setErrorMsg('Vui lòng điền đầy đủ họ tên, email và mật khẩu.');
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setErrorMsg('Mật khẩu xác nhận không khớp. Vui lòng kiểm tra lại.');
      return;
    }

    // Lưu tài khoản mới vào usersList trong AuthContext với role: 'STAFF'
    register(formData);
    toast.success('Đăng ký thành công! Vui lòng đăng nhập.');
    navigate('/login');
  };

  return (
    <div>
      {/* Hộp thông báo màu vàng */}
      <div className={styles.infoBanner}>
        <div className={styles.infoIcon}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#b45309" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        </div>
        <div className={styles.infoText}>
          <h3 className={styles.infoTitle}>Quy trình cấp tài khoản hai bước</h3>
          <p className={styles.infoDesc}>
            Sau khi gửi yêu cầu, hồ sơ sẽ được khởi tạo với vai trò{' '}
            <strong>Nhân viên (STAFF)</strong> để phục vụ đăng nhập vào quầy POS.
          </p>
        </div>
      </div>

      {/* Tiêu đề Form Đăng ký */}
      <div className={styles.cardHeader}>
        <h1 className={styles.cardTitle}>Đăng ký tài khoản Staff</h1>
        <p className={styles.cardSubtitle}>
          Điền thông tin định danh tối thiểu để khởi tạo tài khoản nhân sự.
        </p>
      </div>

      {errorMsg && (
        <div className={styles.errorBox} role="alert">
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleSubmit} className={styles.form}>
        {/* Họ và tên */}
        <div className={styles.fieldGroup}>
          <label htmlFor="fullName" className={styles.label}>
            HỌ VÀ TÊN NHÂN VIÊN <span className={styles.required}>*</span>
          </label>
          <div className={styles.inputWrapper}>
            <span className={styles.leftIcon}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <circle cx="9" cy="10" r="2" />
                <path d="M15 8h2" />
                <path d="M15 12h2" />
                <path d="M7 16h10" />
              </svg>
            </span>
            <input
              type="text"
              id="fullName"
              name="fullName"
              value={formData.fullName}
              onChange={handleChange}
              placeholder="Nguyễn Văn An"
              className={styles.input}
              required
            />
          </div>
          <span className={styles.helperText}>
            Tên sẽ hiển thị trên đơn hàng POS và nhật ký giao dịch.
          </span>
        </div>

        {/* Email đăng nhập */}
        <div className={styles.fieldGroup}>
          <label htmlFor="email" className={styles.label}>
            EMAIL ĐĂNG NHẬP (DUY NHẤT) <span className={styles.required}>*</span>
          </label>
          <div className={styles.inputWrapper}>
            <span className={styles.leftIcon}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94" />
              </svg>
            </span>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="an.nguyen@retailops.vn"
              className={styles.input}
              required
            />
          </div>
          <span className={styles.helperText}>
            Chuẩn hóa chữ thường. Email này không được trùng lặp trong hệ thống.
          </span>
        </div>

        {/* Mật khẩu */}
        <div className={styles.fieldGroup}>
          <label htmlFor="password" className={styles.label}>
            MẬT KHẨU <span className={styles.required}>*</span>
          </label>
          <div className={styles.inputWrapper}>
            <span className={styles.leftIcon}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
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
              placeholder="••••••••••••••••"
              className={`${styles.input} ${styles.inputWithRightIcon}`}
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className={styles.eyeBtn}
              aria-label="Ẩn/Hiện mật khẩu"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </div>
        </div>

        {/* Xác nhận mật khẩu */}
        <div className={styles.fieldGroup}>
          <label htmlFor="confirmPassword" className={styles.label}>
            XÁC NHẬN MẬT KHẨU <span className={styles.required}>*</span>
          </label>
          <div className={styles.inputWrapper}>
            <span className={styles.leftIcon}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 2v6h-6" />
                <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
                <path d="M3 22v-6h6" />
                <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
              </svg>
            </span>
            <input
              type={showPassword ? 'text' : 'password'}
              id="confirmPassword"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleChange}
              placeholder="••••••••••••••••"
              className={styles.input}
              required
            />
          </div>
        </div>

        {/* Khung tiêu chí bảo mật mật khẩu */}
        <div className={styles.criteriaBox}>
          <p className={styles.criteriaTitle}>Tiêu chí bảo mật mật khẩu:</p>
          <div className={styles.criteriaGrid}>
            <div className={styles.criteriaItem}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#087F5B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>Tối thiểu 8 ký tự</span>
            </div>
            <div className={styles.criteriaItem}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#087F5B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>Có chữ hoa &amp; thường</span>
            </div>
            <div className={styles.criteriaItem}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#087F5B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>Ít nhất 1 chữ số</span>
            </div>
            <div className={styles.criteriaItem}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#087F5B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>Khớp với xác nhận</span>
            </div>
          </div>
        </div>

        {/* Ghi chú bảo mật thông tin */}
        <div className={styles.privacyNotice}>
          <svg className={styles.privacyIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#087F5B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <p>
            Thông tin được dùng để tạo tài khoản nhân viên và ghi nhận nhật ký nghiệp vụ. Hệ thống không yêu cầu CCCD/CMND, ảnh chân dung, địa chỉ hay chi nhánh.
          </p>
        </div>

        {/* Nút gửi yêu cầu */}
        <button type="submit" className={styles.submitBtn}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="8.5" cy="7" r="4" />
            <polyline points="17 11 19 13 23 9" />
          </svg>
          <span>Gửi yêu cầu đăng ký</span>
        </button>
      </form>

      {/* Liên kết chuyển về trang Đăng nhập (/login) */}
      <div className={styles.cardFooter}>
        <span>Đã có tài khoản được phê duyệt? </span>
        <Link to="/login" className={styles.loginLink}>
          <span>Đăng nhập ngay</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
            <polyline points="10 17 15 12 10 7" />
            <line x1="15" y1="12" x2="3" y2="12" />
          </svg>
        </Link>
      </div>
    </div>
  );
}
