import test, { describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import axiosClient, {
  invalidateSession,
  startAuthenticatedSession,
  transitionAuthMode,
} from '../api/axiosClient.js';
import {
  formatNotificationTimeVN,
  notificationsApi,
  validateMarkAllReadResponse,
  validateNotificationRead,
  validateUnreadCountResponse,
} from '../api/notificationsApi.js';
import {
  formatApprovalDateTimeVN,
  getEmailInitials,
  parsePositiveApprovalId,
  staffApprovalsApi,
  validateApprovalListItemRead,
  validateApprovalRead,
  validateRejectReason,
} from '../api/staffApprovalsApi.js';
import {
  canUserCloseApprovalModal,
  executeStaffApprovalDecision,
} from '../pages/Staff/staffApprovalModalHelpers.js';

const TEST_DEV_ENV = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };

const VALID_UNREAD_NOTIFICATION = {
  id: 11,
  approval_request_id: 25,
  created_at: '2026-11-11T03:24:00Z',
  read_at: null,
};

const VALID_READ_NOTIFICATION = {
  id: 10,
  approval_request_id: 24,
  created_at: '2026-11-10T02:15:00Z',
  read_at: '2026-11-10T04:00:00Z',
};

describe('AUTH-05 Admin In-App Notifications Real API Test Suite', () => {
  describe('1. DTO Schema Validation (Fail-Closed)', () => {
    test('validates valid unread and read NotificationRead payloads accurately', () => {
      assert.deepEqual(
        validateNotificationRead(VALID_UNREAD_NOTIFICATION),
        VALID_UNREAD_NOTIFICATION
      );
      assert.deepEqual(
        validateNotificationRead(VALID_READ_NOTIFICATION),
        VALID_READ_NOTIFICATION
      );
    });

    test('rejects malformed NotificationRead payloads', () => {
      assert.throws(() => validateNotificationRead(null), /non-null object/);
      assert.throws(
        () => validateNotificationRead({ ...VALID_UNREAD_NOTIFICATION, id: 0 }),
        /positive integer id/
      );
      assert.throws(
        () =>
          validateNotificationRead({
            ...VALID_UNREAD_NOTIFICATION,
            approval_request_id: -1,
          }),
        /positive integer approval_request_id/
      );
      assert.throws(
        () =>
          validateNotificationRead({
            ...VALID_UNREAD_NOTIFICATION,
            created_at: 'invalid-date',
          }),
        /invalid created_at/
      );
      assert.throws(
        () =>
          validateNotificationRead({
            ...VALID_UNREAD_NOTIFICATION,
            read_at: 'not-a-timestamp',
          }),
        /invalid read_at/
      );
    });

    test('validates UnreadCountResponse and MarkAllReadResponse strictly', () => {
      assert.deepEqual(validateUnreadCountResponse({ count: 3 }), { count: 3 });
      assert.deepEqual(validateUnreadCountResponse({ count: 0 }), { count: 0 });
      assert.throws(
        () => validateUnreadCountResponse({ count: -1 }),
        /non-negative integer/
      );
      assert.throws(
        () => validateUnreadCountResponse({ count: '3' }),
        /non-negative integer/
      );

      assert.deepEqual(validateMarkAllReadResponse({ updated_count: 3 }), {
        updated_count: 3,
      });
      assert.throws(
        () => validateMarkAllReadResponse({ updated_count: -2 }),
        /non-negative integer/
      );
    });

    test('formats UTC timestamp into Asia/Ho_Chi_Minh timezone accurately', () => {
      const nowDate = new Date('2026-11-11T04:00:00Z'); // 11:00 in Asia/Ho_Chi_Minh
      assert.equal(
        formatNotificationTimeVN('2026-11-11T03:24:00Z', {
          includeTimezoneLabel: true,
          isRead: false,
          nowDate,
        }),
        '10:24 • Hôm nay (Asia/Ho_Chi_Minh)'
      );
      assert.equal(
        formatNotificationTimeVN('2026-11-11T02:15:00Z', {
          includeTimezoneLabel: false,
          isRead: false,
          nowDate,
        }),
        '09:15 • Hôm nay'
      );
      assert.equal(
        formatNotificationTimeVN('2026-11-10T04:00:00Z', {
          includeTimezoneLabel: false,
          isRead: true,
          nowDate,
        }),
        'Hôm qua (10/11/2026)'
      );
    });
  });

  describe('2. Real API Transport & Mock Isolation', () => {
    let capturedCalls = [];

    beforeEach(() => {
      capturedCalls = [];
      transitionAuthMode(false, TEST_DEV_ENV);
      invalidateSession();
      startAuthenticatedSession('real_jwt_admin_token', 'csrf_admin_token');

      axiosClient.get = async (url, config = {}) => {
        capturedCalls.push({ method: 'GET', url, config });
        if (url === '/admin/notifications') {
          return {
            data: {
              items: [VALID_UNREAD_NOTIFICATION, VALID_READ_NOTIFICATION],
              total: 2,
              page: config.params?.page ?? 1,
              page_size: config.params?.page_size ?? 20,
            },
          };
        }
        if (url === '/admin/notifications/unread-count') {
          return { data: { count: 1 } };
        }
        return { data: {} };
      };

      axiosClient.patch = async (url, data, config = {}) => {
        capturedCalls.push({ method: 'PATCH', url, data, config });
        if (url === '/admin/notifications/11/read') {
          return {
            data: {
              ...VALID_UNREAD_NOTIFICATION,
              read_at: '2026-11-11T03:30:00Z',
            },
          };
        }
        if (url === '/admin/notifications/read-all') {
          return { data: { updated_count: 1 } };
        }
        return { data: {} };
      };
    });

    test('calls GET /admin/notifications and GET /admin/notifications/unread-count with exact contract', async () => {
      const listRes = await notificationsApi.getNotifications({
        page: 1,
        pageSize: 20,
        unreadOnly: false,
      });
      const countRes = await notificationsApi.getUnreadCount();

      assert.equal(capturedCalls.length, 2);
      assert.equal(capturedCalls[0].url, '/admin/notifications');
      assert.deepEqual(capturedCalls[0].config.params, {
        page: 1,
        page_size: 20,
        unread_only: false,
      });
      assert.equal(listRes.total, 2);
      assert.equal(listRes.items[0].approval_request_id, 25);
      assert.equal(countRes.count, 1);
    });

    test('sends strict empty JSON object {} for PATCH /read and PATCH /read-all', async () => {
      const readRes = await notificationsApi.markAsRead({ id: 11 });
      const readAllRes = await notificationsApi.markAllAsRead();

      assert.equal(capturedCalls.length, 2);
      assert.equal(capturedCalls[0].method, 'PATCH');
      assert.equal(capturedCalls[0].url, '/admin/notifications/11/read');
      assert.deepEqual(capturedCalls[0].data, {});
      assert.equal(readRes.read_at, '2026-11-11T03:30:00Z');

      assert.equal(capturedCalls[1].method, 'PATCH');
      assert.equal(capturedCalls[1].url, '/admin/notifications/read-all');
      assert.deepEqual(capturedCalls[1].data, {});
      assert.equal(readAllRes.updated_count, 1);
    });

    test('blocks all notification calls fail-closed when Mock mode is active', async () => {
      await assert.rejects(
        () => notificationsApi.getNotifications({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () => notificationsApi.getUnreadCount({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () => notificationsApi.markAsRead({ isMockMode: true, id: 11 }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () => notificationsApi.markAllAsRead({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      assert.equal(capturedCalls.length, 0);
    });

    test('Header.jsx enforces ADMIN RBAC guard and uses real notificationsApi without fake mock PII', () => {
      const headerSource = fs.readFileSync(
        path.resolve('src/layouts/MainLayout/Header.jsx'),
        'utf-8'
      );
      assert.match(headerSource, /user\?\.status === 'APPROVED'/);
      assert.match(headerSource, /notificationsApi\.getNotifications/);
      assert.match(headerSource, /notificationsApi\.getUnreadCount/);
      assert.match(headerSource, /notificationsApi\.markAsRead/);
      assert.match(headerSource, /notificationsApi\.markAllAsRead/);
      assert.match(headerSource, /Thông báo xét duyệt tài khoản nhân viên/);
      assert.match(headerSource, /Cơ chế chống thông báo trùng lặp:/);
      assert.match(headerSource, /Xem toàn bộ hàng đợi phê duyệt \(AUTH-03\)/);
      assert.doesNotMatch(headerSource, /minh\.nguyen@retailops\.vn/);
      assert.doesNotMatch(headerSource, /mai\.tran@retailops\.vn/);
      assert.doesNotMatch(headerSource, /long\.le@retailops\.vn/);
    });

    test('does not use localStorage applicant caching and relies 100% on real Backend API fields', () => {
      const notificationsApiSource = fs.readFileSync(
        path.resolve('src/api/notificationsApi.js'),
        'utf-8'
      );
      const authContextSource = fs.readFileSync(
        path.resolve('src/context/AuthContext.jsx'),
        'utf-8'
      );
      const headerSource = fs.readFileSync(
        path.resolve('src/layouts/MainLayout/Header.jsx'),
        'utf-8'
      );
      const staffSource = fs.readFileSync(
        path.resolve('src/pages/Staff/StaffApprovalList.jsx'),
        'utf-8'
      );

      assert.doesNotMatch(
        notificationsApiSource,
        /retailops_applicant_display_meta/
      );
      assert.doesNotMatch(authContextSource, /recordApplicantDisplayMeta/);
      assert.doesNotMatch(headerSource, /resolveNotificationApplicants/);
      assert.doesNotMatch(staffSource, /resolveApprovalApplicants/);
    });
  });

  describe('4. Staff Approvals API & UI Contract (AUTH-03 / T04A61F / T04A6F3)', () => {
    const VALID_PENDING_APPROVAL = {
      id: 1,
      user_id: 2,
      attempt_no: 1,
      status: 'PENDING',
      requested_at: '2026-11-11T08:20:00Z',
      decided_by: null,
      decided_at: null,
      decision_reason: null,
    };

    const VALID_PENDING_APPROVAL_LIST_ITEM = {
      ...VALID_PENDING_APPROVAL,
      email: 'binh.nv@retailops.vn',
    };

    test('validateApprovalRead and validateApprovalListItemRead validate strict DTOs', () => {
      const valid = validateApprovalRead(VALID_PENDING_APPROVAL);
      assert.deepEqual(valid, VALID_PENDING_APPROVAL);

      const validListItem = validateApprovalListItemRead(
        VALID_PENDING_APPROVAL_LIST_ITEM
      );
      assert.deepEqual(validListItem, VALID_PENDING_APPROVAL_LIST_ITEM);

      assert.throws(
        () => validateApprovalListItemRead(VALID_PENDING_APPROVAL),
        /missing valid email/i
      );

      assert.throws(
        () => validateApprovalRead({ ...VALID_PENDING_APPROVAL, status: 'UNKNOWN' }),
        /invalid status/i
      );
      assert.throws(
        () => validateApprovalRead({ ...VALID_PENDING_APPROVAL, user_id: 0 }),
        /missing valid positive integer user_id/i
      );

      assert.equal(getEmailInitials('binh.nv@retailops.vn'), 'BN');
      assert.equal(getEmailInitials('staff@example.com'), 'ST');
    });

    test('validateRejectReason enforces 1..500 non-whitespace characters', () => {
      assert.equal(validateRejectReason('').isValid, false);
      assert.equal(validateRejectReason('   ').isValid, false);
      assert.equal(validateRejectReason('a'.repeat(501)).isValid, false);

      const ok = validateRejectReason('  Chưa hoàn tất hồ sơ thử việc  ');
      assert.equal(ok.isValid, true);
      assert.equal(ok.normalized, 'Chưa hoàn tất hồ sơ thử việc');
    });

    test('formatApprovalDateTimeVN formats UTC timestamp to Vietnam timezone', () => {
      const formatted = formatApprovalDateTimeVN('2026-11-04T08:20:00Z');
      assert.equal(formatted, '15:20 • 04/11/2026');
    });

    test('staffApprovalsApi calls GET /staff-approvals, POST /approve, and POST /reject', async () => {
      const calls = [];
      axiosClient.get = async (url, config = {}) => {
        calls.push({
          method: 'GET',
          url,
          params: config.params,
        });
        return {
          data: {
            items: [VALID_PENDING_APPROVAL_LIST_ITEM],
            total: 1,
            page: 1,
            page_size: 10,
          },
        };
      };

      axiosClient.post = async (url, data) => {
        calls.push({
          method: 'POST',
          url,
          data,
        });

        if (url.endsWith('/approve')) {
          return {
            data: {
              ...VALID_PENDING_APPROVAL,
              status: 'APPROVED',
              decided_by: 1,
              decided_at: '2026-11-11T09:00:00Z',
            },
          };
        }

        return {
          data: {
            ...VALID_PENDING_APPROVAL,
            status: 'REJECTED',
            decided_by: 1,
            decided_at: '2026-11-11T09:05:00Z',
            decision_reason: 'Hồ sơ chưa hợp lệ',
          },
        };
      };

      const pageRes = await staffApprovalsApi.getApprovals({
        isMockMode: false,
        status: 'PENDING',
        page: 1,
        pageSize: 10,
      });
      assert.equal(pageRes.total, 1);
      assert.equal(pageRes.items[0].email, 'binh.nv@retailops.vn');
      assert.equal(calls[0].url, '/staff-approvals');
      assert.deepEqual(calls[0].params, {
        page: 1,
        page_size: 10,
        status: 'PENDING',
      });

      const approved = await staffApprovalsApi.approveStaff({
        isMockMode: false,
        id: 1,
      });
      assert.equal(approved.status, 'APPROVED');
      assert.equal(calls[1].url, '/staff-approvals/1/approve');

      const rejected = await staffApprovalsApi.rejectStaff({
        isMockMode: false,
        id: 1,
        reason: 'Hồ sơ chưa hợp lệ',
      });
      assert.equal(rejected.status, 'REJECTED');
      assert.equal(calls[2].url, '/staff-approvals/1/reject');
      assert.deepEqual(calls[2].data, { reason: 'Hồ sơ chưa hợp lệ' });
    });

    test('blocks all staffApprovalsApi calls fail-closed when Mock mode is active', async () => {
      let called = false;
      axiosClient.get = async () => {
        called = true;
        return { data: {} };
      };
      axiosClient.post = async () => {
        called = true;
        return { data: {} };
      };

      await assert.rejects(
        () => staffApprovalsApi.getApprovals({ isMockMode: true }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () => staffApprovalsApi.approveStaff({ isMockMode: true, id: 1 }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      await assert.rejects(
        () =>
          staffApprovalsApi.rejectStaff({
            isMockMode: true,
            id: 1,
            reason: 'Lý do hợp lệ',
          }),
        (err) => err.code === 'ERR_MOCK_NOT_SUPPORTED'
      );
      assert.equal(called, false);
    });

    test('rejects invalid id or blank/overlong reason client-side before sending POST', async () => {
      let postCalled = false;
      axiosClient.post = async () => {
        postCalled = true;
        return { data: {} };
      };

      await assert.rejects(
        () => staffApprovalsApi.approveStaff({ isMockMode: false, id: 0 }),
        /không hợp lệ/i
      );
      await assert.rejects(
        () =>
          staffApprovalsApi.rejectStaff({
            isMockMode: false,
            id: -5,
            reason: 'Lý do hợp lệ',
          }),
        /không hợp lệ/i
      );
      await assert.rejects(
        () =>
          staffApprovalsApi.rejectStaff({
            isMockMode: false,
            id: 1,
            reason: '   ',
          }),
        /không được để trống/i
      );
      await assert.rejects(
        () =>
          staffApprovalsApi.rejectStaff({
            isMockMode: false,
            id: 1,
            reason: 'x'.repeat(501),
          }),
        /500 ký tự/i
      );
      assert.equal(postCalled, false);
    });

    test('propagates HTTP 401, 403, 404, 409 Conflict, and 422 without silent mock fallback', async () => {
      const makeHttpError = (status, code, message) => {
        const err = new Error(message);
        err.response = {
          status,
          data: { code, message },
        };
        return err;
      };

      for (const [status, code, message] of [
        [401, 'UNAUTHENTICATED', 'Authentication required'],
        [403, 'FORBIDDEN', 'Admin role required'],
        [422, 'VALIDATION_ERROR', 'Invalid query parameters'],
      ]) {
        axiosClient.get = async () => {
          throw makeHttpError(status, code, message);
        };
        await assert.rejects(
          () => staffApprovalsApi.getApprovals({ isMockMode: false }),
          (err) => err.response?.status === status
        );
      }

      for (const [status, code, message] of [
        [401, 'UNAUTHENTICATED', 'Authentication required'],
        [403, 'FORBIDDEN', 'Admin role required'],
        [404, 'RESOURCE_NOT_FOUND', 'Approval request not found'],
        [409, 'INVALID_STATE', 'Approval request already decided'],
      ]) {
        axiosClient.post = async () => {
          throw makeHttpError(status, code, message);
        };
        await assert.rejects(
          () => staffApprovalsApi.approveStaff({ isMockMode: false, id: 12 }),
          (err) => err.response?.status === status
        );
        await assert.rejects(
          () =>
            staffApprovalsApi.rejectStaff({
              isMockMode: false,
              id: 12,
              reason: 'Không đạt yêu cầu',
            }),
          (err) => err.response?.status === status
        );
      }
    });

    test('parsePositiveApprovalId strictly accepts positive integers only', () => {
      assert.equal(parsePositiveApprovalId('123'), 123);
      assert.equal(parsePositiveApprovalId(45), 45);
      assert.equal(parsePositiveApprovalId('0'), null);
      assert.equal(parsePositiveApprovalId('-5'), null);
      assert.equal(parsePositiveApprovalId('12.5'), null);
      assert.equal(parsePositiveApprovalId('abc'), null);
      assert.equal(parsePositiveApprovalId(null), null);
    });

    test('findApprovalByIdBounded locates item on current page, other page, or APPROVED/REJECTED tab with bounded requests', async () => {
      let getCount = 0;
      const approvedTarget = {
        ...VALID_PENDING_APPROVAL_LIST_ITEM,
        id: 77,
        status: 'APPROVED',
        decided_by: 1,
        decided_at: '2026-11-11T10:00:00Z',
        email: 'approved77@retailops.vn',
      };
      const page2Target = {
        ...VALID_PENDING_APPROVAL_LIST_ITEM,
        id: 88,
        email: 'page2@retailops.vn',
      };

      axiosClient.get = async (_url, config = {}) => {
        getCount += 1;
        const { status, page } = config.params;
        if (status === 'PENDING' && page === 1) {
          return {
            data: {
              items: [VALID_PENDING_APPROVAL_LIST_ITEM],
              total: 60,
              page: 1,
              page_size: 50,
            },
          };
        }
        if (status === 'PENDING' && page === 2) {
          return {
            data: {
              items: [page2Target],
              total: 60,
              page: 2,
              page_size: 50,
            },
          };
        }
        if (status === 'APPROVED' && page === 1) {
          return {
            data: {
              items: [approvedTarget],
              total: 1,
              page: 1,
              page_size: 50,
            },
          };
        }
        return {
          data: {
            items: [],
            total: 0,
            page: 1,
            page_size: 50,
          },
        };
      };

      // 1. Found on currentItems -> 0 network requests
      getCount = 0;
      const localFound = await staffApprovalsApi.findApprovalByIdBounded({
        isMockMode: false,
        approvalId: 1,
        currentItems: [VALID_PENDING_APPROVAL_LIST_ITEM],
        activeStatus: 'PENDING',
      });
      assert.equal(getCount, 0);
      assert.equal(localFound.fromCurrentPage, true);
      assert.equal(localFound.item.id, 1);

      // 2. Found on page 2 of PENDING
      getCount = 0;
      const page2Found = await staffApprovalsApi.findApprovalByIdBounded({
        isMockMode: false,
        approvalId: 88,
        currentItems: [VALID_PENDING_APPROVAL_LIST_ITEM],
        activeStatus: 'PENDING',
      });
      assert.equal(page2Found.status, 'PENDING');
      assert.equal(page2Found.page, 2);
      assert.equal(page2Found.item.email, 'page2@retailops.vn');

      // 3. Found in APPROVED tab when starting from PENDING
      getCount = 0;
      const approvedFound = await staffApprovalsApi.findApprovalByIdBounded({
        isMockMode: false,
        approvalId: 77,
        currentItems: [VALID_PENDING_APPROVAL_LIST_ITEM],
        activeStatus: 'PENDING',
      });
      assert.equal(approvedFound.status, 'APPROVED');
      assert.equal(approvedFound.item.id, 77);

      // 4. Not found -> returns null within bounded requests
      getCount = 0;
      const missing = await staffApprovalsApi.findApprovalByIdBounded({
        isMockMode: false,
        approvalId: 9999,
        currentItems: [VALID_PENDING_APPROVAL_LIST_ITEM],
        activeStatus: 'PENDING',
        maxPagesPerStatus: 2,
      });
      assert.equal(missing, null);
      assert.ok(getCount <= 6);
    });

    test('StaffApprovalList.jsx uses Modal, real staffApprovalsApi, deep-link bounded lookup, stale-modal lock on 409, and honest current-page search', () => {
      const staffSource = fs.readFileSync(
        path.resolve('src/pages/Staff/StaffApprovalList.jsx'),
        'utf-8'
      );
      const helpersSource = fs.readFileSync(
        path.resolve('src/pages/Staff/staffApprovalModalHelpers.js'),
        'utf-8'
      );
      assert.match(staffSource, /staffApprovalsApi\.getApprovals/);
      assert.match(helpersSource, /staffApprovalsApi\.approveStaff/);
      assert.match(helpersSource, /staffApprovalsApi\.rejectStaff/);
      assert.match(staffSource, /closeDetailModalProgrammatic/);
      assert.match(staffSource, /canUserCloseApprovalModal/);
      assert.match(staffSource, /staffApprovalsApi\s*\.findApprovalByIdBounded/);
      assert.match(staffSource, /parsePositiveApprovalId/);
      assert.match(staffSource, /isModalStale/);
      assert.match(staffSource, /Tìm trong trang hiện tại/);
      assert.match(staffSource, /item\.email/);
      assert.match(staffSource, /selectedApproval\.email/);
      assert.match(staffSource, /<Modal/);
      assert.match(staffSource, /Từ chối/);
      assert.match(staffSource, /Chấp nhận/);
      assert.doesNotMatch(
        staffSource,
        /Hồ sơ đã được xử lý bởi Admin khác/
      );
    });

    test('Header.jsx resets notification state on logout or non-admin session', () => {
      const headerSource = fs.readFileSync(
        path.resolve('src/layouts/MainLayout/Header.jsx'),
        'utf-8'
      );
      assert.match(headerSource, /setNotifications\(\[\]\)/);
      assert.match(headerSource, /setUnreadCount\(0\)/);
      assert.match(headerSource, /badgeGenRef/);
    });
  });

  describe('Approval Modal Lifecycle & Decision Regression (PR #40 Hotfix)', () => {
    const SAMPLE_PENDING_APPROVAL = {
      id: 42,
      user_id: 108,
      email: 'staff.new@retailops.local',
      status: 'PENDING',
      attempt_no: 1,
      decision_reason: null,
    };

    function createModalHarness(initial = {}) {
      const state = {
        selectedApproval:
          initial.selectedApproval !== undefined
            ? initial.selectedApproval
            : { ...SAMPLE_PENDING_APPROVAL },
        rejectReason: initial.rejectReason ?? '',
        isModalStale: initial.isModalStale ?? false,
        modalError: initial.modalError ?? '',
        isSubmittingDecision: false,
        urlParams: new URLSearchParams(initial.search ?? ''),
        refreshCount: 0,
        toasts: [],
        deepLinkGenRef: { current: initial.deepLinkGen ?? 1 },
        isDecisionPendingRef: { current: false },
      };

      const closeModalProgrammatic = () => {
        state.deepLinkGenRef.current += 1;
        state.selectedApproval = null;
        state.rejectReason = '';
        state.isModalStale = false;
        state.modalError = '';
        if (state.urlParams.has('approval_request_id')) {
          state.urlParams.delete('approval_request_id');
        }
      };

      const handleUserClose = () => {
        if (
          !canUserCloseApprovalModal({
            isSubmittingDecision: state.isSubmittingDecision,
            isDecisionPending: state.isDecisionPendingRef.current,
          })
        ) {
          return false;
        }
        closeModalProgrammatic();
        return true;
      };

      return {
        state,
        isDecisionPendingRef: state.isDecisionPendingRef,
        closeModalProgrammatic,
        handleUserClose,
        setIsSubmittingDecision: (v) => {
          state.isSubmittingDecision = v;
        },
        setModalError: (v) => {
          state.modalError = v;
        },
        setIsModalStale: (v) => {
          state.isModalStale = v;
        },
        onRefresh: () => {
          state.refreshCount += 1;
        },
        onSuccessToast: (approval) => {
          state.toasts.push(approval.id);
        },
      };
    }

    test('Approve thành công: đóng modal dù isSubmittingDecision đang true, toast 1 lần, refresh', async () => {
      const h = createModalHarness({ search: 'approval_request_id=42' });
      let closeObservedWhileSubmitting = false;
      const origClose = h.closeModalProgrammatic;
      const spyClose = () => {
        closeObservedWhileSubmitting = h.state.isSubmittingDecision === true;
        origClose();
      };

      const res = await executeStaffApprovalDecision({
        action: 'approve',
        isMockMode: false,
        selectedApproval: h.state.selectedApproval,
        isModalStale: h.state.isModalStale,
        isDecisionPendingRef: h.isDecisionPendingRef,
        staffApprovalsApi: {
          approveStaff: async () => ({ status: 'APPROVED' }),
        },
        getApiErrorMessage: () => 'err',
        setIsSubmittingDecision: h.setIsSubmittingDecision,
        setModalError: h.setModalError,
        setIsModalStale: h.setIsModalStale,
        onSuccessToast: h.onSuccessToast,
        closeModalProgrammatic: spyClose,
        onRefresh: h.onRefresh,
      });

      assert.equal(res.status, 'success');
      assert.equal(closeObservedWhileSubmitting, true);
      assert.equal(h.state.selectedApproval, null);
      assert.equal(h.state.rejectReason, '');
      assert.equal(h.state.modalError, '');
      assert.equal(h.state.isModalStale, false);
      assert.equal(h.state.isSubmittingDecision, false);
      assert.equal(h.state.isDecisionPendingRef.current, false);
      assert.equal(h.state.urlParams.has('approval_request_id'), false);
      assert.deepEqual(h.state.toasts, [SAMPLE_PENDING_APPROVAL.id]);
      assert.equal(h.state.refreshCount, 1);
    });

    test('Reject thành công: đóng modal, reset rejectReason, refresh', async () => {
      const h = createModalHarness({ rejectReason: 'Không thuộc danh sách nhân sự' });
      const res = await executeStaffApprovalDecision({
        action: 'reject',
        isMockMode: false,
        selectedApproval: h.state.selectedApproval,
        isModalStale: h.state.isModalStale,
        isDecisionPendingRef: h.isDecisionPendingRef,
        rejectReason: h.state.rejectReason,
        validateRejectReason,
        staffApprovalsApi: {
          rejectStaff: async () => ({ status: 'REJECTED' }),
        },
        getApiErrorMessage: () => 'err',
        setIsSubmittingDecision: h.setIsSubmittingDecision,
        setModalError: h.setModalError,
        setIsModalStale: h.setIsModalStale,
        onSuccessToast: h.onSuccessToast,
        closeModalProgrammatic: h.closeModalProgrammatic,
        onRefresh: h.onRefresh,
      });

      assert.equal(res.status, 'success');
      assert.equal(h.state.selectedApproval, null);
      assert.equal(h.state.rejectReason, '');
      assert.equal(h.state.refreshCount, 1);
      assert.equal(h.state.toasts.length, 1);
    });

    test('POST đang pending: chặn user đóng modal và chặn double-submit', async () => {
      const h = createModalHarness();
      let resolvePost;
      let postCalls = 0;

      const firstPromise = executeStaffApprovalDecision({
        action: 'approve',
        isMockMode: false,
        selectedApproval: h.state.selectedApproval,
        isModalStale: h.state.isModalStale,
        isDecisionPendingRef: h.isDecisionPendingRef,
        staffApprovalsApi: {
          approveStaff: () =>
            new Promise((resolve) => {
              postCalls += 1;
              resolvePost = resolve;
            }),
        },
        getApiErrorMessage: () => 'err',
        setIsSubmittingDecision: h.setIsSubmittingDecision,
        setModalError: h.setModalError,
        setIsModalStale: h.setIsModalStale,
        onSuccessToast: h.onSuccessToast,
        closeModalProgrammatic: h.closeModalProgrammatic,
        onRefresh: h.onRefresh,
      });

      // Trong lúc request đang pending:
      assert.equal(h.state.isSubmittingDecision, true);
      assert.equal(h.handleUserClose(), false);
      assert.notEqual(h.state.selectedApproval, null);

      const secondRes = await executeStaffApprovalDecision({
        action: 'approve',
        isMockMode: false,
        selectedApproval: h.state.selectedApproval,
        isModalStale: h.state.isModalStale,
        isDecisionPendingRef: h.isDecisionPendingRef,
        staffApprovalsApi: {
          approveStaff: async () => {
            postCalls += 1;
            return {};
          },
        },
        getApiErrorMessage: () => 'err',
        setIsSubmittingDecision: h.setIsSubmittingDecision,
        setModalError: h.setModalError,
        setIsModalStale: h.setIsModalStale,
        onSuccessToast: h.onSuccessToast,
        closeModalProgrammatic: h.closeModalProgrammatic,
        onRefresh: h.onRefresh,
      });
      assert.equal(secondRes.status, 'ignored');
      assert.equal(postCalls, 1);

      resolvePost({ status: 'APPROVED' });
      await firstPromise;
      assert.equal(h.state.selectedApproval, null);
      assert.equal(h.state.isSubmittingDecision, false);
    });

    test('POST trả 409: đánh dấu modal stale, không đóng, refresh danh sách và không retry POST', async () => {
      const h = createModalHarness();
      let postCalls = 0;
      const res = await executeStaffApprovalDecision({
        action: 'approve',
        isMockMode: false,
        selectedApproval: h.state.selectedApproval,
        isModalStale: h.state.isModalStale,
        isDecisionPendingRef: h.isDecisionPendingRef,
        staffApprovalsApi: {
          approveStaff: async () => {
            postCalls += 1;
            const err = new Error('Conflict');
            err.response = { status: 409 };
            throw err;
          },
        },
        getApiErrorMessage: () => 'Conflict',
        setIsSubmittingDecision: h.setIsSubmittingDecision,
        setModalError: h.setModalError,
        setIsModalStale: h.setIsModalStale,
        onSuccessToast: h.onSuccessToast,
        closeModalProgrammatic: h.closeModalProgrammatic,
        onRefresh: h.onRefresh,
      });

      assert.equal(res.status, 'conflict');
      assert.equal(postCalls, 1);
      assert.equal(h.state.isModalStale, true);
      assert.notEqual(h.state.selectedApproval, null);
      assert.match(h.state.modalError, /409 Conflict/);
      assert.equal(h.state.refreshCount, 1);
      assert.equal(h.state.toasts.length, 0);
    });

    test('POST trả 422: giữ nguyên rejectReason để người dùng chỉnh sửa', async () => {
      const originalReason = 'Lý do cần giữ nguyên khi server trả 422';
      const h = createModalHarness({ rejectReason: originalReason });
      const res = await executeStaffApprovalDecision({
        action: 'reject',
        isMockMode: false,
        selectedApproval: h.state.selectedApproval,
        isModalStale: h.state.isModalStale,
        isDecisionPendingRef: h.isDecisionPendingRef,
        rejectReason: h.state.rejectReason,
        validateRejectReason,
        staffApprovalsApi: {
          rejectStaff: async () => {
            const err = new Error('Unprocessable');
            err.response = { status: 422 };
            throw err;
          },
        },
        getApiErrorMessage: () => 'Dữ liệu lý do không hợp lệ',
        setIsSubmittingDecision: h.setIsSubmittingDecision,
        setModalError: h.setModalError,
        setIsModalStale: h.setIsModalStale,
        onSuccessToast: h.onSuccessToast,
        closeModalProgrammatic: h.closeModalProgrammatic,
        onRefresh: h.onRefresh,
      });

      assert.equal(res.status, 'error');
      assert.equal(h.state.rejectReason, originalReason);
      assert.equal(h.state.isModalStale, false);
      assert.notEqual(h.state.selectedApproval, null);
      assert.equal(h.state.modalError, 'Dữ liệu lý do không hợp lệ');
    });

    test('Thành công từ deep-link và stale async response không mở lại modal đã đóng', async () => {
      const h = createModalHarness({
        search: 'approval_request_id=42',
        deepLinkGen: 10,
      });
      const inFlightDeepLinkGen = h.state.deepLinkGenRef.current;

      await executeStaffApprovalDecision({
        action: 'approve',
        isMockMode: false,
        selectedApproval: h.state.selectedApproval,
        isModalStale: h.state.isModalStale,
        isDecisionPendingRef: h.isDecisionPendingRef,
        staffApprovalsApi: {
          approveStaff: async () => ({ status: 'APPROVED' }),
        },
        getApiErrorMessage: () => 'err',
        setIsSubmittingDecision: h.setIsSubmittingDecision,
        setModalError: h.setModalError,
        setIsModalStale: h.setIsModalStale,
        onSuccessToast: h.onSuccessToast,
        closeModalProgrammatic: h.closeModalProgrammatic,
        onRefresh: h.onRefresh,
      });

      assert.equal(h.state.urlParams.has('approval_request_id'), false);
      assert.equal(h.state.selectedApproval, null);
      assert.ok(h.state.deepLinkGenRef.current > inFlightDeepLinkGen);

      // Giả lập một promise deep-link cũ hoàn thành trễ sau khi modal đã đóng
      if (inFlightDeepLinkGen === h.state.deepLinkGenRef.current) {
        h.state.selectedApproval = { ...SAMPLE_PENDING_APPROVAL };
      }
      assert.equal(h.state.selectedApproval, null);
    });
  });
});
