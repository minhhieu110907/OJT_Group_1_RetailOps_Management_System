# T04AAA2 — Performance Benchmark & Security Verification

## Baseline and verification identity

- Task/contract: `T04AAA2` / `PERF,GATE-E2E`.
- Baseline: `origin/develop` at `0c03128165f90b8a404a76c19bf5bc076330744b`.
- Benchmarked implementation: `77dec141c7838cd877bed1d8ca805d20c352c374`.
- Branch: `feature/T04AAA2-performance-security-verification`.
- AI HTTP query was not present when the benchmark was executed. PR #86 merged
  afterward and was merged into this branch as `4dcc1c3`; no unmerged AI code was
  copied into the benchmark baseline.

The final documentation commit is separate from the implementation commit above.
It changes this report only; runtime and benchmark code are identical to the
benchmarked implementation.

## Contract and document conflict

DEC-14/SRS targets are Product/Category/Inventory P95 <=300 ms, Checkout and
Receipt Confirm P95 <=800 ms, Dashboard P95 <=1500 ms, at 10–20 concurrent users.

The business-context summary says Registration is `3/hour/IP`, while approved SRS
INF-02 records `5/60 seconds/IP` as the later PO/Tech Lead decision. Registration
was not changed. Forgot Password is consistently `3/hour/IP` and `3/hour/email`;
its previous defaults did not satisfy that contract and were corrected.

## Environment and workload

- Host: Windows 11 Pro `10.0.26200`, Intel Core i7-12700H (14 cores / 20 logical
  processors), 15.69 GiB physical RAM.
- Docker Desktop: Engine `29.7.2`, Compose `v5.4.0`, WSL2 kernel
  `6.18.33.2`, 20 CPUs, 7.60 GiB Docker memory.
- Stack: Nginx -> Uvicorn/FastAPI -> MySQL 8.4/InnoDB + Redis 8.4.
- Client: Python 3.14.2 + HTTPX on the same host through Nginx loopback.
  Application/test verification used Python 3.12.16.
- Separate c10/c20 projects and volumes: `t04aaa2verify_mysql_data` and
  `t04aaa2c20_mysql_data`. Existing Docker environments were not modified.
- Each project had one ACTIVE product at 1000 units / 10,000 VND, five categories,
  one active supplier, and synthetic ACTIVE Admin/Staff users.
- Each scenario used 20 measured requests. GET scenarios had three untimed warm-up
  requests. Receipt drafts were prepared outside timing. Checkout/confirm used
  unique Idempotency-Keys.
- Authentication, RBAC, validation, Redis limits, Nginx proxying, and business
  transactions remained enabled.

## Independent harness audit

| Check | Evidence/result |
|---|---|
| Real concurrency | Semaphore plus `requests >= concurrency` guard; c10/c20 launched 20 measured tasks per scenario |
| Warm-up excluded | GET warm-up and write fixture setup execute before measurement |
| Percentiles | Nearest-rank P50/P95/P99, unit tested with 1..100 samples |
| Shared state | Per-request context and key; no mutable request context shared between tasks |
| Fresh fixture | Write runs reject multiple concurrency levels; c10/c20 used separate volumes |
| Classification | Success, 401, 403, 409, 429, 5xx, unexpected HTTP, setup failure |
| Error latency | Only expected success enters percentiles; any error fails the scenario |
| Windows config | UTF-8 BOM workload files accepted and regression tested |
| Authorization | Real Admin/Staff login; no dependency override, CSRF disable, or RBAC bypass |

## Performance results — exact implementation SHA

Every row had 20/20 expected responses and zero errors. `server_p95_ms` is null
because the application does not emit server timing; values are end-to-end client
latency through Nginx.

| Workload | Users | P50 ms | P95 ms | P99 ms | RPS | Target | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Product list | 10 | 62.599 | 213.573 | 216.544 | 85.510 | 300 | PASS |
| Category list | 10 | 48.420 | 83.724 | 84.970 | 157.420 | 300 | PASS |
| Inventory list | 10 | 54.856 | 89.915 | 112.224 | 146.184 | 300 | PASS |
| Checkout | 10 | 269.936 | 315.954 | 324.958 | 33.402 | 800 | PASS |
| Receipt Confirm | 10 | 223.658 | 284.849 | 334.976 | 38.380 | 800 | PASS |
| Dashboard | 10 | 63.288 | 102.300 | 113.701 | 125.296 | 1500 | PASS |
| Product list | 20 | 326.060 | **353.410** | 355.083 | 55.435 | 300 | **FAIL** |
| Category list | 20 | 95.551 | 117.139 | 121.286 | 158.079 | 300 | PASS |
| Inventory list | 20 | 98.950 | 118.696 | 120.905 | 157.574 | 300 | PASS |
| Checkout | 20 | 253.908 | 449.168 | 478.515 | 41.374 | 800 | PASS |
| Receipt Confirm | 20 | 260.017 | 422.902 | 432.304 | 45.442 | 800 | PASS |
| Dashboard | 20 | 118.318 | 150.688 | 150.917 | 125.908 | 1500 | PASS |

### Product c20 finding

Product c20 missed the target by 53.410 ms. A pre-commit c20 run measured
112.161 ms P95, demonstrating host-run variance; the exact-SHA result above is
retained rather than selecting the faster run. The database contained one product.
EXPLAIN showed an indexed count and one joined page query, with no N+1 behavior.
Resource evidence did not establish a production-code bottleneck, so no speculative
optimization or threshold/workload change was made. Recommended follow-up: three
controlled exact-SHA trials on a quiet host, retaining every result, with server
timing/query metrics.

## Post-load business invariants

After the exact-SHA runs, both databases reported:

- minimum quantity `1000`; benchmark product final quantity `1000`;
- `stock_version=81` (initial adjustment plus two sets of 20 checkout and 20
  confirm mutations);
- 40 Orders, 40 Receipts, and 81 stock movements;
- c10 had 81/81 completed idempotency records; c20 had 80/80 after the MySQL
  integration fixture cleanup removed the earlier adjustment key between runs;
- zero orphan stock movements.

MySQL concurrency/rollback suites subsequently passed 50 tests, covering last-unit
checkout, duplicate keys, confirm races, password-reset races, session revocation,
rollback, lock timeout, and idempotency collisions.

## Security finding and remediation

### Medium — Forgot Password defaults exceeded the approved quota

- Condition: defaults permitted 5/minute per IP and 5/hour per email rather than
  3/hour for each independent identity.
- Impact: reduced resistance to reset-token/outbox and account-targeted abuse.
- Remediation: defaults, Compose, and `.env.example` now use `3/3600s` for both
  source IP and normalized email.
- Evidence: the first three calls pass, the fourth is blocked, and IP/email use
  independent Redis policy keys.

No Critical/High finding or new security failure was observed.

### Low — PR #86 SQLite orchestrator tests depend on collection order

Running `test_gemini_orchestrator.py` alone produced four SQLite `TINYINT`
compiler failures. The full CI-shaped unit suite passed because another test module
registers the compiler first. This is a test-isolation defect, not a runtime MySQL
authorization failure. AI HTTP E2E passed against real MySQL/Redis with a controlled
provider. Remediation should move SQLite compiler registration into a local fixture
or shared `conftest.py`; it is not required to change production code in T04AAA2.

## Executed verification

| Verification | Result |
|---|---|
| Ruff check + format (Python 3.12.16) | PASS — 234 files |
| Full unit/API after PR #86 merge, excluding integration | PASS — 672 passed, 90 deselected; two pre-existing pytest warnings |
| Scoped auth/CSRF/RBAC/revocation/idempotency/error suite | PASS — 134 passed |
| Harness + rate-limit final regression | PASS — 27 passed |
| MySQL integration/concurrency/rollback | PASS — 50 passed |
| Redis fixed-window integration | PASS — 4 passed |
| Real Nginx trusted-proxy/IP-spoofing integration | PASS — 1 passed |
| AI HTTP MySQL/Redis E2E with controlled provider | PASS — 2 passed; not real Gemini latency |
| c10 benchmark | PASS — 120/120 successful, zero errors |
| c20 benchmark | FAIL — Product P95 353.410 ms; other 100/100 successful |
| `git diff --check` | PASS |

RabbitMQ/Mailpit tests were not required for measured endpoints and were not run.
An initial broad `-m "not integration"` invocation exposed missing integration
markers on some RabbitMQ tests; missing-broker failures from that invalid command
are not treated as product failures. The correctly scoped results above are
authoritative.

## Acceptance status

- **IMPLEMENTATION COMPLETE: YES** — harness, guards, docs, and quota correction
  are implemented and tested.
- **REAL BENCHMARK VERIFIED: YES** — c10/c20 ran through real isolated
  Nginx/FastAPI/MySQL/Redis at the exact implementation SHA.
- **SECURITY VERIFIED: YES** — required security and concurrency regressions pass.
- **RELEASE GATE READY: NO** — Product c20 P95 exceeded DEC-14. Security and
  Business Invariants are PASS; Performance is FAIL pending controlled rerun or
  evidence-based remediation.

Overall T04AAA2 verdict: **PARTIAL / NOT ACCEPTED FOR RELEASE GATE**.

---

## Corrective pass for PR #88 (2026-11-19)

This section preserves every historical result above and records the independent
corrective verification. Runtime/harness implementation SHA:
`834ff4e739be32b12383b07a0784e8025017de01`. The later report commit does not
change the benchmarked application or harness.

### P1 target-isolation remediation

Write workloads now fail before fixture preparation, warm-up, or measured requests
unless the target returns a valid HMAC-SHA256 challenge response. The server emits
that response on the existing health route only when all conditions hold:

- both attestation settings are present, the secret is at least 32 bytes and is not
  a placeholder, and `RETAILOPS_ENVIRONMENT` is exactly `test`;
- the server queries `SELECT DATABASE()` through its real SQLAlchemy session and
  the result equals its server-side isolated-database allowlist;
- the signature binds protocol version, a fresh 256-bit client nonce, and a digest
  of the actual database identity; comparison is constant-time;
- neither database name, credentials, secret, bearer token, nor authorization
  headers are written to the benchmark JSON.

Production cannot enable the feature accidentally: partial configuration or any
environment other than `test` fails Settings validation. Missing headers, malformed
proofs, wrong secrets, unexpected databases, and unsigned targets fail closed.
Authentication, CSRF, RBAC, rate limits, and business authorization remain enabled.
The proof is replay-resistant for another run because every run uses a fresh nonce;
its context is restricted to protocol `v1` and the verified database identity.
The operational requirement remains that every isolated stack use a distinct secret.

Unit coverage includes wrong environment, missing paired metadata, mismatched actual
database, missing/malformed/wrong signatures, challenge-bound valid proof, sample
validation, error classification, and nearest-rank percentiles.

### Statistical-quality remediation

- `--samples` is configurable independently of `--concurrency`; validation rejects
  sample counts below concurrency.
- GET and write warm-ups execute before the timed interval. Write warm-up fixtures
  are created outside measurement and use unique request/idempotency identifiers.
- metadata records exact Git SHA, trial ID, environment label, sample override,
  concurrency levels, dataset, platform, and attestation status.
- every output file is one trial. No cross-trial percentile aggregation is used.
- 401/403/409/429/5xx/unexpected/setup failures remain outside success percentiles,
  remain visible in classification, and force FAIL.

### Controlled Product Read trials at exact SHA

Workload: 10 untimed warm-ups followed by 100 measured Product list requests per
trial through Nginx, using real authentication, Redis policy, Uvicorn, MySQL, and
the one-product historical isolated dataset. c10 and c20 used their existing
separate projects/volumes and ran alternately so the two T04AAA2 stacks did not
compete. No Redis keys were deleted and the 120/minute business policy was not
raised. Trials were spaced across natural fixed-window expiry.

| Trial | Concurrent users | Samples | P50 ms | P95 ms | P99 ms | Throughput req/s | Error rate | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| exact-c10-1 | 10 | 100 | 51.896 | 87.937 | 94.735 | 167.097 | 0.000 | PASS |
| exact-c10-2 | 10 | 100 | 48.004 | 81.118 | 87.427 | 188.173 | 0.000 | PASS |
| exact-c10-3 | 10 | 100 | 45.255 | 72.981 | 80.954 | 198.989 | 0.000 | PASS |
| exact-c20-1 | 20 | 100 | 94.920 | 140.120 | 147.502 | 197.526 | 0.000 | PASS |
| exact-c20-2 | 20 | 100 | 105.596 | 197.731 | 212.662 | 165.779 | 0.000 | PASS |
| exact-c20-3 | 20 | 100 | 183.199 | 261.287 | 307.131 | 101.265 | 0.000 | PASS |

All six exact-SHA trials are retained under
`backend/performance/results/834ff4e/`. Pre-commit diagnostic trials are also
retained. One diagnostic c20 trial returned 100/100 HTTP 429 after a preceding
trial consumed the real fixed-window quota; it remains a FAIL with null latency
percentiles and demonstrates correct error classification. It was not counted as
one of the three stable-window acceptance trials and was not deleted or rewritten.

### Product profiling and root-cause assessment

The Product path performs an indexed count and one joined paginated query; there
is no N+1. On the one-row dataset, MySQL `EXPLAIN ANALYZE` measured approximately
1.52 ms for count and 2.08 ms for the joined page query. The inventory lookup used
its primary key. In-process `ProductService.list_products` profiling over 100 calls
measured P50 0.948 ms, P95 1.684 ms, P99 2.160 ms; Pydantic JSON serialization over
1,000 calls measured P95 0.002 ms. The SQLAlchemy pool is size 5 plus overflow 5.

The original c20 P95 353.410 ms remains valid historical evidence. At that time
both T04AAA2 stacks were running concurrently, alongside several unrelated Docker
stacks; the snapshot showed multiple MySQL containers and a 7.60 GiB Docker memory
limit. After alternating the two task stacks, all three c20 P95 values were below
300 ms, though trial 3 still showed P99 307.131 ms and materially lower throughput.

Evidence therefore does **not** support a Product SQL, pagination, index, DTO, or
serialization bottleneck on this dataset. Host/Docker scheduling and run-to-run
contention are the best-supported explanation for the original outlier, but this is
a medium-confidence environmental attribution rather than a fully instrumented
causal proof: the application does not emit server timing and continuous per-request
CPU/event-loop/pool-wait traces were not collected. No production Product code,
DEC-14 threshold, or workload was changed.

### Corrective security and regression verification

| Verification | Corrective result |
|---|---|
| Ruff check / format | PASS — 241 files |
| Harness, target-safety, Forgot Password, Auth/CSRF/RBAC/Product API scoped suite | PASS — 85 tests |
| Full non-integration unit/API suite with frozen contracts mounted read-only | PASS — 687 passed, 204 deselected, two pre-existing return-value warnings |
| Redis fixed-window integration | PASS — 4 tests |
| MySQL checkout/receipt/password-reset concurrency and rollback | PASS — 34 tests |
| Trusted proxy/IP-spoofing rerun | NOT RUN TO COMPLETION — two runner attempts failed before test execution because the Docker-internal runner could not expose the MySQL connection as fail-closed localhost while also reaching Nginx/Redis. Historical real-Nginx result above remains PASS; proxy/auth code was not modified by this corrective pass. |
| MySQL auth-flow aggregate invocation | NOT AUTHORITATIVE — shared benchmark schema contained historical sessions and one test assumes no unrelated sessions. Data was preserved rather than deleted to manufacture PASS. Token/session regression remains covered by the passing unit/API suite and the historical MySQL result. |

Invalid setup invocations (disallowed internal DB hostname, missing idempotency
secret, missing repository-root contract mount) are not reported as product
failures. Each was corrected or explicitly classified above; no database, Redis
state, container volume, or historical result was reset/deleted.

### Corrective verdict

- **IMPLEMENTATION COMPLETE: YES** — P1 target attestation and P2 statistical
  controls are implemented and unit-tested.
- **REAL BENCHMARK VERIFIED: YES** — three independent 100-sample trials at both
  c10 and c20 ran on exact implementation SHA `834ff4e`.
- **SECURITY VERIFIED: YES WITH LIMITATION** — attestation, rate-limit, Auth/CSRF/
  RBAC, Redis, and MySQL write-path regressions pass; trusted-proxy rerun was blocked
  by test-runner topology, with unchanged historical PASS evidence retained.
- **RELEASE GATE READY: YES FOR DEC-14 PRODUCT CORRECTIVE EVIDENCE** — all three
  controlled c20 trials satisfy Product P95 <=300 ms. Historical 353.410 ms FAIL
  remains visible and the environmental limitation is documented.

Recommendation: **MERGE only if PR CI is green on the final documentation HEAD**.
The corrective findings do not justify a production Product optimization. Continue
monitoring Product P95 on a quiet, release-like host with server/pool timing before
attributing future regressions to application code.
