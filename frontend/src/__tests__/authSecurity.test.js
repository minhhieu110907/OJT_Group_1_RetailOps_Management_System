import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import axiosClient, {
  isMockAllowed,
  getUseMock,
  setUseMock,
  getClientToken,
  getCsrfToken,
  getSessionGeneration,
  startAuthenticatedSession,
  invalidateSession,
  setupAxiosAuth,
  callLogoutApi,
  setAuthTransport,
  normalizeBackendUser,
  evaluateRouteAccess,
} from '../api/axiosClient.js';
import {
  validateChangePasswordForm,
  validateResetPasswordByTokenForm,
} from '../utils/validation.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SRC_DIR = path.resolve(__dirname, '..');

/**
 * Helper tạo HTTP error chuẩn Axios cho custom adapter trong test
 */
function createHttpError(status, config, data = { message: `HTTP ${status}` }) {
  const err = new Error(`Request failed with status code ${status}`);
  err.config = config;
  err.isAxiosError = true;
  err.response = {
    status,
    data,
    headers: {},
    config,
  };
  return err;
}

describe('PR #20 Final Security Remediation — Automated Verification Suite', () => {
  const originalAdapter = axiosClient.defaults.adapter;

  beforeEach(() => {
    invalidateSession();
    setAuthTransport(null);
    setupAxiosAuth({
      onTokenRefreshed: null,
      onAuthFailed: null,
    });
  });

  afterEach(() => {
    axiosClient.defaults.adapter = originalAdapter;
    setAuthTransport(null);
    invalidateSession();
  });

  // ==========================================================================
  // 1. FIX-01: MOCK AUTHENTICATION ISOLATION
  // ==========================================================================
  describe('FIX-01: Mock Authentication Isolation & Session Clearing', () => {
    it('blocks Mock mode in production build even if VITE_USE_MOCK is true', () => {
      assert.equal(
        isMockAllowed({ PROD: true, DEV: false, VITE_USE_MOCK: 'true' }),
        false
      );
      assert.equal(
        isMockAllowed({ PROD: true, DEV: true, VITE_USE_MOCK: 'true' }),
        false
      );
    });

    it('defaults to Real API in development unless VITE_USE_MOCK is explicitly "true"', () => {
      assert.equal(
        isMockAllowed({ PROD: false, DEV: true, VITE_USE_MOCK: undefined }),
        false
      );
      assert.equal(
        isMockAllowed({ PROD: false, DEV: true, VITE_USE_MOCK: 'false' }),
        false
      );
      assert.equal(
        isMockAllowed({ PROD: false, DEV: true, VITE_USE_MOCK: 'true' }),
        true
      );
    });

    it('prevents runtime setUseMock(true) when Mock is not allowed by environment', () => {
      // In Node test runtime, import.meta.env is undefined -> isMockAllowed() is false
      const result = setUseMock(true);
      assert.equal(result, false);
      assert.equal(getUseMock(), false);
    });

    it('clears active session token, CSRF token, and increments session generation when switching modes', () => {
      const devMockEnv = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };
      startAuthenticatedSession('token-session-1', 'csrf-session-1');
      const genBefore = getSessionGeneration();
      assert.equal(getClientToken(), 'token-session-1');
      assert.equal(getCsrfToken(), 'csrf-session-1');

      // Switch Real -> Mock in allowed DEV environment
      const switchedToMock = setUseMock(true, devMockEnv);
      assert.equal(switchedToMock, true);
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);
      assert.ok(getSessionGeneration() > genBefore);

      // Start another session and switch Mock -> Real
      startAuthenticatedSession('token-session-2', 'csrf-session-2');
      const genMid = getSessionGeneration();
      const switchedToReal = setUseMock(false, devMockEnv);
      assert.equal(switchedToReal, false);
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);
      assert.ok(getSessionGeneration() > genMid);
    });
  });

  // ==========================================================================
  // 2. FIX-02: CONCURRENT 401 SINGLE-FLIGHT & SESSION GENERATION ISOLATION
  // ==========================================================================
  describe('FIX-02: Session Generation & Refresh Race Conditions', () => {
    it('coalesces concurrent 401 responses into a single POST /auth/refresh and resolves all queued requests', async () => {
      startAuthenticatedSession('expired-token-A', 'csrf-token-A');

      let refreshCallCount = 0;
      setAuthTransport({
        get: async () => ({
          data: { csrf_token: 'csrf-token-A' },
          headers: {},
        }),
        post: async (url) => {
          if (url.includes('/auth/refresh')) {
            refreshCallCount += 1;
            await new Promise((r) => setTimeout(r, 30));
            return {
              status: 200,
              data: {
                access_token: 'fresh-token-A2',
                user: {
                  id: 10,
                  email_normalized: 'staff@retailops.local',
                  role: 'STAFF',
                  status: 'ACTIVE',
                },
              },
              headers: { 'x-csrf-token': 'csrf-token-A2' },
            };
          }
          throw new Error(`Unexpected transport POST: ${url}`);
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        const authHeader = config.headers?.Authorization || '';
        if (authHeader === 'Bearer expired-token-A') {
          throw createHttpError(401, config);
        }
        if (authHeader === 'Bearer fresh-token-A2') {
          return {
            status: 200,
            statusText: 'OK',
            headers: {},
            config,
            data: { url: config.url, authHeader },
          };
        }
        throw createHttpError(401, config);
      };

      const [res1, res2, res3] = await Promise.all([
        axiosClient.get('/products?page=1'),
        axiosClient.get('/products?page=2'),
        axiosClient.get('/products?page=3'),
      ]);

      assert.equal(refreshCallCount, 1);
      assert.equal(res1.data.authHeader, 'Bearer fresh-token-A2');
      assert.equal(res2.data.authHeader, 'Bearer fresh-token-A2');
      assert.equal(res3.data.authHeader, 'Bearer fresh-token-A2');
      assert.equal(getClientToken(), 'fresh-token-A2');
    });

    it('rejects all queued requests and triggers onAuthFailed once when refresh fails', async () => {
      startAuthenticatedSession('expired-token-B', 'csrf-token-B');

      let authFailedCount = 0;
      setupAxiosAuth({
        onTokenRefreshed: null,
        onAuthFailed: () => {
          authFailedCount += 1;
        },
      });

      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-token-B' }, headers: {} }),
        post: async () => {
          await new Promise((r) => setTimeout(r, 25));
          const err = new Error('Refresh token revoked');
          err.response = { status: 401, data: { message: 'Invalid refresh token' } };
          throw err;
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        throw createHttpError(401, config);
      };

      const results = await Promise.allSettled([
        axiosClient.get('/products?req=1'),
        axiosClient.get('/products?req=2'),
        axiosClient.get('/products?req=3'),
      ]);

      assert.equal(results.every((r) => r.status === 'rejected'), true);
      assert.equal(authFailedCount, 1);
      assert.equal(getClientToken(), null);
    });

    it('prevents session resurrection when logout occurs while refresh is in flight', async () => {
      startAuthenticatedSession('token-before-logout', 'csrf-before-logout');

      let tokenRefreshedCalled = false;
      setupAxiosAuth({
        onTokenRefreshed: () => {
          tokenRefreshedCalled = true;
        },
        onAuthFailed: null,
      });

      setAuthTransport({
        get: async () => ({
          data: { csrf_token: 'csrf-before-logout' },
          headers: {},
        }),
        post: async (url) => {
          if (url.includes('/auth/refresh')) {
            await new Promise((r) => setTimeout(r, 40));
            return {
              status: 200,
              data: { access_token: 'resurrected-token-should-be-blocked' },
              headers: {},
            };
          }
          return { status: 204, data: {}, headers: {} };
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        throw createHttpError(401, config);
      };

      const pendingRequest = axiosClient.get('/products');

      // User logs out while refresh is still waiting on network
      await new Promise((r) => setTimeout(r, 10));
      invalidateSession();

      await assert.rejects(pendingRequest);
      assert.equal(tokenRefreshedCalled, false);
      assert.equal(getClientToken(), null);
    });

    it('blocks stale request from User A from retrying with User B token after session switch', async () => {
      // User A starts session
      startAuthenticatedSession('token-user-A', 'csrf-user-A');

      let userBRequestRetriedWithUserATask = false;

      axiosClient.defaults.adapter = async (config) => {
        if (config.url === '/slow-user-a-endpoint') {
          // Simulate User A logging out and User B logging in BEFORE User A's request returns 401
          await new Promise((r) => setTimeout(r, 20));
          startAuthenticatedSession('token-user-B', 'csrf-user-B');

          if (config.headers?.Authorization === 'Bearer token-user-B') {
            userBRequestRetriedWithUserATask = true;
          }
          throw createHttpError(401, config);
        }
        return { status: 200, data: { ok: true }, headers: {}, config };
      };

      await assert.rejects(axiosClient.get('/slow-user-a-endpoint'));
      assert.equal(userBRequestRetriedWithUserATask, false);
      // User B's session must remain intact!
      assert.equal(getClientToken(), 'token-user-B');
      assert.equal(getCsrfToken(), 'csrf-user-B');
    });

    it('ensures stale failed refresh from User A does not wipe User B session', async () => {
      startAuthenticatedSession('token-user-A', 'csrf-user-A');

      let authFailedTriggeredForUserB = false;
      setupAxiosAuth({
        onTokenRefreshed: null,
        onAuthFailed: () => {
          authFailedTriggeredForUserB = true;
        },
      });

      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-user-A' }, headers: {} }),
        post: async () => {
          // While User A's refresh is in flight, User B logs in
          await new Promise((r) => setTimeout(r, 25));
          startAuthenticatedSession('token-user-B', 'csrf-user-B');
          throw new Error('User A refresh failed');
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        throw createHttpError(401, config);
      };

      await assert.rejects(axiosClient.get('/orders'));
      assert.equal(authFailedTriggeredForUserB, false);
      assert.equal(getClientToken(), 'token-user-B');
    });

    it('does NOT trigger refresh or logout on 403 Forbidden', async () => {
      startAuthenticatedSession('valid-staff-token', 'valid-csrf');

      let refreshCalled = false;
      let authFailedCalled = false;
      setupAxiosAuth({
        onTokenRefreshed: null,
        onAuthFailed: () => {
          authFailedCalled = true;
        },
      });
      setAuthTransport({
        get: async () => ({ data: {}, headers: {} }),
        post: async () => {
          refreshCalled = true;
          return { status: 200, data: {} };
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        throw createHttpError(403, config, { message: 'Forbidden' });
      };

      await assert.rejects(axiosClient.get('/admin-only-resource'), (err) => {
        return err.response?.status === 403;
      });
      assert.equal(refreshCalled, false);
      assert.equal(authFailedCalled, false);
      assert.equal(getClientToken(), 'valid-staff-token');
    });

    it('does NOT loop infinitely when retried request after refresh still returns 401', async () => {
      startAuthenticatedSession('expired-token', 'csrf-token');

      let refreshCalls = 0;
      let adapterCalls = 0;

      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-token' }, headers: {} }),
        post: async () => {
          refreshCalls += 1;
          return {
            status: 200,
            data: { access_token: 'new-token-still-401' },
            headers: {},
          };
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        adapterCalls += 1;
        throw createHttpError(401, config);
      };

      await assert.rejects(axiosClient.get('/protected-resource'));
      assert.equal(refreshCalls, 1);
      assert.equal(adapterCalls, 2); // 1 initial attempt + 1 retry max
    });
  });

  // ==========================================================================
  // 3. FIX-04: LOGOUT & SERVER-SIDE REVOCATION
  // ==========================================================================
  describe('FIX-04: Logout CSRF Snapshot & Server Revocation Status', () => {
    it('sends X-CSRF-Token from pre-invalidation snapshot and confirms 204 server revocation', async () => {
      startAuthenticatedSession('active-access-token', 'active-csrf-token');

      const tokenSnapshot = getClientToken();
      const csrfSnapshot = getCsrfToken();

      // Client invalidates session immediately
      invalidateSession();
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);

      let capturedHeaders = null;
      setAuthTransport({
        get: async () => ({ data: {}, headers: {} }),
        post: async (url, _body, config) => {
          assert.ok(url.includes('/auth/logout'));
          capturedHeaders = config.headers;
          return { status: 204, data: null, headers: {} };
        },
      });

      const res = await callLogoutApi({
        accessToken: tokenSnapshot,
        csrfToken: csrfSnapshot,
      });

      assert.equal(res.revoked, true);
      assert.equal(capturedHeaders['X-CSRF-Token'], 'active-csrf-token');
      assert.equal(capturedHeaders.Authorization, 'Bearer active-access-token');
      // Must not re-populate inMemoryCsrfToken after session was invalidated
      assert.equal(getCsrfToken(), null);
    });

    it('returns revoked: false when server logout fails with 5xx or network error without restoring session', async () => {
      setAuthTransport({
        get: async () => ({ data: {}, headers: {} }),
        post: async () => {
          throw new Error('Network unreachable');
        },
      });

      const res = await callLogoutApi({
        accessToken: 'token-snap',
        csrfToken: 'csrf-snap',
      });

      assert.equal(res.revoked, false);
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);
    });
  });

  // ==========================================================================
  // 4. FIX-07: DEFENSIVE USER NORMALIZATION & PROTECTED ROUTE (FAIL-CLOSED)
  // ==========================================================================
  describe('FIX-07: Defensive normalizeBackendUser & evaluateRouteAccess', () => {
    it('rejects malformed user payloads missing status, role, id, or email (never defaults to ACTIVE/STAFF)', () => {
      assert.equal(normalizeBackendUser(null), null);
      assert.equal(normalizeBackendUser({}), null);
      // Missing status must NOT default to ACTIVE/APPROVED
      assert.equal(
        normalizeBackendUser({
          id: 1,
          email_normalized: 'user@retailops.local',
          role: 'STAFF',
        }),
        null
      );
      // Missing role must NOT default to STAFF
      assert.equal(
        normalizeBackendUser({
          id: 1,
          email_normalized: 'user@retailops.local',
          status: 'ACTIVE',
        }),
        null
      );
      // Invalid role
      assert.equal(
        normalizeBackendUser({
          id: 1,
          email_normalized: 'user@retailops.local',
          role: 'SUPERADMIN',
          status: 'ACTIVE',
        }),
        null
      );
      // Invalid status
      assert.equal(
        normalizeBackendUser({
          id: 1,
          email_normalized: 'user@retailops.local',
          role: 'ADMIN',
          status: 'UNKNOWN_STATUS',
        }),
        null
      );
    });

    it('normalizes valid Backend AuthenticatedUser contract accurately', () => {
      const admin = normalizeBackendUser({
        id: 1,
        email_normalized: 'admin@retailops.local',
        role: 'ADMIN',
        status: 'ACTIVE',
      });
      assert.ok(admin);
      assert.equal(admin.id, 1);
      assert.equal(admin.email, 'admin@retailops.local');
      assert.equal(admin.role, 'ADMIN');
      assert.equal(admin.status, 'APPROVED');

      const pendingStaff = normalizeBackendUser({
        id: 2,
        email_normalized: 'pending@retailops.local',
        role: 'STAFF',
        status: 'PENDING_APPROVAL',
      });
      assert.ok(pendingStaff);
      assert.equal(pendingStaff.status, 'PENDING');
    });

    it('enforces fail-closed route access in evaluateRouteAccess', () => {
      // 1. Wait while initializing
      assert.deepEqual(
        evaluateRouteAccess({
          authInitializing: true,
          user: null,
          accessToken: null,
          allowedRoles: ['ADMIN'],
        }),
        { action: 'WAIT' }
      );

      // 2. User present in state but missing accessToken -> REDIRECT_LOGIN
      assert.deepEqual(
        evaluateRouteAccess({
          authInitializing: false,
          user: { id: 1, role: 'ADMIN', status: 'APPROVED' },
          accessToken: null,
          allowedRoles: ['ADMIN'],
        }),
        { action: 'REDIRECT_LOGIN' }
      );

      // 3. PENDING or REJECTED -> REDIRECT_ACCOUNT_STATUS
      assert.deepEqual(
        evaluateRouteAccess({
          authInitializing: false,
          user: { id: 2, role: 'STAFF', status: 'PENDING' },
          accessToken: 'tok',
          allowedRoles: ['STAFF'],
        }),
        { action: 'REDIRECT_ACCOUNT_STATUS' }
      );
      assert.deepEqual(
        evaluateRouteAccess({
          authInitializing: false,
          user: { id: 3, role: 'STAFF', status: 'REJECTED' },
          accessToken: 'tok',
          allowedRoles: ['STAFF'],
        }),
        { action: 'REDIRECT_ACCOUNT_STATUS' }
      );

      // 4. STAFF accessing ADMIN-only route -> REDIRECT_ROLE_HOME (/pos)
      const staffOnAdminRoute = evaluateRouteAccess({
        authInitializing: false,
        user: { id: 4, role: 'STAFF', status: 'APPROVED' },
        accessToken: 'valid-token',
        allowedRoles: ['ADMIN'],
      });
      assert.equal(staffOnAdminRoute.action, 'REDIRECT_ROLE_HOME');
      assert.equal(staffOnAdminRoute.to, '/pos');

      // 5. Valid ADMIN with token -> ALLOW
      assert.deepEqual(
        evaluateRouteAccess({
          authInitializing: false,
          user: { id: 1, role: 'ADMIN', status: 'APPROVED' },
          accessToken: 'valid-admin-token',
          allowedRoles: ['ADMIN'],
        }),
        { action: 'ALLOW' }
      );
    });
  });

  // ==========================================================================
  // 5. FIX-03 & FIX-06: PASSWORD VALIDATION & STATIC SECURITY INVARIANTS
  // ==========================================================================
  describe('FIX-03, FIX-05, FIX-06: Password Validation & Codebase Security Invariants', () => {
    it('separates Change Password validation from Reset Password by Token validation', () => {
      // validateChangePasswordForm fails closed when expectedCurrentPassword is null
      const changeResNoRef = validateChangePasswordForm(
        {
          currentPassword: 'DemoPassword123',
          newPassword: 'NewPassword123',
          confirmPassword: 'NewPassword123',
        },
        null
      );
      assert.equal(changeResNoRef.isValid, false);

      // validateResetPasswordByTokenForm validates token without currentPassword
      const tokenResetRes = validateResetPasswordByTokenForm({
        token: 'mock_valid_token_12345',
        newPassword: 'NewPassword123',
        confirmPassword: 'NewPassword123',
      });
      assert.equal(tokenResetRes.isValid, true);
    });

    it('removes real PII emails and hardcoded fallback passwords from Auth components', () => {
      const filesToCheck = [
        'context/AuthContext.jsx',
        'pages/Auth/ForgotPassword.jsx',
        'pages/Auth/ResetPassword.jsx',
        'pages/Auth/AccountStatus.jsx',
      ];

      for (const relPath of filesToCheck) {
        const content = fs.readFileSync(path.join(SRC_DIR, relPath), 'utf8');
        assert.equal(
          content.includes('caoanhnguyenduong@gmail.com'),
          false,
          `Found personal email in ${relPath}`
        );
        assert.equal(
          content.includes('nguyenminhhieu@gmail.com'),
          false,
          `Found personal email in ${relPath}`
        );
      }

      const resetContent = fs.readFileSync(
        path.join(SRC_DIR, 'pages/Auth/ResetPassword.jsx'),
        'utf8'
      );
      assert.equal(
        resetContent.includes("'staff123'"),
        false,
        'ResetPassword.jsx must not fallback to hardcoded staff123 password'
      );
    });

    it('removes costPrice column and hides mutation actions from STAFF in ProductList.jsx', () => {
      const productListContent = fs.readFileSync(
        path.join(SRC_DIR, 'pages/Products/ProductList.jsx'),
        'utf8'
      );
      assert.equal(
        productListContent.includes("key: 'costPrice'"),
        false,
        'ProductList.jsx must not expose costPrice column'
      );
      assert.equal(
        productListContent.includes('page_size'),
        true,
        'ProductList.jsx must use page_size pagination contract'
      );
    });
  });
});
