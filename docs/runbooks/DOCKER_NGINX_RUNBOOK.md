# RetailOps V1.0 — Runbook Docker Compose & Nginx (T04A8D1)

## 1. Prerequisites

- Docker Engine + Docker Compose v2 (`docker compose version`).
- Không dùng chung port hoặc volume với stack development (`retailops`, `retailops-rate-test`) khi chạy kiểm thử cô lập.
- Tuyệt đối không commit file `.env` chứa secrets thật.

## 2. Environment configuration

- Sao chép `.env.example` thành `.env` và thay toàn bộ giá trị `CHANGE_ME_*` bằng chuỗi ngẫu nhiên (JWT/CSRF/Idempotency secret tối thiểu 32 bytes).
- Cấu hình `RETAILOPS_CORS_ORIGINS` khớp chính xác với origin công khai của Nginx (ví dụ `http://127.0.0.1` hoặc `https://demo.example.com`) để `/api/v1/auth/refresh` và `/api/v1/auth/logout` vượt qua kiểm tra `Origin`/CSRF.
- Phân biệt 3 chế độ:
  - **Local HTTP development:** `RETAILOPS_ENVIRONMENT=development`, `RETAILOPS_COOKIE_SECURE=false` (mặc định).
  - **Demo / Production (sau HTTPS / Cloudflare Tunnel):** `RETAILOPS_ENVIRONMENT=production`, `RETAILOPS_COOKIE_SECURE=true`. Khi `RETAILOPS_ENVIRONMENT=production`, backend bắt buộc có `RETAILOPS_JWT_SECRET`, `RETAILOPS_CSRF_SECRET` hợp lệ và từ chối `RETAILOPS_COOKIE_SECURE=false`.
  - **CI / Integration test:** dùng `compose.yaml` + `compose.ci.yaml` để trỏ `backend` vào `MYSQL_TEST_DATABASE` (`retailops_test`) bằng `MYSQL_TEST_USER`. **Không dùng `compose.ci.yaml` cho stack demo/development.**

## 3. Trình tự triển khai Cold-Start (Migration trước khi mở traffic)

> **Phân biệt Container Health và Database Schema Readiness:**
> `backend` healthcheck (`/api/v1/health`) chỉ xác nhận tiến trình Uvicorn đã sẵn sàng nhận HTTP request, **không** truy vấn MySQL hay kiểm tra Alembic revision. Trên một database mới khởi tạo, `backend` có thể báo `healthy` khi schema vẫn còn trống. Vì vậy, phải hoàn tất migration (và seed Admin nếu là môi trường mới) **trước khi** khởi động `nginx` để mở traffic.

1. Build images (multi-stage Node 24 -> Nginx 1.29 và backend):
   - *(Bash / PowerShell)*:
     ```bash
     docker compose build
     ```
2. Khởi động `mysql` và `redis` trước, chờ cả hai đạt `healthy`:
   - *(Bash / PowerShell)*:
     ```bash
     docker compose up -d --wait mysql redis
     ```
3. Chạy Migration / Preflight có kiểm soát trên `mysql` (xem mục 4) và Admin Seed (xem mục 5) **trước khi bật `nginx`**.
4. Mở traffic bằng cách khởi động `backend` (chờ `healthy`) và `nginx` (`running`):
   - *(Bash / PowerShell)*:
     ```bash
     docker compose up -d --wait
     docker compose ps
     ```
   *(Lưu ý: `mysql`, `redis`, `backend` có Docker `healthcheck` nên trạng thái là `healthy`; `nginx` không khai báo Docker `healthcheck` riêng nên trạng thái là `running`.)*

## 4. Migration / Preflight (Có kiểm soát)

- `backend` **không** tự chạy Alembic khi khởi động để tránh migration race hoặc tác động ngoài ý muốn lên database hiện hữu.
- Trước khi chạy migration trên môi trường có dữ liệu, xác minh đúng `RETAILOPS_DB_NAME` và tạo backup (mục 7).
- Kiểm tra revision và nâng cấp schema *(Bash / PowerShell)*:
  ```bash
  docker compose run --rm --no-deps backend alembic current
  docker compose run --rm --no-deps backend alembic heads
  docker compose run --rm --no-deps backend alembic upgrade head
  ```
- **Lưu ý rollback:** Không chạy `alembic downgrade` như bước rollback mặc định khi có dữ liệu thật; ưu tiên restore từ bản backup đã được kiểm chứng.

## 5. Admin Seed

- Lệnh seed là idempotent theo `admin_slot=1`. **Không** truyền mật khẩu dạng plaintext trực tiếp trong câu lệnh CLI nếu có nguy cơ lưu vào shell history.
- Khuyến nghị cấu hình tạm `RETAILOPS_ADMIN_SEED_EMAIL` và `RETAILOPS_ADMIN_SEED_PASSWORD` qua file env bảo mật (`chmod 600` / file tạm ngoài repo) hoặc nhập tương tác từ biến phiên rồi xóa ngay sau khi chạy:
  - **Bash:**
    ```bash
    read -r -p "Admin email: " RETAILOPS_ADMIN_SEED_EMAIL
    read -r -s -p "Admin password: " RETAILOPS_ADMIN_SEED_PASSWORD; echo
    docker compose run --rm --no-deps \
      -e RETAILOPS_ADMIN_SEED_EMAIL="$RETAILOPS_ADMIN_SEED_EMAIL" \
      -e RETAILOPS_ADMIN_SEED_PASSWORD="$RETAILOPS_ADMIN_SEED_PASSWORD" \
      backend python -m app.modules.auth.seed
    unset RETAILOPS_ADMIN_SEED_EMAIL RETAILOPS_ADMIN_SEED_PASSWORD
    ```
  - **PowerShell (Windows):**
    ```powershell
    $env:RETAILOPS_ADMIN_SEED_EMAIL = Read-Host "Admin email"
    $sec = Read-Host "Admin password" -AsSecureString
    $env:RETAILOPS_ADMIN_SEED_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
      [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    )
    docker compose run --rm --no-deps -e RETAILOPS_ADMIN_SEED_EMAIL -e RETAILOPS_ADMIN_SEED_PASSWORD backend python -m app.modules.auth.seed
    Remove-Item Env:RETAILOPS_ADMIN_SEED_EMAIL, Env:RETAILOPS_ADMIN_SEED_PASSWORD
    ```

## 6. Health & Smoke Checks

- **Nginx syntax** *(Bash / PowerShell)*: `docker compose exec nginx nginx -t`
- **Backend health** *(Bash)*: `curl -fsS http://127.0.0.1:${NGINX_HOST_PORT:-80}/api/v1/health` -> `{"status":"ok"}`
- **PowerShell HTTP check**:
  ```powershell
  Invoke-WebRequest -Uri "http://127.0.0.1:80/api/v1/health" -UseBasicParsing
  ```
- **SPA & deep link:** `GET /` và `GET /pos` -> `200 OK`, `Cache-Control: no-store, no-cache, must-revalidate`, có `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, không lộ version trong header `Server`.
- **Exact `/api`, missing asset & missing API:** `GET /api`, `GET /assets/does-not-exist.js`, `GET /api/v1/does-not-exist` -> `404` (không fallback về `index.html`).

## 7. Backup & Restore

- **Backup logical (MySQL 8.4):**
  - **Bash:**
    ```bash
    docker compose exec -T mysql sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump --single-transaction --routines --triggers --user=root "$MYSQL_DATABASE"' > "backup_$(date +%Y%m%d_%H%M%S).sql"
    ```
  - **PowerShell (Windows):**
    ```powershell
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    docker compose exec -T mysql sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump --single-transaction --routines --triggers --user=root "$MYSQL_DATABASE"' | Out-File -Encoding utf8 "backup_$ts.sql"
    ```
- **Restore (chỉ thực hiện trên database đích đã xác nhận):**
  - **Bash:**
    ```bash
    docker compose exec -T mysql sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --user=root "$MYSQL_DATABASE"' < backup_file.sql
    ```
  - **PowerShell (Windows):**
    ```powershell
    Get-Content -Raw "backup_file.sql" | docker compose exec -T mysql sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --user=root "$MYSQL_DATABASE"'
    ```
- *Trạng thái kiểm chứng:* Quy trình backup/restore trên là hướng dẫn vận hành; **chưa được tính là PASS** nếu chưa thực thi restore thử vào một database tạm/cô lập và kiểm tra số bảng/bản ghi thực tế.

## 8. Restart & Recovery

- Restart hoặc recreate container `mysql` không làm mất volume `mysql_data`:
  ```bash
  docker compose restart mysql
  docker compose up -d --force-recreate --wait mysql
  ```
- **Lưu ý runtime availability:** Healthcheck đảm bảo `nginx` chỉ start sau khi `backend` healthy, nhưng nếu `backend` đang restart giữa chừng, các request in-flight vẫn có thể nhận `502 Bad Gateway` cho đến khi Uvicorn bind lại port `8000`.

## 9. Cleanup an toàn

- Với stack cô lập (ví dụ `retailops-t04a8d1-verify`), chỉ cleanup đúng project tạm đó:
  ```bash
  docker compose -p retailops-t04a8d1-verify --env-file <isolated.env> -f compose.yaml down --volumes --remove-orphans --rmi local
  ```
- **CẤM** chạy `docker compose down -v` trên project development `retailops`, hoặc `docker volume prune` / `docker system prune`.

## 10. Known Limitations

- `/docs` và `/openapi.json` vẫn được proxy qua Nginx để thuận tiện phát triển local; khi triển khai demo/production cần giới hạn IP allowlist hoặc trả `404` trong `docker/nginx/default.conf`.
- `compose.yaml` mặc định bind `127.0.0.1:3306` và `127.0.0.1:8000` cho Vite dev/integration test trên máy local; trên server public nên tắt hoặc giữ `127.0.0.1` binding để không bypass Nginx.
- Nginx `default.conf` lắng nghe HTTP port 80; TLS termination (HTTPS) do reverse proxy/tunnel phía trước (ví dụ Cloudflare Tunnel) đảm nhiệm.
