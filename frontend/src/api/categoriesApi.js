import axiosClient from './axiosClient.js';
import {
  VALID_CATALOG_STATUSES,
  validateCategoryRead,
  validatePaginatedResponse,
} from './productsApi.js';

export const categoriesApi = {
  async getCategories({ page = 1, pageSize = 8, status = '', search = '' } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 8,
    };
    if (status && VALID_CATALOG_STATUSES.has(status)) {
      params.status = status;
    }
    if (search && typeof search === 'string' && search.trim()) {
      params.search = search.trim();
    }

    const response = await axiosClient.get('/categories', { params });
    const validated = validatePaginatedResponse(response.data, validateCategoryRead);
    return {
      ...validated,
      totalPages: Math.max(1, Math.ceil(validated.total / validated.page_size)),
    };
  },

  async getCategory(id) {
    if (!id || typeof id !== 'number' || id <= 0) {
      throw new Error('ID danh mục không hợp lệ.');
    }
    const response = await axiosClient.get(`/categories/${id}`);
    return validateCategoryRead(response.data);
  },

  async createCategory({ name, description = undefined }) {
    const trimmed = typeof name === 'string' ? name.trim() : '';
    if (!trimmed) {
      throw new Error('Tên danh mục không được để trống.');
    }

    const payload = { name: trimmed };
    if (description !== undefined) {
      if (description !== null && typeof description !== 'string') {
        throw new Error('Mô tả danh mục không hợp lệ.');
      }
      const trimmedDesc = typeof description === 'string' ? description.trim() : '';
      if (trimmedDesc.length > 2000) {
        throw new Error('Mô tả danh mục không được vượt quá 2000 ký tự.');
      }
      payload.description = trimmedDesc || null;
    }

    const response = await axiosClient.post('/categories', payload);
    return validateCategoryRead(response.data);
  },

  async updateCategory(id, { name, description = undefined }) {
    if (!id || typeof id !== 'number' || id <= 0) {
      throw new Error('ID danh mục không hợp lệ.');
    }
    const trimmed = typeof name === 'string' ? name.trim() : '';
    if (!trimmed) {
      throw new Error('Tên danh mục không được để trống.');
    }

    const payload = { name: trimmed };
    if (description !== undefined) {
      if (description !== null && typeof description !== 'string') {
        throw new Error('Mô tả danh mục không hợp lệ.');
      }
      const trimmedDesc = typeof description === 'string' ? description.trim() : '';
      if (trimmedDesc.length > 2000) {
        throw new Error('Mô tả danh mục không được vượt quá 2000 ký tự.');
      }
      payload.description = trimmedDesc || null;
    }

    const response = await axiosClient.patch(`/categories/${id}`, payload);
    return validateCategoryRead(response.data);
  },

  async updateCategoryStatus(id, newStatus) {
    if (!id || typeof id !== 'number' || id <= 0) {
      throw new Error('ID danh mục không hợp lệ.');
    }
    if (!VALID_CATALOG_STATUSES.has(newStatus)) {
      throw new Error(`Trạng thái không hợp lệ "${newStatus}".`);
    }

    const response = await axiosClient.patch(`/categories/${id}/status`, {
      status: newStatus,
    });
    return validateCategoryRead(response.data);
  },
};

