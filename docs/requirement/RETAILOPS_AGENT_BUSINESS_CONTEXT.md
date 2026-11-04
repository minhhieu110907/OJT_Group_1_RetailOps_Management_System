# RETAILOPS V1.0 — AGENT BUSINESS CONTEXT

> **Purpose:** Bản tóm lược nghiệp vụ có thể đọc nhanh dành cho Codex/Copilot/AI coding agents. Đặt file tại `docs/RETAILOPS_AGENT_BUSINESS_CONTEXT.md`.  
> **Source SRS:** `RetailOps_SRS_V1.3_Approval_Candidate.docx` (bản V1.3 ngày 03/11/2026; tiêu đề tài liệu vẫn ghi *Approval Candidate*; nội dung đã được PO chấp thuận trong trao đổi dự án).  
> **Source Data Design:** `docs/database/RetailOps_ERD_V1.0_Chot_Thiet_Ke.dbml` (thiết kế đã chốt, **chưa được chứng nhận migration-ready trên MySQL**).  
> **Additional decisions:** TD-01, TD-03, TD-04 được chốt **sau** khi SRS V1.3 được biên soạn; xem mục 10.  
> **Status:** Agent-readable operational summary; **không thay thế** SRS gốc, DBML, API contract, migrations hay ADR.

## 0. Agent — đọc trước khi sửa code

1. Đọc `docs/RETAILOPS_AGENT_BUSINESS_CONTEXT.md`, sau đó đọc **đúng phần SRS V1.3** và **đúng bảng DBML** liên quan đến task; kiểm tra repository/code hiện tại, không tưởng tượng file hay endpoint.
2. Xác định task ID (AUTH-xx, SALE-xx, ...), phạm vi P0/P1, quyền Actor, các invariant, transaction boundary, trường hợp lỗi và test cần chạy **trước khi code**.
3. Không tự đổi nghiệp vụ, bảng/cột/enum, API contract, security defaults, công nghệ, hay mở rộng scope. Nếu tài liệu mâu thuẫn hoặc thiếu, nêu rõ và đề xuất thay đổi nhỏ nhất, chờ PO/Tech Lead phê duyệt.
4. Kiến trúc **Modular Monolith**. Không đề xuất microservices, distributed transactions, Redis distributed lock hay tự động ghi dữ liệu qua LLM trong V1.
5. Với mọi mutation nhạy cảm, chỉ rõ authorization, optimistic/pessimistic locking, idempotency, atomic commit/rollback và negative/concurrency tests. Không coi unit test bằng SQLite là bằng chứng về InnoDB.
6. Tuyệt đối không log plaintext password, reset/reapply token, refresh token, bearer token, secret, email ciphertext hay PII không cần thiết. Không trả dữ liệu giá nhập/nội bộ cho Staff.
7. Không tuyên bố implementation, CI, migration, benchmark hay crash recovery đã PASS nếu chưa thực thi và cung cấp bằng chứng.
8. Khi hoàn tất task: nêu file đã sửa, mapping task ID, behavioral contract, tests đã chạy, rủi ro còn lại, và các thay đổi migration/API cần phối hợp.

## 1. Scope và ưu tiên

RetailOps là hệ thống quản lý nội bộ **một cửa hàng / một kho**, vai trò `ADMIN` và `STAFF`, quản lý catalog, supplier, phiếu nhập, tồn kho, POS, dashboard, trợ lý AI read-only và gửi email bất đồng bộ. Giao dịch tiền mặt/tại quầy được **ghi nhận** trong hệ thống, không tích hợp payment gateway thực. Tất cả tiền dùng **số nguyên VND**; số lượng hàng **số nguyên**, không dùng float cho tiền.

**P0** là cốt lõi bắt buộc; **P1** chỉ bắt đầu sau khi P0 qua quality gate: `INV-05` (ngưỡng low stock theo Product), `ANA-05` (CSV export), `ENG-10` (đo và tối ưu truy vấn). Không xem P1 là điều kiện bắt buộc của demo V1.

**Ngoài V1:** nhiều kho/cửa hàng, ecommerce, thanh toán thật, trả hàng/hoàn tiền, đảo phiếu nhập đã Confirm, thuế/khuyến mãi, đa tiền tệ, kế toán, social login, khóa/mở khóa Staff, AI write action, vector DB, multi-agent, forecast tự động, tự động tạo purchase receipt từ AI.

**Data/time:** lưu timestamp UTC; các quy tắc “cùng ngày”, thống kê theo ngày và timezone hiển thị dùng `Asia/Ho_Chi_Minh`; convert ngày VN thành [start_utc, end_utc) để truy vấn. Giỏ POS không giữ hàng. Dữ liệu SRS là synthetic/demo, không suy ra đã sản xuất thương mại.

## 2. Quyền và privacy

| Tác vụ | ADMIN | STAFF | Public/Pending/Rejected |
|---|---|---|---|
| Quản lý Staff approvals, master data, supplier/receipt, kiểm kê | Có | Không | Không |
| Catalog / stock / movement / order history | Có, đầy đủ theo nghiệp vụ | Có, **lọc dữ liệu nhạy cảm** | Không |
| POS Checkout | Có | Có | Không |
| Cancel order | Mọi order `COMPLETED` trong **cùng ngày kinh doanh VN** | **Chỉ order do chính mình tạo**, trong **≤900 giây** và cùng ngày VN | Không |
| Dashboard, Analytics, AI | Có | Không | Không |
| Public registration / forgot password / reapply proof | Theo public flow | Theo public flow khi phù hợp | Chỉ các endpoint công khai tương ứng |

- Mọi protected API phải kiểm tra `ACTIVE` + session còn hiệu lực + role + ownership/resource scope + field-level response. Frontend guard không thay thế backend authorization.
- Staff **không nhận** giá nhập, giá vốn, internal adjustment reason, dữ liệu cá nhân không cần thiết từ Movement hoặc kết quả AI.
- Một Admin được seed bằng quy trình vận hành an toàn; không mở endpoint public tạo Admin; không triển khai Staff suspension/reactivation V1.

## 3. Business invariants theo phân hệ

### 3.1 Authentication (`AUTH-01` … `AUTH-05`)

- Public Staff register email/password → một `User(PENDING_APPROVAL)`, một approval request và một in-app Admin notification trong cùng transaction; duplicate pending registration không nhân bản User/request/notification. Normalize email và enforce uniqueness.
- Admin approve/reject chỉ một transition thắng khi concurrent, audit đầy đủ; email event được ghi vào Outbox cùng transaction để gửi **sau commit**.
- `REJECTED` reapply giữ **cùng User ID + lịch sử**, cần chứng minh quyền sở hữu email, tối đa **1 lần trong 24 giờ**. Không cấp quyền nội bộ khi Pending/Rejected.
- JWT access **15 phút**, giữ trong **memory**; opaque rotating refresh cookie `HttpOnly`, `Secure` (+ CSRF/Origin protections), absolute session **≤8 giờ**; logout revoke server-side session để access token cũ cũng bị chặn ở API.
- Staff password reset bằng one-time email token; Admin account recovery thủ công trên đúng seeded Admin, không tự tạo Admin mới.

### 3.2 Product / Category (`PROD-01` … `PROD-04`)

- Product mới: stock = 0; Sale Price > 0 VND; SKU unique theo schema; Product update **không chỉnh quantity**.
- Product `INACTIVE`: chặn checkout và nhập hàng mới; vẫn giữ inventory, lịch sử và cho phép Admin inventory adjustment có audit.
- Category `INACTIVE`: không gán cho Product mới; không cascade inactive Products hiện có; giữ FK lịch sử.
- Search/sort/page phải whitelist sort keys, stable ordering, bounded page size; serializer Staff loại bỏ trường nhạy cảm.

### 3.3 Supplier / Purchase (`PUR-01` … `PUR-05`)

- Supplier `INACTIVE` không được dùng tạo hoặc **confirm** receipt mới; lịch sử không xóa.
- `DRAFT` Receipt: một Supplier; item quantity integer >0; unit_cost integer ≥0 VND; **cùng Product + cùng Unit Cost ⇒ gộp Quantity**; **cùng Product nhưng Unit Cost khác ⇒ validation error**, không tự average cost; cần nhiều cost thì dùng receipt khác.
- Sửa DRAFT bằng `draft_version`/`expected_version`, stale ⇒ `409`; DRAFT không thay đổi stock.
- Confirm: verify version/status + ACTIVE supplier/products + idempotency; update receipt, increment stock, movements, snapshots, audit atomically. `CONFIRMED` **bất biến**, không edit/cancel trong V1.
- Cancel DRAFT: valid version, transition một lần, **không thay stock**, bảo toàn snapshot lịch sử. Bất kỳ stale/terminal-state mutation nào đều phải bị từ chối.

### 3.4 Inventory (`INV-01` … `INV-05`, `ENG-01/02`)

- `inventory.quantity >= 0`; không oversell; mọi thay đổi stock qua **một Inventory Service** với guarded update/locks, movement + version + audit trong cùng transaction.
- Receipt Confirm +stock; Checkout −stock; Cancel completed Order +stock **đúng một lần**; Adjustment dùng **`counted_quantity`** (actual count), backend tự tính `delta`, không cho client nhập delta làm source of truth.
- Adjustment yêu cầu `expected_stock_version` + reason + idempotency; **stale luôn `409`, kể cả nếu counted_quantity trùng current**. Nếu delta=0: ghi audit nhưng **không** movement và **không** tăng stock_version.
- `stock_movements` append-only, trace source order/receipt/adjustment; `first_stocked_at` là **lần đầu tiên 0→dương** do receipt/adjustment hợp lệ, không reset sau depletion/restock.
- `ACTIVE` + stock ≤**5** là low-stock P0; P1 per-product threshold chưa bắt buộc.

### 3.5 POS / Orders (`SALE-01` … `SALE-05`)

- Cart không reserve stock; merge duplicate Product rows, quantity positive integer; UI totals chỉ là quote.
- Checkout xác thực **giá hiển thị** và tồn tại thời điểm thực thi. Nếu bất kỳ giá nào đổi: trả `409 PRICE_CHANGED` với dữ liệu giá mới, **không tạo order / movement / stock update**; lần chấp nhận giá mới dùng **idempotency key mới**.
- Successful checkout tạo `COMPLETED` order tức thời; order items/snapshots, stock decrement, movements, audit và idempotency response commit **nguyên tử**.
- Cancel: Staff chỉ của mình trong ≤15 phút **và** cùng ngày VN; Admin mọi order COMPLETED trong cùng ngày VN; reason bắt buộc, actor/time được audit; status transition + restore đúng một lần atomically; không physical delete.
- Idempotency `(user, operation, key)` cho checkout, receipt confirm, cancel, adjustment: same canonical request ⇒ replay persisted result; same key + different payload ⇒ `409`; concurrent duplicate chờ ngắn rồi replay hoặc `409/425`; completed response giữ **24 giờ**.

### 3.6 Analytics (`ANA-01` … `ANA-05`)

- Revenue, AOV, completed order count: chỉ Order **đang** `COMPLETED`; cancelled luôn bị loại khỏi doanh thu. Cancelled order count quy về **kỳ/ngày bán gốc** (`sold_at`), không theo `cancelled_at`.
- `AOV = revenue / completed_order_count`, làm tròn `ROUND_HALF_UP` đến VND; kỳ mặc định là ngày VN hiện tại.
- Top selling: tổng **quantity** từ items thuộc orders còn `COMPLETED`, mặc định 7 ngày; sắp xếp ổn định.
- Slow moving: `Product ACTIVE`, stock >0, `first_stocked_at` cách hiện tại **>7 ngày**, units sold trong 30 ngày **≤2**, bao gồm 0 units. Không dùng `product.created_at` làm stock age.
- Low stock dùng cùng định nghĩa ngưỡng ở Inventory, Dashboard và AI.

### 3.7 AI (`AI-01` … `AI-04`, `ENG-05`)

- **ADMIN-only**, read-only tool calling qua allowlist và Business Services; validate tool arguments bằng schema, kiểm tra Admin **tại mỗi tool invocation**, limit/timeouts/quotas/tool call count/output size.
- Không cho LLM chạy SQL tự do, gọi write endpoints, chọn identity tuỳ ý, thao túng quyền, sửa receipt/stock/order; không thêm bảng AI hoặc vector DB chỉ để mở rộng ngoài scope.
- AI tổng hợp bằng chứng từ analytics/stock (doanh thu, top sellers, low stock, slow moving) và có thể đưa ra **gợi ý nhập hàng có dẫn chứng**, không tự quyết định số lượng nhập chính xác nếu thiếu lead time/dữ liệu.
- Model/tool timeout, quota hoặc thiếu chứng cứ ⇒ trả lỗi an toàn/nêu giới hạn; không hallucinate số liệu.

### 3.8 Infrastructure / Outbox (`INF-01` … `INF-05`)

- Nginx reverse proxy, forwarded header chỉ trust khi đến từ configured proxy; không tin client-supplied X-Forwarded-For tùy tiện.
- Redis rate limits theo SRS: Login **5/min/IP + 20/hour/account**; Registration **3/hour/IP**; Forgot Password **3/hour/IP và email**; Refresh **10/min/session**; AI **10/min/user**; Business API **120/min/user**. Public auth và AI **fail-closed** khi Redis lỗi; internal POS có thể tiếp tục chỉ nếu MySQL session/RBAC còn bảo vệ an toàn.
- `Outbox Lite` đã được Tech Lead chốt sau SRS: **một independent publisher** polling MySQL after commit; RabbitMQ durable + persistent messages + broker confirm; **một email worker tuần tự** với retry hữu hạn. Worker không phải Publisher; core business commits không phụ thuộc RabbitMQ/SMTP; at-least-once, không nói external email exactly-once.
- Phải chứng minh broker outage không làm mất committed intent; lưu FAILED/unprocessed cho retry/replay, không tự xóa; không gửi SMTP trong transaction nghiệp vụ.
- One-time reset/reapply secret khi gửi qua queue phải bảo vệ trong storage/payload/log; không truyền plaintext secret cho model hoặc để lọt log.

## 4. Các kỹ thuật bắt buộc và kiểm thử

- FastAPI + SQLAlchemy + MySQL 8/InnoDB; React/Vite, Redis, RabbitMQ/Celery, Nginx, Docker Compose, CI GitHub Actions. Đây là stack dự án đã chọn; agent không tự thay bằng framework khác.
- **Transaction ownership** tại Application Service. Repository không tự commit; không I/O SMTP, broker, LLM trong business transaction.
- Trên stock-mutating path phải revalidate sau lock, dùng guarded atomic update/row locks/optimistic version. Lock ordering nhất quán; lock retry bounded + jitter, chứng minh bằng MySQL concurrency tests.
- Idempotency TD-04C **Option A**: claim + toàn bộ business effects + persisted completed response **một MySQL transaction**; không commit riêng `IN_PROGRESS`, không thêm idempotency lease/fencing.
- Snapshot historical order/receipt đúng thời điểm commit; terminal receipts/orders không bị sửa ngầm khi master data đổi.
- Tests: RBAC và field-level leak; simultaneous checkout last unit; duplicate checkout/confirm/cancel; stale adjustment no-op; price changed with zero writes; 2 Admin approve cùng request; token rotation/replay; broker down/outbox publisher crash; worker duplicate/retry; timezone midnight; analytics completed vs cancelled.
- **Không được nhận định passed chỉ vì code “trông đúng”.** Run lint, MySQL migration/constraint tests, integration tests, concurrency tests, static security checks. Business logic coverage target ≥**80%**, nhưng coverage không thay thế critical-flow tests.

## 5. NFR / quality gates

| Nhóm | Contract / mục tiêu |
|---|---|
| Security | Secure password hashing; JWT 15m; max session 8h; HttpOnly Secure refresh; CSRF/Origin; backend RBAC; sanitize logs; secure secrets |
| DB integrity | No negative stock / oversell / double restore / double confirm / orphan movement / duplicate orders |
| Performance target (**not measured**) | 10–20 concurrent users; Product/Category/Inventory Reads P95 ≤300ms; Checkout/Receipt Confirm ≤800ms; Dashboard ≤1500ms; AI timeout riêng |
| CI | PR → `develop`: lint + tests + migration/security checks; không merge nếu gate fail; demo không có Critical/High còn mở |
| Deployment | Docker Compose tái lập được, Alembic migrations, seed Admin, Nginx, HTTPS khi expose, healthcheck + runbook; tunnel/public demo approach chưa bắt buộc |
| Retention | Order/Receipt/Movement/business audit: suốt vòng đời demo; completed idempotency 24h; expired session/refresh cleanup 30d; expired password-reset token cleanup 24h; processed outbox 7d; app logs 14d; **outbox FAILED/unprocessed không tự xoá** |

**Definition of Done cho task:** chính xác SRS contract + RBAC/validation + failure/concurrency cases + test evidence + documentation/OpenAPI/DB changes (nếu có), không còn Critical/High, không tự thêm scope. Benchmark cần ghi fixture/hardware/workload cụ thể.

## 6. HTTP/API convention hướng dẫn (không thay thế OpenAPI)

- `401`: thiếu/không hợp lệ token hoặc session; `403`: có danh tính nhưng không đủ quyền; `409`: stale version, `PRICE_CHANGED`, idempotency payload conflict hoặc terminal state; `422`: dữ liệu đầu vào không hợp lệ; `429`: quota/rate limit; `503`: dependency fail-closed / unavailable phù hợp contract.
- `expected_version`/`expected_stock_version` là input **bắt buộc** ở path tương ứng; không bỏ qua vì UI đã có state mới nhất.
- Không assume field/enum names từ tài liệu tóm tắt: đọc DBML và migration trước khi viết SQL/ORM. Không assume mọi conflict đều 409 nếu API contract cụ thể khác.
- Mọi query analytics nhận khoảng UTC chuẩn từ ngày VN, giới hạn date range và pagination; LLM không viết SQL.

## 7. Checklist trước khi agent thực thi task

- [ ] Đã xác định task ID và trích đúng SRS section.
- [ ] Đã đọc DBML/ADR/contract và code thực tế; ghi rõ mọi khác biệt.
- [ ] Đã kiểm tra Actor, status machine, ownership và dữ liệu không được leak.
- [ ] Đã xác định transaction owner, lock ordering, retry, idempotency và audit nếu mutation.
- [ ] Đã thiết kế negative tests và concurrency tests tương ứng.
- [ ] Không tự thêm P1/out-of-scope, không migrate schema không được duyệt.
- [ ] Đã chạy các test có thể chạy và báo bằng chứng/giới hạn.

## 8. Task index — toàn bộ 63 task của SRS V1.3

Đây là **index điều hướng**, không phải bản sao acceptance criteria. Khi code phải đọc mô tả đầy đủ trong SRS gốc.

### Authentication & Authorization

- `AUTH-01` — Đăng ký tài khoản Staff
- `AUTH-02` — Đăng nhập, đăng xuất và quản lý phiên
- `AUTH-03` — Duyệt và từ chối đăng ký Staff
- `AUTH-04` — Phân quyền truy cập theo vai trò
- `AUTH-05` — Thông báo đăng ký mới cho Admin

### Product & Category

- `PROD-01` — Quản lý sản phẩm
- `PROD-02` — Quản lý danh mục
- `PROD-03` — Tìm kiếm, lọc và phân trang sản phẩm
- `PROD-04` — Xem chi tiết sản phẩm

### Purchasing & Suppliers

- `PUR-01` — Quản lý nhà cung cấp
- `PUR-02` — Tạo và sửa phiếu nhập nháp
- `PUR-03` — Xác nhận phiếu nhập
- `PUR-04` — Hủy phiếu nhập nháp
- `PUR-05` — Lịch sử và chi tiết phiếu nhập

### Inventory

- `INV-01` — Tổng quan tồn kho
- `INV-02` — Điều chỉnh tồn kho theo kiểm kê thực tế
- `INV-03` — Lịch sử biến động kho
- `INV-04` — Cảnh báo tồn kho thấp
- `INV-05` — Ngưỡng tồn kho thấp tùy chỉnh **[P1]**

### POS & Sales

- `SALE-01` — Giỏ hàng POS
- `SALE-02` — Thanh toán bán hàng trực tiếp
- `SALE-03` — Lịch sử và chi tiết đơn hàng
- `SALE-04` — Hủy đơn hàng có điều kiện
- `SALE-05` — Idempotency cho checkout

### Analytics

- `ANA-01` — Tổng hợp doanh thu và chỉ số bán hàng
- `ANA-02` — Sản phẩm bán chạy
- `ANA-03` — Sản phẩm bán chậm
- `ANA-04` — Phân tích tồn kho thấp
- `ANA-05` — Xuất báo cáo CSV **[P1]**

### AI assistant

- `AI-01` — Phân tích kinh doanh bằng ngôn ngữ tự nhiên
- `AI-02` — Tool calling chỉ đọc cho dữ liệu bán hàng và tồn kho
- `AI-03` — Gợi ý nhập hàng có dẫn chứng
- `AI-04` — Xử lý lỗi và độ tin cậy của AI

### Infrastructure & Async

- `INF-01` — Cấu hình Nginx reverse proxy
- `INF-02` — Rate limiting bằng Redis
- `INF-03` — RabbitMQ, Celery và worker
- `INF-04` — Gửi email nghiệp vụ
- `INF-05` — Xử lý lỗi hàng đợi và phục hồi

### Engineering

- `ENG-01` — Concurrency cho bán hàng
- `ENG-02` — Nhất quán dữ liệu nhập hàng và tồn kho
- `ENG-03` — Khung idempotency dùng chung
- `ENG-04` — Bảo mật backend
- `ENG-05` — Bộ thực thi tool cho AI
- `ENG-06` — Kiểm thử tự động
- `ENG-07` — Docker Compose môi trường dự án
- `ENG-08` — CI với GitHub Actions
- `ENG-09` — Triển khai bản demo
- `ENG-10` — Tối ưu truy vấn **[P1]**

### Governance & Design

- `GOV-01` — Khóa phạm vi và mapping quyết định
- `GOV-02` — ERD, migration và seed nền tảng
- `GOV-03` — API contract và danh mục lỗi
- `GOV-04` — Figma và luồng giao diện cơ sở

### Frontend

- `FE-01` — Khung ứng dụng React, routing và auth guard
- `FE-02` — Màn hình xác thực và duyệt đăng ký
- `FE-03` — Giao diện quản lý sản phẩm, danh mục, nhà cung cấp
- `FE-04` — Giao diện phiếu nhập hàng
- `FE-05` — Giao diện tồn kho và điều chỉnh kho
- `FE-06` — Giao diện POS, checkout và lịch sử đơn hàng
- `FE-07` — Giao diện dashboard, analytics và AI

### Quality Assurance

- `QA-01` — Kiểm thử luồng nghiệp vụ đầu cuối
- `QA-02` — Đánh giá hiệu năng và rà soát bảo mật

### Release

- `REL-01` — Tài liệu hướng dẫn chạy và demo
- `REL-02` — UAT, tổng hợp lỗi

## 9. Giao thức báo cáo ngắn cho coding agent

Khi nhận task, trả lời theo mẫu:

```text
TASK: <task ID và scope>
SOURCE: <SRS section + DBML tables + Technical Decision liên quan>
BUSINESS INVARIANTS: <ràng buộc phải giữ>
SECURITY: <auth/RBAC/field-level validation>
TRANSACTION/CONCURRENCY: <lock/version/idempotency, nếu có>
PLAN: <ít bước, thay đổi tối thiểu>
TEST PLAN: <happy path, negative, concurrency, outage>
AFTER IMPLEMENTATION: <files changed, test commands/results, gaps, migrations>
```

Nếu task thiếu dữ liệu, không tự tuyên bố PO đã phê duyệt. Đề xuất phương án nhỏ nhất và nêu rõ `NEEDS PO/TECH LEAD DECISION`.

## 10. Kết nối SRS với quyết định kỹ thuật chốt sau 03/11/2026

**Quy tắc nguồn:** SRS V1.3 đặt business requirements, các quyết định dưới đây là bổ sung kỹ thuật sau khi tài liệu Word được biên soạn. Không giả vờ các dòng này đã xuất hiện trong bản Word.

| Decision | Đã thống nhất | Tác động đến agent |
|---|---|---|
| TD-01 | Reapply ownership via one-time email proof, random opaque token **15 phút**, lưu digest, consume chỉ một lần qua `POST`, 24h cooldown sau reapply thành công | Không coi GET link là mutation; không auto approve; qua Outbox email |
| TD-03 | Immutable historical snapshots tại successful checkout / receipt confirm; cancelled draft receipt giữ snapshot hữu ích | Snapshot không phụ thuộc master data khi xem lịch sử |
| TD-04A | Application Service owns transaction | Không commit trong repository |
| TD-04B | MySQL row locks + guarded atomic stock update + optimistic versions | Không dùng Redis distributed lock làm source of truth |
| TD-04C | **Option A** — same transaction cho claim, business effects, response | Không tạo committed `IN_PROGRESS` riêng |
| TD-04D | Refresh rotation lưu generation history, lock session khi rotate | Consumed token không được cấp token mới; replay policy cần tests |
| TD-04E (V1 scoped) | **Outbox Lite**: 1 polling publisher + 1 serial email worker, retry/recovery, at-least-once | Không đưa dual lease/fencing bản cũ vào V1 |
| TD-05 | Chưa khóa đầy đủ benchmark fixture/hardware, AI timeout, public demo path | Không tự công bố là đã phê duyệt/đã đạt |

**Cảnh báo SRS về snapshot:** Trong text gốc PUR-05/SALE-03 còn mô tả snapshot fields là chờ Data Design. TD-03 và ERD hiện tại đã bổ sung quyết định; giữ SRS gốc làm nguồn nghiệp vụ, dùng tài liệu TD-03/ERD để thực thi thiết kế được chốt, không tự sửa lịch sử phê duyệt.

**Validation status:** ERD Design Baseline đã được chốt cho dự án nhưng chưa chứng minh bằng MySQL migration, constraints và concurrency tests. Agent không được đánh đồng “DBML parse được” với “production safe”.
