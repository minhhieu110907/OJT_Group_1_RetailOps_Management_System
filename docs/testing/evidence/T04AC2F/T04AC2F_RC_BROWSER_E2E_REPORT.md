# Báo cáo Kiểm thử End-to-End Frontend (Chrome Browser & Nginx SPA) — T04AC2F

- **Task ID:** `T04AC2F`
- **Tên công việc:** Kiểm tra end-to-end frontend
- **Người thực hiện:** Vũ Trần Lâm
- **Người nghiệm thu:** Lan Anh (QA)
- **Nhánh kiểm thử:** `test/t04ac2f-rc-browser-e2e` (tách từ `origin/develop` tại commit `3e0d3c0` — đã bao gồm PR #108, PR #109, PR #110)
- **Môi trường thực thi:** Docker Compose live stack (`http://localhost` — Nginx + FastAPI + MySQL 8 + Redis + RabbitMQ + Mailpit + workers, **Real API Only**)
- **Trình duyệt kiểm thử:** Google Chrome (Chrome DevTools live E2E)
- **Kết luận tổng thể:** **PASS (8/8 Browser E2E trên Chrome + 8/8 Nginx SPA Deep-Route Reload + 394/394 FE unit/integration tests + `vite build` PASS · 0 Blocker)**

---

## 1. Kết quả Kiểm thử E2E trực tiếp trên Trình duyệt Chrome (`http://localhost`)

| Mã TC | Luồng nghiệp vụ | Kết quả quan sát thực tế trên Chrome | Ảnh bằng chứng | Trạng thái |
| --- | --- | --- | --- | --- |
| `RC-01` | Đăng nhập (`/login`) | Đăng xuất sạch (`POST /api/v1/auth/logout [204]`), màn hình `/login` hiển thị `Backend: Đã kết nối (API thật)`. Đăng nhập `ADMIN` (`vutranlam1115@gmail.com`) trả `200`, chuyển hướng vào `/dashboard`. | [01_login.png](./screenshots/01_login.png) | **PASS** |
| `RC-02` | Dashboard (`/dashboard`) | Hiển thị đủ 4 thẻ KPI (`Doanh thu bán hàng`, `Số đơn hoàn tất`, `Số đơn đã hủy`, `Giá trị trung bình đơn`), 2 biểu đồ và 4 preset (`Hôm nay`, `7 ngày gần nhất`, `30 ngày qua`, `Tháng này`). Chuyển preset mượt (`GET /api/v1/dashboard` & `/analytics/sales [200]`), có nút **Xuất Excel**. | [02_dashboard.png](./screenshots/02_dashboard.png) | **PASS** |
| `RC-03` | POS Checkout (`/pos`) | Tải danh mục thật (`200`), thêm `1x SP0008 - Nước tinh khiết (1 chai)` (tồn `95 -> 94`), bấm **Xác nhận bán hàng** (`POST /api/v1/orders/checkout [201]`), hiện modal thành công và toast `Thanh toán thành công đơn #11 — Tổng 10.000 ₫.` | [03_pos_checkout.png](./screenshots/03_pos_checkout.png) | **PASS** |
| `RC-04` | Order & Cancel (`/orders`) | Đơn `#11` (`HD-11`) xuất hiện đầu danh sách; mở chi tiết -> bấm **Hủy đơn hàng** -> nhập lý do `Kiem thu E2E T04AC2F hoan tac don` -> `POST /api/v1/orders/11/cancel [200]`, trạng thái chuyển `Đã hủy`, tồn kho hoàn về `95`. | [04_orders_cancel.png](./screenshots/04_orders_cancel.png) | **PASS** |
| `RC-05` | Inventory Modal (`/inventory`) | Danh sách tồn kho hiển thị `SP0008` đã hoàn về `95`. Mở `InventoryAdjustModal` trên `SP0001` xác nhận hiển thị đơn vị **`sản phẩm`** (thay cho `cái`) và **`Dữ liệu từ máy chủ`** (không còn `(v...)`). | [05_inventory_modal.png](./screenshots/05_inventory_modal.png) | **PASS** |
| `RC-06` | Purchasing (`/purchases`) | Điều hướng từ sidebar sang `Nhập hàng`, trang tải sạch, mọi API trả `200`. | [06_purchasing.png](./screenshots/06_purchasing.png) | **PASS** |
| `RC-07` | AI Assistant (`/ai-assistant`) | Điều hướng từ sidebar sang `Trợ lý AI`, trang tải sạch, bảng Smart Reorder & khung chat AI hiển thị bình thường (`200`). | [07_ai_assistant.png](./screenshots/07_ai_assistant.png) | **PASS** |
| `RC-08` | SPA Reload (F5) trên deep route | Tải lại trực tiếp `http://localhost/ai-assistant`: Nginx trả SPA `200`, `GET /api/v1/auth/csrf [200]` & `POST /api/v1/auth/refresh [200]` thành công, **giữ nguyên phiên đăng nhập** tại `/ai-assistant`, không bị văng về `/login`. | [08_spa_reload.png](./screenshots/08_spa_reload.png) | **PASS** |

- **Video ghi hình toàn bộ phiên kiểm thử Chrome (~2 phút 35 giây, 2.89 MB):** [recording.mp4](./recording.mp4)
- **Tổng hợp Network & Console trong phiên Chrome:** `101/101` HTTP requests thành công (`200/201/204/304`), **0 lỗi `4xx/5xx`**, **0 lỗi Console**.

---

## 2. Kiểm thử Tải lại Trang SPA Deep Routes qua Nginx (`http://localhost`)

| Route | HTTP Status | SPA `index.html` (`<div id="root">`) | Kích thước | Kết quả |
| --- | :---: | :---: | :---: | --- |
| `/login` | `200` | `True` | `505 bytes` | **PASS** |
| `/dashboard` | `200` | `True` | `505 bytes` | **PASS** |
| `/pos` | `200` | `True` | `505 bytes` | **PASS** |
| `/orders` | `200` | `True` | `505 bytes` | **PASS** |
| `/inventory` | `200` | `True` | `505 bytes` | **PASS** |
| `/purchasing` | `200` | `True` | `505 bytes` | **PASS** |
| `/ai-assistant` | `200` | `True` | `505 bytes` | **PASS** |
| `/reset-password` | `200` | `True` | `505 bytes` | **PASS** |

---

## 3. Đối soát Phân quyền (`ADMIN`/`STAFF`), HTTP `401/403/409` & Automated Suite

- **Automated Frontend Suite:** `npm --prefix frontend test` **394/394 PASS** (80 suites), `npm --prefix frontend run build` **PASS**.
- **Bằng chứng phân quyền & HTTP `401/403/409` trên API/DB thật (kế thừa và đối soát cùng `T04AAF1` — PR #110 đã merge vào `develop`):**
  - `401 Unauthorized`: `/users/me` khi chưa đăng nhập, đăng nhập sai mật khẩu, và gọi lại `/users/me` sau khi logout (`204 -> 401`).
  - `403 Forbidden`: `STAFF` bị chặn trên 5 endpoint `ADMIN` (`/dashboard`, `/purchase-receipts`, `/suppliers`, `/staff-approvals`, `/ai/query`) và `Staff B` bị chặn khi cố hủy đơn của `Staff A`.
  - `409 Conflict`: `IDEMPOTENCY_KEY_REUSED`, `PRICE_CHANGED`, `INSUFFICIENT_STOCK` trên POS checkout và hủy lại đơn đã hủy bằng key mới.

---

## 4. Danh sách Lỗi Chặn (Blocker List)

- **Số lượng lỗi chặn:** **0 blocker**.
- **Ghi chú cấu hình triển khai Nginx/Docker:** `RETAILOPS_CORS_ORIGINS` trong `.env` triển khai cần bao gồm origin truy cập thực tế (ví dụ `http://localhost`) để `POST /api/v1/auth/refresh` vượt qua kiểm tra `Origin` khi người dùng bấm F5 trên deep route.
