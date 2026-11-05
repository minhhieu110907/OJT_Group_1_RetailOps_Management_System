import { useEffect, useState } from 'react'
import { getApiErrorMessage } from '../api/client'
import { fetchHealthStatus } from '../api/health'
import { StatusBadge } from '../components/StatusBadge'

export function HealthCheckPage() {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({
    status: 'loading',
    data: null,
    httpStatus: null,
    error: '',
    checkedAt: '',
  })

  useEffect(() => {
    const controller = new AbortController()

    fetchHealthStatus({ signal: controller.signal })
      .then(({ data, httpStatus }) => {
        setState({
          status: 'success',
          data,
          httpStatus,
          error: '',
          checkedAt: new Date().toLocaleTimeString('vi-VN'),
        })
      })
      .catch((requestError) => {
        const message = getApiErrorMessage(requestError)
        if (!message) {
          return
        }
        setState({
          status: 'error',
          data: null,
          httpStatus: requestError.response?.status ?? null,
          error: message,
          checkedAt: new Date().toLocaleTimeString('vi-VN'),
        })
      })

    return () => controller.abort()
  }, [attempt])

  const handleRetry = () => {
    setState((prev) => ({
      ...prev,
      status: 'loading',
      error: '',
    }))
    setAttempt((prev) => prev + 1)
  }

  const isLoading = state.status === 'loading'

  return (
    <main className="app-shell">
      <section className="app-card" aria-labelledby="health-page-title">
        <header className="card-header">
          <div>
            <p className="eyebrow">RetailOps V1.0 — Frontend Foundation</p>
            <h1 id="health-page-title">Kiểm tra kết nối hệ thống</h1>
          </div>
          <StatusBadge status={state.status} />
        </header>

        <p className="subtitle">
          Màn hình nền tảng xác minh kết nối thực tế từ ứng dụng React (Vite) tới
          FastAPI Backend qua Axios client dùng chung.
        </p>

        <div className="meta-bar">
          <div className="meta-item">
            <span className="meta-label">Endpoint</span>
            <code>GET /api/v1/health</code>
          </div>
          {state.httpStatus !== null && (
            <div className="meta-item">
              <span className="meta-label">HTTP Status</span>
              <code>{state.httpStatus}</code>
            </div>
          )}
          {state.checkedAt && (
            <div className="meta-item">
              <span className="meta-label">Lần kiểm tra cuối</span>
              <span>{state.checkedAt}</span>
            </div>
          )}
        </div>

        {isLoading && (
          <div className="info-panel" role="status" aria-live="polite">
            <p className="loading-text">
              Đang xử lý dữ liệu... Đang gửi yêu cầu tới <code>/api/v1/health</code>.
            </p>
          </div>
        )}

        {state.status === 'success' && (
          <div className="result-panel">
            <h2>Phản hồi thực tế từ FastAPI Backend</h2>
            <pre>{JSON.stringify(state.data, null, 2)}</pre>
          </div>
        )}

        {state.status === 'error' && (
          <div className="error-panel" role="alert">
            <h2>Không thể kết nối tới Backend</h2>
            <p>{state.error}</p>
          </div>
        )}

        <footer className="action-row">
          <button
            type="button"
            className="primary-button"
            onClick={handleRetry}
            disabled={isLoading}
          >
            {isLoading ? 'Đang kiểm tra...' : 'Thử lại kết nối'}
          </button>
        </footer>
      </section>
    </main>
  )
}
