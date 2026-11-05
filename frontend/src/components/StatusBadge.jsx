const STATUS_LABELS = {
  loading: 'Đang kiểm tra',
  success: 'Kết nối thành công',
  error: 'Mất kết nối',
}

export function StatusBadge({ status }) {
  const label = STATUS_LABELS[status] || 'Chưa xác định'

  return (
    <span className={`status-badge ${status}`} role="status" aria-live="polite">
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  )
}
