import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import axiosClient, { getApiErrorMessage } from '../api/axiosClient.js';
import {
  suppliersApi,
  validateSupplierRead,
  validateSupplierListResponse,
  isValidIsoTimestamp,
  VALID_SUPPLIER_STATUSES,
} from '../api/suppliersApi.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const VALID_SUPPLIER_FIXTURE = {
  id: 1,
  name: 'Công ty Cổ phần Sữa Việt Nam (Vinamilk)',
  contact_email: 'contact@vinamilk.com.vn',
  contact_phone: '028 5415 5555',
  status: 'ACTIVE',
  created_at: '2026-11-01T08:00:00.000Z',
  updated_at: '2026-11-01T08:00:00.000Z',
};

const VALID_SUPPLIER_NULL_CONTACTS = {
  id: 2,
  name: 'Công ty TNHH Nước Giải Khát Suntory PepsiCo',
  contact_email: null,
  contact_phone: null,
  status: 'INACTIVE',
  created_at: '2026-11-02T10:30:00.000Z',
  updated_at: '2026-11-03T14:20:00.000Z',
};

describe('T04A70D Supplier Management & Real API Integration Test Suite', () => {
  beforeEach(() => {
    // Reset any stubbed methods on axiosClient
    delete axiosClient.get;
    delete axiosClient.post;
    delete axiosClient.patch;
  });

  // ==========================================================================
  // 1. F01: SupplierRead Schema Validation & Invariants (Fail-Closed)
  // ==========================================================================
  describe('F01: SupplierRead Schema Validation & Invariants (Fail-Closed)', () => {
    test('validates ISO timestamps accurately with timezone & leap year check', () => {
      assert.equal(isValidIsoTimestamp('2026-11-01T08:00:00.000Z'), true);
      assert.equal(isValidIsoTimestamp('2026-11-01 08:00:00'), true);
      assert.equal(isValidIsoTimestamp('2024-02-29T12:00:00Z'), true); // Leap year 2024
      assert.equal(isValidIsoTimestamp('2026-02-29T12:00:00Z'), false); // Non-leap year 2026
      assert.equal(isValidIsoTimestamp(''), false);
      assert.equal(isValidIsoTimestamp('not-a-timestamp'), false);
      assert.equal(isValidIsoTimestamp(null), false);
    });

    test('validates VALID_SUPPLIER_STATUSES directly (ACTIVE, INACTIVE)', () => {
      assert.ok(VALID_SUPPLIER_STATUSES.has('ACTIVE'));
      assert.ok(VALID_SUPPLIER_STATUSES.has('INACTIVE'));
      assert.equal(VALID_SUPPLIER_STATUSES.has('PENDING'), false);
      assert.equal(VALID_SUPPLIER_STATUSES.has('DELETED'), false);
    });

    test('validates full valid SupplierRead contract accurately', () => {
      const result = validateSupplierRead(VALID_SUPPLIER_FIXTURE);
      assert.deepEqual(result, VALID_SUPPLIER_FIXTURE);
    });

    test('validates SupplierRead with nullable contact_email and contact_phone', () => {
      const result = validateSupplierRead(VALID_SUPPLIER_NULL_CONTACTS);
      assert.deepEqual(result, VALID_SUPPLIER_NULL_CONTACTS);
    });

    test('rejects non-object or null supplier payload', () => {
      assert.throws(() => validateSupplierRead(null), /must be an object|null or not an object/i);
      assert.throws(() => validateSupplierRead(undefined), /must be an object|null or not an object/i);
      assert.throws(() => validateSupplierRead('string'), /must be an object|null or not an object/i);
      assert.throws(() => validateSupplierRead(123), /must be an object|null or not an object/i);
    });

    test('strictly rejects invalid or missing supplier ID', () => {
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, id: null }), /Invalid supplier ID/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, id: 0 }), /Invalid supplier ID/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, id: -5 }), /Invalid supplier ID/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, id: '1' }), /Invalid supplier ID/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, id: 1.5 }), /Invalid supplier ID/i);
    });

    test('strictly rejects invalid or empty supplier name', () => {
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, name: '' }), /invalid name/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, name: '   ' }), /invalid name/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, name: null }), /invalid name/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, name: 12345 }), /invalid name/i);
    });

    test('strictly rejects invalid status (must be strictly ACTIVE or INACTIVE)', () => {
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, status: 'PENDING' }), /invalid status/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, status: 'active' }), /invalid status/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, status: null }), /invalid status/i);
      assert.throws(() => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, status: '' }), /invalid status/i);
    });

    test('strictly rejects non-string contact fields when provided', () => {
      assert.throws(
        () => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, contact_email: 12345 }),
        /invalid contact_email/i
      );
      assert.throws(
        () => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, contact_phone: ['028123456'] }),
        /invalid contact_phone/i
      );
    });

    test('strictly rejects invalid created_at or updated_at timestamps', () => {
      assert.throws(
        () => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, created_at: 'invalid-date' }),
        /invalid created_at/i
      );
      assert.throws(
        () => validateSupplierRead({ ...VALID_SUPPLIER_FIXTURE, updated_at: null }),
        /invalid updated_at/i
      );
    });
  });

  // ==========================================================================
  // 2. F02: SupplierListResponse Paginated Envelope Validation (Fail-Closed)
  // ==========================================================================
  describe('F02: SupplierListResponse Paginated Envelope Validation (Fail-Closed)', () => {
    test('validates valid paginated envelope with accurate totalPages computation', () => {
      const payload = {
        items: [VALID_SUPPLIER_FIXTURE, VALID_SUPPLIER_NULL_CONTACTS],
        total: 2,
        page: 1,
        page_size: 20,
      };

      const result = validateSupplierListResponse(payload);
      assert.equal(result.items.length, 2);
      assert.equal(result.total, 2);
      assert.equal(result.page, 1);
      assert.equal(result.page_size, 20);
      assert.equal(result.totalPages, 1);
    });

    test('calculates correct totalPages across multiple pages', () => {
      const payload = {
        items: [VALID_SUPPLIER_FIXTURE],
        total: 45,
        page: 2,
        page_size: 20,
      };

      const result = validateSupplierListResponse(payload);
      assert.equal(result.totalPages, 3);
      assert.equal(result.page, 2);
    });

    test('rejects non-object envelope', () => {
      assert.throws(() => validateSupplierListResponse(null), /not an object/i);
      assert.throws(() => validateSupplierListResponse('invalid'), /not an object/i);
    });

    test('strictly rejects missing or non-array items', () => {
      assert.throws(
        () => validateSupplierListResponse({ items: null, total: 0, page: 1, page_size: 20 }),
        /must be an array/i
      );
      assert.throws(
        () => validateSupplierListResponse({ items: 'not-array', total: 0, page: 1, page_size: 20 }),
        /must be an array/i
      );
    });

    test('strictly rejects negative or non-integer pagination bounds', () => {
      assert.throws(
        () => validateSupplierListResponse({ items: [], total: -1, page: 1, page_size: 20 }),
        /non-negative integer/i
      );
      assert.throws(
        () => validateSupplierListResponse({ items: [], total: 0, page: 0, page_size: 20 }),
        /positive integer/i
      );
      assert.throws(
        () => validateSupplierListResponse({ items: [], total: 0, page: 1, page_size: 0 }),
        /positive integer/i
      );
    });
  });

  // ==========================================================================
  // 3. F03: suppliersApi Real API Query Parameters & Strict Contracts
  // ==========================================================================
  describe('F03: suppliersApi Real API Query Parameters & Strict Contracts', () => {
    test('getSuppliers passes page, page_size, status, and search query parameters correctly', async () => {
      let capturedConfig = null;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return {
          data: {
            items: [VALID_SUPPLIER_FIXTURE],
            total: 1,
            page: 2,
            page_size: 10,
          },
        };
      };

      const result = await suppliersApi.getSuppliers({
        page: 2,
        pageSize: 10,
        status: 'ACTIVE',
        search: 'Vinamilk',
      });

      assert.equal(capturedConfig.url, '/suppliers');
      assert.deepEqual(capturedConfig.config.params, {
        page: 2,
        page_size: 10,
        status: 'ACTIVE',
        search: 'Vinamilk',
      });
      assert.equal(result.items.length, 1);
      assert.equal(result.totalPages, 1);
    });

    test('getSuppliers omits status if not in VALID_SUPPLIER_STATUSES and omits empty search', async () => {
      let capturedConfig = null;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return {
          data: {
            items: [],
            total: 0,
            page: 1,
            page_size: 20,
          },
        };
      };

      await suppliersApi.getSuppliers({
        page: 1,
        pageSize: 20,
        status: 'ALL', // Invalid status -> omitted
        search: '   ', // Blank search -> omitted
      });

      assert.deepEqual(capturedConfig.config.params, {
        page: 1,
        page_size: 20,
      });
    });

    test('getActiveSuppliers forces status=ACTIVE parameter for draft receipt integration', async () => {
      let capturedConfig = null;
      axiosClient.get = async (url, config) => {
        capturedConfig = { url, config };
        return {
          data: {
            items: [VALID_SUPPLIER_FIXTURE],
            total: 1,
            page: 1,
            page_size: 100,
          },
        };
      };

      const result = await suppliersApi.getActiveSuppliers({ page: 1, pageSize: 100 });
      assert.equal(capturedConfig.config.params.status, 'ACTIVE');
      assert.equal(result.items[0].status, 'ACTIVE');
    });

    test('getSupplier calls GET /suppliers/:id with valid integer ID', async () => {
      let capturedUrl = null;
      axiosClient.get = async (url) => {
        capturedUrl = url;
        return { data: VALID_SUPPLIER_FIXTURE };
      };

      const res = await suppliersApi.getSupplier(1);
      assert.equal(capturedUrl, '/suppliers/1');
      assert.equal(res.id, 1);
    });

    test('getSupplier strictly rejects invalid ID before sending HTTP request', async () => {
      await assert.rejects(() => suppliersApi.getSupplier(0), /Invalid supplier ID/i);
      await assert.rejects(() => suppliersApi.getSupplier(-1), /Invalid supplier ID/i);
      await assert.rejects(() => suppliersApi.getSupplier('abc'), /Invalid supplier ID/i);
    });

    test('createSupplier strictly trims name and sends only allowed fields (no extra forbidden fields)', async () => {
      let capturedPayload = null;
      axiosClient.post = async (url, payload) => {
        capturedPayload = payload;
        return { data: { ...VALID_SUPPLIER_FIXTURE, name: payload.name } };
      };

      await suppliersApi.createSupplier({
        name: '   Nhà Phân Phối Masan   ',
        contact_email: '  masan@consumer.vn  ',
        contact_phone: '  028 3822 5555  ',
        // Should not accept or forward extra fields
      });

      assert.deepEqual(capturedPayload, {
        name: 'Nhà Phân Phối Masan',
        contact_email: 'masan@consumer.vn',
        contact_phone: '028 3822 5555',
      });
    });

    test('createSupplier rejects empty or whitespace name', async () => {
      await assert.rejects(
        () => suppliersApi.createSupplier({ name: '   ' }),
        /Tên nhà cung cấp không được để trống/i
      );
    });

    test('updateSupplier supports explicit null to clear contact fields', async () => {
      let capturedPayload = null;
      let capturedUrl = null;
      axiosClient.patch = async (url, payload) => {
        capturedUrl = url;
        capturedPayload = payload;
        return {
          data: {
            ...VALID_SUPPLIER_FIXTURE,
            ...payload,
            updated_at: '2026-11-05T12:00:00.000Z',
          },
        };
      };

      await suppliersApi.updateSupplier(1, {
        name: 'Tên Đã Cập Nhật',
        contact_email: null,
        contact_phone: null,
      });

      assert.equal(capturedUrl, '/suppliers/1');
      assert.deepEqual(capturedPayload, {
        name: 'Tên Đã Cập Nhật',
        contact_email: null,
        contact_phone: null,
      });
    });

    test('updateSupplierStatus validates status and calls PATCH /suppliers/:id/status', async () => {
      let capturedUrl = null;
      let capturedPayload = null;
      axiosClient.patch = async (url, payload) => {
        capturedUrl = url;
        capturedPayload = payload;
        return {
          data: {
            ...VALID_SUPPLIER_FIXTURE,
            status: payload.status,
            updated_at: '2026-11-05T12:00:00.000Z',
          },
        };
      };

      const res = await suppliersApi.updateSupplierStatus(1, 'INACTIVE');
      assert.equal(capturedUrl, '/suppliers/1/status');
      assert.deepEqual(capturedPayload, { status: 'INACTIVE' });
      assert.equal(res.status, 'INACTIVE');

      // Rejects invalid status
      await assert.rejects(
        () => suppliersApi.updateSupplierStatus(1, 'INVALID_STATUS'),
        /Invalid status/i
      );
    });
  });

  // ==========================================================================
  // 4. F04: Error Envelopes (401/403/404/409/422) & No Silent Mock Fallback
  // ==========================================================================
  describe('F04: Error Envelopes (401/403/404/409/422) & No Silent Mock Fallback', () => {
    test('handles 401, 403, 404, 409 Conflict, and 422 Validation cleanly without falling back to Mock', async () => {
      const errorScenarios = [
        { status: 401, code: 'UNAUTHORIZED', message: 'Phiên đăng nhập đã hết hạn.' },
        { status: 403, code: 'FORBIDDEN', message: 'Yêu cầu quyền Quản trị viên (ADMIN).' },
        { status: 404, code: 'NOT_FOUND', message: 'Không tìm thấy nhà cung cấp với mã 999.' },
        { status: 409, code: 'CONFLICT', message: 'Trùng thông tin hoặc trạng thái nhà cung cấp xung đột.' },
        { status: 422, code: 'VALIDATION_ERROR', message: 'Dữ liệu đầu vào không đúng định dạng.' },
      ];

      for (const scenario of errorScenarios) {
        axiosClient.get = async () => {
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
              await suppliersApi.getSuppliers();
            } catch (err) {
              const extracted = getApiErrorMessage(err);
              assert.equal(extracted, scenario.message);
              throw err;
            }
          },
          (err) => err.response?.status === scenario.status
        );
      }
    });

    test('network failure throws genuine error and extracts error message without mock fallback', async () => {
      axiosClient.get = async () => {
        const networkError = new Error('Network Error');
        networkError.code = 'ERR_NETWORK';
        throw networkError;
      };

      await assert.rejects(
        async () => {
          await suppliersApi.getSuppliers();
        },
        (err) => {
          const msg = getApiErrorMessage(err, 'Lỗi kết nối máy chủ.');
          assert.ok(msg.length > 0);
          return true;
        }
      );
    });
  });

  // ==========================================================================
  // 5. F05: RBAC & Security Invariants on Supplier UI (AUTH-04, FE-01, T04A70D)
  // ==========================================================================
  describe('F05: RBAC & Security Invariants on Supplier UI (AUTH-04, FE-01, T04A70D)', () => {
    test('SupplierList component strictly verifies role ADMIN using useAuth', () => {
      const supplierListPath = path.resolve(
        __dirname,
        '../pages/Suppliers/SupplierList.jsx'
      );
      assert.ok(fs.existsSync(supplierListPath), 'SupplierList.jsx must exist');
      const content = fs.readFileSync(supplierListPath, 'utf8');

      // Must import useAuth
      assert.ok(
        content.includes("useAuth"),
        'SupplierList.jsx must import and use useAuth hook'
      );

      // Must check user role === 'ADMIN'
      assert.ok(
        content.includes("user?.role === 'ADMIN'"),
        "SupplierList.jsx must verify user?.role === 'ADMIN'"
      );

      // Must guard create action with isAdmin
      assert.ok(
        content.includes('{isAdmin &&') && content.includes('Thêm nhà cung cấp'),
        'Create button must be conditionally rendered only for ADMIN'
      );

      // Must guard table action column with isAdmin
      assert.ok(
        content.includes('if (isAdmin)'),
        'Action column in table must be conditionally added only for ADMIN'
      );

      // Must guard drawer actions with isAdmin
      assert.ok(
        content.includes('disabled={!isAdmin || isSubmitting}'),
        'Form inputs in drawer must be disabled for non-ADMIN'
      );

      // Must handle 403 Forbidden
      assert.ok(
        content.includes('403'),
        'SupplierList.jsx must handle 403 Forbidden state gracefully'
      );
    });

    test('SupplierList component does not store tokens in localStorage', () => {
      const supplierListPath = path.resolve(
        __dirname,
        '../pages/Suppliers/SupplierList.jsx'
      );
      const content = fs.readFileSync(supplierListPath, 'utf8');
      assert.equal(
        content.includes('localStorage.setItem'),
        false,
        'SupplierList.jsx must not store tokens in localStorage'
      );
    });

    test('suppliersApi.js is fail-closed and contains zero mock fallbacks', () => {
      const apiPath = path.resolve(__dirname, '../api/suppliersApi.js');
      const content = fs.readFileSync(apiPath, 'utf8');

      assert.equal(
        content.includes('mockSuppliers'),
        false,
        'suppliersApi.js must not contain mockSuppliers data'
      );
      assert.equal(
        content.includes('isMockMode'),
        false,
        'suppliersApi.js must not check isMockMode'
      );
    });
  });

  // ==========================================================================
  // 6. F06: Business Constraint PUR-01 / PUR-02
  // ==========================================================================
  describe('F06: Business Constraints PUR-01 & PUR-02', () => {
    test('getActiveSuppliers returns only ACTIVE suppliers to prevent selecting INACTIVE suppliers in ReceiptEditor', async () => {
      const allSuppliers = [
        VALID_SUPPLIER_FIXTURE, // ACTIVE
        VALID_SUPPLIER_NULL_CONTACTS, // INACTIVE
      ];

      axiosClient.get = async (_url, config) => {
        // Backend filters by status query param
        const filtered = allSuppliers.filter((s) => !config.params.status || s.status === config.params.status);
        return {
          data: {
            items: filtered,
            total: filtered.length,
            page: 1,
            page_size: 20,
          },
        };
      };

      const result = await suppliersApi.getActiveSuppliers();
      assert.equal(result.items.length, 1);
      assert.equal(result.items[0].status, 'ACTIVE');
      assert.equal(result.items[0].id, 1);
    });
  });
});

