# RetailOps V1.0 — Bonus: Staff account locking, profile, password change

Status: **Approved Bonus Scope — RetailOps V1.0, Implementation Verified**.
Baseline: `develop` commit `8e835a5df9981da3b54906fb4998563b8be5c24a`, 2026-11-19.
Owner: Backend Lead. Deadline: 2026-11-25.
This is an explicitly accepted Bonus extension to AUTH-03 for RetailOps V1.0, confirmed by the project lead on 2026-11-19. The approved SRS baseline remains unchanged and continues to exclude Staff suspension/reactivation from its original core scope; this document records the separate Bonus addendum. GitHub review and required CI remain independent merge requirements.

## Scope and non-goals

Single-store/single-warehouse Modular Monolith, two roles ADMIN and STAFF. This feature permits an active ADMIN to lock/unlock approved STAFF accounts; permits authenticated ACTIVE users to read/update their own minimal profile and change their own password. Do not add HR management, shifts, new roles, account deletion, social login, email changes, avatar storage, extra notifications or email recovery for ADMIN. Keep existing staff approval/reapply and one-time email reset separate.

## Identity and account lifecycle

- `UserStatus` adds exactly `LOCKED`. The current `users.status` column is `VARCHAR(16)`, sufficient for this value; update the MySQL `ck_users_role_status_admin_slot` constraint via a new linear Alembic migration after `20261118_01`. ADMIN remains ACTIVE and unique (admin_slot=1). STAFF allows PENDING_APPROVAL, ACTIVE, REJECTED, LOCKED.
- Staff transitions: `PENDING_APPROVAL -> ACTIVE|REJECTED` via existing approval service; `ACTIVE -> LOCKED` and `LOCKED -> ACTIVE` only via ADMIN account-management service. No direct transition from rejected/pending to locked, and no re-approval on unlock.
- Lock must atomically change status and set `revoked_at` on ALL still-active `auth_sessions` for the target user, including the session authenticating the current request if any. Unlock MUST NOT clear `revoked_at` or restore any previously revoked access/refresh tokens. A locked user can log in only after unlock with a new session. `find_live_principal`, `find_live_session_by_refresh` and `AuthService.refresh` continue checking ACTIVE status and revoked_at. Locked login should use a safe, domain-specific error without exposing password correctness to unauthenticated clients; consider uniform INVALID_CREDENTIALS as default.
- Define strict consistency semantics: requests starting after a lock commit must fail authentication; requests already authorized/in progress may complete. Design server-side transaction lock ordering (User row before auth_sessions/refresh row when mutations touch both) for login, refresh, change-password, lock/unlock, and reset-password flows. Avoid introducing deadlocks by changing only one flow. MySQL concurrency tests must prove no session created/revived during conflicting lock/login/refresh. A lock is not a distributed cancellation of in-flight work.
- For password-change: require current live principal, old password, new password. Verify old using existing `PasswordHasher`, reject reuse of current password, use existing bcrypt limits (72 UTF-8 bytes), update `password_hash`, `updated_at`, and revoke all OTHER sessions in one transaction. Preserve current session, but rotate its refresh-token generation in a CSRF-protected or equivalent authenticated flow if feasible; do not return raw refresh tokens in JSON or log them. Ensure concurrent refresh/reset/lock/change cannot leave stale credentials alive. Never extend absolute session expiry.
- Coordinate with existing `AuthResetService.consume_reset`, which revokes ALL sessions. Forgot/reset remains STAFF only and uses one-time email token. This Bonus does not alter the public reset contract.

## HTTP boundary (new; path proposal, freeze with frontend before implementation)

All responses use the existing stable API error envelope, `Cache-Control: no-store` for account/profile and sensitive mutations, and explicit Pydantic DTO allowlists (`extra='forbid'` for requests). No self-service ID in request payload; derive identity exclusively from `CurrentPrincipal`.

| Method | Relative path | Permission | Request | Success |
|---|---|---|---|---|
| GET | `/admin/staff` | ACTIVE ADMIN | `status=ACTIVE|LOCKED`, `search`, `page`, `page_size` | paginated allowlisted Staff account records |
| POST | `/admin/staff/{user_id}/lock` | ACTIVE ADMIN | empty object, or no body (choose one and freeze) | safe account DTO |
| POST | `/admin/staff/{user_id}/unlock` | ACTIVE ADMIN | same as lock | safe account DTO |
| GET | `/users/me` | ACTIVE ADMIN / STAFF | none | `{id,email_normalized,full_name,role,status,created_at,updated_at}` |
| PATCH | `/users/me` | ACTIVE ADMIN / STAFF | `{full_name: string|null}` | same safe profile DTO |
| POST | `/auth/change-password` | ACTIVE ADMIN / STAFF | `{current_password,new_password}` | safe message-only response (choose session cookie rotation design before freezing) |

- Admin management targets `users.id`, not `staff_approval_requests.id`. Exclude ADMIN/PENDING_APPROVAL/REJECTED targets from lock and unlock; return 404 for nonexistent/non-Staff and 409 for invalid current state. Repeat transitions must not create duplicate effects. STAFF action returns 403.
- Default list is ACTIVE and LOCKED; stable sort `id DESC` with bounded `page_size <=100`, parameterized search and no N+1. Use explicit allowlisted fields: `id,email_normalized,full_name,status,created_at,updated_at`; never return `password_hash`, refresh/session tokens or internal notes.
- Profile only changes `full_name`: normalize whitespace with existing `normalize_full_name`, permit `null` to clear, reject blank string and unexpected fields. Do not change email, role, status, admin_slot through profile. Expose profile to ADMIN too because the shared Header already offers the interaction to both roles.
- Required error tests: unauthenticated 401; STAFF on admin endpoint 403; invalid account lifecycle 409; unrecognized account 404; invalid payload 422; wrong old password safe 400/422 per frozen error envelope; optionally rate-limit credential attempts.
- Define audit evidence of lock/unlock (actor ID, target ID, action, timestamp) with an explicit persistent design that does not create an unnecessary generic audit subsystem. Must not log password or token secrets.

## Frontend integration

- Keep `/staff` approvals UI. Add a clearly separated `Tài khoản nhân viên` tab/view backed by real `/admin/staff`; the existing APPROVED approvals tab is not a reliable listing of currently ACTIVE accounts.
- Reuse `Header.jsx` profile and change-password modals; do not recreate a new shell/theme. The current ResetPassword component is Mock-only for both token reset/change, so make real change-password a separate authenticated form/service from public one-time token reset, preserving current mock isolation.
- Keep `normalizeBackendUser` fail-closed and add the LOCKED server status to parser without mapping it to APPROVED. On revoked session/401 clear memory token, invalidate generation and prevent refresh/replay loops. Mutation requests never silently replay. Do not show STAFF the admin account-management controls.
- UX: Vietnamese text, Quiet Utility Green, explicit loading/empty/error, confirmation for lock, preserve typed API validation and no mock fallback on errors.

## Verification / quality gate

- **Real MySQL 8/InnoDB**: clean linear Alembic migration; constraint rejects illegal role/status; transaction atomic lock+revoke; concurrent lock/login, lock/refresh, lock/unlock, password-change/refresh, reset/change; revoked access JWT and refresh tokens fail on next request; unlock does not revive sessions; no writes on 403/409.
- HTTP + contract: RBAC, field allowlists, own-profile ID source, validation, password reuse/wrong-old, preserving current session and revoking others, cookie/CSRF/Origin when mutation rotates refresh credential.
- FE: real API integration and route guard; session invalidation across tabs/requests; profile modal and change password modal behavior; status LOCKED does not map to approved or rejected.
- Full regressions on login, logout, refresh, registration, approval, rejected reapply, forgot/reset. Backend Ruff/unit/MySQL, Frontend lint/test/build, CI checks on PR to `develop`.
- No merge until migration backup/rollback plan and concurrency evidence are verified. No source-code changes should be interpreted as Product Owner approval of this Bonus addendum.

## Delivery sequence

1. Freeze exact payloads and session-rotation semantics in contracts/OpenAPI, and approve this scope change.
2. Migrate status/check constraint; add ADMIN list/lock/unlock and self-profile/password services with consistent transactions and security tests.
3. Integrate React existing modals and add ACTIVE/LOCKED Staff account tab.
4. Full MySQL concurrency/HTTP/FE E2E and CI; independent PR review and merge to `develop`.
