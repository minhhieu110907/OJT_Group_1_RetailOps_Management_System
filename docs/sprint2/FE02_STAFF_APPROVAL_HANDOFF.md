# RetailOps V1.0 — FE-02 / AUTH-03: Hướng dẫn màn hình duyệt Staff

> Trạng thái: hướng dẫn tích hợp cho Lâm sau thay đổi API AUTH-03. Chuẩn HTTP: `contracts/openapi.yaml`. Không tạo API mới khi đã có API tương ứng.

## 1. Quyết định và phạm vi

- Không có `full_name` trong `users`, không thêm cột hoặc migration; sử dụng email làm định danh hiển thị.
- Chỉ Admin ACTIVE được xem và quyết định duyệt/từ chối; Staff không được truy cập API này.
- Dữ liệu list được trả về trong một API (JOIN từ `users.email_normalized`), không gọi N API để lấy user tương ứng.
- Không sửa API đăng ký/đăng nhập; không sửa response của hai POST quyết định.

## 2. HTTP contract chính thức

**Danh sách chờ duyệt**

```http
GET /api/v1/staff-approvals?status=PENDING&page=1&page_size=20
Authorization: Bearer <access_token>
```

Response 200 (ví dụ):

```json
{
  "items": [{
    "id": 12,
    "user_id": 8,
    "email": "staff@example.com",
    "attempt_no": 1,
    "status": "PENDING",
    "requested_at": "2026-11-12T02:00:00Z",
    "decided_by": null,
    "decided_at": null,
    "decision_reason": null
  }],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

- `items[].id` = **approval request ID**, dùng làm URL parameter cho approve/reject.
- `items[].user_id` = ID tài khoản Staff; **không** dùng trong URL quyết định.
- `items[].email` = email đã chuẩn hóa, chỉ phục vụ nhận diện trong UI; không chứa full name.
- `requested_at` trả UTC; khi hiển thị chuyển sang `Asia/Ho_Chi_Minh`, không tự giả định là giờ địa phương.
- `status` tùy chọn: `PENDING`, `APPROVED`, `REJECTED`; mặc định không truyền nghĩa là không lọc. Màn hình chờ duyệt luôn truyền `status=PENDING`.
- `page >= 1`, `1 <= page_size <= 100`; mặc định `page=1`, `page_size=20`.
- Phân trang dùng `total`; danh sách theo `requested_at DESC, id DESC`.

**Duyệt:**

```http
POST /api/v1/staff-approvals/12/approve
Authorization: Bearer <access_token>
```

**Từ chối:**

```http
POST /api/v1/staff-approvals/12/reject
Authorization: Bearer <access_token>
Content-Type: application/json

{"reason":"Không đáp ứng điều kiện tuyển dụng"}
```

- Lý do từ chối là chuỗi không trắng, tối đa 500 ký tự; trim input trước gửi.
- Cả hai POST trả `ApprovalRead` như cũ, **không chứa email**. Frontend không lấy email từ response POST.
- Thành công: cập nhật phản hồi người dùng, refetch list + total để tránh dữ liệu stale.

## 3. Màn hình Admin (FE-02)

Hiển thị các cột: **Email | Ngày yêu cầu | Trạng thái | Thao tác**. Mỗi dòng PENDING có hai nút **Duyệt** và **Từ chối**. Từ chối phải mở modal xác nhận và nhập lý do. Trong lúc gửi, vô hiệu hóa nút để tránh double-click; đây không thay thế kiểm soát concurrency ở backend.

Trạng thái giao diện cần có: loading/skeleton; empty (`items=[]`); lỗi kết nối + thao tác retry GET; phân trang; đang gửi quyết định; thành công; stale/conflict.

## 4. Xử lý lỗi và an toàn

| HTTP | FE xử lý |
| --- | --- |
| 401 | Chuyển vào quy trình auth/session hiện tại; không hiển thị dữ liệu đã cache khi không còn phiên hợp lệ |
| 403 | Hiển thị không đủ quyền; không tự gọi lại với role khác |
| 404 | Thông báo yêu cầu không tồn tại, làm mới danh sách |
| 409 | Thông báo hồ sơ đã thay đổi/đã xử lý; refetch danh sách; **không tự retry POST** |
| 422 | Hiển thị lỗi input/bộ lọc, giữ dữ liệu người dùng nhập hợp lệ |
| 5xx/network | Hiển thị lỗi; có thể retry GET, nhưng không tự retry POST khi chưa biết kết quả server |

Không render mật khẩu, token hoặc thông tin người dùng không cần thiết. Email không phải bằng chứng xác minh nhân sự; Admin phải kiểm tra thực tế trước khi duyệt.

## 5. Acceptance / kiểm tra với Backend

- Một Staff đăng ký hợp lệ xuất hiện với email đúng; `id` URL của POST là approval ID.
- API chỉ trả trường trong DTO, không có `password_hash`.
- Đổi filter và page không làm sai email hoặc tổng số; khi không còn pending, empty state hiển thị đúng.
- Admin có thể duyệt/từ chối theo trạng thái hợp lệ; thao tác stale có 409 và UI refetch.
- Staff hoặc người chưa đăng nhập không thể xem danh sách/dùng quyết định.
- Test tương ứng: `backend/tests/modules/auth/test_staff_approval_api.py`, `backend/tests/modules/auth/test_staff_approval_unit.py`, `backend/tests/integration/test_staff_approval.py`.

## 6. Handoff

Hiếu cung cấp contract/API và chứng cứ CI; Lâm tích hợp FE-02 theo đúng path/trường ở trên, ACK bằng test và PR frontend riêng. Quyết định nào thay đổi contract phải cập nhật `contracts/openapi.yaml` cùng code và tests trước khi tích hợp.
