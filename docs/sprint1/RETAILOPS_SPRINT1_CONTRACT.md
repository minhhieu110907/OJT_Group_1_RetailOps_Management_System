# RETAILOPS V1.0

## SPRINT 1 — API CONTRACT & KỊCH BẢN TRIỂN KHAI

Bản rút gọn dành cho nhóm Backend / Frontend / AI coding agent  •  06/11/2026  •  Contract S1-API-1.1

Trạng thái: ĐỀ XUẤT KHÓA — Tech Lead review và merge qua PR trước khi các agent coi là nguồn chuẩn.

## 1. Nguyên tắc chung (giữ từ contract gốc)

- Nguồn ưu tiên: SRS đã duyệt → ERD DBML + Technical Decisions → tài liệu API này → code. Không thay ERD vì một endpoint viết sai.

- Stack: FastAPI + Pydantic + SQLAlchemy + MySQL 8; Modular Monolith. Mỗi module tách Router → Service → Repository → Database/Models; request/response schema tách biệt. Không bắt buộc “4 lớp” đồng nghĩa 4 lần commit.

- Router: HTTP, dependency/auth và DTO; Service: nghiệp vụ, transaction owner; Repository: truy vấn DB, không tự commit; Database: Session/UoW, ORM, migration. Pydantic Request/Response nằm ở schema; tất cả layer có thể dùng OOP và Dependency Injection.

- Chỉ Service ở ranh giới use case/UoW được quyết định commit/rollback; service con và repository dùng chung Session, không commit ngầm. Không dùng Redis/distributed lock để thay transaction MySQL.

- RBAC kiểm tra tại backend. Không log password/JWT/refresh token/CSRF token; không trả giá vốn, giá nhập hoặc internal reason cho Staff. Test trên MySQL với transaction, race, FK và unique.

- HTTP: /api/v1; JSON snake_case; single resource trả DTO trực tiếp; create 201; update 200; logout 204; list {items,total,page,page_size} (mặc định 1/20, tối đa 100). Timestamp UTC ISO-8601; VND integer. Error JSON thống nhất {code,message,details}.

## 2. Sơ đồ task theo thứ tự phụ thuộc

AUTH: Hiếu T3C9A19 (User/Approval/Session model) → Dương T3C9B8A (Notification model) → Hiếu T3C9A33 (Register/Login/Refresh/Logout) → Dương T3C9BA4 (Notification API) → Lâm T3C9E1A + T3C9E33 (Auth UI)

CATALOG: Na Na T3C9D63 (Category/Supplier model) + Dương T3C9AD1 (Product/Inventory model bàn giao) → Na Na T3C9D7D (Category/Supplier API) + Lan Anh T3C9AEB (Product API) → Tân T3C9C86 (Product UI)

PURCHASING: User + Supplier + Product models → Dương T3C9B8A (Receipt model riêng PR) → Lan Anh (Receipt DRAFT API Sprint 2)

FE SHARED: Lâm T3C9E1A (Router/API client/mock adapter) → Lâm T3C9E33 (Auth UI) + Tân T3C9C6C (design-to-component mapping) → Tân T3C9C86 (Product UI)

Các mũi tên là dependency kỹ thuật, không phải yêu cầu mọi người đợi nhau: contract và mock giúp code song song. Chỉ đánh dấu “tích hợp thật” khi API đã merge và smoke test PASS.

## 3. Quy tắc xử lý lỗi OOP tập trung

Tham chiếu cấu trúc từ dự án FastAPI mẫu đã gửi: app/core/exceptions.py + app/core/handlers.py + đăng ký exception handler trong app/main.py. RetailOps dùng app/core/exceptions.py, app/core/exception_handlers.py (hoặc handlers.py; chốt một tên trong PR đầu tiên).

AppException(message, status_code, code, details=None)

├─ AuthenticationError / InvalidCredentialsError (401)

├─ ForbiddenError (403)

├─ ResourceNotFoundError (404)

├─ ConflictError / InvalidStateError / DuplicateSkuError (409)

├─ DomainValidationError (422)

├─ RateLimitedError (429 — chỉ khi Redis hoạt động)

└─ DependencyUnavailableError (503)

- Handler tập trung: bắt AppException, trả {"code":"...","message":"...","details":null}; override RequestValidationError (422) để cùng envelope; handler lỗi không dự kiến trả 500 chung, log an toàn. Không sao chép response cũ {success,error_code} vì khác contract này.

- Service raise domain exception; Router không chứa chuỗi if/except lặp lại; Repository không tự biến mọi IntegrityError thành 409. Unique SKU → 409; FK/missing relation → 404/422 theo contract; lỗi DB không phân loại → 500 và rollback.

- Không dùng exception để bỏ qua authorization, transaction boundary hoặc kiểm tra version. Login dùng lỗi public chung để hạn chế account enumeration.

## 4. Luồng từng người — việc LMS trước, việc S1 sau

### 4.1. Hiếu — T3C9A19 → T3C9A33 (Auth)

Ưu tiên LMS: model users, staff_approval_requests, auth_sessions, refresh_tokens; seed Admin an toàn; Register/Login với session và role; tiếp theo refresh rotation/logout. Không coi Auth SRS hoàn tất khi approval, reset, outbox chưa tích hợp.

| API / Luồng | Request → Response | Ngoại lệ và test tối thiểu |

| --- | --- | --- |

| POST /auth/register | {email,password} → 202 {message}; tạo User PENDING + Approval PENDING + 1 Notification (cùng transaction) | 422 input; duplicate pending giữ response chung; test duplicate/race + forced rollback toàn bộ |

| POST /auth/login | {email,password} → 200 {access_token,token_type,expires_in,user} + refresh cookie | 401 generic cho sai mật khẩu/PENDING/REJECTED; test session 8h, access 15 phút |

| GET /auth/csrf → POST /auth/refresh | CSRF bootstrap → refresh cookie + CSRF header → access mới, cookie rotate | 401 invalid/reuse; Origin/CSRF reject; concurrent refresh chỉ 1 thắng |

| POST /auth/logout | Refresh session + CSRF → 204; revoke DB session và clear cookie | Test access token cũ bị từ chối; logout lặp không lộ session |

Thực hiện tiếp S1: full refresh security tests, error handlers, Auth integration với Notification. Staff Approval GET/approve/reject thuộc T3C9A4D Sprint 2: chốt DTO sớm, không tự đánh dấu đã implement.

### 4.2. Dương — T3C9B8A → T3C9BA4 (Notification + Receipt model)

Ưu tiên LMS: admin_notifications với approval_request_id UNIQUE; 4 API Notification; bàn giao Product/Stock/StockMovement model từ T3C9AD1. Receipt ORM + migration nằm PR riêng sau khi Supplier/Product/User schema ổn định.

| API | Luồng / response | Ngoại lệ và test |

| --- | --- | --- |

| GET /admin/notifications | ?page&page_size&unread_only → Page<NotificationRead> | 401/403; chỉ current Admin; stable sort; query scope trong SQL |

| GET /admin/notifications/unread-count | → 200 {count:int} | 403 Staff; count đúng theo read_at IS NULL |

| PATCH /admin/notifications/{id}/read | {} → 200 NotificationRead; chỉ set read_at nếu NULL | 404 notification khác owner; idempotent repeat không đổi timestamp |

| PATCH /admin/notifications/read-all | {} → 200 {updated_count:int} | 403 Staff; chỉ update unread của current Admin; concurrent repeat không tăng count |

NotificationRead = {id,approval_request_id,created_at,read_at}; không tự thêm title/message/url/is_read vào DB. create_for_approval nhận Session của Hiếu, flush nhưng KHÔNG commit; test forced rollback cả User/Approval/Notification.

Thực hiện tiếp S1: Receipt tables purchase_receipts / purchase_receipt_items, FK/check/composite PK (receipt_id,product_id), draft_version. Không triển khai Receipt HTTP/Confirm trong S1.

### 4.3. Na Na — T3C9D63 → T3C9D7D (Category/Supplier)

Ưu tiên LMS: ORM/migration/seed Category và Supplier; Category API trước để mở đường Product; Supplier API sau. API read cần rõ quyền: Category STAFF/ADMIN, Supplier chỉ ADMIN.

| API | Request/Response | Ngoại lệ và test |

| --- | --- | --- |

| GET /categories; GET /categories/{id} | page,page_size,status? → Page<CategoryRead> / CategoryRead | 401,404,422 invalid filter; Staff GET được |

| POST/PATCH /categories; PATCH /categories/{id}/status | {name} hoặc {status:ACTIVE|INACTIVE} → 201/200 CategoryRead | 403 Staff; 422 name trống/>120; 404; inactive category không được gán cho Product mới |

| GET /suppliers; GET /suppliers/{id} | page,page_size,status? → Page<SupplierRead> / SupplierRead | 403 Staff; 404; nullable contact fields đúng ERD |

| POST/PATCH /suppliers; PATCH /suppliers/{id}/status | {name,contact_email?,contact_phone?} / {status} → 201/200 SupplierRead | 422 invalid input; 404; PATCH null xóa contact; không xóa lịch sử Receipt |

CategoryRead = {id,name,status,created_at,updated_at}. SupplierRead thêm contact_email/contact_phone nullable. ERD không có UNIQUE(name), không tự tạo 409 tên trùng. Seed idempotent.

Thực hiện tiếp S1: hỗ trợ Lan Anh kiểm thử Category ACTIVE/INACTIVE, review response shape để Tân mock. Product search/filter/sort nâng cao T3C9D97 thuộc S2.

### 4.4. Lan Anh — T3C9AEB (Product API)

Ưu tiên LMS: Product GET list/detail tối thiểu để FE tích hợp; create → update → activate/deactivate. Bắt đầu sau khi nhận Product model của Dương và Category model của Na Na.

| API | Request/Response | Ngoại lệ và test |

| --- | --- | --- |

| GET /products; GET /products/{id} | page,page_size → Page<ProductRead>; ProductRead | 401; 404; STAFF được read; không N+1 và không lộ cost fields |

| POST /products | {sku,name,category_id,sale_price_vnd} → 201 ProductRead | 403 Staff, 404 Category, 409 SKU, 422 price; tạo Product + Inventory 0 cùng transaction |

| PATCH /products/{id} | Whitelist sku/name/category_id/sale_price_vnd → 200 ProductRead | 409 duplicate SKU; Category ACTIVE; không cho sửa quantity/stock_version |

| PATCH /products/{id}/status | {status:ACTIVE|INACTIVE} → 200 ProductRead | 403 Staff; 404; status không xóa stock/historical refs |

ProductRead = {id,category_id,sku,name,status,sale_price_vnd,quantity,stock_version,created_at,updated_at}. Quantity/stock_version chỉ đọc từ Inventory; Product không có stock_quantity. Test duplicate SKU race, create + inventory rollback, inactive Category, Staff permission.

Thực hiện tiếp S1: tích hợp real API với Tân và xử lý negative tests. Search/category/status/sort trên GET /products được khóa query contract cho Na Na mở rộng S2, không đổi DTO.

### 4.5. Lâm — T3C9E1A → T3C9E33 (React/Auth)

Ưu tiên LMS: Router, Axios API client, refresh single-flight, route guards; Register/Login UI, pending/rejected states. Forgot/Reset dùng mock/placeholder theo contract, backend implementation S2.

| UI / API | Luồng | Ngoại lệ / test |

| --- | --- | --- |

| Register | form → POST /auth/register → thông báo public chung | 422 validation, 429/503 khi có rate limiter; không hiển thị tồn tại email |

| Login | POST /auth/login → access token memory → route ACTIVE | 401 chung, failed network, pending UI không vượt security |

| Refresh/Logout | GET CSRF → cookie request with credentials → single-flight refresh / logout | Không refresh storm, không retry vô hạn, clear client state khi session invalid |

Thực hiện tiếp S1: mock Approval UI (S2) nếu có capacity; mentor/review Product UI của Tân; Frontend phải merge sớm qua PR.

### 4.6. Tân — T3C9C6C → T3C9C86 (Product React)

Ưu tiên LMS: KHÔNG vẽ lại wireframe; map thiết kế freeze thành component/routes, sau đó Product list/detail/form theo ProductRead mock; chuyển GET real khi Lan Anh merge. Để search/filter nâng cao mock-only cho đến S2.

| UI / API | Luồng | Ngoại lệ / test |

| --- | --- | --- |

| Product list | GET /products?page=1&page_size=20 → table, paging, loading/empty | 401 session, 403, 5xx/network, stable pagination |

| Product form | POST/PATCH products → cập nhật list theo response | 422 field errors, 409 duplicate SKU; pending submit, disable double click |

| Activation | PATCH /products/{id}/status → confirm/reload | 403 Staff, 404 missing; không gửi quantity từ form |

Thực hiện tiếp S1: responsive và UI permission states cùng Lâm; mock và real API dùng chung DTO; không claim tích hợp khi còn mock.

## 5. Contract HTTP thống nhất (bản tóm tắt)

- Base /api/v1; path trong bảng task là phần sau prefix. JSON request dùng snake_case và extra=forbid; server-side authorization luôn là nguồn quyết định.

- Success: DTO trực tiếp; list {items,total,page,page_size}; create 201, update 200, logout 204. Error chuẩn {code,message,details}; 401 unauthenticated, 403 forbidden, 404 not found, 409 conflict, 422 invalid, 429 rate limit, 503 dependency unavailable.

- Access JWT 15 phút trong memory; refresh digest trong MySQL và cookie HttpOnly + Secure, session tối đa 8 giờ; CSRF/Origin cho cookie mutations, CORS allowlist. Local FE qua Vite proxy /api; production HTTPS.

- Mọi Product CREATE tạo Inventory quantity=0, stock_version=0 trong một transaction. Category/Supplier/Product chỉ inactive, không hard delete; không cascade phá lịch sử. Tiền VND integer; UTC timestamp; mọi list có bound pagination và stable ordering.

- Approval APIs đã xác định cho Sprint 2: GET /staff-approvals?status=PENDING; POST /staff-approvals/{id}/approve; POST /staff-approvals/{id}/reject với {reason}. 409 nếu transition đã xử lý, event email ghi Outbox cùng transaction. Không xem đã code trong S1.

## 6. Thứ tự ưu tiên để kịp tối Chủ nhật 08/11

| Thời điểm | Ưu tiên làm trước để hoàn thành LMS | Sau đó mới làm |

| --- | --- | --- |

| 06/11 | Commit tài liệu sau review; chốt migration order; branch/PR; kiểm tra Product schema đã code | FE mocks; tạo test skeleton |

| 07/11 | Auth + Category/Supplier + Product/Inventory + Notification models/migrations; React shell | Receipt model PR riêng; FE form mock |

| 08/11 tối | Register/Login basic; Category CRUD; Product GET/Create; Notification list/count; FE preview (đánh nhãn real/mock) | Refresh/logout; remaining mutation; Supplier details nếu chưa xong |

| 09/11 | Product PATCH/status; Supplier CRUD; Notification read/read-all; refresh/logout; FE real integration | Fix negative tests, permission, concurrent race |

| 10/11 | Merge/CI, migration from clean MySQL, API contract smoke tests, regression, evidence LMS | Không nhận bonus; chuyển chính thức phần tồn sang S2 nếu cần |

Ưu tiên task LMS không đồng nghĩa cho phép bỏ test/authorization tối thiểu của endpoint được merge. Ngày 08/11 là “Integration Preview”, không tự nhận Sprint 1 đã nghiệm thu 100%. Deadline LMS 11/11 nằm ngoài timebox S1 (kết thúc 10/11): PO/Scrum Master phải sửa khi quản lý tiến độ.

## 7. Quy trình Git, Migration và kiểm thử (giữ nguyên nguyên tắc)

- Branch feature/* từ develop mới nhất → code theo owner → module tests → PR có Task ID → CI + Tech Lead review → merge develop → FE smoke test. Không direct push protected branch, không merge main khi chưa release review.

- Migration do Tech Lead điều phối: baseline 20261105_01 → Auth/Category/Supplier theo FK → Product/Inventory/StockMovement → Notification → Receipt. Không mở nhiều Alembic head rồi merge tùy tiện; PR chưa merge phải rebase migration hợp lệ.

- Không cho AI agent sửa file ngoài domain task; không cho tự thay ERD/SRS; không tự thêm API trùng; khi cần đổi DTO/path phải PR sửa contract và báo cả FE/BE.

- Test tối thiểu theo rủi ro: ORM/FK/unique + seed idempotent; auth 401/session/race; Notification scope & duplicate; Category/Supplier RBAC; Product atomic create/unique race; Frontend loading/error/mocks; MySQL integration/rollback, OpenAPI khớp contract. Không lấy ảnh Swagger thay automated tests.

- Tech Lead mở PR có thể vướng CODEOWNERS chính chủ — giải quyết reviewer hợp lệ trước khi khóa merge. Team phải báo blocker sớm và review PR từng ngày, không chờ cuối Sprint.

## 8. Giới hạn và quản lý thay đổi

- Sprint 1 KHÔNG triển khai full Staff Approval, Forgot/Reset, reapply email proof, advanced Product Search, Receipt Confirm, Inventory Adjustment, AI hoặc Worker. Nếu cần đưa lên sớm, sửa LMS/scope trước; không đánh dấu pass giả.

- Auth hoàn chỉnh theo SRS còn phụ thuộc approve/reject, email Outbox, password reset/reapply. S1 có thể chạy flow partial và phải ghi rõ những gì chỉ là mock.

- Redis rate limit, Outbox Publisher/Email Worker, Nginx/full-stack Compose vẫn là baseline V1, phải có task/owner ở các sprint sau. Không cam kết đã PASS khi chưa có evidence.

- Tài liệu này khóa interface đề xuất; nếu cần đổi phải cập nhật contract, OpenAPI/fixtures và thông báo BE + FE trước code. Tên class, đường dẫn file không phải tiêu chuẩn bắt buộc nếu codebase đã có convention tốt hơn; tránh tạo layer hình thức.
