# T04AAA2 performance harness

This harness measures the five DEC-14 API groups through the real HTTP boundary.
It preserves authentication, backend RBAC, validation, rate limiting, idempotency,
and transaction behavior. Only responses explicitly listed in
`expected_statuses` contribute to P50/P95/P99; 401, 403, 409, 429, 5xx, setup
failures, and other responses are reported separately and make the scenario fail.

## Safety prerequisites

1. Use a dedicated `retailops_test` schema and Docker project/volumes. Never aim
   write scenarios at production or a shared demo database.
   Configure `RETAILOPS_ENVIRONMENT=test`, a unique
   `RETAILOPS_BENCHMARK_ATTESTATION_SECRET` (at least 32 random bytes), and
   `RETAILOPS_BENCHMARK_ISOLATED_DATABASE` in that stack. Export the same secret
   only in the benchmark runner process. The server signs a fresh challenge only
   after its actual `SELECT DATABASE()` value matches the configured isolated DB.
2. Copy `workloads.example.json`, verify actual product/supplier IDs and prices,
   and ensure enough inventory for both concurrency runs.
3. Obtain synthetic ACTIVE Staff and Admin access tokens through the real login
   flow. Keep them only in process environment variables; never commit them.
4. Run the 10-user workload on a fresh fixture, restore a fresh fixture, then run
   the 20-user workload. Running both sequentially against the same fixture changes
   stock and analytics inputs.
5. After each write run, execute the MySQL checkout, receipt, inventory, and
   idempotency integration suites to verify non-negative stock, single effects,
   movements, and rollback behavior.

## Command

From `backend/`, after starting the isolated Compose stack and exporting tokens:

```powershell
$env:RETAILOPS_BENCHMARK_STAFF_TOKEN = '<synthetic staff access token>'
$env:RETAILOPS_BENCHMARK_ADMIN_TOKEN = '<synthetic admin access token>'
$env:RETAILOPS_BENCHMARK_ATTESTATION_SECRET = '<test-stack-only secret>'
uv run python -m performance.benchmark `
  --config performance/workloads.local.json `
  --base-url http://127.0.0.1:8080 `
  --concurrency 10 `
  --samples 100 `
  --trial-id c10-trial-1 `
  --environment-label local-isolated-c10 `
  --output ../artifacts/T04AAA2-c10.json `
  --isolated-test-data
```

Repeat from a restored fixture with `--concurrency 20`. The safety acknowledgement
is mandatory. Non-loopback test environments additionally require
`--allow-remote-test-target`; that flag does not authorize production use.

The JSON output records UTC time, exact Git SHA, host/platform/Python details,
dataset description, concurrency, request counts, P50/P95/P99, throughput, error
rate, status distribution, target, and verdict. `server_p95_ms` is populated only
when the server emits `Server-Timing-Ms`; otherwise client latency remains the
authoritative measurement and the field is `null`.

The workload file defaults to 20 measured requests per scenario; `--samples`
overrides that count without changing concurrency. Receipt drafts are prepared
outside the timed interval, one per confirmation, and extracted IDs/versions are
then used by the timed request. Every checkout and confirm uses a unique
`Idempotency-Key`. Read and write warm-up requests (including write fixture setup)
run before the timed interval. Each invocation records one independent trial;
never combine trials to calculate a more favorable percentile.

## Validation commands

```powershell
uv run ruff check performance tests/performance/test_benchmark.py
uv run pytest tests/performance/test_benchmark.py tests/test_rate_limit.py -q
uv run pytest tests/modules/sales/test_checkout_mysql.py `
  tests/modules/purchasing/test_receipt_confirmation_mysql.py `
  tests/integration/test_idempotency.py -q
git diff --check
```

Benchmark JSON may contain environment details. Review and sanitize it before
sharing; it never records bearer tokens or request authorization headers.
