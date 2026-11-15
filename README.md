# RetailOps — Hệ thống quản lý vận hành bán lẻ (V1.0)

**RetailOps V1.0** là hệ thống quản lý và vận hành cửa hàng bán lẻ toàn diện được thiết kế theo kiến trúc **Modular Monolith**, cung cấp các luồng nghiệp vụ khép kín từ xác thực phân quyền, quản lý danh mục & hàng hóa, quản lý mua hàng & phiếu nhập, kiểm soát kho & biến động tồn, bán hàng tại quầy (POS), đối soát đơn hàng, đến phân tích báo cáo và tích hợp AI.

---

## 1. Tổng quan Dự án & Kiến trúc Hệ thống

### 1.1. Hiện trạng Triển khai các Phân hệ Nghiệp vụ (Implementation Status)

Để đảm bảo tính minh bạch và chính xác theo tiến độ dự án, các phân hệ được phân loại rõ ràng theo trạng thái mã nguồn trên Git:

#### A. Đã Hoàn Thành và Đã Merge vào `develop` (Sprint 1 & Sprint 2 Baseline):
- **Auth & RBAC (`app.modules.auth`):** Đăng nhập an toàn qua HttpOnly Cookie + CSRF token, phân quyền 2 vai trò chuẩn theo SRS là `ADMIN` và `STAFF`, quy trình phê duyệt tài khoản nhân viên mới, thu hồi phiên đăng nhập từ phía server.
- **Categories & Suppliers (`app.modules.categories`, `app.modules.suppliers`):** Quản lý danh mục hàng hóa phân cấp, chuẩn hóa thông tin nhà cung cấp và xác thực số điện thoại theo định dạng quốc tế E.164.
- **Products Catalog (`app.modules.products`):** Quản lý vòng đời sản phẩm, bảo đảm tính duy nhất tuyệt đối của Barcode/SKU, bảo mật trường giá vốn (`cost_price` / `unit_cost_vnd`) không lộ cho Staff trên cả API và UI.
- **Purchasing & Receipts (`app.modules.purchasing`):** Lập phiếu nhập nháp (`DRAFT`), cơ chế tự động gộp dòng sản phẩm trùng giá (item merging), khóa lạc quan (`draft_version`), hủy phiếu nháp không ảnh hưởng tồn kho, và xác nhận phiếu nhập (`CONFIRMED`) tăng tồn kho nguyên tử kèm kiểm tra Idempotency (PR #35, PR #44).
- **Inventory & Stock Movements (`app.modules.inventory`):** Quản lý tồn kho thời gian thực, cảnh báo tồn thấp theo ngưỡng an toàn cố định (threshold = 5), kiểm kê điều chỉnh tồn kho yêu cầu `Idempotency-Key` và `stock_version`, ghi nhận thẻ kho bất biến (`StockMovement`) với 4 loại giao dịch chuẩn: `PURCHASE_CONFIRM`, `SALE`, `ORDER_CANCEL`, `ADJUSTMENT`.
- **POS Sales & Order Cancel (`app.modules.sales`):** Bán hàng tại quầy POS, tính giá tự động, thanh toán nguyên tử (trừ kho tức thời), chặn bán vượt tồn kho (HTTP 409 `INSUFFICIENT_STOCK`) và chặn đổi giá (HTTP 409 `PRICE_CHANGED`), hỗ trợ hủy đơn trong vòng 15 phút kèm lý do và hoàn trả tồn kho đúng 1 lần (PR #62).

#### B. Đang Triển Khai / Pull Request Đang Mở Review (Sprint 3 Scope):
- **Sales Analytics (`app.modules.analytics` / `T04A92B`):** Endpoint `GET /api/v1/analytics/sales` với query parameters `from` và `to` tổng hợp doanh thu, số đơn và AOV loại trừ đơn cancelled (PR #60 đang mở review).
- **Dashboard API (`app.modules.analytics` / `T04AA36`):** Endpoint `GET /api/v1/dashboard` tổng hợp KPI vận hành toàn diện cho màn hình quản trị (PR #61 đang mở review).
- **Tài liệu & UAT Master (`T04A996`):** Chuẩn hóa tài liệu vận hành Docker/Nginx, kịch bản UAT E2E và Defect Ledger (PR #63 đang mở review).

#### C. Dự Kiến Triển Khai trong Sprint 3 (Pending Implementation):
- **Transactional Outbox & Email Worker (`app.modules.outbox` / `T04A90F`, `T04AA00`):** Xử lý bất đồng bộ các sự kiện miền qua mô hình Transactional Outbox, worker định kỳ quét và gửi email thông báo với cơ chế retry và exponential backoff.
- **Password Reset Flow (`T04AA1C`):** Khôi phục mật khẩu Staff bằng one-time token lưu hash trong DB qua endpoint `POST /api/v1/auth/forgot-password` và `POST /api/v1/auth/reset-password`.
- **Read-Only AI Assistant & Reorder Advisor (`app.modules.ai` / `T04A9E6`, `T04AA86`, `T04AB0B`):** Trợ lý AI khuyến nghị kế hoạch nhập hàng thông minh theo hợp đồng chỉ đọc qua `POST /api/v1/ai/query` (bắt buộc role `ADMIN`, giới hạn 15s deadline / tối đa 3 tool calls / $\le 32$ KiB dữ liệu).

---

### 1.2. Kiến trúc Mạng Docker Compose (`proxy` & `application`)

Hệ thống được tổ chức phân tầng mạng nhằm kiểm soát lưu lượng và tăng cường bảo mật:

```
               [ Client Browser / Quầy POS ]
                             │
                  Port 80 / 8080 (HTTP)
                             ▼
              ┌─────────────────────────────┐
              │     Nginx Reverse Proxy     │
              │       (172.30.10.2)         │
              └──────────────┬──────────────┘
                             │  Network: proxy (172.30.10.0/29)
                             ▼
              ┌─────────────────────────────┐
              │     FastAPI Backend         │
              │       (172.30.10.3)         │
              └──────────────┬──────────────┘
                             │  Network: application (internal: true)
                 ┌───────────┴───────────┐
                 ▼                       ▼
      ┌─────────────────────┐ ┌─────────────────────┐
      │   MySQL 8.4 InnoDB  │ │   Redis 8.4 Alpine  │
      │   (Dữ liệu nghiệp vụ)│ │   (Rate limit & MQ) │
      └─────────────────────┘ └─────────────────────┘
                 │ (Loopback only)
                 ▼
       Host: 127.0.0.1:3306
```

- **Mạng `proxy` (Bridge `172.30.10.0/29`):** Kết nối giữa `nginx` và `backend`. Nginx là cổng tiếp nhận traffic duy nhất từ bên ngoài mạng, phục vụ SPA tĩnh, xử lý header bảo mật (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`), và reverse proxy các request `/api/` về Backend.
- **Mạng `application` (`internal: true`):** Kết nối Backend với MySQL và Redis. Thiết lập `internal: true` ngăn chặn các container trong mạng này định tuyến trực tiếp ra Internet hoặc các mạng bên ngoài qua gateway của Docker.
- **Cơ chế Host Loopback Binding:**
  Trong file `compose.yaml`, cổng MySQL được công bố dưới dạng loopback binding:
  ```yaml
  ports:
    - "127.0.0.1:${MYSQL_HOST_PORT:-3306}:3306"
  ```
  *Ý nghĩa bảo mật:* Cổng 3306 **chỉ lắng nghe trên địa chỉ loopback cục bộ (`127.0.0.1`) của máy host**, phục vụ các công cụ quản trị (DBeaver, MySQL Workbench) hoặc local FastAPI development. Các máy tính khác trong mạng LAN hoặc Internet **hoàn toàn không thể kết nối** trực tiếp vào MySQL. Redis trong chế độ chuẩn **không** công bố cổng ra máy host.

---

### 1.3. Hai Chế độ Chạy Docker Compose

1. **Chế độ 1 — Chạy Ứng dụng / Demo Chuẩn (`docker compose up -d`):**
   ```powershell
   docker compose up -d
   ```
   Chỉ sử dụng file `compose.yaml`. Mạng `application` là `internal: true`. MySQL chỉ bind ra loopback `127.0.0.1`, Redis hoàn toàn đóng kín trong mạng nội bộ Docker.

2. **Chế độ 2 — Chạy Host-side Integration Tests (`docker compose -f compose.yaml -f compose.ci.yaml up -d`):**
   ```powershell
   docker compose -f compose.yaml -f compose.ci.yaml up -d
   ```
   File overlay `compose.ci.yaml` cấu hình:
   - Mạng `application` chuyển thành `internal: false`.
   - Redis được mở thêm cổng loopback máy host tại `127.0.0.1:${REDIS_HOST_PORT:-16379}:6379`.
   - Backend container chuyển biến môi trường sang kết nối `MYSQL_TEST_DATABASE` (`retailops_test`) với `MYSQL_TEST_USER`.

> [!WARNING]
> **Lưu ý an toàn về Volume và Dữ liệu:**
> Cả hai chế độ mặc định đều chia sẻ cùng Docker volume `mysql_data` nếu chạy trong cùng một project name. Do đó, **tuyệt đối không chạy overlay CI trên stack demo đang có dữ liệu cần bảo toàn**, để tránh trường hợp các bài kiểm thử tích hợp ghi dữ liệu hoặc làm thay đổi trạng thái volume.

*Lệnh cấp quyền tài khoản test user trên MySQL volume hiện có:*
Nếu volume database đã khởi tạo từ trước và test user chưa được cấp quyền trên schema `retailops_test`, thực thi công cụ sau:
```powershell
docker compose exec -e CONFIRM_RETAILOPS_LOCAL_PROVISIONING=retailops-local mysql bash /usr/local/bin/provision-existing-test-user
```
*(Yêu cầu mật khẩu root hợp lệ; công cụ chỉ tạo/cấp quyền cho test user trên `retailops_test`, không thay đổi mật khẩu của tài khoản ứng dụng `retailops_app`).*

---

## 2. Yêu cầu Môi trường (Prerequisites)

- **Docker Desktop** (khuyến nghị kích hoạt WSL2 backend trên Windows) hoặc Docker Engine + Docker Compose v2 (`docker compose version`).
- **Python:** Bắt buộc **`Python >=3.12, <3.13`** theo cấu hình `backend/pyproject.toml`, kèm công cụ quản lý gói `uv`.
- **Node.js:** Bắt buộc phiên bản Node.js tương thích với ràng buộc của Vite 8.x (`^20.19.0 || >=22.12.0` theo `frontend/package-lock.json`). Khuyến nghị sử dụng **Node.js LTS >= 20.19.0**, **Node.js 22 LTS (>= 22.12.0)** hoặc **Node.js 24** (phiên bản cấu hình trong CI `.github/workflows/frontend-ci.yml`), kèm `npm`. *(Lưu ý: Node.js 18 và các bản Node.js 20 < 20.19.0 không được Vite 8.x và Oxlint hỗ trợ).*

---

## 3. Cấu hình `.env` từ `.env.example`

Sao chép file cấu hình mẫu tại thư mục gốc:

```powershell
Copy-Item .env.example .env
```

> [!IMPORTANT]
> **Quy tắc bảo mật bắt buộc:**
> - Thay thế **toàn bộ** các giá trị chứa `CHANGE_ME_*` bằng chuỗi ngẫu nhiên độc lập.
> - Các khóa `RETAILOPS_JWT_SECRET`, `RETAILOPS_CSRF_SECRET`, và `RETAILOPS_IDEMPOTENCY_SECRET` bắt buộc phải có độ dài **tối thiểu 32 bytes ngẫu nhiên** và tuyệt đối không được giữ tiền tố `CHANGE_ME`.
> - Thiết lập `RETAILOPS_ADMIN_SEED_EMAIL` và `RETAILOPS_ADMIN_SEED_PASSWORD` trong `.env` khi cần thực hiện seed tài khoản Quản trị viên khởi tạo.
> - Tuyệt đối không commit file `.env` chứa thông tin thật lên Git repository.

### Xử lý Xung đột Cổng thường gặp trên Windows
- **Xung đột cổng MySQL (3306):** Thường do Hyper-V / WinNAT hoặc MySQL cục bộ chiếm cổng. Khắc phục bằng cách đặt trong `.env`:
  ```dotenv
  MYSQL_HOST_PORT=13306
  ```
  Và đồng bộ cổng tương ứng trong chuỗi kết nối kiểm thử:
  ```dotenv
  RETAILOPS_TEST_DATABASE_URL=mysql+pymysql://retailops_test_runner:CHANGE_ME_GENERATE_A_SEPARATE_TEST_PASSWORD@127.0.0.1:13306/retailops_test?charset=utf8mb4
  ```
- **Xung đột cổng HTTP (80):** Thường do dịch vụ IIS hoặc tiến trình HTTP.sys (System PID 4) chiếm cổng. Khắc phục bằng cách đổi trong `.env`:
  ```dotenv
  NGINX_HOST_PORT=8080
  ```

---

## 4. Quy trình Cold-Start 4 Bước Chuẩn (Đồng bộ với Runbook)

> [!WARNING]
> **Phân biệt Container Health và Database Readiness:**
> Healthcheck của container `backend` (`/api/v1/health`) chỉ xác nhận tiến trình Uvicorn đang chạy và phản hồi HTTP, **không** kiểm tra xem cơ sở dữ liệu đã chạy migration hay chưa. Nếu khởi chạy Nginx và mở traffic ngay khi database chưa hoàn tất migration/seed, các truy vấn nghiệp vụ của người dùng sẽ gặp lỗi `HTTP 500 Internal Server Error`. Vì vậy, bắt buộc phải tuân thủ nghiêm ngặt 4 bước dưới đây (đã loại bỏ hoàn toàn tham chiếu sai tới `compose.local.yaml`):

### Bước 1: Build Docker Images
```powershell
docker compose build
```

### Bước 2: Khởi động MySQL và Redis trước
Khởi chạy dịch vụ lưu trữ và chờ cả hai đạt trạng thái `healthy`:
```powershell
docker compose up -d --wait mysql redis
```

### Bước 3: Migration Schema và Nạp Đủ 3 Lệnh Seed Idempotent
Chạy migration có kiểm soát bằng Alembic trên container Backend tạm thời:
```powershell
docker compose run --rm --no-deps backend alembic current
docker compose run --rm --no-deps backend alembic upgrade head
```

Sau khi schema đạt revision mới nhất (`20261113_01`), tiến hành nạp đầy đủ 3 bộ dữ liệu hạt giống (tất cả các lệnh seed đều được thiết kế **idempotent**, an toàn tuyệt đối khi chạy lại nhiều lần):

1. **Seed tài khoản Quản trị viên (Admin):**
   ```powershell
   docker compose run --rm --no-deps -e RETAILOPS_ADMIN_SEED_EMAIL -e RETAILOPS_ADMIN_SEED_PASSWORD backend python -m app.modules.auth.seed
   ```
2. **Seed Danh mục Hàng hóa (Categories — 5 danh mục chuẩn từ code: "Đồ uống", "Bánh kẹo & Đồ ăn vặt", "Thực phẩm đóng hộp", "Hóa mỹ phẩm & Tẩy rửa", "Đồ gia dụng tiện ích"):**
   ```powershell
   docker compose run --rm --no-deps backend python -m app.modules.categories.seed
   ```
3. **Seed Nhà cung cấp Mẫu (Suppliers — 3 đối tác chuẩn từ code: "Công ty TNHH Phân phối Nước giải khát Việt", "Công ty Cổ phần Thực phẩm An Toàn", "Đại lý Phân phối Hàng gia dụng Miền Bắc"):**
   ```powershell
   docker compose run --rm --no-deps backend python -m app.modules.suppliers.seed
   ```

### Bước 4: Khởi động Backend và Nginx Mở Traffic
```powershell
docker compose up -d --wait
docker compose ps
```

Kiểm tra hệ thống hoạt động:
- Truy cập giao diện ứng dụng: `http://127.0.0.1:80` (hoặc `http://127.0.0.1:8080` nếu đã đổi `NGINX_HOST_PORT`).
- Kiểm tra sức khỏe API: `curl -fsS http://127.0.0.1:80/api/v1/health` -> `{"status":"ok"}`.

---

## 5. Hướng dẫn Phát triển Cục bộ (Local Development)

### 5.1. Khởi chạy Backend độc lập (FastAPI với `uv`)
```powershell
cd backend
uv sync --locked
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Tài liệu tương tác Swagger UI khả dụng tại: `http://127.0.0.1:8000/docs`.

### 5.2. Khởi chạy Frontend độc lập (React + Vite)
```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```
Giao diện lập trình mở tại `http://127.0.0.1:5173`. Vite dev proxy tự động điều hướng toàn bộ request `/api/*` về `http://127.0.0.1:8000`.

---

## 6. Kiểm thử và Kiểm tra Chất lượng (Testing & QA)

### 6.1. Backend Testing
- **Kiểm tra cú pháp và định dạng mã nguồn (Linter & Formatter):**
  ```powershell
  cd backend
  uv run ruff check .
  uv run ruff format --check .
  ```
- **Kiểm thử Unit & API độc lập (Không cần MySQL thật):**
  ```powershell
  cd backend
  uv run pytest -m "not integration"
  ```
- **Kiểm thử Tích hợp MySQL & Concurrency Locking:**
  Khởi động container test với overlay `compose.ci.yaml`:
  ```powershell
  docker compose -f compose.yaml -f compose.ci.yaml up -d --wait mysql redis
  ```
  Nạp biến môi trường an toàn từ `.env` trước khi thực thi pytest:
  - *Trên Linux / macOS / WSL (Bash):*
    ```bash
    cd backend
    set -a && source ../.env && set +a
    uv run pytest -m integration
    # Hoặc chạy riêng suite kiểm thử phiếu nhập và khóa lạc quan:
    uv run pytest tests/integration/test_purchase_receipts_mysql.py -v
    ```
  - *Trên Windows (PowerShell):*
    ```powershell
    cd backend
    Get-Content ..\.env | Where-Object { $_ -match '^[^#=]+=' } | ForEach-Object {
        $k, $v = $_.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
    }
    uv run pytest -m integration
    ```
- **Kiểm thử Tích hợp Redis Rate Limit & Proxy Registration:**
  ```powershell
  cd backend
  uv run pytest tests/integration/test_redis_rate_limit.py
  uv run pytest tests/integration/test_proxy_registration.py
  ```

### 6.2. Frontend Testing
- **Kiểm tra linter tiêu chuẩn code React:**
  ```powershell
  cd frontend
  npm run lint
  ```
- **Chạy bộ kiểm thử tự động Frontend (Node Test Runner):**
  ```powershell
  cd frontend
  npm test
  ```
- **Kiểm tra quá trình Build tĩnh (Production bundle):**
  ```powershell
  cd frontend
  npm run build
  ```

---

## 7. Quản lý Dữ liệu và Dừng Dịch vụ

### Dừng dịch vụ an toàn (Bảo toàn dữ liệu)
```powershell
docker compose down
```
Lệnh này dừng các container nhưng giữ nguyên toàn bộ dữ liệu database trong Docker volume `mysql_data`.

> [!CAUTION]
> **CẢNH BÁO MẤT DỮ LIỆU:**
> Tuyệt đối không dùng cờ `-v` (`docker compose down -v`) trừ khi bạn chủ động muốn hủy toàn bộ dữ liệu thử nghiệm để làm sạch hoàn toàn môi trường từ đầu.

---

## 8. Liên kết Nhanh tới Bộ Tài liệu Dự án (`docs/`)

- [docs/START_HERE.md](docs/START_HERE.md): Quy chế kỹ thuật, danh sách task Sprint 1-3, nguyên tắc bất biến nghiệp vụ và Security Gate.
- [docs/sprint3/UAT_SCENARIOS_AND_DEFECT_LEDGER.md](docs/sprint3/UAT_SCENARIOS_AND_DEFECT_LEDGER.md): Kịch bản kiểm thử nghiệm thu người dùng đầu cuối (E2E UAT), ma trận task Sprint 3, sổ cái theo dõi lỗi (Defect Ledger) và bằng chứng kiểm chứng.
- [docs/runbooks/DOCKER_NGINX_RUNBOOK.md](docs/runbooks/DOCKER_NGINX_RUNBOOK.md): Sổ tay vận hành Docker Compose, cấu hình Nginx, thủ tục sao lưu & phục hồi dữ liệu (Backup & Disaster Recovery).
- [docs/SPRINT2_SPRINT3_CF2_4_README.md](docs/SPRINT2_SPRINT3_CF2_4_README.md): Hướng dẫn phối hợp, tích hợp và kiểm thử giữa các module Sprint 2 và Sprint 3.
- [docs/contracts/API_INTEGRATION.md](docs/contracts/API_INTEGRATION.md) & [docs/contracts/BACKEND_INTERFACES.md](docs/contracts/BACKEND_INTERFACES.md): Đặc tả hợp đồng API và giao diện backend.
- [docs/requirement/RetailOps_SRS_Approved.md](docs/requirement/RetailOps_SRS_Approved.md): Đặc tả yêu cầu phần mềm RetailOps V1.0 chính thức đã duyệt.
- [docs/database/RetailOps_ERD_V1.0_Giai_Thich_Bang_Va_Truong_Chot.md](docs/database/RetailOps_ERD_V1.0_Giai_Thich_Bang_Va_Truong_Chot.md): Mô hình thực thể liên kết (ERD) và từ điển dữ liệu chuẩn.
- [frontend/README.md](frontend/README.md): Hướng dẫn chi tiết kiến trúc và phát triển giao diện React.
- [CONTRIBUTING.md](CONTRIBUTING.md): Quy ước commit, branching workflow (`feature/*` -> `develop` -> `main`) và merge gate.
