import axiosClient from './axiosClient.js';

export const purchasesApi = {
  async getPurchaseDrafts({ page = 1, pageSize = 10, search = '', status = '' } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 10,
    };
    if (search && typeof search === 'string' && search.trim()) {
      params.search = search.trim();
    }
    if (status && status !== 'ALL') {
      params.status = status;
    }

    const response = await axiosClient.get('/purchases', { params });
    const data = response.data || {};
    return {
      items: data.items || [],
      total: data.total || 0,
      page: data.page || page,
      page_size: data.page_size || pageSize,
      totalPages: data.total_pages || Math.max(1, Math.ceil((data.total || 0) / (data.page_size || pageSize))),
      stats: data.stats || null,
    };
  },

  async getPurchaseHistory({ page = 1, pageSize = 10, search = '' } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 10,
    };
    if (search && typeof search === 'string' && search.trim()) {
      params.search = search.trim();
    }

    const response = await axiosClient.get('/purchases/history', { params });
    const data = response.data || {};
    return {
      items: data.items || [],
      total: data.total || 0,
      page: data.page || page,
      page_size: data.page_size || pageSize,
      totalPages: data.total_pages || Math.max(1, Math.ceil((data.total || 0) / (data.page_size || pageSize))),
    };
  },

  async confirmPurchase(id) {
    if (!id || id <= 0) {
      throw new Error('ID phiếu nhập không hợp lệ.');
    }
    const response = await axiosClient.post(`/purchases/${id}/confirm`, {});
    return response.data;
  },

  async cancelPurchase(id) {
    if (!id || id <= 0) {
      throw new Error('ID phiếu nhập không hợp lệ.');
    }
    const response = await axiosClient.post(`/purchases/${id}/cancel`, {});
    return response.data;
  },

  async savePurchase(id, data) {
    if (!id || id <= 0) {
      throw new Error('ID phiếu nhập không hợp lệ.');
    }
    const response = await axiosClient.patch(`/purchases/${id}`, data);
    return response.data;
  },

  async createPurchase(data) {
    const response = await axiosClient.post('/purchases', data);
    return response.data;
  },
};

