import axiosClient, {
  ensureCsrfToken,
  getSessionGeneration,
} from './axiosClient.js';
import { assertRealApiMode } from './productsApi.js';

/**
 * Staff account administration and self-service account APIs.
 * The real backend remains authoritative; never silently fall back to mock.
 */
export const accountApi = {
  async listStaff({ isMockMode = false, status, search, page = 1, pageSize = 20 } = {}) {
    assertRealApiMode(isMockMode);
    const params = { page, page_size: pageSize };
    if (status) params.status = status;
    if (search?.trim()) params.search = search.trim();
    const { data } = await axiosClient.get('/admin/staff', { params });
    if (!data || !Array.isArray(data.items) || !Number.isInteger(data.total)) {
      throw new Error('Phản hồi danh sách tài khoản Staff không hợp lệ.');
    }
    return data;
  },

  async lockStaff(id, isMockMode = false) {
    assertRealApiMode(isMockMode);
    const { data } = await axiosClient.post(`/admin/staff/${id}/lock`);
    return data;
  },

  async unlockStaff(id, isMockMode = false) {
    assertRealApiMode(isMockMode);
    const { data } = await axiosClient.post(`/admin/staff/${id}/unlock`);
    return data;
  },

  async getProfile(isMockMode = false) {
    assertRealApiMode(isMockMode);
    const { data } = await axiosClient.get('/users/me');
    return data;
  },

  async updateProfile(fullName, isMockMode = false) {
    assertRealApiMode(isMockMode);
    const { data } = await axiosClient.patch('/users/me', { full_name: fullName });
    return data;
  },

  async changePassword(currentPassword, newPassword, isMockMode = false) {
    assertRealApiMode(isMockMode);
    const generation = getSessionGeneration();
    const csrf = await ensureCsrfToken(generation);
    if (!csrf || generation !== getSessionGeneration()) {
      throw new Error('Không thể xác minh phiên bảo mật. Vui lòng thử lại.');
    }
    // A non-idempotent credential mutation: one request, no automatic replay.
    const response = await axiosClient.post(
      '/auth/change-password',
      {
        current_password: currentPassword,
        new_password: newPassword,
      },
      {
        headers: { 'X-CSRF-Token': csrf },
        withCredentials: true,
      }
    );
    if (generation !== getSessionGeneration()) {
      throw new Error('Phiên đăng nhập đã thay đổi. Vui lòng đăng nhập lại.');
    }
    return {
      body: response.data,
      csrfToken: response.headers?.['x-csrf-token'] || null,
    };
  },

  async requestPasswordReset(email, isMockMode = false) {
    assertRealApiMode(isMockMode);
    const trimmedEmail = String(email || '').trim().toLowerCase();
    const { data } = await axiosClient.post('/auth/forgot-password', {
      email: trimmedEmail,
    });
    return data;
  },

  async confirmPasswordReset(token, newPassword, isMockMode = false) {
    assertRealApiMode(isMockMode);
    const trimmedToken = String(token || '').trim();
    const { data } = await axiosClient.post('/auth/reset-password', {
      token: trimmedToken,
      new_password: String(newPassword || ''),
    });
    return data;
  },
};
