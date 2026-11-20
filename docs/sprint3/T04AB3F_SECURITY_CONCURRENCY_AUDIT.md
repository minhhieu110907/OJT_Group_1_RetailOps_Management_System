# T04AB3F — Independent Security & Concurrency Audit (Phase 1 + Phase 2)

> **Lưu ý lịch sử:** Các mục 1–12 giữ nguyên bằng chứng và kết luận tại thời điểm
> Phase 1 để audit trail không bị xóa. Kết luận Phase 1 về SEC-001 đã bị bác bỏ
> sau khi đối chiếu SRS được phê duyệt. Mục 13 là disposition và Security Gate
> có thẩm quyền sau corrective remediation Phase 2.

## 1. Baseline và phạm vi

- Task LMS: `T04AB3F` — rà soát bảo mật và concurrency.
- Baseline: `c7292c49b4c8b798963e6a6d6decc3da7db1cbfe` (`origin/develop`).
- Baseline là merge commit PR #88: `Merge pull request #88 ... T04AAA2-performance-security-verification`.
- Feature branch: `feature/T04AB3F-security-concurrency-audit`.
- Worktree audit cô lập: `D:\RetailOps.worktrees\attachment-pasted-text-1-1e2f8e80`.
- Workspace gốc có thay đổi chưa commit không bị checkout, stash, reset, clean hoặc ghi đè.
- Phase 1 chỉ đọc/kiểm thử code và tạo báo cáo này; không sửa production code, schema hoặc migration.

Nguồn đối chiếu chính:

- `docs/requirement/RETAILOPS_AGENT_BUSINESS_CONTEXT.md`.
- `docs/requirement/RetailOps_SRS_Approved.md`.
- `docs/database/RetailOps_ERD_V1.0.dbml` và migration Alembic hiện tại.
- API/router/service/repository thực tế tại `backend/app`.
- Test thực tế tại `backend/tests` và CI tại `.github/workflows/backend-ci.yml`.

Phạm vi đã đọc và kiểm chứng: Auth/session/password reset/Bonus Staff Account; RBAC và field-level response; validation/rate limit/CORS/trusted proxy; Docker/Nginx/secrets/benchmark attestation; AI read-only tool boundary; checkout, receipt, inventory, cancellation, idempotency; outbox/publisher/worker/RabbitMQ.

## 2. Xác minh branch và workspace

| Hạng mục | Kết quả |
|---|---|
| `git fetch origin --prune` | Thành công |
| PR #88 trong `develop` | Đã xác minh tại commit `c7292c4` |
| HEAD khi bắt đầu audit | `c7292c49b4c8b798963e6a6d6decc3da7db1cbfe` |
| Nhánh audit | `feature/T04AB3F-security-concurrency-audit` |
| Nguồn nhánh | Chính xác `origin/develop` |
| Worktree trước audit | Sạch |
| Production code/schema/migration thay đổi | Không |
| Commit/push/PR | Không |

## 3. Security coverage matrix

| Nhóm | Implementation/evidence chính | Mức kiểm chứng | Kết luận |
|---|---|---|---|
| Password/JWT | `auth/security.py`; bcrypt cost 12, giới hạn 72 byte; JWT HS256 cố định, issuer/audience/required claims/expiry | Unit + MySQL auth tests | Đạt các invariant đã mô tả; password-strength policy cụ thể chưa được SRS khóa |
| Refresh/session/logout | `auth/service.py`; lock `User -> AuthSession -> RefreshToken`, rotation history, replay revoke session, live DB session check | MySQL: replay, concurrent refresh, logout, lock/session revocation | Đạt |
| Password reset/change | Token ngẫu nhiên, lưu hash; outbox secret AES-GCM; one-time consume; revoke session/reset token | Unit + MySQL; Rabbit e2e một phần | Đạt phần MySQL; worker e2e còn gap môi trường |
| Staff states/Bonus Account | Backend re-check ACTIVE; Admin-only lock/unlock; lock revoke session/reset proof; self-profile lấy actor từ JWT | API/unit/MySQL | Đạt implementation hiện tại |
| CSRF/cookie/origin | Refresh/logout/change-password yêu cầu signed double-submit + exact Origin; refresh HttpOnly, SameSite=Lax, Secure bắt buộc ở production | Unit + API | Đạt |
| Public rate limits | Redis fail-closed cho register/login/refresh/forgot/reset; trusted client IP | Unit + Redis + proxy | **Không đạt registration quota; SEC-001** |
| Business rate limit | 120/phút/user, MySQL auth trước quota; Redis outage fail-open theo quyết định POS nội bộ | Unit + Redis | Đạt contract hiện tại |
| RBAC/BFLA | Mutation master data/purchasing/inventory/analytics/AI Admin-only; checkout/order read/cancel active Admin/Staff | API + MySQL | Không thấy bypass có đường đi thực tế |
| Field-level data | Product/Inventory/Order không có cost; Staff movement dùng schema riêng không có actor/reason; purchasing Admin-only | Code + API tests | Không thấy leak `unit_cost`/internal reason cho Staff |
| Input/API security | Request mutation dùng `extra="forbid"`; enum sort allowlist; page size <=100; SQLAlchemy bound params; sanitized 500/422 | Unit/API/MySQL | Đạt phần đã kiểm chứng |
| CORS/trusted proxy | Exact HTTP(S) origin; wildcard bị cấm; Nginx ghi đè forwarding headers; Uvicorn trust đúng proxy IP | Unit + proxy integration | Đạt |
| Secrets/infrastructure | Services nội bộ; MySQL/backend host-loopback; Rabbit identities tách bootstrap/publisher/worker; app chạy non-root | Static + Compose/Rabbit một phần | Không thấy secret hard-code trong source |
| Benchmark attestation | Secret + isolated DB bắt buộc đi cùng nhau; chỉ `environment=test`; placeholder/short secret bị chặn | Unit/static | Đạt; không benchmark lại |
| AI security | `/ai/query` Admin-only; JWT-derived actor; allowlist 4 tool read-only; schema/key bounds; per-tool Admin re-check; Redis quota/concurrency; deadline/output budget | Unit + MySQL/Redis e2e | Đạt phần đã kiểm chứng |

## 4. Concurrency và transaction matrix

| Luồng | Lock/version/idempotency/transaction | Evidence thực chạy | Kết luận |
|---|---|---|---|
| Checkout | Idempotency claim trước mutation; Product ASC -> Inventory ASC `FOR UPDATE`; price/active/stock re-check; order + items + stock + movement + response cùng commit | Single last-unit competition, same/different key concurrency, price refusal zero writes, rollback after order flush | Không oversell/stock âm trong test; lock-timeout API mapping còn lỗi SEC-002 |
| Receipt | Receipt `FOR UPDATE`, `expected_draft_version`, supplier/product active re-check, ordered stock lock; terminal immutable; idempotent confirm | Concurrent confirm single winner, stale, inactive master, rollback | Đạt |
| Inventory adjustment | `expected_stock_version` bắt buộc; Product/Inventory ordered locks; stale trước no-op; no-op audit không movement/version increment | MySQL concurrent decrease, reversed multi-item order, rollback, no-op/idempotency | Đạt |
| Order cancellation | Idempotency + Order header `FOR UPDATE`; ownership/time/VN business day; restore stock/movement cùng transaction | Replay once, concurrent different keys, rollback, 15-minute/day boundary | Đạt ngoại trừ lock-timeout API mapping dùng shared SEC-002 |
| Idempotency framework | `(user, operation, key HMAC)`; claim/effect/completed response cùng transaction; response giữ 24h; 2s MySQL wait | Real concurrent duplicate, timeout rollback/retry, real deadlock rollback | Atomicity đạt; timeout trả raw DB error ở service boundary — SEC-002 |
| Outbox publisher | Event ghi cùng business transaction; publisher polling after commit; publisher confirm/mandatory routing; stuck recovery | MySQL 4/4; Rabbit protocol/recovery một phần | Đạt phần kiểm chứng |
| Email worker | Serial worker, finite retry 30/120/300, duplicate guard, FAILED/park/replay | Rabbit 7/11 pass; 4 test không xác minh trên Windows | PENDING do test-harness portability gap |

## 5. Các lệnh/test đã thực sự chạy

Môi trường:

- Windows, PowerShell, Python 3.12.10.
- Dependency đồng bộ từ `backend/uv.lock` vào virtualenv tạm.
- Docker Compose project cô lập `retailops_t04ab3f`.
- MySQL 8.4 test DB riêng `retailops_audit_test`, Redis DB test, RabbitMQ/Mailpit với port, network và volume riêng.
- Không dùng production/demo DB và không đụng volume của workspace khác.

| Command (rút gọn, secrets không ghi vào báo cáo) | Kết quả |
|---|---|
| `ruff check .` | PASS — All checks passed |
| `ruff format --check .` | PASS — 241 files formatted |
| `pytest -m "not integration and not rabbitmq_integration"` | PASS — 683 passed, 4 skipped, 204 deselected |
| `pytest -m "integration and not redis_integration and not proxy_integration and not rabbitmq_integration"` | PASS — 186 passed |
| `pytest -m redis_integration` | PASS — 6 passed |
| `pytest -m proxy_integration` | PASS — 1 passed |
| `pytest -m rabbitmq_integration tests/integration/test_outbox_rabbitmq.py` | PARTIAL — 7 passed, 4 failed |

Giải thích 4 Rabbit failures:

- Hai failure trực tiếp do `tests/integration/test_outbox_rabbitmq.py:184` gọi `os.pread`, API không tồn tại trên Windows.
- Hai worker scenario khác không đạt trạng thái mong đợi sau khi chuỗi test worker bị gián đoạn/cạnh tranh queue; chưa đủ bằng chứng kết luận lỗi production.
- CI chính chạy Linux và có job Rabbit riêng, nhưng audit local này không tự coi CI lịch sử là PASS. Bốn scenario được ghi `NOT VERIFIED`: transient SMTP retry routing, fourth-attempt terminal failure, invalid-envelope parking, password-reset full e2e/log assertion.

## 6. Phase 1 findings (historical; superseded by mục 13)

### SEC-001 — FALSE POSITIVE: stale business-context documentation

| Field | Nội dung |
|---|---|
| Severity | Medium |
| Module | Auth / Redis rate limit / Compose |
| File/Line | `backend/app/core/config.py:65-66`; `compose.yaml:129-130`; `backend/tests/test_rate_limit.py:232` |
| Root Cause | Default và Compose đặt registration `5/60 giây`; business context yêu cầu `3/3600 giây/IP`. Test hiện tại còn cố định hành vi sai “allows five”. |
| Exploit/Failure Scenario | Một IP dùng email khác nhau gửi tối đa khoảng 300 đăng ký/giờ thay vì 3/giờ, mỗi request thực hiện bcrypt và có thể tạo User, approval, notification và outbox event. |
| Impact | Tăng 100 lần budget công khai; tạo spam approval/outbox và tiêu thụ CPU/DB, làm suy giảm availability. Redis vẫn fail-closed nhưng policy bị cấu hình sai. |
| Evidence | Endpoint `/auth/register` gắn `enforce_registration_rate_limit`; dependency dùng trực tiếp hai setting trên; unit test xác nhận mặc định request thứ 6 mới bị chặn. |
| Proposed Fix | Đổi default và Compose thành `3`/`3600`; cập nhật `.env.example`; thay regression test để request thứ 4 trả 429; giữ test proxy để chứng minh không giả mạo forwarding header. |
| Regression Test | Unit default policy 3/hour; Redis integration bucket thật; proxy integration với forged `X-Forwarded-For`. |
| Release Blocking | YES — sai security contract public endpoint. |

### SEC-002 — Phase 1 finding: same-key idempotency timeout returned HTTP 500

| Field | Nội dung |
|---|---|
| Severity | Medium |
| Module | Shared Idempotency / Checkout / Confirm / Cancel / Adjustment |
| File/Line | `backend/app/modules/idempotency/repository.py:34-61`; `backend/app/modules/idempotency/service.py:106`; `backend/tests/integration/test_idempotency.py:443-494`; `backend/app/core/exception_handlers.py:47-58` |
| Root Cause | Repository giới hạn lock wait còn 2 giây nhưng không chuyển MySQL `1205/1213` tại idempotency claim thành domain error/retry có bounded jitter. Application services rollback rồi re-raise; global handler biến lỗi thành generic 500. |
| Exploit/Failure Scenario | Hai request cùng actor/operation/key; request đầu giữ transaction >2 giây. Request sau timeout trên unique/row lock, nhận 500 thay vì replay hoặc `409/425 REQUEST_IN_PROGRESS`. Client khó phân biệt lỗi an toàn để retry. |
| Impact | Availability/API-contract failure trên mutation nhạy cảm; có thể gây retry mù và trải nghiệm “không biết giao dịch đã hoàn tất chưa”. Atomicity vẫn được giữ và test chứng minh claim/effect của loser rollback. |
| Evidence | MySQL test `test_duplicate_lock_timeout_rolls_back_then_retry_replays` kỳ vọng raw `OperationalError(1205)`; không có API test mapping timeout. |
| Proposed Fix | Tại shared idempotency boundary, rollback đúng transaction owner rồi map `1205/1213` sang bounded retry+jitter hoặc `REQUEST_IN_PROGRESS` 409/425 theo quyết định Tech Lead; không commit `IN_PROGRESS` riêng. |
| Regression Test | API-level concurrent same-key barrier cho cả checkout/confirm/cancel/adjust; giữ first request > bounded wait; assert không 500, không duplicate effects, replay sau commit trả persisted result. |
| Release Blocking | YES — vi phạm contract concurrency của critical mutations. |

Không có finding Critical hoặc High được xác nhận.

## 7. Potential risks (chưa đủ bằng chứng để gọi bug)

1. Password request schema cho phép độ dài 1–72. Hashing an toàn nhưng không có minimum-strength policy. SRS hiện chỉ yêu cầu “hash mật khẩu an toàn”, chưa khóa minimum; cần PO/Tech Lead quyết định trước khi coi là defect.
2. AI re-check ACTIVE+ADMIN tại mỗi tool invocation nhưng không re-check chính `session_id` đã bind trong request. Nếu Admin logout/revoke session trong lúc một request AI dài đang chạy, tool kế tiếp vẫn có thể đọc dữ liệu cho tới deadline 15 giây. Admin hiện không có lock transition; impact hẹp. Cần quyết định liệu “session live tại mỗi tool invocation” có thuộc AI-02 hay không.
3. Nginx hiện expose `/docs` và `/openapi.json` và ghi chú deployment phải restrict. Không có bằng chứng đây là deployment production/public nên chưa gọi finding.
4. Compose mặc định phục vụ HTTP; requirement yêu cầu HTTPS khi expose. Public demo path/TLS termination chưa được cung cấp trong workspace, nên verdict deployment exposure là PENDING.

## 8. Coverage gaps

- Bốn RabbitMQ worker scenario `NOT VERIFIED` trên Windows vì test harness dùng POSIX-only `os.pread`; cần chạy job Linux hoặc sửa harness đa nền tảng (không đổi production code).
- Không có API-level assertion cho MySQL idempotency lock timeout; lower-level test đang xác nhận raw DB exception.
- Không có regression test buộc registration default `3/hour`; test hiện tại củng cố default sai.
- Không chạy lại benchmark T04AAA2 vì audit không thay production code/performance path; chỉ kiểm tra attestation/config và report đã merge.
- Không chạy SAST/dependency vulnerability scanner chuyên dụng (Bandit/pip-audit/Trivy); CI hiện chỉ thể hiện Ruff + tests, không có security-scanner gate riêng.
- Không kiểm chứng TLS/public deployment vì không có isolated public endpoint/certificate trong task environment.

## 9. Release blockers

1. `SEC-001`: sửa registration quota về đúng `3/hour/IP` và có unit + Redis/proxy regression.
2. `SEC-002`: quyết định/mapping rõ same-key lock timeout sang bounded retry hoặc 409/425; thêm API concurrency regression, không được trả generic 500.
3. Chạy lại đầy đủ 11 RabbitMQ integration scenarios trên Linux CI/isolate stack và lưu run evidence; local Windows hiện chỉ 7/11.

## 10. Remediation tối thiểu theo ưu tiên (Phase 2 đề xuất)

1. P0 — sửa SEC-001 ở Settings, Compose, `.env.example`, unit/Redis/proxy tests.
2. P0 — sửa shared idempotency timeout/deadlock mapping một lần ở boundary dùng chung; giữ TD-04C Option A và atomic rollback.
3. P0 verification — chạy Rabbit job Linux và lưu exact SHA/log; nếu vẫn fail thì điều tra worker/retry/parking trước Release Gate.
4. P1 hardening — Tech Lead/PO khóa password-strength policy và yêu cầu session re-check giữa các AI tool calls.
5. Deployment gate — xác nhận TLS termination và policy `/docs` trước khi expose public.

Không cần sửa: lock ordering stock ASC; optimistic versions; non-negative DB constraints; field-level Staff movement serializer; JWT/session/replay mechanism; transaction-owned outbox; AI allowlist/read-only dispatch — các phần này có code và test evidence phù hợp trong audit hiện tại.

## 11. Verdict sơ bộ

- **SECURITY: FAIL** — SEC-001 là sai security policy public endpoint và là release blocker.
- **CONCURRENCY: FAIL** — SEC-002 vi phạm response/recovery contract cho same-key contention; atomicity/data integrity tests còn PASS.
- **RELEASE BLOCKERS:** SEC-001, SEC-002, và full RabbitMQ Linux verification 11/11.

## 12. Phase 1 completion

- Audit report: `docs/sprint3/T04AB3F_SECURITY_CONCURRENCY_AUDIT.md`.
- Feature branch: `feature/T04AB3F-security-concurrency-audit`.
- Commit: **NOT CREATED**.
- Push: **NOT PERFORMED**.
- PR: **NOT OPENED**.
- Production code changes: **NONE**.
- Next action: chờ Backend Lead review findings và phê duyệt Phase 2.

## 13. Phase 2 corrective remediation — authoritative disposition

### 13.1 SEC-001 — FALSE POSITIVE

| Field | Phase 2 disposition |
|---|---|
| Classification | **FALSE POSITIVE — stale documentation, không phải security vulnerability** |
| Authoritative contract | `docs/requirement/RetailOps_SRS_Approved.md`, INF-02: Registration **5 requests / 60 seconds / IP**, theo quyết định Product Owner/Tech Lead. |
| Root cause of Phase 1 mismatch | `docs/requirement/RETAILOPS_AGENT_BUSINESS_CONTEXT.md` còn giữ quota cũ `3/hour/IP` và đã được dùng nhầm để ghi đè SRS đã duyệt. |
| Remediation | Đồng bộ business context thành `5 requests/60 seconds/IP`. Không thay đổi production settings, Compose hoặc regression tests vì chúng đã đúng contract. |
| Security impact | Không có. Endpoint production đã thực thi đúng SRS; finding Phase 1 là lỗi phân loại do tài liệu stale. |
| Status | **CLOSED — FALSE POSITIVE** |

### 13.2 SEC-002 — REMEDIATED

| Field | Phase 2 disposition |
|---|---|
| Classification | **REMEDIATED** |
| Scope | Chỉ MySQL `OperationalError` mã `1205` phát sinh trong `IdempotencyRepository.claim_or_lock`. |
| Mapping | Repository phát `IdempotencyClaimLockTimeoutError`; shared executor ánh xạ thành domain error `409 REQUEST_IN_PROGRESS`. |
| SQL behavior preserved | MySQL `1213` và mọi lỗi SQL không phải `1205` tiếp tục truyền nguyên trạng. Không retry toàn bộ business transaction. |
| Transaction ownership | Repository không commit/rollback; checkout/cancel/confirm owner và FastAPI DB dependency tiếp tục rollback theo boundary hiện hữu. |
| Timeout restoration | `_bounded_lock_wait` ưu tiên exception gốc nếu restore session timeout cũng thất bại; integration test xác minh timeout được khôi phục trong đường `1205`, rồi connection dùng lại được sau rollback. |
| Invariants | Không đổi fingerprint, replay, TTL 24 giờ, response persistence hoặc claim/effect atomicity. |
| Contention evidence | Hai transaction MySQL thật cùng actor/operation/key cạnh tranh: loser nhận `REQUEST_IN_PROGRESS`; command loser không chạy; winner chỉ ghi một mutation; retry sau commit replay kết quả; deadlock `1213` vẫn giữ behavior cũ. |
| Status | **CLOSED — REMEDIATED** |

### 13.3 RabbitMQ — VERIFIED

- Root cause bốn scenario `NOT VERIFIED` ở Phase 1 là test utility dùng
  `os.pread`, API không có trên Windows.
- Test utility được đổi tối thiểu sang log file có tên và mở một read handle riêng;
  không thay production publisher, worker, retry hoặc parking behavior.
- Linux Docker run trên exact working tree: **11 passed / 11 scenarios** trong
  `124.47s`. Các scenario transient retry, fourth-attempt terminal failure,
  invalid-envelope parking và password-reset full e2e/log assertion đều PASS.
- Classification: **VERIFIED — platform-specific coverage gap closed**.

### 13.4 Phase 2 verification evidence

| Verification | Result |
|---|---|
| Ruff check | PASS — All checks passed |
| Ruff format check | PASS — 241 files formatted |
| Unit/API regression | PASS — 688 passed, 204 deselected |
| MySQL integration | PASS — 186 passed, 706 deselected |
| Targeted MySQL idempotency | PASS — 13 passed |
| Redis integration/security | PASS — 6 passed, 886 deselected |
| RabbitMQ Linux integration | PASS — 11 passed |
| MySQL unrelated-error behavior | PASS — real deadlock test vẫn nhận raw `1213` |

### 13.5 Final gate and remaining risk

- **SECURITY GATE: PASS** — SEC-001 là false positive và tài liệu stale đã đồng bộ.
- **CONCURRENCY GATE: PASS** — SEC-002 được remediation với narrow `1205`
  mapping; atomicity và transaction ownership được giữ nguyên.
- **RABBITMQ COVERAGE: VERIFIED** — đủ 11/11 trên Linux; không có evidence yêu
  cầu sửa production worker.
- Remaining risks từ Phase 1 mục 7 vẫn là potential/non-blocking và không được
  mở rộng scope trong remediation này.
- Merge recommendation: **RECOMMEND MERGE** sau khi CI trên exact PR HEAD PASS;
  không approve hoặc merge tự động.
