import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient, { getApiErrorMessage } from '../api/axiosClient.js';
import { categoriesApi } from '../api/categoriesApi.js';
import {
  validateCategoryRead,
  VALID_CATALOG_STATUSES,
} from '../api/productsApi.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const VALID_CATEGORY_FIXTURE = {
  id: 1,
  name: 'Đồ uống & Giải khát',
  status: 'ACTIVE',
  created_at: '2026-11-01T00:00:00.000Z',
  updated_at: '2026-11-01T00:00:00.000Z',
};

const INACTIVE_CATEGORY_FIXTURE = {
  id: 2,
  name: 'Văn phòng phẩm thanh lý',
  status: 'INACTIVE',
  created_at: '2026-11-02T10:00:00.000Z',
  updated_at: '2026-11-03T11:00:00.000Z',
};

describe('T04A70D Category Management & Real API Integration Test Suite', () => {
  beforeEach(() => {
    delete axiosClient.get;
    delete axiosClient.post;
    delete axiosClient.patch;
  });

  // ==========================================================================
  // 1. F01: CategoryRead Schema Validation & Invariants (Fail-Closed)
  // ==========================================================================
  describe('F01: CategoryRead Schema Validation & Invariants (Fail-Closed)', () => {
    test('validates valid CategoryRead contract accurately', () => {
      const result = validateCategoryRead(VALID_CATEGORY_FIXTURE);
      assert.deepEqual(result, VALID_CATEGORY_FIXTURE);
    });

    test('validates VALID_CATALOG_STATUSES correctly (ACTIVE, INACTIVE)', () => {
      assert.ok(VALID_CATALOG_STATUSES.has('ACTIVE'));
      assert.ok(VALID_CATALOG_STATUSES.has('INACTIVE'));
      assert.equal(VALID_CATALOG_STATUSES.has('PENDING'), false);
    });

    test('rejects non-object or null category payloads', () => {
      assert.throws(() => validateCategoryRead(null), /must be an object/i);
      assert.throws(() => validateCategoryRead(undefined), /must be an object/i);
      assert.throws(() => validateCategoryRead('string'), /must be an object/i);
    });

    test('strictly rejects invalid or missing category ID', () => {
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, id: null }), /missing valid integer id/i);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, id: 0 }), /missing valid integer id/i);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, id: -1 }), /missing valid integer id/i);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, id: '1' }), /missing valid integer id/i);
    });

    test('strictly rejects invalid or empty category name', () => {
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, name: '' }), /missing valid name/i);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, name: '   ' }), /missing valid name/i);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, name: null }), /missing valid name/i);
    });

    test('strictly rejects invalid status', () => {
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, status: 'UNKNOWN' }), /invalid status/i);
      assert.throws(() => validateCategoryRead({ ...VALID_CATEGORY_FIXTURE, status: null }), /invalid status/i);
    });
  });

  // ==========================================================================
  // 2. F02: categoriesApi Real API Query Parameters & Strict Contracts
  // ==========================================================================
  describe('F02: categoriesApi Real API Query Parameters & Strict Contracts', () => {
    test('getCategories sends page, page_size, status, and search query parameters', async () => {
      let capturedConfig = null;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return {
          data: {
            items: [VALID_CATEGORY_FIXTURE],
            total: 1,
            page: 1,
            page_size: 8,
          },
        };
      };

      const result = await categoriesApi.getCategories({
        page: 1,
        pageSize: 8,
        status: 'ACTIVE',
        search: 'Đồ uống',
      });

      assert.equal(capturedConfig.url, '/categories');
      assert.deepEqual(capturedConfig.config.params, {
        page: 1,
        page_size: 8,
        status: 'ACTIVE',
        search: 'Đồ uống',
      });
      assert.equal(result.items.length, 1);
      assert.equal(result.totalPages, 1);
    });

    test('getCategory calls GET /categories/:id with valid integer ID', async () => {
      let capturedUrl = null;
      axiosClient.get = async (url) => {
        capturedUrl = url;
        return { data: VALID_CATEGORY_FIXTURE };
      };

      const res = await categoriesApi.getCategory(1);
      assert.equal(capturedUrl, '/categories/1');
      assert.equal(res.id, 1);
    });

    test('createCategory sends only name to satisfy backend extra="forbid"', async () => {
      let capturedPayload = null;
      axiosClient.post = async (url, payload) => {
        capturedPayload = payload;
        return {
          data: {
            ...VALID_CATEGORY_FIXTURE,
            name: payload.name,
          },
        };
      };

      await categoriesApi.createCategory({
        name: '   Bánh kẹo các loại   ',
        description: 'Mô tả không được gửi lên server',
      });

      assert.deepEqual(capturedPayload, {
        name: 'Bánh kẹo các loại',
      });
    });

    test('updateCategory sends only name to satisfy backend extra="forbid"', async () => {
      let capturedUrl = null;
      let capturedPayload = null;
      axiosClient.patch = async (url, payload) => {
        capturedUrl = url;
        capturedPayload = payload;
        return {
          data: {
            ...VALID_CATEGORY_FIXTURE,
            name: payload.name,
          },
        };
      };

      await categoriesApi.updateCategory(1, {
        name: '   Bánh kẹo nhập khẩu   ',
      });

      assert.equal(capturedUrl, '/categories/1');
      assert.deepEqual(capturedPayload, {
        name: 'Bánh kẹo nhập khẩu',
      });
    });

    test('updateCategoryStatus calls PATCH /categories/:id/status with valid status', async () => {
      let capturedUrl = null;
      let capturedPayload = null;
      axiosClient.patch = async (url, payload) => {
        capturedUrl = url;
        capturedPayload = payload;
        return {
          data: {
            ...INACTIVE_CATEGORY_FIXTURE,
            status: payload.status,
          },
        };
      };

      const res = await categoriesApi.updateCategoryStatus(2, 'INACTIVE');
      assert.equal(capturedUrl, '/categories/2/status');
      assert.deepEqual(capturedPayload, { status: 'INACTIVE' });
      assert.equal(res.status, 'INACTIVE');

      await assert.rejects(
        () => categoriesApi.updateCategoryStatus(2, 'DELETED'),
        /Trạng thái không hợp lệ/i
      );
    });
  });

  // ==========================================================================
  // 3. F03: Error Envelopes (401/403/409/422) & No Silent Mock Fallback
  // ==========================================================================
  describe('F03: Error Envelopes (401/403/409/422) & No Silent Mock Fallback', () => {
    test('handles 401, 403, 404, 409 Duplicate Name, and 422 Validation without mock fallback', async () => {
      const errorScenarios = [
        { status: 401, code: 'UNAUTHORIZED', message: 'Phiên đăng nhập đã hết hạn.' },
        { status: 403, code: 'FORBIDDEN', message: 'Yêu cầu quyền Quản trị viên (ADMIN).' },
        { status: 404, code: 'NOT_FOUND', message: 'Không tìm thấy danh mục.' },
        { status: 409, code: 'DUPLICATE_CATEGORY', message: 'Tên danh mục đã tồn tại.' },
        { status: 422, code: 'VALIDATION_ERROR', message: 'Dữ liệu đầu vào không hợp lệ.' },
      ];

      for (const scenario of errorScenarios) {
        axiosClient.post = async () => {
          const err = new Error(scenario.message);
          err.response = {
            status: scenario.status,
            data: {
              code: scenario.code,
              message: scenario.message,
              details: null,
            },
          };
          throw err;
        };

        await assert.rejects(
          async () => {
            try {
              await categoriesApi.createCategory({ name: 'Trùng tên' });
            } catch (err) {
              const msg = getApiErrorMessage(err);
              assert.equal(msg, scenario.message);
              throw err;
            }
          },
          (err) => err.response?.status === scenario.status
        );
      }
    });
  });

  // ==========================================================================
  // 4. F04: RBAC & Security Invariants in CategoryList.jsx (AUTH-04, FE-01)
  // ==========================================================================
  describe('F04: RBAC & Security Invariants in CategoryList.jsx (AUTH-04, FE-01)', () => {
    test('CategoryList component strictly verifies role ADMIN using useAuth', () => {
      const categoryListPath = path.resolve(
        __dirname,
        '../pages/Categories/CategoryList.jsx'
      );
      assert.ok(fs.existsSync(categoryListPath), 'CategoryList.jsx must exist');
      const content = fs.readFileSync(categoryListPath, 'utf8');

      // Must import useAuth
      assert.ok(
        content.includes("useAuth"),
        'CategoryList.jsx must import useAuth'
      );

      // Must check user role === 'ADMIN'
      assert.ok(
        content.includes("user?.role === 'ADMIN'"),
        "CategoryList.jsx must verify user?.role === 'ADMIN'"
      );

      // Must guard create button with isAdmin
      assert.ok(
        content.includes('{isAdmin &&') && content.includes('Thêm danh mục'),
        'Create category button must be conditionally rendered only for ADMIN'
      );

      // Must guard action column in table
      assert.ok(
        content.includes('if (isAdmin)'),
        'Action column must be conditionally added only for ADMIN'
      );

      // Must disable drawer inputs when not ADMIN
      assert.ok(
        content.includes('disabled={!isAdmin || isSubmitting}'),
        'Drawer inputs must be disabled for non-ADMIN'
      );
    });
  });
});
