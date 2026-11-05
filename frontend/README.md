# RetailOps V1.0 — Frontend Foundation (`T3C98D1`)

Thư mục `frontend/` chứa nền tảng ứng dụng **React + Vite + Axios** của dự án **RetailOps V1.0**.

Phạm vi của task `T3C98D1` tập trung vào việc khởi tạo cấu trúc dự án React chuẩn, thiết lập Axios API client dùng chung, cấu hình Vite dev proxy an toàn và kiểm chứng kết nối thực tế tới FastAPI Backend qua endpoint `GET /api/v1/health`.

---

## 1. Yêu cầu môi trường

- **Node.js:** Khuyến nghị **Node.js 24.x** (đồng bộ với `.github/workflows/frontend-ci.yml`; tương thích với Node.js `>= 20.19.0` hoặc `>= 22.12.0`).
- **npm:** Đi kèm theo Node.js (`npm >= 10`).
- **Backend đi kèm:** FastAPI (`http://127.0.0.1:8000` mặc định).

Kiểm tra phiên bản trên máy trước khi chạy:

```powershell
node -v
npm -v
```

---

## 2. Cấu trúc thư mục

```text
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── api/
│   │   ├── client.js             # Axios instance dùng chung và chuẩn hóa thông báo lỗi
│   │   └── health.js             # Hàm gọi API kiểm tra trạng thái GET /api/v1/health
│   ├── components/
│   │   └── StatusBadge.jsx       # Component hiển thị trạng thái kết nối
│   ├── pages/
│   │   └── HealthCheckPage.jsx   # Màn hình kiểm tra kết nối FastAPI (/api/v1/health)
│   ├── App.css
│   ├── App.jsx
│   ├── index.css
│   └── main.jsx
├── .env.example                  # Mẫu cấu hình biến môi trường (an toàn để commit)
├── .gitignore
├── .oxlintrc.json                # Cấu hình linter cho React
├── index.html
├── package.json
├── package-lock.json
├── vite.config.js                # Cấu hình Vite dev server và proxy /api
└── README.md
```

---

## 3. Cài đặt dependencies

Di chuyển vào thư mục `frontend/`:

```powershell
cd frontend
```

- Khi phát triển trên máy cá nhân:
  ```powershell
  npm install
  ```
- Khi cần cài đặt chính xác theo `package-lock.json` (giống môi trường CI):
  ```powershell
  npm ci
  ```

---

## 4. Cấu hình biến môi trường và Vite Proxy

Tạo file `.env` từ file mẫu `.env.example` (lưu ý: **không commit file `.env`**):

```powershell
Copy-Item .env.example .env
```

Các biến môi trường trong `.env`:

| Biến | Giá trị mặc định | Ý nghĩa |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | Base URL cho Axios client. Khi để `/api/v1`, trình duyệt gửi request cùng origin tới Vite dev server và được Vite proxy chuyển tiếp sang Backend mà không cần thay đổi cấu hình CORS trên Backend. |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Địa chỉ FastAPI Backend đích mà Vite dev server chuyển tiếp các request bắt đầu bằng `/api`. |
| `VITE_API_TIMEOUT` | `10000` | Thời gian chờ tối đa của mỗi request Axios (tính bằng mili-giây). |

> **Lưu ý bảo mật:** Vite dev server và preview server được cấu hình lắng nghe trên `127.0.0.1` thay vì `0.0.0.0` để tránh mở proxy công khai ra mạng nội bộ khi chưa được kiểm soát.

---

## 5. Cách chạy Backend đi kèm

Trước khi kiểm tra kết nối từ giao diện React, cần khởi chạy FastAPI Backend tại `http://127.0.0.1:8000`.

### Cách 1: Chạy toàn bộ stack qua Docker Compose (từ thư mục gốc dự án)

```powershell
Copy-Item .env.example .env
# Cập nhật các giá trị mật khẩu CHANGE_ME trong file .env ở thư mục gốc trước khi chạy
docker compose up --build -d
```

### Cách 2: Chạy nhanh tiến trình FastAPI local để kiểm tra `/api/v1/health`

Nếu chỉ cần kiểm tra kết nối `GET /api/v1/health` mà chưa cần kết nối MySQL:

```powershell
cd backend
uv sync --locked
$env:RETAILOPS_DB_HOST="127.0.0.1"
$env:RETAILOPS_DB_NAME="retailops"
$env:RETAILOPS_DB_USER="retailops_app"
$env:RETAILOPS_DB_PASSWORD="local_dev_only_password"
uv run --locked python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Kiểm tra nhanh trên trình duyệt hoặc terminal:
- Health endpoint: `http://127.0.0.1:8000/api/v1/health` → `{"status":"ok"}`
- Swagger UI: `http://127.0.0.1:8000/docs`

---

## 6. Cách chạy Vite Development Server

Tại thư mục `frontend/`:

```powershell
npm run dev
```

Mở trình duyệt tại địa chỉ:
- `http://127.0.0.1:5173`

Giao diện sẽ tự động gọi `GET /api/v1/health` thông qua Axios (`src/api/client.js`) và hiển thị:
- Trạng thái **Đang kiểm tra** khi request đang xử lý.
- Trạng thái **Kết nối thành công** kèm dữ liệu JSON thực tế (`{"status": "ok"}`) và mã HTTP `200` từ FastAPI.
- Trạng thái **Mất kết nối** kèm thông báo tiếng Việt rõ ràng và nút **Thử lại kết nối** nếu Backend chưa bật hoặc không phản hồi.

---

## 7. Kiểm tra Lint và Production Build

Trước khi tạo commit hoặc mở Pull Request, chạy đầy đủ các bước kiểm tra tương ứng với `.github/workflows/frontend-ci.yml`:

```powershell
cd frontend
npm run lint
npm run build
```

Xem thử bản build production tại `http://127.0.0.1:4173`:

```powershell
npm run preview
```

---

## 8. Các lỗi thường gặp và cách xử lý

1. **Giao diện báo "Mất kết nối" hoặc lỗi HTTP 500/502 từ Vite proxy:**
   - **Nguyên nhân:** FastAPI Backend chưa chạy hoặc đang chạy ở cổng khác `8000` (ví dụ `BACKEND_HOST_PORT=18000`).
   - **Cách xử lý:** Đảm bảo Backend đang chạy, sau đó kiểm tra `http://127.0.0.1:8000/api/v1/health`. Nếu Backend dùng cổng khác, cập nhật `VITE_API_PROXY_TARGET` trong `frontend/.env` rồi khởi động lại `npm run dev`.

2. **Lỗi CORS trên trình duyệt khi gọi API:**
   - **Nguyên nhân:** Đặt `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1` (gọi trực tiếp khác origin) trong khi Backend không bật CORS cho origin đó.
   - **Cách xử lý:** Giữ `VITE_API_BASE_URL=/api/v1` trong `frontend/.env` để đi qua Vite dev proxy.

3. **Lỗi `Port 5173 is already in use`:**
   - **Nguyên nhân:** Có một tiến trình Vite khác đang chiếm cổng `5173` (`strictPort: true`).
   - **Cách xử lý:** Tắt tiến trình Vite cũ trước khi chạy lại `npm run dev`.

4. **Lỗi `EPERM: operation not permitted` khi chạy `npm ci` hoặc `npm install` trên Windows / OneDrive:**
   - **Nguyên nhân:** OneDrive đồng bộ file hoặc tiến trình `vite` đang chạy giữ khóa thư mục `node_modules/.bin`.
   - **Cách xử lý:** Dừng `npm run dev`, đợi vài giây rồi chạy lại lệnh `npm install` hoặc `npm ci`.
