# T04AA50 — MySQL Regression Testing Report (Sprint 2–3)

- **Task ID**: `T04AA50`
- **Ngày thực hiện**: `2026-11-23`
- **Branch**: `feature/t04aa50-mysql-regression`
- **Base Commit (`origin/develop`)**: `3e0d3c08073c1f703d72f8625e2db9cde8884129`
- **Database Target**: **Real MySQL 8.4 / InnoDB** (via isolated `compose.yaml` + `compose.ci.yaml` in GitHub Actions `Backend / MySQL integration` & `Backend / RabbitMQ protocol and ACL`; **ZERO SQLite replacement**).

---

## 1. Audit Coverage Matrix (Sprint 2–3 MySQL Regression)

| Module | P0 Scenario | Existing MySQL Tests | Gap Identified | Action Taken (`T04AA50`) |
|---|---|---|---|---|
| **Receipt** | Confirm + stock increase, duplicate confirm, concurrent confirm, rollback mid-tx, stale version, inactive supplier/product | `test_purchase_receipts_mysql.py`, `test_receipt_confirmation_mysql.py`, `test_t04aabc_purchasing_email_mysql.py` | Covered at MySQL level; added unauthorized HTTP mutation check | Verified via CI + Auth boundary test |
| **Checkout** | Valid decrement, oversell race, same-key concurrent idempotency, price changed, rollback after flush | `test_checkout_mysql.py`, `test_auth_checkout_cancel_mysql.py` | Multi-item checkout refusal (item 1 sufficient, item 2 insufficient) + mid-tx rollback + retry exact same `Idempotency-Key` | Added `test_t04aa50_multi_item_checkout_atomicity_rollback_and_retry_same_key_mysql` |
| **Cancel** | Valid restore, duplicate replay, concurrent cancel, rollback on restore failure, RBAC 15m window | `test_checkout_mysql.py`, `test_auth_checkout_cancel_mysql.py`, `test_inventory_movements_mysql.py` | Covered at MySQL level | Verified via CI |
| **Inventory** | Non-negative stock, concurrent decreases, multi-item lock ordering, stale adjustment 409, no-op audit-only | `test_inventory_mysql.py`, `test_inventory_adjustment_api.py`, `test_inventory_integration.py`, `test_inventory_movements_mysql.py` | **Race 5**: Concurrent `Inventory Adjustment` vs `Checkout` on the exact same SKU | Added `test_t04aa50_race5_concurrent_adjustment_and_checkout_same_sku_mysql` |
| **Auth** | Active login, refresh rotation/replay, logout revocation, CSRF, single-admin constraint | `test_auth_flows.py`, `test_auth_models.py`, `test_staff_approval.py`, `test_auth_checkout_cancel_mysql.py` | Cross-endpoint unauthorized (`401`/`403`) DB-unchanged proof on Receipt/Inventory/Checkout | Added `test_t04aa50_auth_boundary_mutations_leave_mysql_unchanged` |
| **Email / Outbox Boundary** | Outbox durability, delivery budget, stuck detection, RabbitMQ retry/parking/replay | `test_outbox_delivery_mysql.py`, `test_outbox_rabbitmq.py`, `test_t04aabc_purchasing_email_mysql.py` | Mid-tx rollback leaving 0 phantom `OutboxEvent` + broker outage keeping committed user & durable event without secret leak | Added `test_t04aa50_email_outbox_rollback_and_broker_failure_isolation_mysql` |
| **AI Boundary** | Read-only services on MySQL | `test_tool_executor_mysql.py` (1 test only), `test_ai_query_mysql_redis_e2e.py` | Real MySQL 8 STAFF/PENDING/forged `ToolContext` denial (`403`) + adversarial write/SQL tools (`422`) + MySQL unchanged proof | Added `test_t04aa50_ai_boundary_rbac_and_write_tool_denial_mysql` |

---

## 2. Reproducible Test Commands (Real MySQL 8)

### Full MySQL Regression Suite (exact CI command)
```bash
cd backend
uv run --locked pytest -m "integration and not redis_integration and not proxy_integration"
```

### Targeted `T04AA50` P0 Gap Suite (Race 5, Rollback, Idempotency Retry, Outbox/AI/Auth Boundaries)
```bash
cd backend
uv run --locked pytest -vv tests/integration/test_t04aa50_mysql_p0_regression.py
```

### By Module (Real MySQL 8)
- **Receipt**: `uv run --locked pytest -vv tests/integration/test_purchase_receipts_mysql.py tests/modules/purchasing/test_receipt_confirmation_mysql.py tests/modules/purchasing/test_t04aabc_purchasing_email_mysql.py`
- **Checkout & Cancel**: `uv run --locked pytest -vv tests/modules/sales/test_checkout_mysql.py tests/integration/test_auth_checkout_cancel_mysql.py`
- **Inventory**: `uv run --locked pytest -vv tests/modules/inventory/test_inventory_mysql.py tests/modules/inventory/test_inventory_adjustment_api.py tests/integration/test_inventory_integration.py tests/integration/test_inventory_movements_mysql.py`
- **Auth**: `uv run --locked pytest -vv tests/integration/test_auth_flows.py tests/integration/test_auth_models.py tests/integration/test_staff_approval.py tests/integration/test_staff_registration.py`
- **Email / Outbox**: `uv run --locked pytest -vv tests/integration/test_outbox_delivery_mysql.py` (+ `-m rabbitmq_integration tests/integration/test_outbox_rabbitmq.py`)
- **AI Boundary**: `uv run --locked pytest -vv tests/modules/ai/test_tool_executor_mysql.py tests/integration/test_t04aa50_mysql_p0_regression.py -k ai_boundary`
- **Idempotency**: `uv run --locked pytest -vv tests/integration/test_idempotency.py`

---

## 3. Execution Evidence (CI Real MySQL 8.4 + Local Verification)

- **Local Lint & Collection**:
  - `uv run --locked ruff format --check .` & `uv run --locked ruff check .`
  - `uv run --locked pytest --collect-only tests/integration/test_t04aa50_mysql_p0_regression.py` (`5 tests collected`)
  - Local Docker Desktop daemon is stopped on developer workstation; therefore **real MySQL 8.4 execution evidence is verified directly via GitHub Actions CI (`Backend / MySQL integration`, `Backend / RabbitMQ protocol and ACL`, `Backend / Ruff + unit`)** on the `T04AA50` Pull Request.
- **CI Verification**: Recorded in the PR checks upon push (all 196 MySQL integration tests including all 5 new `T04AA50` tests run against isolated `mysql:8.4` in Docker Compose).
- **Defects Found**: None (0 production defects discovered).
