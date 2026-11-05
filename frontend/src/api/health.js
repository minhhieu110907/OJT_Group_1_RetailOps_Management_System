import { apiClient } from './client'

export async function fetchHealthStatus(config = {}) {
  const response = await apiClient.get('/health', config)
  return {
    data: response.data,
    httpStatus: response.status,
  }
}
