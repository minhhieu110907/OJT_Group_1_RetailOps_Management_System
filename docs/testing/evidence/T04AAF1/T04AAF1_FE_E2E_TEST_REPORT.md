# Báo cáo Bằng chứng Kiểm thử Frontend Nghiệp vụ (E2E trên API & DB thật) — T04AAF1

- **Task ID:** `T04AAF1`
- **Tên công việc:** Kiểm thử frontend nghiệp vụ (Auth, POS, Checkout/Cancel, Dashboard trên API thật)
- **Người thực hiện:** Vũ Trần Lâm
- **Người nghiệm thu:** Lan Anh (QA)
- **Nhánh kiểm thử:** `test/t04aaf1-fe-business-e2e` (tách từ `develop` tại commit `ddf13a7`)
- **Thời gian thực hiện:** `2026-11-22` (UTC+7 / `Asia/Ho_Chi_Minh`)
- **Kết luận tổng thể:** **PASS (18/18 kịch bản E2E API/DB thật + 392/392 unit/integration FE + 6/6 theme test + lint/build sạch)**

---

## 1. Môi trường & Nguyên tắc Kiểm thử

- **Stack thực thi:** Docker Compose live stack (8 container đang chạy `Up / healthy`):
  - `nginx` (`http://localhost`, phục vụ SPA production build và reverse proxy `/api/v1/*`)
  - `backend` (FastAPI live API)
  - `mysql` (MySQL 8.0 thật)
  - `redis` (Redis 7 thật — lưu rate-limit, session/AI concurrency guard)
  - `rabbitmq`, `mailpit`, `email-worker`, `outbox-publisher`
- **Nguyên tắc đối soát (Real API Only):**
  - Toàn bộ kiểm thử E2E chạy trực tiếp qua `http://localhost` (Nginx -> FastAPI -> MySQL 8 + Redis), **không sử dụng mock fallback**.
  - Các tài khoản nhân viên sinh tạm trong quá trình kiểm thử đều được khóa (`POST /api/v1/admin/staff/{id}/lock`) sau khi kết thúc để giữ sạch dữ liệu vận hành; đơn hàng kiểm thử được hủy hoàn tác để đảm bảo bất biến tồn kho (`stock_final == stock_initial`).

---

## 2. Kết quả Automated Frontend Suite (trên `test/t04aaf1-fe-business-e2e`)

| Hạng mục | Lệnh thực thi | Kết quả | Chi tiết ghi nhận |
| --- | --- | --- | --- |
| Static Lint | `npm --prefix frontend run lint` (`oxlint`) | **PASS** | `0 errors`, `23 warnings` |
| Unit & Component/Page Tests | `npm --prefix frontend test` (`vitest`) | **PASS** | **392/392 tests passed** (`80/80` test files) — bao phủ Auth, Login/Register/Forgot/Reset, POS Cart/Checkout/409 Conflict/Retry, Order History/Detail/Cancel Modal, Dashboard 4 presets/CSV/Cache, Inventory, RBAC Route Guards |
| Theme & Token Contract | `npm --prefix frontend run test:theme` | **PASS** | **6/6 tests passed** |
| Production Bundle Build | `npm --prefix frontend run build` (`vite build`) | **PASS** | Build thành công trong `971ms` (`dist/assets/index-BvGhhBgB.js`) |

---

## 3. Bằng chứng Kiểm thử E2E trên API & DB thật (`http://localhost`)

### 3.1. Hạ tầng SPA & Healthcheck

| Mã TC | Nhóm | Kịch bản kiểm thử | Kết quả kỳ vọng | Kết quả quan sát thực tế | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `E2E-00` | INFRA | `GET /` qua Nginx SPA | `HTTP 200`, trả về `index.html` | `HTTP 200`, `len=505` bytes | **PASS** |
| `E2E-01` | INFRA | `GET /api/v1/health` qua Nginx reverse proxy | `HTTP 200`, `{"status": "ok"}` | `HTTP 200`, `{"status": "ok"}` | **PASS** |

### 3.2. Luồng Auth, Refresh (F5), RBAC, Chống dò tài khoản & Logout

| Mã TC | Nhóm | Kịch bản kiểm thử | Kết quả kỳ vọng | Kết quả quan sát thực tế | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `E2E-A1` | AUTH | Gọi `GET /api/v1/users/me` khi chưa đăng nhập | `HTTP 401` | `HTTP 401` | **PASS** |
| `E2E-A2` | AUTH | Đăng nhập sai mật khẩu (`POST /api/v1/auth/login`) | `HTTP 401` | `HTTP 401` | **PASS** |
| `E2E-A3` | AUTH | Đăng nhập tài khoản `ADMIN` hợp lệ | `HTTP 200`, trả `access_token`, cấp cookie `HttpOnly` refresh | `HTTP 200`, `role=ADMIN`, `refresh_cookie=yes` | **PASS** |
| `E2E-A4` | AUTH | Làm mới phiên (luồng F5 reload): `GET /api/v1/auth/csrf` -> `POST /api/v1/auth/refresh` kèm cookie + `X-CSRF-Token` + `Origin` hợp lệ | `HTTP 200`, xoay vòng `access_token` mới | `HTTP 200`, `rotated=True` (thiếu `Origin` hợp lệ bị chặn `403` theo đúng cơ chế CSRF/Origin check) | **PASS** |
| `E2E-A5` | AUTH | Đăng ký Staff (`POST /api/v1/auth/register`) -> thử đăng nhập khi `PENDING` -> Admin duyệt (`POST /api/v1/staff-approvals/{id}/approve`) -> Staff đăng nhập thành công | Đăng ký `202` (anti-enumeration), đăng nhập khi `PENDING` bị chặn (`401`), sau khi Admin duyệt đăng nhập `200` | Tạo và duyệt thành công `staff_a_id=24`, `staff_b_id=25`; đăng nhập `PENDING` bị chặn đúng quy tắc anti-enumeration; sau duyệt trả `200` + `access_token` | **PASS** |
| `E2E-A6` | RBAC | Tài khoản `STAFF` gọi trực tiếp 5 endpoint chỉ dành cho `ADMIN` | Tất cả trả `HTTP 403` | `GET /dashboard=403`, `GET /purchase-receipts=403`, `GET /suppliers=403`, `GET /staff-approvals?status=PENDING=403`, `POST /ai/query=403` | **PASS** |
| `E2E-A7` | AUTH | Đăng xuất (`POST /api/v1/auth/logout` kèm CSRF + Origin) -> gọi lại `GET /api/v1/users/me` bằng token cũ | Logout `204`, `/users/me` sau đó trả `401` | `logout=204`, `me_after=401` (phiên đã bị thu hồi hoàn toàn) | **PASS** |

> **Ghi nhận bổ sung về Rate Limit (Redis):** Trong quá trình chạy lặp liên tiếp vượt ngưỡng `5 request/60s/IP` của `POST /api/v1/auth/login`, backend thực thi chặn `HTTP 429` đúng theo cấu hình `RETAILOPS_LOGIN_IP_RATE_LIMIT` trên Redis thật.

### 3.3. Luồng POS Checkout, Idempotency/Retry & Xử lý Xung đột 409

| Mã TC | Nhóm | Kịch bản kiểm thử | Kết quả kỳ vọng | Kết quả quan sát thực tế | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `E2E-B1` | POS | Checkout hợp lệ (`POST /api/v1/orders/checkout`) + gửi lại cùng `Idempotency-Key` và cùng payload (mô phỏng retry mạng / double click) | Cả 2 lần trả `HTTP 201`, cùng `order_id`, tồn kho chỉ trừ đúng 1 lần | `HTTP 201 / 201`, `order_id=9 / 9`, tồn kho `95 -> 94`, `creator='Vũ Trần Lâm (Admin)'` | **PASS** |
| `E2E-B2` | POS | Tái sử dụng `Idempotency-Key` của `E2E-B1` với payload khác (`quantity=2`) | `HTTP 409 IDEMPOTENCY_KEY_REUSED` | `HTTP 409`, `code=IDEMPOTENCY_KEY_REUSED` | **PASS** |
| `E2E-B3` | POS | Checkout với `viewed_unit_price_vnd` lệch giá hiện tại trên server | `HTTP 409 PRICE_CHANGED` | `HTTP 409`, `code=PRICE_CHANGED` | **PASS** |
| `E2E-B4` | POS | Checkout với số lượng vượt quá tồn kho khả dụng (`qty_after_ck + 50`) | `HTTP 409 INSUFFICIENT_STOCK` | `HTTP 409`, `code=INSUFFICIENT_STOCK` | **PASS** |

### 3.4. Luồng Lịch sử Đơn hàng & Hủy đơn (Phân quyền, 15 phút, Replay, Hoàn kho)

| Mã TC | Nhóm | Kịch bản kiểm thử | Kết quả kỳ vọng | Kết quả quan sát thực tế | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `E2E-C1` | CANCEL | `Staff B` cố hủy đơn hàng do `Staff A` tạo | `HTTP 403 FORBIDDEN` | `HTTP 403`, `code=FORBIDDEN` | **PASS** |
| `E2E-C2` | CANCEL | `Staff A` hủy đơn của chính mình trong cửa sổ 15 phút (`POST /api/v1/orders/{id}/cancel`) -> gửi lại cùng `Idempotency-Key` -> gửi lại với `Idempotency-Key` mới | Lần 1: `200 CANCELLED`; Replay cùng key: `200`; Hủy lại bằng key mới: `409` | `HTTP 200 / 200 / 409`, `status=CANCELLED`, `creator='NV E2E A 1ff95864'` | **PASS** |
| `E2E-C3` | CANCEL | `ADMIN` hủy đơn `#9` trong cùng ngày VN -> kiểm tra lại tồn kho sản phẩm | `HTTP 200`, tồn kho hoàn trả khớp chính xác số lượng ban đầu (`95`) | `HTTP 200`, `stock=95 (initial=95)` — bảo toàn bất biến tồn kho | **PASS** |

### 3.5. Kiểm thử Dashboard Hoàn chỉnh (4 Presets & Xuất CSV)

Đã đối soát đầy đủ API contract `GET /api/v1/dashboard?from=...&to=...` trên 4 mốc thời gian theo múi giờ Việt Nam (`Asia/Ho_Chi_Minh`, ngày `2026-11-22`) và chức năng xuất báo cáo CSV:

| Mã TC | Preset / Endpoint | Khoảng ngày (VN) | Doanh thu (VND) | Đơn hoàn tất | Đơn đã hủy | Sản phẩm sắp hết (`low_stock_count`) | Trạng thái |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `E2E-D1a` | `TODAY` (`GET /api/v1/dashboard`) | `2026-11-22 .. 2026-11-22` | `0` | `0` | `2` | `6` | **PASS** (`200`, ghi nhận đúng 2 đơn hủy từ `E2E-C2` & `E2E-C3`) |
| `E2E-D1b` | `LAST_7_DAYS` (`GET /api/v1/dashboard`) | `2026-11-16 .. 2026-11-22` | `856,000` | `3` | `2` | `6` | **PASS** (`200`) |
| `E2E-D1c` | `LAST_30_DAYS` (`GET /api/v1/dashboard`) | `2026-10-24 .. 2026-11-22` | `2,788,000` | `5` | `5` | `6` | **PASS** (`200`) |
| `E2E-D1d` | `THIS_MONTH` (`GET /api/v1/dashboard`) | `2026-11-01 .. 2026-11-22` | `2,788,000` | `5` | `5` | `6` | **PASS** (`200`) |
| `E2E-D2` | CSV Export (`GET /api/v1/analytics/sales/daily/export/csv`) | `2026-11-22 .. 2026-11-22` | — | — | — | — | **PASS** (`HTTP 200`, `Content-Type: text/csv; charset=utf-8`, `105 bytes`) |

---

## 4. Ghi nhận Lỗi UI/UX & Bản sửa lỗi Liên quan đã Xử lý trong Quá trình Kiểm thử

Trong quá trình kiểm thử thủ công & E2E trên giao diện thật, các bất cập UI/UX đã được phát hiện và tách thành các PR sửa lỗi độc lập để tránh lẫn phạm vi với báo cáo QA:

1. **POS Mobile Cart & UX (`PR #103`, nhánh `fix/pos-mobile-cart-and-ux`, đã merge vào `develop`):** Sửa trải nghiệm giỏ hàng POS trên màn hình nhỏ và thao tác thanh toán.
2. **Responsive & Nhãn tài khoản Admin (`fix/ui-mobile-responsive-and-admin-label`, commit `1a06a44`, đã merge vào `develop` tại `ddf13a7`):** Hoàn thiện responsive đa màn hình và chuẩn hóa hiển thị nhãn người tạo đơn / tài khoản quản trị.
3. **Khóa cuộn/kéo Modal, nút ẩn/hiện mật khẩu & tối ưu chuyển đổi Preset/Table (`fix/modal-ux-scroll-lock-and-dashboard-table-perf`, commit `b737b52`, đang mở PR):**
   - Ngăn đóng nhầm modal khi bôi đen chữ kéo chuột ra ngoài backdrop; khóa cuộn trang nền khi mở modal.
   - Bổ sung toggle ẩn/hiện mật khẩu cho ô mật khẩu hiện tại và mật khẩu mới.
   - Giữ dữ liệu cũ (`keepPreviousData`) khi chuyển bộ lọc/tab bảng và cache 60 giây cho 4 preset Dashboard để loại bỏ hiện tượng nháy/giật giao diện.

---

## 5. Kết luận Nghiệm thu `T04AAF1`

- Đáp ứng đầy đủ tiêu chí nghiệm thu của `T04AAF1`:
  - Kiểm thử E2E trên **API & MySQL/Redis thật** cho toàn bộ luồng **Auth, RBAC, Refresh/CSRF, Logout, POS Checkout, Idempotency/Retry, 409 Conflicts, Order Cancel (Staff 15 phút / Cross-staff 403 / Admin same-day / Hoàn kho)** đều **PASS 100% (18/18)**.
  - Kiểm thử **Dashboard hoàn chỉnh** (4 preset `TODAY`, `LAST_7_DAYS`, `LAST_30_DAYS`, `THIS_MONTH` + đối soát số liệu đơn hủy trong ngày + xuất CSV) đều **PASS**.
  - Bộ kiểm thử tự động frontend (`oxlint`, `vitest` 392/392, `test:theme` 6/6, `vite build`) đều **PASS**, sẵn sàng bàn giao cho QA (Lan Anh) nghiệm thu.
