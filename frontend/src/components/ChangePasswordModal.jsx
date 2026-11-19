import { useState } from 'react';
import { Modal, useToast } from './common';
import { useAuth } from '../context/AuthContext';
import { getApiErrorMessage } from '../api/axiosClient';
import modalStyles from './common/Modal/Modal.module.css';
import styles from './ChangePasswordModal.module.css';

export default function ChangePasswordModal({ onClose }) {
  const { changeMyPassword } = useAuth();
  const toast = useToast();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
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
        <input id="current-password" className={styles.input} type="password" required maxLength={72}
          autoComplete="current-password" value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)} />
        <label className={styles.label} htmlFor="new-password">Mật khẩu mới</label>
        <input id="new-password" className={styles.input} type="password" required maxLength={72}
          autoComplete="new-password" value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)} />
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
