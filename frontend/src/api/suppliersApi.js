import axiosClient from './axiosClient.js';

export const VALID_SUPPLIER_STATUSES = new Set(['ACTIVE', 'INACTIVE']);

export function isValidIsoTimestamp(val) {
  if (typeof val !== 'string' || !val.trim()) return false;
  const trimmed = val.trim();
  const match = trimmed.match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(?:Z|([+-]\d{2}:?\d{2}))?$/
  );
  if (!match) return false;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);

  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;
  if (hour < 0 || hour > 23) return false;
  if (minute < 0 || minute > 59) return false;
  if (second < 0 || second > 59) return false;

  const isLeapYear = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const daysInMonths = [31, isLeapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (day > daysInMonths[month - 1]) return false;

  return true;
}

export function validateSupplierRead(item) {
  if (!item || typeof item !== 'object') {
    throw new Error('Schema violation: Supplier item is null or not an object.');
  }

  if (typeof item.id !== 'number' || !Number.isInteger(item.id) || item.id <= 0) {
    throw new Error(`Schema violation: Invalid supplier ID "${item.id}".`);
  }

  if (typeof item.name !== 'string' || !item.name.trim()) {
    throw new Error(`Schema violation: Supplier ${item.id} has invalid name.`);
  }

  if (typeof item.status !== 'string' || !VALID_SUPPLIER_STATUSES.has(item.status)) {
    throw new Error(`Schema violation: Supplier ${item.id} has invalid status "${item.status}".`);
  }

  if (item.contact_email !== null && item.contact_email !== undefined && typeof item.contact_email !== 'string') {
    throw new Error(`Schema violation: Supplier ${item.id} has invalid contact_email.`);
  }

  if (item.contact_phone !== null && item.contact_phone !== undefined && typeof item.contact_phone !== 'string') {
    throw new Error(`Schema violation: Supplier ${item.id} has invalid contact_phone.`);
  }

  if (!isValidIsoTimestamp(item.created_at)) {
    throw new Error(`Schema violation: Supplier ${item.id} has invalid created_at timestamp.`);
  }

  if (!isValidIsoTimestamp(item.updated_at)) {
    throw new Error(`Schema violation: Supplier ${item.id} has invalid updated_at timestamp.`);
  }

  return {
    id: item.id,
    name: item.name.trim(),
    contact_email: item.contact_email ? item.contact_email.trim() : null,
    contact_phone: item.contact_phone ? item.contact_phone.trim() : null,
    status: item.status,
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

export function validateSupplierListResponse(payload) {
  if (!payload || typeof payload !== 'object') {
    throw new Error('Schema violation: Supplier response is not an object.');
  }

  const { items, total, page, page_size } = payload;

  if (!Array.isArray(items)) {
    throw new Error('Schema violation: "items" must be an array.');
  }

  if (typeof total !== 'number' || !Number.isInteger(total) || total < 0) {
    throw new Error('Schema violation: "total" must be a non-negative integer.');
  }

  if (typeof page !== 'number' || !Number.isInteger(page) || page < 1) {
    throw new Error('Schema violation: "page" must be a positive integer.');
  }

  if (typeof page_size !== 'number' || !Number.isInteger(page_size) || page_size < 1) {
    throw new Error('Schema violation: "page_size" must be a positive integer.');
  }

  const validatedItems = items.map((item) => validateSupplierRead(item));

  return {
    items: validatedItems,
    total,
    page,
    page_size,
    totalPages: Math.max(1, Math.ceil(total / page_size)),
  };
}

export const suppliersApi = {
  async getSuppliers({ page = 1, pageSize = 20, status = '', search = '' } = {}) {
    const params = {
      page: Number(page) || 1,
      page_size: Number(pageSize) || 20,
    };

    if (status && VALID_SUPPLIER_STATUSES.has(status)) {
      params.status = status;
    }

    if (search && typeof search === 'string' && search.trim()) {
      params.search = search.trim();
    }

    const response = await axiosClient.get('/suppliers', { params });
    return validateSupplierListResponse(response.data);
  },

  async getActiveSuppliers({ page = 1, pageSize = 100, search = '' } = {}) {
    return this.getSuppliers({ page, pageSize, status: 'ACTIVE', search });
  },

  async getSupplier(id) {
    if (!id || typeof id !== 'number' || id <= 0) {
      throw new Error('Invalid supplier ID.');
    }
    const response = await axiosClient.get(`/suppliers/${id}`);
    return validateSupplierRead(response.data);
  },

  async createSupplier({ name, contact_email = null, contact_phone = null }) {
    const trimmedName = typeof name === 'string' ? name.trim() : '';
    if (!trimmedName) {
      throw new Error('Tên nhà cung cấp không được để trống.');
    }

    const payload = {
      name: trimmedName,
      contact_email: contact_email?.trim() || null,
      contact_phone: contact_phone?.trim() || null,
    };

    const response = await axiosClient.post('/suppliers', payload);
    return validateSupplierRead(response.data);
  },

  async updateSupplier(id, { name, contact_email, contact_phone }) {
    if (!id || typeof id !== 'number' || id <= 0) {
      throw new Error('Invalid supplier ID.');
    }

    const payload = {};
    if (name !== undefined) {
      const trimmedName = typeof name === 'string' ? name.trim() : '';
      if (!trimmedName) {
        throw new Error('Tên nhà cung cấp không được để trống.');
      }
      payload.name = trimmedName;
    }

    if (contact_email !== undefined) {
      payload.contact_email = contact_email ? contact_email.trim() : null;
    }

    if (contact_phone !== undefined) {
      payload.contact_phone = contact_phone ? contact_phone.trim() : null;
    }

    const response = await axiosClient.patch(`/suppliers/${id}`, payload);
    return validateSupplierRead(response.data);
  },

  async updateSupplierStatus(id, newStatus) {
    if (!id || typeof id !== 'number' || id <= 0) {
      throw new Error('Invalid supplier ID.');
    }
    if (!VALID_SUPPLIER_STATUSES.has(newStatus)) {
      throw new Error(`Invalid status "${newStatus}". Expected ACTIVE or INACTIVE.`);
    }

    const response = await axiosClient.patch(`/suppliers/${id}/status`, {
      status: newStatus,
    });
    return validateSupplierRead(response.data);
  },
};

// Chuẩn hóa và so sánh dirty state cho nhà cung cấp (dùng chung cho UI & kiểm thử)
export function normalizeSupplierSnapshot(supplier) {
  if (!supplier) return null;
  const name = typeof supplier.name === 'string' ? supplier.name.trim() : '';
  const contactPhone = typeof supplier.contact_phone === 'string' && supplier.contact_phone.trim()
    ? supplier.contact_phone.trim()
    : null;
  const contactEmail = typeof supplier.contact_email === 'string' && supplier.contact_email.trim()
    ? supplier.contact_email.trim()
    : null;
  const status = supplier.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE';

  return {
    id: supplier.id ?? null,
    name,
    contact_phone: contactPhone,
    contact_email: contactEmail,
    status,
  };
}

export function detectSupplierChanges(currentForm, snapshot) {
  if (!snapshot) {
    return {
      hasInfoChanges: false,
      hasStatusChange: false,
      normalizedPayload: null,
    };
  }

  const currentNormalized = normalizeSupplierSnapshot(currentForm);
  const hasNameChange = currentNormalized.name !== snapshot.name;
  const hasPhoneChange = currentNormalized.contact_phone !== snapshot.contact_phone;
  const hasEmailChange = currentNormalized.contact_email !== snapshot.contact_email;
  const hasStatusChange = currentNormalized.status !== snapshot.status;

  const hasInfoChanges = hasNameChange || hasPhoneChange || hasEmailChange;

  return {
    hasInfoChanges,
    hasStatusChange,
    normalizedPayload: currentNormalized,
  };
}

