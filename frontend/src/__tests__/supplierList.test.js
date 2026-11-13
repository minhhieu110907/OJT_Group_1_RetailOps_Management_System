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
  normalizeSupplierSnapshot,
  detectSupplierChanges,
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

  // ==========================================================================
  // 7. F07: Supplier Modal Refactor, Native Form Semantics & Regression
  // ==========================================================================
  describe('F07: Supplier Modal Refactor, Native Form Semantics & Regression', () => {
    const supplierListPath = path.resolve(__dirname, '../pages/Suppliers/SupplierList.jsx');
    const supplierCssPath = path.resolve(__dirname, '../pages/Suppliers/SupplierList.module.css');

    test('SupplierList imports shared Modal and modalStyles cleanly', () => {
      const content = fs.readFileSync(supplierListPath, 'utf8');
      assert.ok(content.includes("import { Modal, Pagination, Table, useToast } from '../../components/common';"));
      assert.ok(content.includes("import modalStyles from '../../components/common/Modal/Modal.module.css';"));
    });

    test('SupplierList completely removes obsolete Drawer classes from JSX and CSS', () => {
      const jsxContent = fs.readFileSync(supplierListPath, 'utf8');
      const cssContent = fs.readFileSync(supplierCssPath, 'utf8');

      // Obsolete drawer elements must not exist
      assert.equal(jsxContent.includes('styles.drawerOverlay'), false, 'drawerOverlay must not exist in JSX');
      assert.equal(jsxContent.includes('styles.drawerHeader'), false, 'drawerHeader must not exist in JSX');
      assert.equal(jsxContent.includes('styles.drawerBody'), false, 'drawerBody must not exist in JSX');
      assert.equal(jsxContent.includes('styles.drawerFooter'), false, 'drawerFooter must not exist in JSX');
      assert.equal(jsxContent.includes('styles.drawerSection'), false, 'drawerSection must not exist in JSX');

      assert.equal(cssContent.includes('.drawerOverlay'), false, 'drawerOverlay must not exist in CSS');
      assert.equal(cssContent.includes('.drawerHeader'), false, 'drawerHeader must not exist in CSS');
      assert.equal(cssContent.includes('.drawerBody'), false, 'drawerBody must not exist in CSS');
      assert.equal(cssContent.includes('.drawerFooter'), false, 'drawerFooter must not exist in CSS');
      assert.equal(cssContent.includes('.drawerSection'), false, 'drawerSection must not exist in CSS');
    });

    test('SupplierList associates footer submit button via native form attribute and useId()', () => {
      const content = fs.readFileSync(supplierListPath, 'utf8');

      // Must import useId
      assert.ok(content.includes('useId'), 'SupplierList.jsx must import useId');
      assert.ok(content.includes('const supplierFormId = useId();'), 'Must declare supplierFormId with useId()');

      // Form must bind id={supplierFormId} and onSubmit={handleSubmitForm}
      assert.ok(
        content.includes('id={supplierFormId}'),
        'Form must bind id={supplierFormId}'
      );
      assert.ok(
        content.includes('onSubmit={handleSubmitForm}'),
        'Form must bind onSubmit={handleSubmitForm}'
      );

      // Footer confirm button must have type="submit" and form={supplierFormId}
      assert.ok(
        content.includes('type="submit"'),
        'Confirm button must have type="submit"'
      );
      assert.ok(
        content.includes('form={supplierFormId}'),
        'Confirm button must link form={supplierFormId}'
      );

      // Confirm button must not have redundant onClick={handleSubmitForm}
      assert.equal(
        content.includes('onClick={handleSubmitForm}'),
        false,
        'Confirm button must not have redundant onClick handler'
      );

      // Internal buttons must have explicit type="button" to prevent unwanted submission
      assert.ok(
        content.includes('className={styles.statusToggleBtn}') &&
          content.includes('type="button"'),
        'Status toggle button inside form must have type="button"'
      );
    });

    test('Double-submit protection blocks concurrent supplier mutations in same tick', async () => {
      const content = fs.readFileSync(supplierListPath, 'utf8');
      assert.ok(
        content.includes('const isSubmittingRef = useRef(false);'),
        'Must define isSubmittingRef for synchronous submission locking'
      );
      assert.ok(
        content.includes('if (isSubmittingRef.current)'),
        'Must check isSubmittingRef.current before proceeding'
      );
      assert.ok(
        content.includes('isSubmittingRef.current = true;'),
        'Must set isSubmittingRef.current = true on submit'
      );
      assert.ok(
        content.includes('isSubmittingRef.current = false;'),
        'Must reset isSubmittingRef.current in finally block'
      );

      let callCount = 0;
      axiosClient.post = async () => {
        callCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return { data: VALID_SUPPLIER_FIXTURE };
      };

      const isSubmittingRef = { current: false };
      const simulatedSubmit = async (payload) => {
        if (isSubmittingRef.current) return null;
        isSubmittingRef.current = true;
        try {
          return await suppliersApi.createSupplier(payload);
        } finally {
          isSubmittingRef.current = false;
        }
      };

      const [res1, res2] = await Promise.all([
        simulatedSubmit({ name: 'Nhà cung cấp sữa Vinamilk' }),
        simulatedSubmit({ name: 'Nhà cung cấp sữa Vinamilk' }),
      ]);

      assert.equal(callCount, 1, 'Only one createSupplier request allowed concurrently');
      assert.ok(res1 !== null || res2 !== null);
      assert.ok(res1 === null || res2 === null);
      assert.equal(isSubmittingRef.current, false, 'Lock must be released in finally');
    });

    test('Supplier form client validation enforces length bounds and email regex', () => {
      const content = fs.readFileSync(supplierListPath, 'utf8');

      assert.ok(content.includes('Tên nhà cung cấp là bắt buộc.'));
      assert.ok(content.includes('trimmedName.length > 160'));
      assert.ok(content.includes('Tên nhà cung cấp không được vượt quá 160 ký tự.'));
      assert.ok(content.includes('trimmedPhone.length > 32'));
      assert.ok(content.includes('Số điện thoại không được vượt quá 32 ký tự.'));
      assert.ok(content.includes('trimmedEmail.length > 254'));
      assert.ok(content.includes('Email không được vượt quá 254 ký tự.'));
      assert.ok(content.includes('Email kinh doanh không đúng định dạng.'));
      assert.ok(content.includes('handleCloseModal'));
    });
  });

  // ==========================================================================
  // 8. F08: Dirty-State Detection & Partial Failure Handling (PR #46 Corrective Patch)
  // ==========================================================================
  describe('F08: Dirty-State Detection & Partial Failure Handling (PR #46 Corrective Patch)', () => {
    const supplierListPath = path.resolve(__dirname, '../pages/Suppliers/SupplierList.jsx');

    test('normalizeSupplierSnapshot correctly trims whitespace and maps empty contacts to null', () => {
      const raw = {
        id: 5,
        name: '   Công ty Cổ phần ABC   ',
        contact_phone: '   0901234567   ',
        contact_email: '   abc@company.vn   ',
        status: 'ACTIVE',
      };
      const normalized = normalizeSupplierSnapshot(raw);
      assert.deepEqual(normalized, {
        id: 5,
        name: 'Công ty Cổ phần ABC',
        contact_phone: '0901234567',
        contact_email: 'abc@company.vn',
        status: 'ACTIVE',
      });

      const rawEmpty = {
        id: 6,
        name: 'XYZ Corp',
        contact_phone: '   ',
        contact_email: '',
        status: 'INACTIVE',
      };
      const normalizedEmpty = normalizeSupplierSnapshot(rawEmpty);
      assert.deepEqual(normalizedEmpty, {
        id: 6,
        name: 'XYZ Corp',
        contact_phone: null,
        contact_email: null,
        status: 'INACTIVE',
      });
    });

    test('Decision Matrix: 0 changes -> hasInfoChanges=false, hasStatusChange=false', () => {
      const snapshot = normalizeSupplierSnapshot(VALID_SUPPLIER_FIXTURE);
      const formSame = {
        id: VALID_SUPPLIER_FIXTURE.id,
        name: '  ' + VALID_SUPPLIER_FIXTURE.name + '  ', // whitespace difference only
        contact_phone: VALID_SUPPLIER_FIXTURE.contact_phone,
        contact_email: VALID_SUPPLIER_FIXTURE.contact_email,
        status: VALID_SUPPLIER_FIXTURE.status,
      };

      const changes = detectSupplierChanges(formSame, snapshot);
      assert.equal(changes.hasInfoChanges, false, 'Whitespace difference should not be dirty');
      assert.equal(changes.hasStatusChange, false);
    });

    test('Decision Matrix: only status changed -> hasInfoChanges=false, hasStatusChange=true', () => {
      const snapshot = normalizeSupplierSnapshot(VALID_SUPPLIER_FIXTURE);
      const formStatusChanged = {
        ...VALID_SUPPLIER_FIXTURE,
        status: 'INACTIVE',
      };

      const changes = detectSupplierChanges(formStatusChanged, snapshot);
      assert.equal(changes.hasInfoChanges, false);
      assert.equal(changes.hasStatusChange, true);
    });

    test('Decision Matrix: only info changed -> hasInfoChanges=true, hasStatusChange=false', () => {
      const snapshot = normalizeSupplierSnapshot(VALID_SUPPLIER_FIXTURE);
      const formInfoChanged = {
        ...VALID_SUPPLIER_FIXTURE,
        name: 'Vinamilk Mới',
      };

      const changes = detectSupplierChanges(formInfoChanged, snapshot);
      assert.equal(changes.hasInfoChanges, true);
      assert.equal(changes.hasStatusChange, false);
    });

    test('Decision Matrix: both info and status changed -> hasInfoChanges=true, hasStatusChange=true', () => {
      const snapshot = normalizeSupplierSnapshot(VALID_SUPPLIER_FIXTURE);
      const formBothChanged = {
        ...VALID_SUPPLIER_FIXTURE,
        name: 'Vinamilk Mới',
        status: 'INACTIVE',
      };

      const changes = detectSupplierChanges(formBothChanged, snapshot);
      assert.equal(changes.hasInfoChanges, true);
      assert.equal(changes.hasStatusChange, true);
    });

    test('SupplierList source code enforces Decision Matrix, sequential mutations, and partial failure recovery', () => {
      const content = fs.readFileSync(supplierListPath, 'utf8');

      // Dirty state detection and no-op exit
      assert.ok(content.includes('detectSupplierChanges(supplierForm, initialSnapshot)'));
      assert.ok(content.includes("toast.info('Không có thay đổi nào để lưu.');"));

      // Sequential mutations: info first, then status
      assert.ok(content.includes('if (hasInfoChanges) {'));
      assert.ok(content.includes('await suppliersApi.updateSupplier('));
      assert.ok(content.includes('infoUpdated = true;'));
      assert.ok(content.includes('if (hasStatusChange) {'));
      assert.ok(content.includes('await suppliersApi.updateSupplierStatus('));

      // Partial failure handling with GET sync
      assert.ok(content.includes('if (infoUpdated) {'));
      assert.ok(content.includes('await suppliersApi.getSupplier(supplierForm.id)'));
      assert.ok(content.includes('setInitialSnapshot(newSnapshot);'));
      assert.ok(content.includes('setSupplierForm({'));

      // Status toggle button guarded by isSubmitting
      assert.ok(content.includes('if (isSubmitting || modalMode !=='));
    });

    test('Mutation flow: info failure halts before status PATCH', async () => {
      let infoCalls = 0;
      let statusCalls = 0;

      axiosClient.patch = async (url) => {
        if (url.endsWith('/status')) {
          statusCalls += 1;
          return { data: VALID_SUPPLIER_FIXTURE };
        }
        infoCalls += 1;
        const err = new Error('Database locked');
        err.response = { status: 500, data: { detail: 'Database locked' } };
        throw err;
      };

      const executeMutationFlow = async ({ hasInfoChanges, hasStatusChange, id, payload }) => {
        let infoUpdated = false;
        if (hasInfoChanges) {
          await suppliersApi.updateSupplier(id, payload);
          infoUpdated = true;
        }
        if (hasStatusChange) {
          try {
            await suppliersApi.updateSupplierStatus(id, payload.status);
          } catch (statusErr) {
            if (infoUpdated) {
              return { partial: true, error: statusErr };
            }
            throw statusErr;
          }
        }
        return { success: true };
      };

      await assert.rejects(
        executeMutationFlow({
          hasInfoChanges: true,
          hasStatusChange: true,
          id: 1,
          payload: { name: 'New Name', status: 'INACTIVE' },
        }),
        (err) => err.message.includes('Database locked')
      );

      assert.equal(infoCalls, 1, 'Info PATCH was called once');
      assert.equal(statusCalls, 0, 'Status PATCH was never called after info failure');
    });

    test('Mutation flow: info success + status failure triggers partial failure handling', async () => {
      let infoCalls = 0;
      let statusCalls = 0;
      let getCalls = 0;

      const updatedSupplier = {
        ...VALID_SUPPLIER_FIXTURE,
        name: 'Công ty Cổ phần Sữa Vinamilk Mới',
        status: 'ACTIVE', // status update failed, still ACTIVE
      };

      axiosClient.patch = async (url) => {
        if (url.endsWith('/status')) {
          statusCalls += 1;
          const err = new Error('Status transition conflict');
          err.response = { status: 409, data: { detail: 'Status transition conflict' } };
          throw err;
        }
        infoCalls += 1;
        return { data: updatedSupplier };
      };

      axiosClient.get = async (url) => {
        if (url.includes('/suppliers/1')) {
          getCalls += 1;
          return { data: updatedSupplier };
        }
        return { data: { items: [], total: 0, page: 1, page_size: 10 } };
      };

      const executeMutationFlow = async ({ hasInfoChanges, hasStatusChange, id, payload }) => {
        let infoUpdated = false;
        if (hasInfoChanges) {
          await suppliersApi.updateSupplier(id, payload);
          infoUpdated = true;
        }
        if (hasStatusChange) {
          try {
            await suppliersApi.updateSupplierStatus(id, payload.status);
          } catch (statusErr) {
            if (infoUpdated) {
              const latest = await suppliersApi.getSupplier(id);
              return { partial: true, latest, error: statusErr };
            }
            throw statusErr;
          }
        }
        return { success: true };
      };

      const result = await executeMutationFlow({
        hasInfoChanges: true,
        hasStatusChange: true,
        id: 1,
        payload: { name: updatedSupplier.name, status: 'INACTIVE' },
      });

      assert.equal(infoCalls, 1);
      assert.equal(statusCalls, 1);
      assert.equal(getCalls, 1, 'GET supplier was called to synchronize after partial failure');
      assert.equal(result.partial, true);
      assert.equal(result.latest.name, 'Công ty Cổ phần Sữa Vinamilk Mới');
      assert.equal(result.latest.status, 'ACTIVE');
    });
  });
});

