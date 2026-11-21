# T04AB73 — REAL E2E Integration & Demo Guide: AI + Redis + Email Worker

- **Task ID**: `T04AB73`
- **Task Name**: Tích hợp và demo Worker/Redis/AI
- **Owner**: Cao Nguyễn Anh Dương
- **Branch**: `feature/T04AB73-worker-redis-ai-e2e`
- **Base Branch**: `develop` (`6af6c10`)

## 1. Purpose and Scope
Xác minh tích hợp đầu-cuối (REAL E2E) trên hạ tầng Docker Compose hiện có của RetailOps cho hai luồng cốt lõi:
1. **AI + Redis Pipeline**: `Authenticated ADMIN → POST /api/v1/ai/query → Redis Rate Limit (10/min/user) & Concurrency Guard (1 inflight/user, fail-closed) → AIOrchestrator / GeminiProvider → AIToolExecutor (allowlist 4 read-only tools, 15s deadline, 3 calls, 32 KiB) → MySQL 8.4`.
2. **Transactional Outbox + Email Worker Pipeline**: `Business Transaction → OutboxWriter → MySQL outbox_events → OutboxPublisher (confirm publish) → RabbitMQ (retailops.email / retailops.email.v1 quorum queue) → Celery Email Worker (--pool=solo --concurrency=1) → EmailEventHandler → SMTP → Mailpit`.

Phạm vi bao gồm cả **kiểm thử gián đoạn và phục hồi dịch vụ (fault injection & recovery)** cho Redis, RabbitMQ, Celery Worker, SMTP/Mailpit và kiểm tra **security-safe logging**.

## 2. Prerequisites & Safe Isolated Setup
- Docker Desktop đang chạy (daemon `dockerDesktopLinuxEngine` sẵn sàng).
- Python 3.12 + `uv` (`backend/.venv` đã sync theo `backend/uv.lock`).
- **Quy tắc an toàn dữ liệu tuyệt đối**:
  - **KHÔNG** chạy `docker compose down -v` trên project dev mặc định để tránh xóa `mysql_data` của database `retailops`.
  - Dùng project cô lập (`$env:COMPOSE_PROJECT_NAME = "retailops-t04ab73-e2e"`) kèm `compose.yaml` + `compose.ci.yaml` để mọi test chỉ chạm vào schema disposable `retailops_test` (được bảo vệ bởi `tests/integration/database_guard.py`).

## 3. Required Environment Variables (Names Only — No Secret Values)
- **MySQL test isolation**: `MYSQL_DATABASE`, `MYSQL_TEST_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_TEST_USER`, `MYSQL_TEST_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `MYSQL_HOST_PORT`, `RETAILOPS_TEST_DATABASE_URL`
- **Auth / Security**: `RETAILOPS_JWT_SECRET`, `RETAILOPS_CSRF_SECRET`, `RETAILOPS_IDEMPOTENCY_SECRET`, `RETAILOPS_OUTBOX_SECRET_KEY`
- **Redis**: `REDIS_HOST_PORT`, `RETAILOPS_TEST_REDIS_URL`
- **AI (Real Provider)**: `RETAILOPS_GEMINI_API_KEY`, `RETAILOPS_GEMINI_MODEL` (khuyến nghị `gemini-3.1-flash-lite` cho key mới)
- **RabbitMQ & Mailpit**: `RABBITMQ_BOOTSTRAP_USER`, `RABBITMQ_BOOTSTRAP_PASSWORD`, `RABBITMQ_PUBLISHER_USER`, `RABBITMQ_PUBLISHER_PASSWORD`, `RABBITMQ_WORKER_USER`, `RABBITMQ_WORKER_PASSWORD`, `RABBITMQ_AMQP_HOST_PORT`, `RABBITMQ_MANAGEMENT_HOST_PORT`, `MAILPIT_SMTP_HOST_PORT`, `MAILPIT_HTTP_HOST_PORT`, `RETAILOPS_TEST_RABBITMQ_MANAGEMENT_URL`, `RETAILOPS_TEST_RABBITMQ_BOOTSTRAP_URL`, `RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL`, `RETAILOPS_TEST_RABBITMQ_WORKER_URL`

## 4. Start Isolated Services (Windows PowerShell)
```powershell
$env:COMPOSE_PROJECT_NAME = "retailops-t04ab73-e2e"
docker compose -f compose.yaml -f compose.ci.yaml --profile email --profile email-local up -d --wait mysql redis rabbitmq mailpit
docker compose -f compose.yaml -f compose.ci.yaml --profile email run --rm --build --no-deps rabbitmq-bootstrap
docker compose -f compose.yaml -f compose.ci.yaml --profile email --profile email-local ps -a
```

## 5. Execute Real E2E Integration Tests (Windows PowerShell)
Load biến môi trường test cô lập (tuyệt đối không trỏ `RETAILOPS_TEST_DATABASE_URL` vào database `retailops`), sau đó chạy:

```powershell
Set-Location backend

# 1. AI + Redis (bao gồm Redis fail-closed outage/recovery, auth, read-only, safe logs, và live Gemini nếu có RETAILOPS_GEMINI_API_KEY)
uv run --locked pytest -vv -m redis_integration tests/integration/test_t04ab73_worker_redis_ai_e2e.py tests/modules/ai/test_ai_query_mysql_redis_e2e.py tests/integration/test_redis_rate_limit.py

# 2. Outbox MySQL delivery budget & commit ambiguity
uv run --locked pytest -vv -m integration tests/integration/test_outbox_delivery_mysql.py

# 3. RabbitMQ + Celery Worker + Mailpit E2E + Worker outage/recovery + Broker outage + SMTP transient retry
uv run --locked pytest -vv -m rabbitmq_integration tests/integration/test_t04ab73_worker_redis_ai_e2e.py tests/integration/test_outbox_rabbitmq.py
```

## 6. Fault Injection & Recovery Procedures (Manual Demo / Verification)
1. **Redis interruption**: `docker compose -f compose.yaml -f compose.ci.yaml stop redis` → gọi `POST /api/v1/ai/query` phải trả `503` (fail-closed) → `docker compose ... start redis` → gọi lại trả `200 OK`.
2. **RabbitMQ interruption**: `docker compose ... --profile email stop rabbitmq` → ghi Outbox event trong `retailops_test` → `OutboxPublisher.publish_due` giữ `published_at IS NULL` → `start rabbitmq` → publish lại thành công (`test_t04aa00_broker_outage_and_controlled_replay_recovery`).
3. **Worker interruption**: Giữ `email-worker` tắt khi publish vào `retailops.email.v1` → message giữ nguyên trong quorum queue → khởi động `email-worker` → tiêu thụ và gửi email tới Mailpit (`test_t04ab73_worker_interruption_recovery_and_mailpit_safe_logs`).
4. **SMTP interruption**: Tạm dừng `mailpit` hoặc dùng cổng SMTP đóng → worker phân loại lỗi tạm, giữ nguyên event không đánh dấu `SENT`, đẩy retry theo backoff cấu hình (`test_real_worker_transient_smtp_publishes_routed_retry`, `test_real_worker_fourth_transient_attempt_is_terminal`).

## 7. Teardown Isolated Test Project Only
```powershell
$env:COMPOSE_PROJECT_NAME = "retailops-t04ab73-e2e"
docker compose -f compose.yaml -f compose.ci.yaml --profile email --profile email-local down --volumes --remove-orphans
```

## 8. Execution Status & Known Limitations
- **Unit & Lint Verification (Local)**: Đã chạy `ruff check .`, `ruff format --check .`, và `pytest -m "not integration and not rabbitmq_integration"` (xem chi tiết kết quả ở báo cáo PR/task).
- **Real Docker E2E Local Execution**: **BLOCKED** tại thời điểm tạo tài liệu do Docker Desktop daemon (`dockerDesktopLinuxEngine`) trên máy local đang tắt. Cần bật Docker Desktop và chạy lại các lệnh ở Mục 4–5 (hoặc chạy trên CI `Backend / MySQL integration` + `Backend / RabbitMQ protocol and ACL`) để hoàn tất nghiệm thu thực tế.
- **Known Limitations**:
  - Delivery semantics của SMTP là **at-least-once** (không cam kết external SMTP exactly-once nếu worker crash sau khi SMTP accept nhưng trước khi commit `outcome=SENT`).
  - Live Gemini E2E cần `RETAILOPS_GEMINI_API_KEY` hợp lệ tại máy chạy; không dùng trong CI nếu secret chưa được cấu hình.
