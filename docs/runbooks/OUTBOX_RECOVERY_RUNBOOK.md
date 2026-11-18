# Outbox Controlled Recovery Runbook (`T04AA00`)

## 1. Automatic Behavior (`outbox-publisher`)

- `outbox-publisher` catches transient `SQLAlchemyError` with bounded exponential backoff (up to `60s`) and sanitized logging.
- `OutboxStuckDetector` runs periodically (`RETAILOPS_OUTBOX_RECONCILE_INTERVAL_SECONDS`, default `60s`) in **read-only / detect-only** mode for events where:
  - `outcome IS NULL`
  - `published_at IS NOT NULL`
  - `published_at <= now - RETAILOPS_OUTBOX_STUCK_AFTER_SECONDS` (default `900s`)
  - `event_type IN ('STAFF_REGISTERED', 'STAFF_APPROVED', 'STAFF_REJECTED')`

## 2. Controlled Operator Replay Procedure

1. **Inspect stuck candidates (read-only):**
   ```bash
   python -m app.worker.reconcile_outbox --detect-only
   ```
2. **Quiesce all publisher and worker instances:**
   Stop every `outbox-publisher` and `email-worker` instance (not just a single container if multiple hosts exist).
3. **Dry-run eligibility check (default):**
   ```bash
   python -m app.worker.reconcile_outbox --event-id <canonical-uuid>
   ```
   - Verifies via RabbitMQ AMQP `queue_declare(passive=True)` (using `RABBITMQ_BOOTSTRAP_USER` / `RABBITMQ_BOOTSTRAP_PASSWORD`) that `consumer_count == 0` and `message_count == 0` on `retailops.email.v1`.
   - Returns `REPLAY_NOT_VERIFIABLE` if any consumer or message remains or the broker is unreachable.
4. **Execute controlled replay (single event):**
   ```bash
   python -m app.worker.reconcile_outbox --event-id <canonical-uuid> --reason "<ticket-or-reason>" --execute
   ```
   - Locks the row with `SELECT ... FOR UPDATE`, preserves `delivery_attempts` and `publish_attempts`, rejects terminal outcomes (`SENT`/`FAILED`/`SKIPPED`), disabled secret events, or exhausted budget (`delivery_attempts >= 4`).
   - Note: Controlled replay guarantees RabbitMQ/Celery is no longer processing the event, **not** that an earlier crashed attempt never reached SMTP (at-least-once semantics).
5. **Resume runtime:**
   Start `outbox-publisher` and `email-worker`.
