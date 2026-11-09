/**
 * ============================================================================
 * BỘ QUY TẮC KIỂM TRA DỮ LIỆU BIỂU MẪU & BẢO MẬT OWASP (RetailOps v1.0)
 * ============================================================================
 */

// Biểu thức chính quy kiểm tra định dạng Email tiêu chuẩn
export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Thông báo chuẩn OWASP chống dò quét tài khoản (User Enumeration Defense)
export const OWASP_FORGOT_PASSWORD_MESSAGE =
  'Nếu email tồn tại trong hệ thống, chúng tôi đã gửi liên kết đặt lại mật khẩu. Vui lòng kiểm tra hộp thư (bao gồm cả thư mục spam).';

/**
 * Kiểm tra trường Email (Dùng chung cho Login, Register, ForgotPassword)
 * @param {string} email
 * @returns {string} Chuỗi lỗi (rỗng nếu hợp lệ)
 */
export function validateEmail(email) {
  const trimmed = String(email || '').trim();
  if (!trimmed) {
    return 'Vui lòng nhập địa chỉ email.';
  }
  if (!EMAIL_REGEX.test(trimmed)) {
    return 'Địa chỉ email không đúng định dạng (ví dụ: ten@retailops.vn).';
  }
  return '';
}

/**
 * Kiểm tra mật khẩu ở Form Đăng nhập (Bắt buộc, tối thiểu 6 ký tự)
 * @param {string} password
 * @returns {string} Chuỗi lỗi (rỗng nếu hợp lệ)
 */
export function validateLoginPassword(password) {
  const value = String(password || '');
  if (!value) {
    return 'Vui lòng nhập mật khẩu đăng nhập.';
  }
  if (value.length < 6) {
    return 'Mật khẩu phải có độ dài tối thiểu 6 ký tự.';
  }
  return '';
}

/**
 * Kiểm tra Họ và tên ở Form Đăng ký (Bắt buộc, không để trống)
 * @param {string} fullName
 * @returns {string} Chuỗi lỗi (rỗng nếu hợp lệ)
 */
export function validateFullName(fullName) {
  const trimmed = String(fullName || '').trim();
  if (!trimmed) {
    return 'Vui lòng nhập họ và tên nhân viên.';
  }
  return '';
}

/**
 * Kiểm tra Mật khẩu ở Form Đăng ký:
 * Tối thiểu 8 ký tự, bao gồm ít nhất 1 chữ cái và 1 chữ số
 * @param {string} password
 * @returns {string} Chuỗi lỗi (rỗng nếu hợp lệ)
 */
export function validateRegisterPassword(password) {
  const value = String(password || '');
  if (!value) {
    return 'Vui lòng nhập mật khẩu khởi tạo.';
  }
  if (value.length < 8) {
    return 'Mật khẩu phải có tối thiểu 8 ký tự.';
  }
  const hasLetter = /[A-Za-z]/.test(value);
  const hasNumber = /\d/.test(value);
  if (!hasLetter || !hasNumber) {
    return 'Mật khẩu phải bao gồm ít nhất 1 chữ cái và 1 chữ số.';
  }
  return '';
}

/**
 * Kiểm tra Xác nhận mật khẩu ở Form Đăng ký:
 * Phải khớp 100% với mật khẩu đã nhập bên trên
 * @param {string} password
 * @param {string} confirmPassword
 * @returns {string} Chuỗi lỗi (rỗng nếu hợp lệ)
 */
export function validateConfirmPassword(password, confirmPassword) {
  const confirmVal = String(confirmPassword || '');
  if (!confirmVal) {
    return 'Vui lòng nhập lại mật khẩu xác nhận.';
  }
  if (confirmVal !== String(password || '')) {
    return 'Mật khẩu xác nhận không khớp với mật khẩu đã nhập.';
  }
  return '';
}

/**
 * Đánh giá trực quan từng tiêu chí mật khẩu trên giao diện Đăng ký
 * @param {string} password
 * @param {string} confirmPassword
 */
export function evaluatePasswordCriteria(password = '', confirmPassword = '') {
  const val = String(password);
  return {
    minLength: val.length >= 8,
    hasLetter: /[A-Za-z]/.test(val),
    hasNumber: /\d/.test(val),
    isConfirmed: Boolean(val) && val === String(confirmPassword),
  };
}

/**
 * Validate toàn bộ Form Đăng nhập
 * @param {{ email: string, password: string }} values
 */
export function validateLoginForm(values = {}) {
  const errors = {
    email: validateEmail(values.email),
    password: validateLoginPassword(values.password),
  };

  return {
    isValid: !errors.email && !errors.password,
    errors,
  };
}

/**
 * Validate toàn bộ Form Đăng ký
 * @param {{ fullName: string, email: string, password: string, confirmPassword: string }} values
 */
export function validateRegisterForm(values = {}) {
  const errors = {
    fullName: validateFullName(values.fullName),
    email: validateEmail(values.email),
    password: validateRegisterPassword(values.password),
    confirmPassword: validateConfirmPassword(
      values.password,
      values.confirmPassword
    ),
  };

  return {
    isValid:
      !errors.fullName &&
      !errors.email &&
      !errors.password &&
      !errors.confirmPassword,
    errors,
  };
}

/**
 * Validate Form Quên mật khẩu
 * @param {{ email: string }} values
 */
export function validateForgotPasswordForm(values = {}) {
  const errors = {
    email: validateEmail(values.email),
  };

  return {
    isValid: !errors.email,
    errors,
  };
}

/**
 * Kiểm tra Mật khẩu hiện tại ở Form Đổi/Đặt lại mật khẩu
 * @param {string} currentPassword
 * @param {string} actualPassword
 * @returns {string} Chuỗi lỗi (rỗng nếu hợp lệ)
 */
export function validateCurrentPassword(currentPassword, actualPassword) {
  const val = String(currentPassword || '');
  if (!val) {
    return 'Vui lòng nhập mật khẩu hiện tại.';
  }
  if (!actualPassword || val !== actualPassword) {
    return 'Mật khẩu hiện tại không đúng.';
  }
  return '';
}

/**
 * Kiểm tra Mật khẩu mới theo tiêu chuẩn bảo mật:
 * Tối thiểu 8 ký tự, bao gồm chữ hoa, chữ thường và ít nhất một chữ số.
 * @param {string} password
 * @returns {string} Chuỗi lỗi (rỗng nếu hợp lệ)
 */
export function validateNewPassword(password) {
  const val = String(password || '');
  if (!val) {
    return 'Vui lòng nhập mật khẩu mới.';
  }
  if (val.length < 8) {
    return 'Mật khẩu phải có độ dài tối thiểu 8 ký tự.';
  }
  const hasUpper = /[A-Z]/.test(val);
  const hasLower = /[a-z]/.test(val);
  const hasNumber = /\d/.test(val);
  if (!hasUpper || !hasLower || !hasNumber) {
    return 'Mật khẩu phải bao gồm chữ hoa, chữ thường và ít nhất một chữ số.';
  }
  return '';
}

/**
 * Validate toàn bộ Form Đổi mật khẩu của người dùng đang đăng nhập (Change Password)
 * @param {{ currentPassword?: string, newPassword?: string, confirmPassword?: string }} values
 * @param {string | null} [expectedMockPassword] - Chỉ truyền khi ở chế độ Mock Demo
 */
export function validateChangePasswordForm(
  values = {},
  expectedMockPassword = null
) {
  const errors = {
    currentPassword: validateCurrentPassword(
      values.currentPassword,
      expectedMockPassword
    ),
    newPassword: validateNewPassword(values.newPassword),
    confirmPassword: validateConfirmPassword(
      values.newPassword,
      values.confirmPassword
    ),
  };

  return {
    isValid:
      !errors.currentPassword && !errors.newPassword && !errors.confirmPassword,
    errors,
  };
}

/**
 * Validate Form Đặt lại mật khẩu qua Email Token (Reset Password via One-Time Token)
 * Tách biệt hoàn toàn với nghiệp vụ Change Password của người dùng đang đăng nhập.
 * @param {{ token?: string, newPassword?: string, confirmPassword?: string }} values
 */
export function validateResetPasswordByTokenForm(values = {}) {
  const tokenVal = String(values.token || '').trim();
  const errors = {
    token: tokenVal
      ? ''
      : 'Mã xác thực đặt lại mật khẩu (token) không hợp lệ hoặc đã thiếu.',
    newPassword: validateNewPassword(values.newPassword),
    confirmPassword: validateConfirmPassword(
      values.newPassword,
      values.confirmPassword
    ),
  };

  return {
    isValid: !errors.token && !errors.newPassword && !errors.confirmPassword,
    errors,
  };
}


