# RetailOps — Hệ thống quản lý vận hành bán lẻ

**RetailOps V1.0** là dự án nhóm phát triển hệ thống hỗ trợ vận hành cửa hàng bán lẻ. Dự án được tổ chức theo kiến trúc **Modular Monolith**, với Backend FastAPI, MySQL và Frontend React/Vite theo kế hoạch triển khai.

> **Trạng thái:** Hướng dẫn dưới đây phản ánh Backend Foundation đã có trong repository. Các chức năng nghiệp vụ và giao diện React được bổ sung qua các task/PR riêng. Không coi các chức năng dự kiến là đã hoàn thành.

## Frontend Foundation (T3C98D1)

Repository đã được khởi tạo dự án React + Vite trong thư mục `frontend/` với Axios client và Vite proxy để tích hợp với FastAPI local. Xem hướng dẫn chi tiết tại [frontend/README.md](frontend/README.md).

### Chạy local

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Mặc định Vite chạy trên `http://127.0.0.1:5173` và chuyển tiếp các request `/api` tới backend `http://127.0.0.1:8000`.

### Build và lint

```powershell
cd frontend
npm run lint
npm run build
```

## Công nghệ và cấu trúc

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic.
- **Database:** MySQL 8.4 (Docker Compose).
- **Frontend dự kiến:** React + Vite + Axios.
- **Kiểm thử/CI:** Pytest, Ruff, GitHub Actions; Frontend CI chỉ chạy lint/build thực sự khi dự án frontend đã được khởi tạo.
- **Quản lý mã nguồn:** `feature/*` → `develop` → `main`.

Các quy tắc cộng tác và commit message được mô tả tại [CONTRIBUTING.md](CONTRIBUTING.md). Đặc tả yêu cầu đã phê duyệt nằm tại [docs/requirement/RetailOps_SRS_Approved.md](docs/requirement/RetailOps_SRS_Approved.md).

## 1. Chuẩn bị môi trường local

Cần cài **Docker Desktop** với Docker Compose. Để chạy kiểm thử Backend trực tiếp trên máy, cần thêm **Python 3.12** và `uv`. Frontend sẽ yêu cầu Node.js/npm khi được triển khai; xem hướng dẫn trong `frontend/README.md` khi file đó xuất hiện.

### 1.1. Tạo file cấu hình

Sao chép file mẫu:

```powershell
Copy-Item .env.example .env
```

Thay **toàn bộ** giá trị `CHANGE_ME` bằng mật khẩu mạnh, riêng biệt, tự tạo cho máy local. Không sử dụng lại giá trị mẫu, không dùng chung một bộ mật khẩu cho cả nhóm và **không commit `.env`**.

Nếu mật khẩu trong `RETAILOPS_TEST_DATABASE_URL` có ký tự đặc biệt, phải URL-encode đúng. Chuỗi này phải sử dụng đúng tài khoản kiểm thử và cùng cổng host với `MYSQL_HOST_PORT`.

### 1.2. Khởi chạy MySQL và Backend

```powershell
docker compose up --build -d
```

MySQL chỉ được ánh xạ vào `127.0.0.1`; Backend mặc định tại `http://127.0.0.1:8000`. Docker Compose đợi kiểm tra kết nối MySQL có xác thực (`SELECT 1`) thành công trước khi khởi chạy Backend.

Nếu cổng `3306` trên máy đã bị MySQL khác sử dụng, đổi **cả hai** giá trị trong `.env`:

- `MYSQL_HOST_PORT=13306`
- Cổng trong `RETAILOPS_TEST_DATABASE_URL` cũng phải là `13306`.

Lưu ý: Cổng `3306` **bên trong container** không thay đổi. Nếu bạn đã cấu hình `BACKEND_HOST_PORT` khác `8000`, hãy dùng cổng thực tế khi truy cập Backend.

## 2. Lưu ý quan trọng về MySQL volume và mật khẩu

Script khởi tạo MySQL chỉ chạy khi thư mục dữ liệu `/var/lib/mysql` được tạo lần đầu. **Đổi mật khẩu trong `.env` không tự đổi mật khẩu các tài khoản đã tồn tại trong MySQL volume**, cũng không tự chạy lại script cấp quyền cho test user.

Với volume local đã tồn tại, trước hết kiểm tra đúng Docker Compose project và volume:

```powershell
docker volume inspect retailops_mysql_data --format '{{json .Labels}}'
docker compose ps
```

Sau khi xác nhận volume thuộc đúng project local `retailops` và các thông tin xác thực phù hợp, có thể khởi động MySQL rồi cấp lại tài khoản **test** bằng công cụ đã có:

```powershell
docker compose up -d --wait mysql
docker compose exec `
  -e CONFIRM_RETAILOPS_LOCAL_PROVISIONING=retailops-local `
  mysql bash /usr/local/bin/provision-existing-test-user
```

Công cụ này yêu cầu mật khẩu root local hợp lệ ở thời điểm thực thi. Nó **chỉ tạo lại tài khoản test chuyên dụng và các quyền trong test schema**, đồng thời thu hồi quyền truy cập test schema cũ của development user (nếu có); **không đổi mật khẩu tài khoản development user**.

Nếu đã thay mật khẩu root/development user của volume cũ, phải có quy trình `ALTER USER` hoặc đồng bộ thông tin xác thực phù hợp trước; các lệnh trên không tự giải quyết sai lệch đó. **Không xóa volume để xử lý lỗi đăng nhập khi chưa xác nhận dữ liệu có thể bỏ đi.**

## 3. Database migration với Alembic

Áp dụng migration đã được review và xem revision hiện tại:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

T3C9A19 tạo đúng bốn bảng nền Auth: `users`,
`staff_approval_requests`, `auth_sessions`, `refresh_tokens`. Không tạo bảng
Notification hoặc domain khác.

### 3.1. Seed tài khoản Admin

Điền `RETAILOPS_ADMIN_SEED_EMAIL` và `RETAILOPS_ADMIN_SEED_PASSWORD` trong
`.env` bằng credentials local do Tech Lead cung cấp. Hai biến này không được
truyền vào container Backend chạy thường trực. Sau khi migration hoàn tất, chỉ
nạp chúng vào container seed ngắn hạn bằng lệnh tường minh:

```powershell
docker compose -f compose.yaml -f compose.local.yaml run --rm `
  --env-from-file .env backend python -m app.modules.auth.seed
```

Seed không chạy khi FastAPI startup hoặc trong Alembic migration. Lần đầu seed
tạo đúng một tài khoản `ADMIN/ACTIVE`; chạy lại với cùng email là no-op và
không rotate password. Nếu đã có Admin khác hoặc email đã thuộc tài khoản khác,
lệnh fail closed. Command không in email, password hoặc password hash.

MySQL DDL có thể implicit commit và Alembic coi DDL là thao tác không có rollback transaction hoàn chỉnh. Vì vậy, mọi migration nghiệp vụ sau này phải có kế hoạch backup/recovery; không giả định DDL sẽ tự rollback an toàn khi lỗi.

Kiểm tra toàn bộ chuỗi migration trên Docker Compose project và volume tạm độc lập:

```powershell
.\scripts\verify-clean-migration.ps1
```

Script xác minh nhãn project của volume tạm trước khi dọn dẹp. Nó không reset volume development/test thông thường.

## 4. Chạy kiểm thử Backend

### Unit/API tests — không cần Docker/MySQL

```powershell
cd backend
uv sync --locked
uv run pytest -m "not integration"
```

### Integration tests — cần MySQL test riêng

Trước tiên khởi chạy MySQL. Sau đó chạy trong thư mục `backend`, nạp biến từ file `.env` ở thư mục gốc chỉ cho tiến trình test:

```powershell
cd backend
uv run dotenv -f ../.env run -- pytest -m integration
```

Integration tests chỉ chấp nhận URL `mysql+pymysql` trỏ đến `127.0.0.1` hoặc `localhost`; tên database và test user phải khớp chính xác `MYSQL_TEST_DATABASE`, `MYSQL_TEST_USER`. Tài khoản test phải khác development user và không có quyền truy cập development schema. Thiếu cấu hình hoặc cấu hình không an toàn sẽ làm lệnh test **thất bại**, không được lặng lẽ bỏ qua.

## 5. Dừng và quản lý dữ liệu local

Dừng container **và giữ nguyên dữ liệu** trong MySQL volume:

```powershell
docker compose down
```

Đổi `.env` không phải thao tác xoay vòng (rotate) mật khẩu trên volume cũ. Khi cần giữ dữ liệu, ưu tiên quy trình `ALTER USER` có kiểm soát.

Chỉ khi **đã xác minh toàn bộ dữ liệu local được phép xóa**, kiểm tra chính xác Compose project, nhãn volume và trạng thái dữ liệu trước khi cân nhắc lệnh sau:

```powershell
docker compose down -v
```

**CẢNH BÁO: `-v` xóa volume và dữ liệu MySQL.** Không dùng để dừng dự án thông thường và không chạy tự động.

## 6. Quy trình phát triển nhóm

Mỗi thành viên clone repository một lần, sau đó cập nhật `develop`, tạo nhánh `feature/*` từ `develop`, commit có mã task, push và mở Pull Request vào `develop`. Chỉ merge khi các kiểm tra phù hợp đã chạy và người review chấp thuận.

Đọc [CONTRIBUTING.md](CONTRIBUTING.md) để biết lệnh Git, định dạng commit, cách review PR và điều kiện đưa code lên `main`.
