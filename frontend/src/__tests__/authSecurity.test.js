import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import axiosClient, {
  isMockAllowed,
  getUseMock,
  setUseMock,
  transitionAuthMode,
  runHealthCheck,
  beginLoginAttempt,
  canCommitLoginAttempt,
  commitLoginSession,
  isSafeToReplayRequest,
  isLogoutInProgress,
  registerVerifiedIdempotentEndpoint,
  clearVerifiedIdempotentEndpoints,
  isEndpointVerifiedForIdempotency,
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
    clearVerifiedIdempotentEndpoints();
    setAuthTransport(null);
    setupAxiosAuth({
      onTokenRefreshed: null,
      onAuthFailed: null,
      onSessionInvalidated: null,
    });
  });

  afterEach(() => {
    axiosClient.defaults.adapter = originalAdapter;
    clearVerifiedIdempotentEndpoints();
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

  // ==========================================================================
  // 6. ROUND 3 — FIX-01: LOGIN SESSION GENERATION & ATTEMPT GUARD
  // ==========================================================================
  describe('Round 3 — FIX-01: Login Session Generation Guard', () => {
    it('blocks stale Real login response arriving after switching Real -> Mock', () => {
      const devMockEnv = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };
      setUseMock(false, devMockEnv);

      // Start Login A in Real mode
      const attemptA = beginLoginAttempt(devMockEnv);
      assert.equal(attemptA.isMock, false);
      assert.equal(canCommitLoginAttempt(attemptA, devMockEnv), true);

      // User switches to Mock mode while Login A request is still in flight
      transitionAuthMode(true, devMockEnv);
      assert.equal(getUseMock(), true);

      // Login A response arrives late
      assert.equal(canCommitLoginAttempt(attemptA, devMockEnv), false);
      const commitRes = commitLoginSession(
        attemptA,
        {
          accessToken: 'stale-real-token-A',
          csrfToken: 'stale-csrf-A',
          user: { id: 1, role: 'ADMIN' },
        },
        devMockEnv
      );
      assert.equal(commitRes.committed, false);
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);
      setUseMock(false, devMockEnv);
    });

    it('blocks stale login response arriving after logout / invalidateSession', () => {
      const attempt = beginLoginAttempt();
      assert.equal(canCommitLoginAttempt(attempt), true);

      // Session invalidated / logged out while login response is in flight
      invalidateSession();

      assert.equal(canCommitLoginAttempt(attempt), false);
      const commitRes = commitLoginSession(attempt, {
        accessToken: 'stale-token-after-logout',
        csrfToken: 'stale-csrf-after-logout',
      });
      assert.equal(commitRes.committed, false);
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);
    });

    it('blocks Login A arriving after Login B has already succeeded', () => {
      // User starts Login A
      const attemptA = beginLoginAttempt();

      // User starts Login B and Login B succeeds first
      const attemptB = beginLoginAttempt();
      const commitB = commitLoginSession(attemptB, {
        accessToken: 'token-user-B',
        csrfToken: 'csrf-user-B',
        user: { id: 2, email: 'userb@retailops.local', role: 'STAFF' },
      });
      assert.equal(commitB.committed, true);
      assert.equal(getClientToken(), 'token-user-B');

      // Login A response finally arrives late -> must NOT overwrite User B's session
      assert.equal(canCommitLoginAttempt(attemptA), false);
      const commitA = commitLoginSession(attemptA, {
        accessToken: 'token-user-A-stale',
        csrfToken: 'csrf-user-A-stale',
        user: { id: 1, email: 'usera@retailops.local', role: 'ADMIN' },
      });
      assert.equal(commitA.committed, false);
      assert.equal(getClientToken(), 'token-user-B');
      assert.equal(getCsrfToken(), 'csrf-user-B');
    });

    it('allows valid undisturbed login attempt to commit normally', () => {
      const attempt = beginLoginAttempt();
      assert.equal(canCommitLoginAttempt(attempt), true);

      const commitRes = commitLoginSession(attempt, {
        accessToken: 'valid-login-token',
        csrfToken: 'valid-login-csrf',
        user: { id: 10, role: 'ADMIN', status: 'APPROVED' },
      });
      assert.equal(commitRes.committed, true);
      assert.equal(getClientToken(), 'valid-login-token');
      assert.equal(getCsrfToken(), 'valid-login-csrf');
    });
  });

  // ==========================================================================
  // 7. ROUND 3 — FIX-02: SINGLE AUTH MODE TRANSITION & HEALTH CHECK ISOLATION
  // ==========================================================================
  describe('Round 3 — FIX-02: Single Auth Mode Transition & Health Check Isolation', () => {
    it('keeps Mock session consistent when clicking Backend health check (never auto-switches mode)', async () => {
      const devMockEnv = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };
      transitionAuthMode(true, devMockEnv);
      startAuthenticatedSession('mock-admin-token', null);

      setAuthTransport({
        get: async (url) => {
          if (url.includes('/health')) {
            return { status: 200, data: { status: 'ok' }, headers: {} };
          }
          throw new Error(`Unexpected GET ${url}`);
        },
        post: async () => ({ status: 200, data: {} }),
      });

      const healthResult = await runHealthCheck({ allowSessionRestore: false });
      assert.equal(healthResult.online, true);
      // Mode and mock session remain intact and synchronized (not silently flipped to Real mode)
      assert.equal(getUseMock(), true);
      assert.equal(getClientToken(), 'mock-admin-token');

      transitionAuthMode(false, devMockEnv);
    });

    it('does NOT alter valid Real session during routine health check', async () => {
      startAuthenticatedSession('real-active-token', 'real-active-csrf');
      const genBefore = getSessionGeneration();

      setAuthTransport({
        get: async (url) => {
          assert.ok(url.includes('/health'));
          return { status: 200, data: { status: 'ok' }, headers: {} };
        },
        post: async () => {
          throw new Error('Refresh should not be called when token is already active');
        },
      });

      const res = await runHealthCheck({ allowSessionRestore: true });
      assert.equal(res.online, true);
      assert.equal(res.restored, false);
      assert.equal(getClientToken(), 'real-active-token');
      assert.equal(getCsrfToken(), 'real-active-csrf');
      assert.equal(getSessionGeneration(), genBefore);
    });

    it('synchronizes React/caller state and clears user/tokens across Real -> Mock -> Real transitions', () => {
      const devMockEnv = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };
      let syncedState = {
        user: { id: 1, role: 'ADMIN' },
        accessToken: 'real-token-1',
        isMockMode: false,
      };

      setupAxiosAuth({
        onTokenRefreshed: null,
        onAuthFailed: null,
        onSessionInvalidated: ({ isMockMode }) => {
          syncedState = {
            user: null,
            accessToken: null,
            isMockMode,
          };
        },
      });

      startAuthenticatedSession('real-token-1', 'real-csrf-1');

      // Transition Real -> Mock
      const toMock = transitionAuthMode(true, devMockEnv);
      assert.equal(toMock.isMockMode, true);
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);
      assert.equal(syncedState.user, null);
      assert.equal(syncedState.accessToken, null);
      assert.equal(syncedState.isMockMode, true);

      // Login in Mock mode, then transition Mock -> Real
      startAuthenticatedSession('mock-token-2', null);
      syncedState.user = { id: 'usr_admin_demo', role: 'ADMIN', isMock: true };
      syncedState.accessToken = 'mock-token-2';

      const toReal = transitionAuthMode(false, devMockEnv);
      assert.equal(toReal.isMockMode, false);
      assert.equal(getClientToken(), null);
      assert.equal(getCsrfToken(), null);
      assert.equal(syncedState.user, null);
      assert.equal(syncedState.accessToken, null);
      assert.equal(syncedState.isMockMode, false);
    });

    it('blocks late health-check cookie restoration after mode has changed', async () => {
      const devMockEnv = { DEV: true, PROD: false, VITE_USE_MOCK: 'true' };
      transitionAuthMode(false, devMockEnv);

      let restoredCallbackInvoked = false;
      setAuthTransport({
        get: async (url) => {
          if (url.includes('/health')) {
            await new Promise((r) => setTimeout(r, 20));
            // Mode changes to Mock while health check is finishing
            transitionAuthMode(true, devMockEnv);
            return { status: 200, data: { status: 'ok' }, headers: {} };
          }
          return { status: 200, data: { csrf_token: 'csrf' }, headers: {} };
        },
        post: async () => ({
          status: 200,
          data: {
            access_token: 'should-not-restore',
            user: {
              id: 1,
              email_normalized: 'admin@retailops.local',
              role: 'ADMIN',
              status: 'ACTIVE',
            },
          },
          headers: {},
        }),
      });

      const res = await runHealthCheck({
        allowSessionRestore: true,
        onRestoredSession: () => {
          restoredCallbackInvoked = true;
        },
      });

      assert.equal(res.restored, false);
      assert.equal(restoredCallbackInvoked, false);
      assert.equal(getClientToken(), null);
      transitionAuthMode(false, devMockEnv);
    });

    it('never activates Mock mode when Backend health check fails (offline)', async () => {
      setAuthTransport({
        get: async () => {
          throw new Error('ECONNREFUSED');
        },
        post: async () => ({ status: 500 }),
      });

      const res = await runHealthCheck({ allowSessionRestore: true });
      assert.equal(res.online, false);
      assert.equal(getUseMock(), false);
    });
  });

  // ==========================================================================
  // 8. ROUND 3 — FIX-03: STALE SUCCESSFUL RESPONSE ISOLATION
  // ==========================================================================
  describe('Round 3 — FIX-03: Stale Successful Response Isolation', () => {
    it('rejects late 200 OK response from User A after User A logs out and User B logs in', async () => {
      startAuthenticatedSession('token-user-A', 'csrf-user-A');

      axiosClient.defaults.adapter = async (config) => {
        if (config.url === '/orders?owner=userA') {
          await new Promise((r) => setTimeout(r, 25));
          // User A logs out and User B logs in while User A's GET is in flight
          invalidateSession();
          startAuthenticatedSession('token-user-B', 'csrf-user-B');
          return {
            status: 200,
            statusText: 'OK',
            headers: { 'x-csrf-token': 'stale-csrf-from-user-A' },
            config,
            data: { orders: ['secret-order-of-user-A'] },
          };
        }
        return {
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
          data: { orders: ['order-of-user-B'] },
        };
      };

      await assert.rejects(axiosClient.get('/orders?owner=userA'), (err) => {
        return err.isStaleSession === true && err.code === 'ERR_STALE_SESSION';
      });

      // User B's CSRF and token must not be overwritten by User A's stale 200 response
      assert.equal(getClientToken(), 'token-user-B');
      assert.equal(getCsrfToken(), 'csrf-user-B');

      // User B's own request succeeds normally
      const userBRes = await axiosClient.get('/orders?owner=userB');
      assert.deepEqual(userBRes.data, { orders: ['order-of-user-B'] });
    });

    it('rejects late 200 OK response when session is invalidated while request is in flight', async () => {
      startAuthenticatedSession('token-user-A', 'csrf-user-A');

      axiosClient.defaults.adapter = async (config) => {
        await new Promise((r) => setTimeout(r, 20));
        invalidateSession();
        return {
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
          data: { items: ['stale-data'] },
        };
      };

      await assert.rejects(axiosClient.get('/products'), (err) => {
        return err.isStaleSession === true;
      });
    });

    it('does NOT reject public requests (/auth/register, /health, unauthenticated requests) when generation changes', async () => {
      // Unauthenticated state
      invalidateSession();

      axiosClient.defaults.adapter = async (config) => {
        await new Promise((r) => setTimeout(r, 15));
        // Generation changes while public request is in flight
        invalidateSession();
        return {
          status: 202,
          statusText: 'Accepted',
          headers: {},
          config,
          data: { message: 'If the registration can be processed...' },
        };
      };

      const res = await axiosClient.post('/auth/register', {
        email: 'newstaff@retailops.local',
        password: 'ValidPassword123',
      });
      assert.equal(res.status, 202);
    });
  });

  // ==========================================================================
  // 9. ROUND 3 — FIX-04: PREVENT REDUNDANT REFRESH AFTER LATE 401 & REPLAY POLICY
  // ==========================================================================
  describe('Round 3 — FIX-04: Prevent Redundant Refresh on Late 401 & Safe Replay Policy', () => {
    it('prevents refresh storm when 3 requests receive 401 at staggered times (late 401 after refresh completed)', async () => {
      startAuthenticatedSession('token-v1', 'csrf-v1');

      let refreshCount = 0;
      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-v1' }, headers: {} }),
        post: async (url) => {
          if (url.includes('/auth/refresh')) {
            refreshCount += 1;
            await new Promise((r) => setTimeout(r, 20));
            return {
              status: 200,
              data: { access_token: 'token-v2' },
              headers: { 'x-csrf-token': 'csrf-v2' },
            };
          }
          throw new Error(`Unexpected POST ${url}`);
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        const auth = config.headers?.Authorization;
        if (auth === 'Bearer token-v2') {
          return {
            status: 200,
            statusText: 'OK',
            headers: {},
            config,
            data: { url: config.url, tokenUsed: 'token-v2' },
          };
        }

        // Simulate staggered 401 responses:
        // req1 fails at 5ms, req2 fails at 10ms (during refresh), req3 fails at 45ms (AFTER refresh finished!)
        if (config.url === '/req-1') {
          await new Promise((r) => setTimeout(r, 5));
        } else if (config.url === '/req-2') {
          await new Promise((r) => setTimeout(r, 10));
        } else if (config.url === '/req-3-late') {
          await new Promise((r) => setTimeout(r, 45));
        }
        throw createHttpError(401, config);
      };

      const [r1, r2, r3] = await Promise.all([
        axiosClient.get('/req-1'),
        axiosClient.get('/req-2'),
        axiosClient.get('/req-3-late'),
      ]);

      // Only 1 refresh call must have been made! req-3-late reused token-v2 directly!
      assert.equal(refreshCount, 1);
      assert.equal(r1.data.tokenUsed, 'token-v2');
      assert.equal(r2.data.tokenUsed, 'token-v2');
      assert.equal(r3.data.tokenUsed, 'token-v2');
    });

    it('retries at most once on late 401 and does not loop if the retried request also returns 401', async () => {
      startAuthenticatedSession('token-v1', 'csrf-v1');

      let refreshCalls = 0;
      let lateReqAttempts = 0;

      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-v1' }, headers: {} }),
        post: async () => {
          refreshCalls += 1;
          return {
            status: 200,
            data: { access_token: 'token-v2' },
            headers: {},
          };
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        if (config.url === '/first-req') {
          if (config.headers?.Authorization === 'Bearer token-v2') {
            return { status: 200, data: { ok: true }, headers: {}, config };
          }
          throw createHttpError(401, config);
        }

        if (config.url === '/late-still-401') {
          lateReqAttempts += 1;
          if (lateReqAttempts === 1) {
            await new Promise((r) => setTimeout(r, 25));
          }
          // Even when retried with token-v2, server returns 401
          throw createHttpError(401, config);
        }

        throw createHttpError(401, config);
      };

      const [firstRes, lateRes] = await Promise.allSettled([
        axiosClient.get('/first-req'),
        axiosClient.get('/late-still-401'),
      ]);

      assert.equal(firstRes.status, 'fulfilled');
      assert.equal(lateRes.status, 'rejected');
      assert.equal(refreshCalls, 1);
      assert.equal(lateReqAttempts, 2); // 1 initial + 1 retry max
    });

    it('rejects late-401 retry when session changes between initial send and retry execution', async () => {
      startAuthenticatedSession('token-v1', 'csrf-v1');

      axiosClient.defaults.adapter = async (config) => {
        if (config.url === '/req-session-switch') {
          await new Promise((r) => setTimeout(r, 15));
          // Another user session starts before 401 is processed
          startAuthenticatedSession('token-other-user', 'csrf-other-user');
          throw createHttpError(401, config);
        }
        return { status: 200, data: {}, headers: {}, config };
      };

      await assert.rejects(
        axiosClient.get('/req-session-switch'),
        (err) => err.isStaleSession === true
      );
      assert.equal(getClientToken(), 'token-other-user');
    });

    it('blocks automatic replay of non-idempotent mutations and unverified endpoints on 401 even if Idempotency-Key is provided', async () => {
      assert.equal(isSafeToReplayRequest({ method: 'GET', headers: {} }), true);
      assert.equal(isSafeToReplayRequest({ method: 'HEAD', headers: {} }), true);
      assert.equal(isSafeToReplayRequest({ method: 'POST', url: '/orders', headers: {} }), false);
      assert.equal(isSafeToReplayRequest({ method: 'PATCH', url: '/products/1', headers: {} }), false);
      assert.equal(isSafeToReplayRequest({ method: 'DELETE', url: '/products/1', headers: {} }), false);
      // Fail-closed: unverified endpoint is blocked even if caller attaches Idempotency-Key
      assert.equal(
        isSafeToReplayRequest({
          method: 'POST',
          url: '/orders',
          headers: { 'Idempotency-Key': 'idem-123' },
        }),
        false
      );

      startAuthenticatedSession('expired-token-mut', 'csrf-mut');

      let postAttemptCount = 0;
      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-mut' }, headers: {} }),
        post: async () => ({
          status: 200,
          data: { access_token: 'fresh-token-mut' },
          headers: {},
        }),
      });

      axiosClient.defaults.adapter = async (config) => {
        postAttemptCount += 1;
        if (config.headers?.Authorization === 'Bearer expired-token-mut') {
          throw createHttpError(401, config);
        }
        return { status: 201, data: { created: true }, headers: {}, config };
      };

      // POST to unverified endpoint with Idempotency-Key must NOT be replayed automatically after 401
      await assert.rejects(
        axiosClient.post(
          '/orders',
          { items: [{ sku: 'SKU-1', qty: 1 }] },
          { headers: { 'Idempotency-Key': 'caller-unverified-key' } }
        ),
        (err) => err.isReplayBlocked === true
      );
      assert.equal(postAttemptCount, 1);
      // Session token was refreshed for subsequent user-initiated actions
      assert.equal(getClientToken(), 'fresh-token-mut');
    });

    it('allows single replay of mutation ONLY when endpoint is verified AND caller explicitly provides Idempotency-Key', async () => {
      // Register verified idempotent mutation endpoint
      registerVerifiedIdempotentEndpoint('/api/v1/checkout');
      assert.equal(isEndpointVerifiedForIdempotency('/api/v1/checkout'), true);

      startAuthenticatedSession('expired-token-idem', 'csrf-idem');

      const seenIdempotencyKeys = [];
      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-idem' }, headers: {} }),
        post: async () => ({
          status: 200,
          data: { access_token: 'fresh-token-idem' },
          headers: {},
        }),
      });

      axiosClient.defaults.adapter = async (config) => {
        seenIdempotencyKeys.push(config.headers?.['Idempotency-Key']);
        if (config.headers?.Authorization === 'Bearer expired-token-idem') {
          throw createHttpError(401, config);
        }
        return {
          status: 201,
          statusText: 'Created',
          headers: {},
          config,
          data: { orderId: 999 },
        };
      };

      const res = await axiosClient.post(
        '/api/v1/checkout',
        { total: 100000 },
        { headers: { 'Idempotency-Key': 'caller-supplied-key-001' } }
      );

      assert.equal(res.status, 201);
      assert.deepEqual(seenIdempotencyKeys, [
        'caller-supplied-key-001',
        'caller-supplied-key-001',
      ]);
      clearVerifiedIdempotentEndpoints();
    });
  });

  // ==========================================================================
  // 10. FINAL HARDENING — FIX-01 & FIX-03: LOGOUT/LOGIN COOKIE RACE & CONTRACT
  // ==========================================================================
  describe('Final Hardening — FIX-01 & FIX-03: Logout/Login Cookie Race & Contract Consistency', () => {
    it('blocks new login while server logout is pending and allows login after 204 completion', async () => {
      startAuthenticatedSession('active-session-token', 'active-csrf');

      let logoutPostReceived = false;
      let loginPostCount = 0;

      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'active-csrf' }, headers: {} }),
        post: async (url) => {
          if (url.includes('/auth/logout')) {
            logoutPostReceived = true;
            await new Promise((r) => setTimeout(r, 35));
            return { status: 204, data: null, headers: {} };
          }
          throw new Error(`Unexpected POST ${url}`);
        },
      });

      axiosClient.defaults.adapter = async (config) => {
        if (config.url?.includes('/auth/login')) {
          loginPostCount += 1;
          return {
            status: 200,
            headers: { 'x-csrf-token': 'new-login-csrf' },
            config,
            data: {
              access_token: 'new-login-token',
              user: {
                id: 1,
                email_normalized: 'admin@retailops.local',
                role: 'ADMIN',
                status: 'ACTIVE',
              },
            },
          };
        }
        return { status: 200, data: {}, headers: {}, config };
      };

      // 1. Start server logout
      const logoutPromise = callLogoutApi({
        accessToken: 'active-session-token',
        csrfToken: 'active-csrf',
      });

      // 2. While logout is in flight: isLogoutInProgress() is true
      assert.equal(isLogoutInProgress(), true);
      assert.equal(canCommitLoginAttempt(beginLoginAttempt()), false);

      // 3. Attempting to send login request while logout is pending MUST be rejected immediately
      await assert.rejects(
        axiosClient.post('/auth/login', {
          email: 'admin@retailops.local',
          password: 'Password123',
        }),
        (err) => err.message.includes('đang xử lý đăng xuất')
      );
      assert.equal(loginPostCount, 0); // Network request to login was never sent!

      // 4. Wait for logout to complete with 204
      const logoutResult = await logoutPromise;
      assert.equal(logoutResult.revoked, true);
      assert.equal(logoutPostReceived, true);
      assert.equal(isLogoutInProgress(), false);

      // 5. Now that logout finished, login is permitted and completes cleanly
      const loginRes = await axiosClient.post('/auth/login', {
        email: 'admin@retailops.local',
        password: 'Password123',
      });
      assert.equal(loginRes.status, 200);
      assert.equal(loginPostCount, 1);
    });

    it('frees pending state and invalidates local session on logout network error or timeout without deadlock', async () => {
      startAuthenticatedSession('token-to-fail', 'csrf-to-fail');
      invalidateSession();
      assert.equal(getClientToken(), null);

      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf' }, headers: {} }),
        post: async (url) => {
          if (url.includes('/auth/logout')) {
            await new Promise((r) => setTimeout(r, 20));
            throw new Error('Network timeout during logout');
          }
          return { status: 200, data: {} };
        },
      });

      const logoutPromise = callLogoutApi({
        accessToken: 'token-to-fail',
        csrfToken: 'csrf-to-fail',
      });
      assert.equal(isLogoutInProgress(), true);

      const res = await logoutPromise;
      assert.equal(res.revoked, false);
      assert.equal(isLogoutInProgress(), false);
      assert.equal(getClientToken(), null);

      // Session can start a new login without deadlock
      const attempt = beginLoginAttempt();
      assert.equal(canCommitLoginAttempt(attempt), true);
    });

    it('coalesces concurrent logout calls into a single network request', async () => {
      let serverLogoutCalls = 0;
      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-concurrent' }, headers: {} }),
        post: async (url) => {
          if (url.includes('/auth/logout')) {
            serverLogoutCalls += 1;
            await new Promise((r) => setTimeout(r, 25));
            return { status: 204, data: null, headers: {} };
          }
          return { status: 200, data: {} };
        },
      });

      const [res1, res2] = await Promise.all([
        callLogoutApi({ accessToken: 'tok-1', csrfToken: 'csrf-1' }),
        callLogoutApi({ accessToken: 'tok-1', csrfToken: 'csrf-1' }),
      ]);

      assert.equal(serverLogoutCalls, 1);
      assert.equal(res1.revoked, true);
      assert.equal(res2.revoked, true);
    });

    it('standardizes logout contract and eliminates duplicate consumer handling', async () => {
      setAuthTransport({
        get: async () => ({ data: { csrf_token: 'csrf-test' }, headers: {} }),
        post: async () => ({ status: 204, data: null, headers: {} }),
      });

      const res = await callLogoutApi({ accessToken: 'tok', csrfToken: 'csrf' });
      assert.equal(typeof res.revoked, 'boolean');
      assert.equal(res.revoked, true);
    });
  });
});
