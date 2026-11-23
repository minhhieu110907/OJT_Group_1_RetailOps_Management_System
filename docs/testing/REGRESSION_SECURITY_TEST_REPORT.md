# Real Integration, Regression & Security Test Report (Inventory / Receipt / Order / Worker / AI)

## A. Test Environment

- **Base Commit SHA**: `340862dde9b10b209ae357fb4b1994038503ced6` (`origin/develop`)
- **Branch**: `test/inventory-receipt-order-worker-ai-security`
- **Python / Pytest**: Python `3.12.14`, `pytest 8.4.2`, `anyio 4.16.0`, `uv` locked environment
- **Docker Compose Project**: `compose.yaml` + `compose.ci.yaml` (Docker Compose `v5.6.1`)
- **Local Infrastructure Status**:
  - **Unit / API / Security / Service suites**: Executed locally (**PASS**).
  - **MySQL 8 / Redis / RabbitMQ / Celery Worker / Mailpit**: **BLOCKED locally** because Docker Desktop daemon is stopped (`//./pipe/dockerDesktopLinuxEngine` unavailable). Real integration suites are wired to run in GitHub Actions CI (`Backend / MySQL integration` and `Backend / RabbitMQ protocol and ACL`) as soon as this branch is pushed / PR opened, or locally once Docker Desktop is started.
- **AI Provider Mode**: Adversarial / deterministic test `LLMProvider` (verifying backend-enforced authorization, allowlist, schema validation, read-only DB invariants, and limit caps without relying on LLM refusal).
- **Re-run Commands**:
  - Local non-integration + AI security suite:
    ```powershell
    Set-Location backend
    uv run --locked pytest -vv tests/modules/ai/test_ai_security_regression.py
    uv run --locked pytest -q -m "not integration and not rabbitmq_integration"
    ```
  - Real MySQL 8 integration & concurrency suite (requires Docker / MySQL 8):
    ```powershell
    Set-Location backend
    uv run --locked pytest -vv tests/integration/test_cross_module_invariants_mysql.py `
      tests/modules/inventory/test_inventory_mysql.py `
      tests/integration/test_purchase_receipts_mysql.py `
      tests/modules/purchasing/test_receipt_confirmation_mysql.py `
      tests/modules/sales/test_checkout_mysql.py `
      tests/integration/test_auth_checkout_cancel_mysql.py
    ```
  - Real RabbitMQ / Celery Worker / Mailpit suite (requires Docker / RabbitMQ / Mailpit):
    ```powershell
    Set-Location backend
    uv run --locked pytest -vv -m rabbitmq_integration tests/integration/test_outbox_rabbitmq.py
    ```

---

## B. Test Results Matrix

| Module | Scenario | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| Inventory | Service & API unit/contract (adjustments, stale version 409, no-op audit-only, STAFF 403, lock order, overflow) | Enforce invariants, non-negative stock, version guard | All non-integration inventory tests passed locally | **PASS (Unit/API)** | [PYTEST_EXECUTION_EVIDENCE.md](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/docs/testing/evidence/REGRESSION_SECURITY/PYTEST_EXECUTION_EVIDENCE.md) |
| Inventory | Real MySQL 8 concurrent decrease, multi-item lock order, API↔DB consistency | No negative stock, no deadlock, no lost update | Suite added & collected (`test_cross_module_invariants_mysql.py` + `test_inventory_mysql.py`); local Docker daemon stopped | **BLOCKED (Local) / CI-Ready** | [test_cross_module_invariants_mysql.py](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/backend/tests/integration/test_cross_module_invariants_mysql.py) |
| Receipt | Draft merge/cost-conflict/version/RBAC + confirm unit tests | Atomic draft/confirm, no duplicate stock increase | All non-integration purchasing tests passed locally | **PASS (Unit/API)** | [PYTEST_EXECUTION_EVIDENCE.md](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/docs/testing/evidence/REGRESSION_SECURITY/PYTEST_EXECUTION_EVIDENCE.md) |
| Receipt | Real MySQL 8 multi-item confirm, replay/duplicate confirm, rollback on inactive 2nd item | `CONFIRMED` immutable, replay safe, full rollback on failure | Added & collected in `test_cross_module_invariants_mysql.py`; local Docker daemon stopped | **BLOCKED (Local) / CI-Ready** | [test_cross_module_invariants_mysql.py](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/backend/tests/integration/test_cross_module_invariants_mysql.py) |
| Order | Checkout, price-changed 409, cancel RBAC/15m window, idempotency unit/API tests | Exact totals, single stock deduction/restore | All non-integration sales tests passed locally | **PASS (Unit/API)** | [PYTEST_EXECUTION_EVIDENCE.md](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/docs/testing/evidence/REGRESSION_SECURITY/PYTEST_EXECUTION_EVIDENCE.md) |
| Order | Real MySQL 8 concurrent checkout (`stock=5`, 2×`qty=4` → `[201, 409]`) & concurrent cancel (`[200, 409]`) | Final stock `1` after checkout, `5` after cancel, 1 order, 1 cancel restore | Added & collected in `test_cross_module_invariants_mysql.py`; local Docker daemon stopped | **BLOCKED (Local) / CI-Ready** | [test_cross_module_invariants_mysql.py](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/backend/tests/integration/test_cross_module_invariants_mysql.py) |
| Worker | Outbox runtime & idempotency unit tests | Retry/envelope/budget contracts enforced | Passed in local non-integration suite | **PASS (Unit)** | [PYTEST_EXECUTION_EVIDENCE.md](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/docs/testing/evidence/REGRESSION_SECURITY/PYTEST_EXECUTION_EVIDENCE.md) |
| Worker | Real RabbitMQ + Celery Worker interruption, transient retry, dead-letter parking, duplicate delivery, broker outage & replay | At-least-once delivery + idempotent processing, no duplicate side effects | Covered by `tests/integration/test_outbox_rabbitmq.py` (11 tests); local Docker daemon stopped | **BLOCKED (Local) / CI-Ready** | [test_outbox_rabbitmq.py](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/backend/tests/integration/test_outbox_rabbitmq.py) |
| AI Security | Unauthorized access (no token, bad/expired/revoked JWT, pending user, STAFF 403, extra body fields 422, forged `ToolContext`) | Backend rejects all unauthorized paths; DB unchanged | `test_ai_unauthorized_access_matrix_and_db_unchanged` **PASSED** | **PASS** | [test_ai_security_regression.py](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/backend/tests/modules/ai/test_ai_security_regression.py) |
| AI Security | Prompt injection & adversarial write-tool calls (`increase_stock`, `decrease_stock`, `adjust_inventory`, `create_purchase_receipt`, `checkout_order`, `cancel_order`, `execute_sql`, `update_product_price`) | Backend blocks with `422`; DB snapshot before == after | All 8 parametrized cases + injected args + unknown tool **PASSED** | **PASS** | [test_ai_security_regression.py](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/backend/tests/modules/ai/test_ai_security_regression.py) |
| AI Limits | Tool loop cap, >4000 char / blank input 422, provider timeout 504, rate limit 429, Redis fail-closed 503, output byte budget & deadline | Stops cleanly at caps, fail-closed on Redis outage, zero secret/traceback leak | `test_ai_limits_tool_loop_timeout_rate_limit_and_redis_fail_closed` **PASSED** | **PASS** | [test_ai_security_regression.py](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/backend/tests/modules/ai/test_ai_security_regression.py) |
| Regression | Full backend non-integration suite + `ruff` | Zero regressions, clean formatting/lint | `730 passed, 4 skipped (POSIX bash on Windows), 211 deselected`; `ruff` 249 files clean | **PASS** | [PYTEST_EXECUTION_EVIDENCE.md](file:///c:/Users/Admin/OJT_Group_1_RetailOps_Management_System/docs/testing/evidence/REGRESSION_SECURITY/PYTEST_EXECUTION_EVIDENCE.md) |

---

## C. Data Integrity (Cross-Module Invariant Design & Proof)

Defined and enforced in `tests/integration/test_cross_module_invariants_mysql.py` (`test_cross_module_receipt_inventory_order_cancel_invariants_mysql`):

| Step | Action | Product A (`qty / ver / first_stocked_at`) | Product B (`qty / ver`) | Movement Ledger Proof |
|---|---|---|---|---|
| 0 | Initial state | `0 / v1 / NULL` | `10 / v1` | `0` movements |
| 1 | Receipt DRAFT (`A:+15`, `B:+5`) | `0 / v1 / NULL` (unchanged) | `10 / v1` (unchanged) | `0` movements |
| 2 | Receipt CONFIRM (+ replay same key + repeat new key `409`) | `15 / v2 / SET` | `15 / v2` | `+15` (`PURCHASE_CONFIRM`), `+5` (`PURCHASE_CONFIRM`) |
| 3 | Order CHECKOUT (`A:-4`, `B:-3`) + replay same key | `11 / v3 / SET` | `12 / v3` | `-4` (`SALE`), `-3` (`SALE`) |
| 4 | Adjustment: STAFF (`403`), stale v1 (`409`), no-op `counted=11` v3 (`200`) | `11 / v3 / SET` (`movement_created=False`) | `12 / v3` | No spurious movement, version unchanged |
| 5 | Order CANCEL (+ replay same key + repeat new key `409`) | `15 / v4 / SET` | `15 / v4` | `+4` (`ORDER_CANCEL`), `+3` (`ORDER_CANCEL`) |
| 6 | Final Read-Only SQL Audit | `sum(deltas) = +15 - 4 + 4 = 15 == qty` | `10 + (+5 - 3 + 3) = 15 == qty` | Zero negative stock, zero orphan movements, zero duplicates |

---

## D. Worker Recovery

- Existing real RabbitMQ/Celery/Mailpit coverage in `backend/tests/integration/test_outbox_rabbitmq.py` (11 tests):
  - `test_real_worker_transient_smtp_publishes_routed_retry` (transient SMTP error -> routed retry).
  - `test_real_worker_fourth_transient_attempt_is_terminal` (retry exhaustion -> terminal state).
  - `test_real_worker_invalid_envelope_is_parked` (invalid envelope -> dead-letter parking queue).
  - `test_t04aa00_duplicate_delivery_is_idempotent` (duplicate delivery -> no duplicate business effect; at-least-once + idempotent handling).
  - `test_t04aa00_broker_outage_and_controlled_replay_recovery` (broker outage + controlled replay).
  - `test_password_reset_e2e_api_outbox_rabbitmq_worker_mailpit_and_reset` (full API -> Outbox -> RabbitMQ -> Worker -> Mailpit -> Reset).
- **Local execution status**: **BLOCKED** (Docker Desktop stopped locally); executes automatically in CI job `Backend / RabbitMQ protocol and ACL`.

---

## E. AI Security

- **Identity & RBAC**: Enforced strictly server-side via `authenticate_current_principal` -> `get_current_principal` -> `get_current_active_user` -> `require_active_admin` and per-request `ToolContext` capability verifier (`bind_authenticated_request`).
- **Allowlist**: Only 4 read-only tools permitted (`get_sales_summary`, `get_top_products`, `get_slow_products`, `get_low_stock`). Every disallowed/write tool is blocked at both `AIOrchestrator` (`422`) and `AIToolExecutor` (`DomainValidationError`).
- **Schema & Input Hardening**: `AIQueryRequest` and all tool input DTOs use `extra="forbid"`, strict types, canonical `YYYY-MM-DD` regex, and bounded limits.
- **Database Unchanged Proof**: Every test in `test_ai_security_regression.py` captures `_db_snapshot(session)` before and after (`inventories`, `products`, `users`, `stock_movements`, `purchase_receipts`, `orders`, `order_items`) and asserts exact equality (`after == before`).

---

## F. Bugs Found

| Severity | Bug | Reproduction | Impact | Status |
|---|---|---|---|---|
| Critical | None found in inspected production code paths | — | — | — |
| High | None found in inspected production code paths | — | — | — |
| Low (Pre-existing test hygiene) | `tests/test_products_api.py::test_settings` and `tests/test_purchase_receipts_api.py::test_settings` are named `test_*` while returning `Settings` (triggers `PytestReturnNotNoneWarning`) | Run `pytest -q -m "not integration and not rabbitmq_integration"` | Pytest warning only; no production impact | Open (out of scope) |
