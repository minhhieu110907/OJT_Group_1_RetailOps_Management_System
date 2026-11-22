import { useState } from 'react';
import { Modal, useToast } from './common';
import { useAuth } from '../context/AuthContext';
import { getApiErrorMessage } from '../api/axiosClient';
import modalStyles from './common/Modal/Modal.module.css';
import styles from './ChangePasswordModal.module.css';

function PasswordEyeIcon({ visible }) {
  return visible ? (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  ) : (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export default function ChangePasswordModal({ onClose }) {
  const { changeMyPassword } = useAuth();
  const toast = useToast();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    setError('');
    if (newPassword !== confirmPassword) {
      setError('Mật khẩu xác nhận không khớp.');
      return;
    }
    if (newPassword === currentPassword) {
      setError('Mật khẩu mới phải khác mật khẩu hiện tại.');
      return;
    }
    setSaving(true);
    try {
      await changeMyPassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setShowCurrentPassword(false);
      setShowNewPassword(false);
      toast.success('Đã đổi mật khẩu. Các phiên khác đã bị đăng xuất.');
      onClose();
    } catch (err) {
      setError(getApiErrorMessage(err) || err.message || 'Không thể đổi mật khẩu.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={saving ? undefined : onClose}
      title="Đổi mật khẩu"
      maxWidth="460px"
      footer={
        <>
          <button type="button" className={modalStyles.cancelBtn} disabled={saving} onClick={onClose}>
            Hủy
          </button>
          <button type="submit" form="change-account-password" className={modalStyles.confirmBtn}
            disabled={saving || !currentPassword || !newPassword || !confirmPassword}>
            {saving ? 'Đang cập nhật...' : 'Đổi mật khẩu'}
          </button>
        </>
      }
    >
      <form id="change-account-password" onSubmit={submit} className={styles.form} autoComplete="off">
        <label className={styles.label} htmlFor="current-password">Mật khẩu hiện tại</label>
        <div className={styles.passwordWrap}>
          <input
            id="current-password"
            className={`${styles.input} ${styles.inputWithEye}`}
            type={showCurrentPassword ? 'text' : 'password'}
            required
            maxLength={72}
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
          <button
            type="button"
            className={styles.eyeBtn}
            onClick={() => setShowCurrentPassword((prev) => !prev)}
            aria-label={showCurrentPassword ? 'Ẩn mật khẩu hiện tại' : 'Hiện mật khẩu hiện tại'}
            aria-pressed={showCurrentPassword}
            title={showCurrentPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
          >
            <PasswordEyeIcon visible={showCurrentPassword} />
          </button>
        </div>

        <label className={styles.label} htmlFor="new-password">Mật khẩu mới</label>
        <div className={styles.passwordWrap}>
          <input
            id="new-password"
            className={`${styles.input} ${styles.inputWithEye}`}
            type={showNewPassword ? 'text' : 'password'}
            required
            maxLength={72}
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <button
            type="button"
            className={styles.eyeBtn}
            onClick={() => setShowNewPassword((prev) => !prev)}
            aria-label={showNewPassword ? 'Ẩn mật khẩu mới' : 'Hiện mật khẩu mới'}
            aria-pressed={showNewPassword}
            title={showNewPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
          >
            <PasswordEyeIcon visible={showNewPassword} />
          </button>
        </div>

        <label className={styles.label} htmlFor="confirm-password">Xác nhận mật khẩu mới</label>
        <input id="confirm-password" className={styles.input} type="password" required maxLength={72}
          autoComplete="new-password" value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)} />
        <p className={styles.hint}>Các phiên đăng nhập khác sẽ bị thu hồi sau khi cập nhật thành công.</p>
        {error && <p className={styles.error} role="alert">{error}</p>}
      </form>
    </Modal>
  );
}
