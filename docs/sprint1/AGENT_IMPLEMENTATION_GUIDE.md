# RETAILOPS V1.0 — HƯỚNG DẪN TRIỂN KHAI MODULE CHO AI AGENT

**Phiên bản:** S1-IMPL-1.0 · **Ngày:** 06/11/2026
**Phạm vi:** Sprint 1 — hướng dẫn implementation cho Backend, hỗ trợ Frontend kiểm tra contract.
**Trạng thái:** **Đề xuất để Tech Lead review/merge**; không tự coi là thay thế SRS, ERD hoặc API Contract.

> **Đọc theo thứ tự:** `docs/requirement/RetailOps_SRS_Approved.md` → `docs/database/RetailOps_ERD_V1.0.dbml` → `SPRINT1_API_CONTRACT` (bản đã được nhóm phê duyệt) → tài liệu này → code hiện tại. Mâu thuẫn phải báo Tech Lead; **không tự sửa ERD/SRS, không tự thêm endpoint hoặc cột**.
>
> Đây là *implementation guide*, không phải lệnh viết lại Backend. Các path/class bên dưới là **quy ước đề xuất**; agent phải đọc code thật trước và giữ convention đang hoạt động. Các API phải tuân thủ contract đã duyệt, không suy ra JSON payload từ ORM.

## 1. Sơ đồ phụ thuộc và mục tiêu triển khai

```text
AUTH:  Hiếu User/Approval/Session models ─┐
                                          ├→ Hiếu Register/Login/Refresh/Logout → Lâm Auth UI
       Dương Notification model/API ──────┘
CATALOG: Na Na Category/Supplier models → Category API ────────────────┐
         Dương bàn giao Product/Inventory schema → Lan Anh Product API ├→ Tân Product UI
         Na Na Supplier API ────────────────────────────────────────────┘
RECEIPT: User + Product + Supplier schema → Dương Receipt models → Lan Anh Purchasing (S2)
```

**Ưu tiên S1:** migration + model merge → contract API ổn định → API đơn giản + test → Auth/Notification transaction → FE dùng mock/real → regression. **Tối 08/11** là mốc preview, **10/11** là quality gate; deadline LMS 11/11 cần được điều chỉnh/quản lý rõ.

**Ownership:** Hiếu Auth/transaction; Dương Notification + Receipt foundation; Lan Anh Product; Na Na Category/Supplier; Lâm React/Auth/FE shared; Tân Product UI. Product model do Dương bàn giao, không tự tạo lại ở Product PR. API Product read/list tối thiểu do Lan Anh làm S1; Na Na mở rộng search/filter/sort cùng endpoint S2.

## 2. Cấu trúc module và trách nhiệm từng layer

```text
backend/app/
├── api/router.py                 # router tổng, include module routers
├── core/
│   ├── config.py                 # Settings hiện có; không đưa business errors vào đây
│   ├── exceptions.py             # AppException + các lớp con
│   └── exception_handlers.py     # handler tập trung, đăng ký trong app factory
├── db/                           # engine, session, Base hiện có
└── modules/                      # tên thư mục chỉ áp dụng sau khi thống nhất PR nền
    ├── auth/
    ├── notifications/
    ├── categories/
    ├── suppliers/
    ├── products/
    └── purchasing/
       # trong mỗi module: router.py, service.py, repository.py,
       # models.py, schemas.py; thêm dependencies.py khi thực sự cần
backend/migrations/versions/     # revisions theo một chuỗi đã review
backend/tests/                   # unit + API + MySQL integration
```

Nếu codebase đã có layout khác, **không mass-refactor** để khớp cây trên. Đề xuất thay đổi layout bằng PR riêng trước khi các agent cùng triển khai.

| Layer | Được làm | Không được làm |
|---|---|---|
| **Router** | Khai báo URL/HTTP status, Pydantic Request/Response, dependency auth/role, gọi Service | SQL, business rule phức tạp, tự commit, trả ORM raw |
| **Service (OOP)** | Điều phối use case, invariant, transaction/UoW, gọi các Service liên quan, raise domain exception | Tự quản session riêng cho service con, trả HTTP response trực tiếp |
| **Repository (OOP)** | Query SQLAlchemy, filter quyền ngay SQL, lock/select/update cần thiết, `flush` khi cần ID | `commit`, tạo token/cookie, swallow DB errors, check role thay Router/Service |
| **Database/Models** | ORM khớp ERD, FK/UNIQUE/CHECK/index, migration, session lifecycle | Field tự phát, business rule chỉ nằm ở callback ORM |
| **Request/Response schemas** | Validate type/length/enum; `extra='forbid'` cho input; whitelist output | Expose `password_hash`, token digest, internal cost; coi schema validation thay cho transaction validation |

**Transaction mẫu (minh họa, không phải interface đã được chốt):**

```python
class ProductService:
    def __init__(self, products: ProductRepository, inventory: InventoryRepository):
        self.products = products
        self.inventory = inventory

    def create(self, session, data, actor):
        # auth + business validation trước mutation; kiểm tra lại dưới lock khi cần
        product = self.products.add(session, data)
        session.flush()                     # lấy product.id, CHƯA COMMIT
        self.inventory.add_zero(session, product.id)
        return product                      # UoW/use-case boundary commit 1 lần
```

- Một HTTP use case có **một transaction owner**. Router/dependency/UoW cấp `Session` cho toàn bộ luồng. Không được hiểu snippet trên là có thể trả response trước khi commit. Response phải được tạo từ dữ liệu đã commit hoặc được xử lý nhất quán khi commit thất bại.
- MySQL/InnoDB là nguồn dữ liệu có thẩm quyền; kiểm tra trạng thái trước ghi, `flush`, atomic commit/rollback; kiểm tra các `IntegrityError` theo constraint cụ thể. Không dùng Redis lock cho database invariant.
- Với protected request, JWT **và** phiên sống/role/status trong MySQL đều phải được kiểm tra; không dùng FE route guard làm security boundary.

## 3. Exception OOP tập trung (theo project FastAPI mẫu)

Project mẫu sử dụng `app/core/exceptions.py` (`AppException` và subclass) và `app/core/handlers.py`. RetailOps kế thừa **cách tổ chức**, nhưng **không sao chép response** `{success,message,error_code,details}` của project cũ: API Contract yêu cầu `{code,message,details}`.

**Khóa tên file ở PR nền:** `app/core/exceptions.py` và `app/core/exception_handlers.py` (nếu đã có `handlers.py` trong code thật thì sử dụng tên có sẵn; tránh tạo song song).

```python
class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

class ResourceNotFoundError(AppException):
    def __init__(self, message="Không tìm thấy tài nguyên."):
        super().__init__("RESOURCE_NOT_FOUND", message, 404)

class ConflictError(AppException):
    def __init__(self, code="CONFLICT", message="Dữ liệu xung đột."):
        super().__init__(code, message, 409)
```

Tạo thêm subclasses **khi có use case cụ thể**, không dựng hàng chục class chưa sử dụng. Bộ mapping chuẩn:

| HTTP | Code | Trường hợp chính |
|---|---|---|
| 401 | `UNAUTHENTICATED`, `INVALID_CREDENTIALS`, `SESSION_INVALID` | Thiếu token, login lỗi chung, phiên revoked/expired |
| 403 | `FORBIDDEN` | ACTIVE Staff gọi Admin API |
| 404 | `RESOURCE_NOT_FOUND` | Resource không tồn tại hoặc nằm ngoài scope actor |
| 409 | `DUPLICATE_SKU`, `INVALID_STATE`, `STALE_VERSION`, `CONFLICT` | Unique, state transition, concurrent update |
| 422 | `VALIDATION_ERROR` | Request field/enum/length/price invalid |
| 429/503 | `RATE_LIMITED` / `SERVICE_UNAVAILABLE` | **Chỉ khi** limiter/dependency tương ứng đã triển khai |
| 500 | `INTERNAL_SERVER_ERROR` | Lỗi ngoài dự kiến; không lộ SQL/traceback |

Handler tập trung chuyển `AppException`, `RequestValidationError`, và lỗi ngoài dự kiến thành JSON `{ "code": "...", "message": "...", "details": null }`; details 422 chỉ chứa field/reason đã sanitize. Không log password, token, cookie, raw body, DB credential. `IntegrityError` **không luôn là 409**: mapping theo unique/FK/check cụ thể; lỗi khác rollback và báo 500 an toàn. **Không dùng try/except phủ mọi lỗi ở mỗi Router.**

## 4. Interface giữa các module — khóa trước khi code

| Caller → Callee | Hợp đồng nội bộ bắt buộc |
|---|---|
| **Auth → Notification (Hiếu ↔ Dương)** | Auth điều phối `User(PENDING_APPROVAL) + Approval(PENDING) + AdminNotification` trong **1 MySQL transaction**. Dương cung cấp `create_for_approval(session, admin_user_id, approval_request_id)`; không tự commit/close session; `approval_request_id` UNIQUE. Tên/signature cụ thể phải được cả hai xác nhận trước PR. |
| **Product → Category (Lan Anh ↔ Na Na)** | Product kiểm tra Category tồn tại và `ACTIVE` trong transaction; không sửa Category qua Product Service. Category không tự inactive Product đã tham chiếu. |
| **Product → Inventory (Lan Anh ↔ Dương schema)** | `POST Product` tạo Product và Inventory `quantity=0`, `stock_version=0` **cùng transaction**. `ProductRead` lấy tồn từ Inventory nhưng create/update không nhận `quantity` hoặc `stock_version`. |
| **Notification → Approval** | `GET notifications` chỉ chọn dòng theo `admin_user_id` trong SQL; `approval_request_id` là link tới hồ sơ, không phải quyền tự approve. API approve/reject thuộc S2, không tự thêm trong S1. |
| **Receipt → Supplier/Product/User** | S1 chỉ models/migration theo ERD; receipt headers/items FK đầy đủ, composite PK `(receipt_id,product_id)`; chưa triển khai confirm/stock adjustment. |

**Bàn giao trước giờ code:** mỗi owner xác nhận names/import paths, DTO fields, service signature và commit/rollback owner vào PR/contract. Không để agent tự phát minh interface liên module.

## 5. Checklist triển khai theo từng task LMS

Tất cả path dưới đây có prefix `/api/v1`. **Contract chi tiết là nơi quyết định cuối cùng về request/response**, phần dưới là thứ tự triển khai và test cases tối thiểu.

### 5.1 Hiếu — `T3C9A19` models → `T3C9A33` Auth

**LMS làm trước:** `users`, `staff_approval_requests`, `auth_sessions`, `refresh_tokens` ORM/migration; seed 1 Admin an toàn; register/login; kế tiếp refresh/logout.

| API | Service flow | Các test / ngoại lệ bắt buộc |
|---|---|---|
| `POST /auth/register` | Normalize email → hash password → create User + Approval + 1 Notification **atomically** → 202 chung | 422 invalid; duplicate pending không nhân bản; 2 concurrent register chỉ 1 User; forced notification failure rollback toàn bộ; REJECTED không tự tạo User mới |
| `POST /auth/login` | Check credentials + ACTIVE → create session ≤8h, refresh digest DB, JWT 15m, cookie → 200 | 401 generic cho email không tồn tại/sai mật khẩu/PENDING/REJECTED; không log hash/token; test Admin seed |
| `GET /auth/csrf` + `POST /auth/refresh` | CSRF bootstrap; verify Origin/CSRF; khóa session row, consume refresh digest, rotate generation, tạo JWT/cookie mới | 401 invalid/replay/expired; concurrency: chỉ 1 refresh thắng; không kéo dài absolute session |
| `POST /auth/logout` | Verify cookie/Origin/CSRF → revoke session → clear cookie → 204 | Session revoked khiến access JWT cũ bị từ chối; repeat logout safe |

**Sau phần ưu tiên LMS, vẫn trong S1:** negative tests/Auth full integration, csrf cold-start, Notification race. **Không tuyên bố Auth đạt toàn bộ SRS** nếu thiếu Staff Approval, Reset, Outbox/Email (S2). Do not hardcode seeded Admin password.

### 5.2 Dương — `T3C9B8A` → `T3C9BA4` Notification; Receipt foundation

**LMS làm trước:** model `admin_notifications`/migration, service create-for-approval + 4 endpoint; bàn giao Product/Inventory schema (`T3C9AD1`) cho Lan Anh. **Sau đó:** Receipt models ở PR riêng, không gộp schema lẫn domain Notification.

| API | Flow | Test / lỗi |
|---|---|---|
| `GET /admin/notifications` | Current Admin → SQL filter owner → list paginated, stable sort | 401/403; không đọc được notification người khác; `unread_only` đúng |
| `GET /admin/notifications/unread-count` | Count `read_at IS NULL` theo current Admin | 403 Staff; count chuẩn |
| `PATCH /admin/notifications/{id}/read` | Chỉ set `read_at` nếu NULL; response read DTO | 404 ngoài owner; repeat không đổi `read_at` |
| `PATCH /admin/notifications/read-all` | Chỉ update unread của Admin hiện tại; trả affected-row count | 403 Staff, multi-user isolation, concurrent repeat không đếm sai |

**Cấm thêm các cột** `title`, `message`, `url`, `is_read`; ERD chỉ có `admin_user_id`, `approval_request_id`, `created_at`, `read_at` ngoài PK. Test duplicate registration cùng `approval_request_id` không tạo 2 notification. Receipt S1 **không có HTTP confirm**.

### 5.3 Na Na — `T3C9D63` → `T3C9D7D` Category/Supplier

**LMS làm trước:** migration Category/Supplier → Category API để unblock Product → Supplier API; seed idempotent.

| API | Flow | Test / lỗi |
|---|---|---|
| `GET /categories`, `GET /categories/{id}` | Admin/Staff → list/detail read DTO | 401/404/422 bad filter; pagination bound |
| `POST /categories`, `PATCH /categories/{id}`, `PATCH /categories/{id}/status` | Admin-only; name trim, 1–120; status ACTIVE/INACTIVE | 403 Staff, 404, 422 empty/overlength, inactive Category không được gán cho Product mới |
| `GET /suppliers`, `GET /suppliers/{id}` | Admin-only → list/detail | 403 Staff, 404, pagination |
| `POST /suppliers`, `PATCH /suppliers/{id}`, `PATCH /suppliers/{id}/status` | Admin-only; name 1–160; email/phone nullable đúng schema | 403, 404, 422; PATCH null clear contact; không cascade phá Receipt |

**ERD không có UNIQUE(name)** cho Category/Supplier. Không tạo unique index hoặc tự trả 409 theo tên chỉ vì suy đoán. **Sau đó:** hỗ trợ Product Category test và FE mock data. Advanced Product Search thuộc S2.

### 5.4 Lan Anh — `T3C9AEB` Product API

**LMS làm trước:** nhận Product/Inventory model của Dương + Category model của Na Na; triển khai Product read/list tối thiểu → create → update/status; test theo transaction. (LMS Product CRUD là trọng tâm; read/list được bổ sung S1 để unblock Tân.)

| API | Flow | Test / lỗi |
|---|---|---|
| `GET /products`, `GET /products/{id}` | ACTIVE Admin/Staff → Product DTO join Inventory, stable pagination | 401/404; không lộ cost; tránh N+1 khi list |
| `POST /products` | Admin → validate Category ACTIVE + SKU + `sale_price_vnd>0` → Product + Inventory(0) **1 transaction** → 201 | 403 Staff; 404 Category; 409 duplicate SKU/race; 422 price; forced Inventory failure rollback Product |
| `PATCH /products/{id}` | Admin → whitelist sku/name/category_id/sale_price_vnd → 200 | 404, 409 duplicate SKU, 422 invalid; forbid quantity/stock_version; new Category ACTIVE |
| `PATCH /products/{id}/status` | Admin → set ACTIVE/INACTIVE, giữ stock/lịch sử | 403 Staff; 404; status roundtrip; inactive bị chặn ở POS/Receipt (kiểm thử liên module S2) |

**Sau đó:** phối hợp Tân real API integration; không nhận search/filter/sort nâng cao ngoài contract S1. Money phải integer VND, SKU canonical và unique DB theo ERD.

### 5.5 Lâm `T3C9E1A`/`T3C9E33` và Tân `T3C9C6C`/`T3C9C86`

- **Lâm:** React Router, auth client, access JWT **memory**, refresh **single-flight**, cookie credentials, CSRF/Origin-aware auth calls; Register/Login/Pending UI. Không lưu token trong localStorage. Mock Reset/Approval được gắn nhãn chưa tích hợp; API backend S2 không giả là completed.
- **Tân:** dùng UI Design Freeze, **không vẽ lại wireframe**; Product list/detail/form → mock đúng `ProductRead` → đổi sang real API khi Lan Anh merge. Loading/empty/401/403/409/422/network, Staff read-only, disable repeated submit. Search/filter nâng cao mock-only đến S2.
- **FE contract tests:** fixtures phải khớp field và HTTP status; không tự tạo `data` wrapper; không tự đọc refresh cookie. Frontend merge PR nhỏ vào `develop`, không chờ BE hoàn tất mới mở PR.

## 6. Quy tắc test và PR cho AI agent

**Test theo rủi ro:**

- **Pure unit:** normalize/validate, rule helpers; không cần DB nếu logic thuần.
- **API tests:** status/error envelope/field whitelist/RBAC; test thật qua FastAPI client.
- **MySQL integration:** ORM FK/UNIQUE/CHECK, transaction rollback, seed idempotence, migration; **không dùng SQLite** để chứng minh InnoDB.
- **Concurrency:** register duplicate, refresh rotation, Product duplicate SKU, Notification read/read-all. Dùng nhiều transaction độc lập khi cần chứng minh race; không viết test mock rồi gọi đó là concurrency test.
- **Frontend:** lint/build và critical states; mock contract fixtures; smoke API thật sau merge.

**PR bắt buộc ghi:** `[LMS-ID]`, scope/owner, file changed, schema/migration impact, HTTP/DTO changes, security/transaction notes, test commands/results, blocker và FE handoff. Reviewer chỉ approve khi CI, test và migration phù hợp PASS. Ghi chính xác phần chưa test, không claim pass bằng ảnh Swagger.

**Migration:** baseline `20261105_01` → Hiếu/Na Na schema căn bản → Dương Product/Inventory schema đã bàn giao → Notification → Receipt. Không tạo song song nhiều Alembic heads trên `develop`; mỗi PR phải cập nhật với head mới nhất, kiểm tra `alembic heads`, `upgrade head` trên DB sạch và rollback test phù hợp khi revision thay đổi. Bảo vệ volume cũ, không chạy reset dữ liệu ngoài môi trường test tự quản lý.

**Code review Security/System Design:** kiểm tra JWT/session state, CSRF + CORS allowlist, field-level leaks, 401/403/409/422, no implicit commit, no arbitrary SQL/sort, index cho list, N+1, input bounds, rollback/concurrency và không lộ secrets. Không thêm microservice, distributed transaction hoặc Redis distributed lock trong S1.

## 7. Prompt dùng cho một task cụ thể

```text
Bạn là Backend Engineer triển khai RetailOps V1.0.
ĐỌC trước khi sửa: RetailOps_SRS_Approved.md, RetailOps_ERD_V1.0.dbml,
SPRINT1_API_CONTRACT (bản đã khóa), AGENT_IMPLEMENTATION_GUIDE.md và code hiện tại.
Task LMS: <ID>. Owner: <người>. Module: <module>.

1. Trước khi code, báo cáo dependency, file sẽ sửa, migration impact,
   request/response DTO, role, lỗi và transaction owner.
2. Không đổi SRS/ERD/API Contract; không sửa module của người khác; không tự
   commit trong Repository; dùng exception OOP tập trung.
3. Triển khai Router → Service → Repository → ORM + Pydantic schemas,
   tái dùng session/UoW hiện có. Không tạo layer hình thức nếu codebase đã có.
4. Viết unit/API/MySQL integration/negative tests theo rủi ro của task.
5. Chạy tests, lint, migration checks; báo PASS/FAIL thực tế và limitations.
6. Gửi diff summary, test evidence và nội dung PR có LMS ID.
Nếu dependency chưa có trên branch, chỉ tạo code độc lập khi contract rõ;
không tự sáng tạo model/field hoặc sửa file ngoài scope để 'cho chạy'.
```

## 8. Điều kiện hoàn thành và giới hạn

- **LMS DONE ≠ code tồn tại trên local**: cần evidence đúng yêu cầu LMS; **Engineering DONE** cần PR merge `develop`, CI xanh, test và tích hợp tương ứng.
- **08/11:** preview có ghi rõ real/mock; **10/11:** Sprint 1 quality gate; deadline LMS 11/11 vượt timebox phải do PO/Scrum Master giải quyết.
- S1 không tự triển khai full Staff Approval, Reset/Reapply, RabbitMQ/Celery, Redis, advanced search, Receipt Confirm/Inventory Adjustment, AI. Những việc đó vẫn thuộc baseline S2/S3 và có dependency riêng; nếu chuyển lên sớm phải sửa kế hoạch kiểm soát.
- Tài liệu này **không khóa tên class hay function một cách máy móc**; những interface liên module chỉ được coi là đã khóa khi các owner và Tech Lead duyệt. Khi contract đổi: cập nhật source, DTO, fixtures, OpenAPI và thông báo BE/FE trong cùng PR.
