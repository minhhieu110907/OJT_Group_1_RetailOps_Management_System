import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Modal, useToast } from '../../components/common';
import { accountApi } from '../../api/accountApi';
import { getApiErrorMessage } from '../../api/axiosClient';
import { useAuth } from '../../context/AuthContext';
import modalStyles from '../../components/common/Modal/Modal.module.css';
import styles from './StaffAccounts.module.css';

const PAGE_SIZE = 20;

export default function StaffAccounts() {
  const { user, isMockMode } = useAuth();
  const toast = useToast();
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [target, setTarget] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const result = await accountApi.listStaff({
        isMockMode,
        status: status || undefined,
        search: query,
        page,
        pageSize: PAGE_SIZE,
      });
      if (signal.aborted) return;
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      if (!signal.aborted) {
        setError(getApiErrorMessage(err) || err.message);
        setItems([]);
        setTotal(0);
      }
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [isMockMode, status, query, page]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, version]);

  if (user?.role !== 'ADMIN') return <p>Chỉ quản trị viên được quản lý tài khoản.</p>;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const performAction = async () => {
    if (saving || !target) return;
    setSaving(true);
    setActionError('');
    try {
      if (target.status === 'ACTIVE') {
        await accountApi.lockStaff(target.id, isMockMode);
      } else if (target.status === 'LOCKED') {
        await accountApi.unlockStaff(target.id, isMockMode);
      } else {
        throw new Error('Trạng thái tài khoản không hợp lệ.');
      }
      toast.success(target.status === 'ACTIVE'
        ? 'Đã khóa tài khoản và thu hồi mọi phiên.'
        : 'Đã mở khóa tài khoản. Nhân viên cần đăng nhập lại.');
      setTarget(null);
      setVersion((v) => v + 1);
    } catch (err) {
      const status = err?.response?.status;
      const conflictMsg =
        status === 409
          ? target.status === 'ACTIVE'
            ? 'Tài khoản nhân viên này đã được khóa ở một phiên làm việc khác. Danh sách đã được cập nhật.'
            : 'Tài khoản nhân viên này đã được mở khóa ở một phiên làm việc khác. Danh sách đã được cập nhật.'
          : getApiErrorMessage(err) || err.message;
      setActionError(conflictMsg);
      toast.error(conflictMsg);
      setTarget(null);
      setVersion((v) => v + 1);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={styles.page}>
      <div className={styles.heading}>
        <div>
          <h1>Tài khoản nhân viên</h1>
          <p>Quản lý quyền đăng nhập của những nhân viên đã được duyệt.</p>
        </div>
        <Link className={styles.back} to="/staff">Hồ sơ xét duyệt</Link>
      </div>
      <div className={styles.filters}>
        <form onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
          setPage(1);
        }}>
          <label htmlFor="staff-search">Tìm theo email hoặc họ tên</label>
          <input id="staff-search" value={search} maxLength={120}
            onChange={(e) => setSearch(e.target.value)} placeholder="Email hoặc họ tên" />
          <button type="submit">Tìm kiếm</button>
        </form>
        <div className={styles.statusFilter}>
          <label htmlFor="staff-status">Trạng thái</label>
          <select id="staff-status" value={status} onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}>
            <option value="">Tất cả</option>
            <option value="ACTIVE">Đang hoạt động</option>
            <option value="LOCKED">Đã khóa</option>
          </select>
        </div>
      </div>
      {isMockMode && <p role="alert">Chức năng này chỉ hỗ trợ API thật.</p>}
      {(actionError || error) && (
        <p role="alert" className={styles.error}>
          {actionError || error}
        </p>
      )}
      {loading ? <p role="status">Đang tải tài khoản...</p> : (
        <div className={styles.tableScroll}>
          <table>
            <thead><tr><th>Mã nhân viên</th><th>Email</th><th>Họ tên</th>
              <th>Trạng thái</th><th>Thao tác</th></tr></thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>#{item.id}</td>
                  <td>{item.email_normalized}</td>
                  <td>{item.full_name || '—'}</td>
                  <td>{item.status === 'ACTIVE' ? 'Đang hoạt động' : 'Đã khóa'}</td>
                  <td>
                    <button type="button" disabled={saving || isMockMode}
                      className={item.status === 'ACTIVE' ? styles.lock : styles.unlock}
                      onClick={() => setTarget(item)}>
                      {item.status === 'ACTIVE' ? 'Khóa' : 'Mở khóa'}
                    </button>
                  </td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={5}>Không có tài khoản phù hợp.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      <div className={styles.pagination}>
        <span>{total} tài khoản</span>
        <button disabled={page <= 1 || loading} onClick={() => setPage((v) => v - 1)}>
          Trước
        </button>
        <span>{page}/{totalPages}</span>
        <button disabled={page >= totalPages || loading} onClick={() => setPage((v) => v + 1)}>
          Sau
        </button>
      </div>
      <Modal isOpen={Boolean(target)} onClose={saving ? undefined : () => setTarget(null)}
        title={target?.status === 'ACTIVE' ? 'Xác nhận khóa tài khoản' : 'Xác nhận mở khóa'}
        maxWidth="420px" footer={
          <>
            <button className={modalStyles.cancelBtn} type="button"
              disabled={saving} onClick={() => setTarget(null)}>Hủy</button>
            <button type="button" disabled={saving}
              className={target?.status === 'ACTIVE' ? modalStyles.dangerBtn : modalStyles.confirmBtn}
              onClick={performAction}>
              {saving ? 'Đang xử lý...' : target?.status === 'ACTIVE' ? 'Khóa tài khoản' : 'Mở khóa'}
            </button>
          </>
        }>
        <p>{target?.email_normalized}</p>
        <p>{target?.status === 'ACTIVE'
          ? 'Mọi phiên đăng nhập hiện tại của nhân viên sẽ bị thu hồi.'
          : 'Nhân viên cần đăng nhập lại. Không khôi phục các phiên cũ.'}</p>
      </Modal>
    </section>
  );
}
