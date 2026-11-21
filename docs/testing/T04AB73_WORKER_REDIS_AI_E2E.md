# T04AB73 — REAL E2E Integration & Demo Guide: AI + Redis + Email Worker

- **Task ID**: `T04AB73`
- **Task Name**: Tích hợp và demo Worker/Redis/AI
- **Owner**: Cao Nguyễn Anh Dương
- **Branch**: `feature/T04AB73-worker-redis-ai-e2e` (PR #101)
- **Base Branch**: `develop` (`6af6c10`)

## 1. Purpose and Scope
Xác minh tích hợp đầu-cuối (REAL E2E) trên hạ tầng Docker Compose hiện có của RetailOps cho hai luồng cốt lõi:
1. **AI + Redis Pipeline**: `Authenticated ADMIN → POST /api/v1/ai/query → Redis Rate Limit (10/min/user) & Concurrency Guard (1 inflight/user, fail-closed) → AIOrchestrator / GeminiProvider → AIToolExecutor (allowlist 4 read-only tools, 15s deadline, 3 calls, 32 KiB) → MySQL 8.4`.
2. **Transactional Outbox + Email Worker Pipeline**: `Business Transaction → OutboxWriter → MySQL outbox_events → OutboxPublisher (confirm publish) → RabbitMQ (retailops.email / retailops.email.v1 quorum queue) → Celery Email Worker (--pool=solo --concurrency=1) → EmailEventHandler → SMTP → Mailpit`.

## 2. Prerequisites & Safe Isolated Setup
- Docker Desktop đang chạy (hoặc chạy qua GitHub Actions CI cô lập).
- Python 3.12 + `uv` (`backend/.venv` đã sync theo `backend/uv.lock`).
- **Quy tắc an toàn dữ liệu tuyệt đối**:
  - **KHÔNG** chạy `docker compose down -v` trên project dev mặc định (`retailops`).
  - **KHÔNG** gọi `FLUSHDB` / `FLUSHALL` trên Redis — mọi test đều dùng namespace riêng theo `run_id` (`t04ab73-{run_id}:*`) và chỉ xóa đúng key thuộc namespace của chính mình bằng `SCAN` + `DELETE` (đã xác minh bằng canary key không bị ảnh hưởng).
  - Dùng project cô lập (`$env:COMPOSE_PROJECT_NAME = "retailops-t04ab73-e2e"`) kèm `compose.yaml` + `compose.ci.yaml` để mọi test chỉ chạm vào schema disposable `retailops_test` (được bảo vệ bởi `tests/integration/database_guard.py`).

## 3. Required Environment Variables (Names Only — No Secret Values)
- **MySQL test isolation**: `MYSQL_DATABASE`, `MYSQL_TEST_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_TEST_USER`, `MYSQL_TEST_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `MYSQL_HOST_PORT`, `RETAILOPS_TEST_DATABASE_URL`
- **Auth / Security**: `RETAILOPS_JWT_SECRET`, `RETAILOPS_CSRF_SECRET`, `RETAILOPS_IDEMPOTENCY_SECRET`, `RETAILOPS_OUTBOX_SECRET_KEY`
- **Redis**: `REDIS_HOST_PORT`, `RETAILOPS_TEST_REDIS_URL`
- **AI (Real Provider — opt-in)**: `RETAILOPS_GEMINI_API_KEY`, `RETAILOPS_GEMINI_MODEL` (khuyến nghị `gemini-3.1-flash-lite` cho key mới)
- **RabbitMQ & Mailpit**: `RABBITMQ_BOOTSTRAP_USER`, `RABBITMQ_BOOTSTRAP_PASSWORD`, `RABBITMQ_PUBLISHER_USER`, `RABBITMQ_PUBLISHER_PASSWORD`, `RABBITMQ_WORKER_USER`, `RABBITMQ_WORKER_PASSWORD`, `RABBITMQ_AMQP_HOST_PORT`, `RABBITMQ_MANAGEMENT_HOST_PORT`, `MAILPIT_SMTP_HOST_PORT`, `MAILPIT_HTTP_HOST_PORT`, `RETAILOPS_TEST_RABBITMQ_MANAGEMENT_URL`, `RETAILOPS_TEST_RABBITMQ_BOOTSTRAP_URL`, `RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL`, `RETAILOPS_TEST_RABBITMQ_WORKER_URL`

## 4. Test Matrix — CI Execution vs Simulation vs Live Provider

| Test | Loại kiểm thử | Chạy trên CI (`backend-ci.yml`) | Ghi chú |
|---|---|---|---|
| `test_t04ab73_ai_redis_interruption_recovery_and_safe_logs` | Direct-tool AI + real MySQL + real Redis + **simulated** Redis connection failure (`127.0.0.1:1`) & recovery + safe logs + Redis key isolation | ✅ `Backend / MySQL integration` (`pytest -m redis_integration`) | Không gọi Gemini API; kiểm tra fail-closed `503`, phục hồi `200`, read-only DB, canary key Redis |
| `test_t04ab73_real_gemini_provider_e2e_with_mysql_and_redis` | **Real live `GeminiProvider`** + function calling + real `AIToolExecutor` + real MySQL + real Redis + read-only DB + safe logs | ⏭️ `SKIPPED` trên CI nếu không cấu hình `RETAILOPS_GEMINI_API_KEY` | Dùng `_ObservingLiveGeminiProvider` pass-through (không mock) để chứng minh `generate_turn`, tool call và `submit_tool_results` đều thực sự chạy |
| `test_t04ab73_worker_interruption_recovery_and_mailpit_safe_logs` | Real MySQL Outbox + real RabbitMQ + **real Worker stopped → started** + real SMTP/Mailpit delivery + safe worker logs | ✅ `Backend / RabbitMQ protocol and ACL` (`pytest -vv -m rabbitmq_integration ...`) | Chứng minh message tồn tại trong quorum queue khi worker dừng và được giao tới Mailpit sau khi worker bật lại |
| `test_outbox_rabbitmq.py` (`test_t04aa00_broker_outage_and_controlled_replay_recovery`, `test_real_worker_transient_smtp_publishes_routed_retry`, `test_real_worker_fourth_transient_attempt_is_terminal`, `test_t04aa00_duplicate_delivery_is_idempotent`, `test_password_reset_e2e_api_outbox_rabbitmq_worker_mailpit_and_reset`) | Real RabbitMQ broker outage/recovery, transient SMTP retry, bounded 4-attempt terminal failure, idempotency, password reset Mailpit E2E | ✅ `Backend / RabbitMQ protocol and ACL` | Đã tích hợp và chạy cùng job với test Worker của `T04AB73` |
| `test_redis_rate_limit.py`, `test_ai_query_mysql_redis_e2e.py` | Real Redis rate limit, concurrency, MySQL Auth + controlled Gemini E2E | ✅ `Backend / MySQL integration` (`pytest -m redis_integration`) | Chạy cùng job với test AI+Redis của `T04AB73` |

## 5. Start Isolated Services (Windows PowerShell)
```powershell
$env:COMPOSE_PROJECT_NAME = "retailops-t04ab73-e2e"
docker compose -f compose.yaml -f compose.ci.yaml --profile email --profile email-local up -d --wait mysql redis rabbitmq mailpit
docker compose -f compose.yaml -f compose.ci.yaml --profile email run --rm --build --no-deps rabbitmq-bootstrap
docker compose -f compose.yaml -f compose.ci.yaml --profile email --profile email-local ps -a
```

## 6. Exact Test Commands (Windows PowerShell)
```powershell
Set-Location backend

# 1. Lint & Format
uv run --locked ruff check .
uv run --locked ruff format --check .

# 2. Unit & API regression (không cần Docker)
uv run --locked pytest -m "not integration and not rabbitmq_integration"

# 3. AI + Redis integration (thêm RETAILOPS_GEMINI_API_KEY để chạy live Gemini E2E)
uv run --locked pytest -vv -m redis_integration tests/integration/test_t04ab73_worker_redis_ai_e2e.py tests/modules/ai/test_ai_query_mysql_redis_e2e.py tests/integration/test_redis_rate_limit.py

# 4. Outbox MySQL delivery budget & commit ambiguity
uv run --locked pytest -vv -m integration tests/integration/test_outbox_delivery_mysql.py

# 5. RabbitMQ + Celery Worker + Mailpit E2E (khớp chính xác job CI)
uv run --locked pytest -vv -m rabbitmq_integration tests/integration/test_outbox_rabbitmq.py tests/integration/test_t04ab73_worker_redis_ai_e2e.py
```

## 7. Real Container Fault Injection & Recovery Procedures (Manual Demo)
1. **Redis container stop/start**: `docker compose -f compose.yaml -f compose.ci.yaml stop redis` → gọi `POST /api/v1/ai/query` trả `503` (fail-closed) → `docker compose ... start redis` → gọi lại trả `200 OK`.
2. **RabbitMQ container stop/start**: `docker compose ... --profile email stop rabbitmq` → Outbox event giữ `published_at IS NULL` → `start rabbitmq` → `OutboxPublisher.publish_due` publish thành công.
3. **Worker stop/start**: Dừng `email-worker` trước khi publish vào `retailops.email.v1` → message giữ nguyên trong quorum queue → bật `email-worker` → tiêu thụ và gửi email tới Mailpit.
4. **SMTP/Mailpit stop/start**: Dừng `mailpit` → worker retry theo backoff cấu hình, không đánh dấu `SENT` → bật `mailpit` trong giới hạn retry → giao thành công (hoặc terminal `FAILED` khi hết 4 lần thử).

## 8. Safe Teardown (Isolated Project Only)
```powershell
$env:COMPOSE_PROJECT_NAME = "retailops-t04ab73-e2e"
docker compose -f compose.yaml -f compose.ci.yaml --profile email --profile email-local down --volumes --remove-orphans
```

## 9. Known Limitations & Honest Status
- **Local Docker execution**: Docker Desktop trên máy local không bật trong phiên review này, nên các bài test real MySQL / Redis / RabbitMQ / Mailpit được xác minh trực tiếp qua GitHub Actions CI trên PR #101.
- **Live Gemini API E2E (`test_t04ab73_real_gemini_provider_e2e_with_mysql_and_redis`)**: `SKIPPED` trên CI khi không cấu hình secret `RETAILOPS_GEMINI_API_KEY`; cần chạy local có key hợp lệ và Docker đang chạy để nghiệm thu nhánh live Gemini.
- **Delivery semantics**: SMTP là **at-least-once** (không cam kết external SMTP exactly-once nếu worker crash sau khi SMTP accept nhưng trước khi commit `outcome=SENT`).
