import axios from 'axios'

const DEFAULT_TIMEOUT_MS = 10000

const parsedTimeout = Number.parseInt(import.meta.env.VITE_API_TIMEOUT, 10)
const timeout =
  Number.isFinite(parsedTimeout) && parsedTimeout > 0
    ? parsedTimeout
    : DEFAULT_TIMEOUT_MS

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout,
  headers: {
    Accept: 'application/json',
  },
})

export function getApiErrorMessage(error) {
  if (axios.isCancel(error)) {
    return ''
  }

  if (error?.code === 'ECONNABORTED') {
    return 'Yêu cầu tới máy chủ quá thời gian chờ. Vui lòng kiểm tra kết nối và thử lại.'
  }

  if (error?.response) {
    const status = error.response.status
    const detail = error.response.data?.detail
    if (typeof detail === 'string' && detail.trim().length > 0) {
      return detail
    }
    if (status >= 500) {
      return 'Máy chủ FastAPI phản hồi lỗi kết nối hoặc dịch vụ tạm thời chưa sẵn sàng. Hãy đảm bảo Backend đang chạy tại cổng đã cấu hình.'
    }
    return `Máy chủ trả về trạng thái không mong đợi (HTTP ${status}).`
  }

  return 'Không thể kết nối tới FastAPI Backend. Hãy kiểm tra dịch vụ Backend và cấu hình Vite proxy.'
}
