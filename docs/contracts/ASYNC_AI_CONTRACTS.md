# RETAILOPS CF-2.1 — ASYNC AI CONTRACTS
> Bản tinh gọn: nội dung các tài liệu CF-2.0 được hợp nhất, không thay đổi nguồn chuẩn HTTP (`contracts/openapi.yaml`) và Python ABI (`contracts/python/*.pyi`). Các chương bên dưới là phần tham khảo có thể chứa ví dụ chữ ký cũ; khi khác canonical contract, ưu tiên ABI/OpenAPI và mở PR sửa hướng dẫn.


---

## OUTBOX, EMAIL, RESET

# RETAILOPS CF-2.0 — Outbox, Email Worker, Password Reset & Reapply

**Owner core:** Hiếu (Outbox Writer, Publisher, Worker, recovery). **Dương** tiêu thụ contract phục vụ Password Reset/email integration và test; **Lan Anh/Na Na** QA. Đây là interface design baseline mới, chưa phải code đang tồn tại.

## 1. Interface Python (nguồn chuẩn `contracts/python/retailops_extended_ports.pyi`)

```python
class OutboxWriter:
    def append(self, session: Session, *, subject_user_id: int, event_type: EventType,
               payload: Mapping[str, JsonValue], available_at_utc: datetime,
               secret_ciphertext: bytes | None = None,
               secret_expires_at_utc: datetime | None = None) -> bytes: ...

class OutboxPublisher:
    def publish_due(self, session_factory: Callable[[], Session], *, batch_size: int) -> PublishBatchResult: ...

class EmailEventHandler:
    def handle(self, *, event_id: bytes) -> EmailOutcome: ...
```

- `OutboxWriter.append` **không** tự commit, không gửi RabbitMQ/SMTP. Caller Approval/Register/Reset sở hữu transaction; event record đi cùng business effects.
- `publish_due` chạy ở **một publisher instance**; SELECT event chưa published, đã due; publish RabbitMQ message **chỉ chứa** `event_id`, chờ publisher confirm, rồi mới set `published_at` commit độc lập. Nếu crash giữa broker confirm và DB update có thể gửi message lặp. Không tự thêm lease/fencing khi chưa có design change. `batch_size` bounded bằng cấu hình được review.
- `EmailEventHandler.handle` chạy ở **một worker xử lý email tuần tự** theo TD-04E-LITE. Load event bằng ID, bỏ qua trạng thái terminal, kiểm tra expiry, giải mã ciphertext nếu là link action, gửi theo template allowlist, update `outcome`/`finished_at` và attempt count; retry lỗi tạm có giới hạn và backoff, lỗi vĩnh viễn terminal FAILED. Không hứa SMTP exactly-once.
- `EventType`: `STAFF_REGISTERED`, `STAFF_APPROVED`, `STAFF_REJECTED`, `PASSWORD_RESET`, `STAFF_REAPPLY_PROOF`. `payload` là metadata schema version + non-sensitive values, không có token, mật khẩu, cookie, raw PII cần hạn chế. Một event ID duy nhất, UUID bytes BINARY(16); không dùng RabbitMQ payload đưa identity tùy ý cho worker.
- Trạng thái `published_at`, `publish_attempts`, `delivery_attempts`, `outcome`, `finished_at`, `secret_ciphertext`, `secret_expires_at` theo ERD; không có `lease_owner`, `locked_until` trong phạm vi V1. Secrets mã hóa AEAD, key bên ngoài DB; xóa/scrub ciphertext khi terminal/hết hạn.

## 2. JSON event envelope và template mapping

```json
{"event_id":"3a7a6e1b-8d55-4132-bb4c-1fd0e7e2c001","schema_version":1}
```

Message trên broker chỉ có event ID (và version khi cần), worker truy DB để lấy metadata, subject và ciphertext. Template mapping theo `event_type` cố định; email không chứa stack trace và không phản ánh account enumeration cho người gọi public.

## 3. Reset token — Dương → Lâm, QA; Hiếu security gate

- API trong OpenAPI: `POST /auth/forgot-password` nhận `{email}`, trả **generic 202** bất kể email tồn tại; `POST /auth/reset-password` nhận `{token,new_password}`; action-token `purpose=PASSWORD_RESET`, hash/digest at rest, một lần dùng, expiration, purpose separation. Không gửi token plaintext vào DB/log/analytics. Link qua email có token one-time mã hóa trong Outbox ciphertext để Worker gửi sau commit.
- Chỉ Staff self-service; Admin recovery là vận hành thủ công trên Admin hiện có. Khi reset thành công, revoke toàn bộ sessions/refresh tokens của user liên quan, consume token atomically, hash mật khẩu theo chính sách hiện hành. Concurrent consume một token → chỉ một thành công.
- **Reapply bị thiếu ở CF-1.0:** `POST /auth/reapply/request-proof` nhận email và trả generic 202; `POST /auth/reapply/confirm` nhận one-time token. Rejected Staff chứng minh email, tối đa 1 lần/24 giờ; giữ User ID, tạo approval attempt mới+notification+event trong cùng transaction. API path là **đề xuất mới CF-2.0, cần Hiếu/Lâm xác nhận trước khi merge**, không tự suy ra đã tồn tại ở S1.
- CSRF/Origin áp dụng khi dùng refresh cookie; nếu token gửi trong header/bearer không dựa vào cookie, vẫn rate limit + same-origin phù hợp. FE không tự xác nhận email tồn tại.

## 4. Trường hợp lỗi cần có bằng chứng

| Scenario | Expected |
|---|---|
| Broker offline sau Approval commit | Approval + outbox vẫn tồn tại; publisher có thể gửi sau hồi phục |
| Publisher confirm rồi crash trước DB update | Republish có thể xảy ra; worker dùng event ID để tránh trùng xử lý đã terminal |
| SMTP tạm lỗi | Retriable, no event lost; bounded retries; chưa báo SENT |
| SMTP accept rồi worker crash trước outcome commit | Không thể chứng minh external exactly-once, chấp nhận khả năng email trùng; log/monitor cho phép quan sát |
| Reset token hết hạn/đã dùng/sai purpose | Fail 4xx generic, không thay đổi mật khẩu |
| Hai reset đồng thời cùng token | Một thành công; token không dùng lại |
| Rejected reapply request spam | Account enumeration safe, rate limit + 24h invariant |

## 5. Handoff & gating

- **S2 10/11:** Hiếu bàn giao schema Outbox Lite + `OutboxWriter.append` và unit fake để Approval không chờ S3. Registration event phải được nối vào transaction khi phù hợp.
- **S3 18/11:** Hiếu bàn giao event schema, publisher/handler signatures + RabbitMQ/Celery config; Dương mock handler để kiểm thử reset trước khi worker chạy thật.
- **S3 20–23/11:** Worker broker outage, replay, retry, encrypt/decrypt e2e; reset/reapply integration trên MySQL test + fake SMTP.
- **Không merge** nếu startup cần token plaintext hardcode, không có MySQL test database guard, hoặc nhiều worker/publisher trái ERD.


---

## AI TOOL EXECUTOR

# RETAILOPS CF-2.0 — AI Executor, Orchestration & FE

**Provider AI security infrastructure:** Hiếu; **consumer/orchestration, AI tools & recommendation:** Dương; **data providers:** Na Na/Dương Analytics, Na Na Inventory Read; **FE:** Lâm. AI là P0 theo SRS nhưng không được vượt lên làm chậm Checkout/Inventory P0.

## 1. Bộ thực thi — chữ ký liên task

```python
@dataclass(frozen=True)
class ToolContext:
    actor_id: int
    actor_role: str   # từ CurrentPrincipal, không từ model
    request_id: str

class AIToolExecutor:
    def execute(self, session: Session, *, tool_id: ToolId,
                arguments: Mapping[str, JsonValue], context: ToolContext) -> ToolResult: ...
```

**Tool IDs V1 đóng băng trong CF-2.0:** `get_sales_summary`, `get_top_products`, `get_slow_products`, `get_low_stock`.

| Tool ID | Arguments schema (JSON) | Service gọi | Result DTO | Authorization |
|---|---|---|---|---|
| `get_sales_summary` | `{start_date?:YYYY-MM-DD,end_date?:YYYY-MM-DD}` | `SalesAnalyticsService.summary` | `SalesSummary` + period | ADMIN |
| `get_top_products` | `{days?:integer[1..90],limit?:integer[1..20]}` | `ProductAnalyticsService.top` | bounded `ProductAnalyticsItem[]` | ADMIN |
| `get_slow_products` | `{limit?:integer[1..20]}` | `ProductAnalyticsService.slow` | bounded `ProductAnalyticsItem[]` | ADMIN |
| `get_low_stock` | `{limit?:integer[1..20]}` | `InventoryReadService.low_stock` | bounded `LowStockItem[]` | ADMIN |

All schema `additionalProperties:false`, JSON simple types, no free-form SQL, URL, files, actor_id, role, tenant_id. `ToolResult={tool_id,data,source_period}`; exclude PII/cost from model context. Period behavior `start_date/end_date` date inclusive at user boundary converted to UTC half-open query.

## 2. Trách nhiệm hai backend

- **Hiếu:** `AIToolExecutor`, allowlist, input schema validation, `CurrentPrincipal` verified ADMIN on **every execution**, per-request budget, output size caps, audit with no token/raw sensitive fields, timeout handling, fail-safe errors. `session` chỉ read; không `commit`/SQL từ model.
- **Dương:** model adapter/orchestration parse tool calls → `AIToolExecutor.execute` → summarize `ToolResult` + evidence; max tool turns, bounded context, prompting hardening; prompt injection trong LLM output không được cấp quyền. Reorder recommendation chỉ tính từ tồn/sales đã commit, đưa lời khuyên có lý do, **không tạo phiếu nhập**.
- **FE Lâm:** `POST /ai/query` request `{message}` và response `{answer,evidence,insufficient_data}`; loading label **“Đang xử lý dữ liệu...”**; lỗi 429, 503, insufficient evidence hiện copy an toàn, không lộ tool/raw SQL/model/provider details.

## 3. Giới hạn & lỗi

- Các mức **đã khóa bởi SRS:** AI 10 requests/phút/user, ADMIN-only, timeout/quota/tool call count phải có giới hạn nhưng **con số timeout/turn caps cụ thể cần PR phê duyệt** (TD-04/05). Đừng để mỗi agent hardcode khác nhau; dùng config central với conservative safe defaults được review.
- Không đưa model key vào FE hoặc log; scrub messages và PII, bounded prompt/result/response; tool-timeout mapped 503 or safe AI failure contract as appropriate; error envelope chung.
- LLM có thể sai số liệu: mọi câu trả lời phải có evidence/source period và thừa nhận khi không đủ dữ liệu. Test fixture để so số liệu AI viện dẫn với ToolResult thực tế.

## 4. Test matrix bắt buộc

1. Staff gọi `/ai/query` → 403; fake model gọi executor với STAFF → 403, không truy DB.
2. Model gọi `delete_product`/`execute_sql` → deny; model tự chèn `actor_id=1` → validation deny.
3. Tool arguments negative days, unknown fields, excessive limit, out-of-range dates → validation deny.
4. Slow/retry/model unavailable → safe 503/timeout, không leak secret/log; quota 429.
5. Recommendation không được ghi `purchase_receipts`, `inventory`, `orders`; compare snapshots before/after.
6. Prompt asks to reveal password/email/SKU costs → schema/role limits still enforce; no invented KPI from model.

## 5. Handoff & timing

**18/11:** Hiếu bàn giao executor stub + Tool IDs + schema fixture; Dương mock executor. **19–20/11:** Analytics DTO và tool adapter integration. **21–23/11:** model integration và MySQL E2E, FE real API test, red-team input. Bất kỳ breaking change nào phải sửa chung tool schema + tests + FE response.


---

## S3 CONTRACT TEST MATRIX

# RETAILOPS CF-2.0 — Integration/Contract Tests Sprint 3

**Không phải test results.** Đây là test cases owner/QA phải chuyển thành automated tests. DB/worker phải dùng môi trường test độc lập, không đánh dấu PASS nếu chỉ chạy mock hoặc `--collect-only`.

| ID | Provider → consumer | Scenario cụ thể | Evidence/expected outcome |
|---|---|---|---|
| O01 | Hiếu → Dương | Approval commit, RabbitMQ down | Approval và event trong MySQL, email chưa gửi; sau phục hồi publisher gửi event |
| O02 | Hiếu → Worker | Publisher RabbitMQ confirm rồi crash trước DB publish mark | Có thể republish; một event ID; terminal outcome không bị ghi hai lần |
| O03 | Hiếu → Worker | SMTP temporary error | Retry bounded, không đặt outcome SENT sớm |
| O04 | Hiếu → Worker | Permanent email failure | Outcome FAILED, monitoring ghi error code an toàn, không mất event |
| O05 | Hiếu → Worker | Two publisher/worker processes | Deployment config từ chối hoặc đảm bảo duy nhất một instance đúng ERD Lite |
| O06 | Hiếu/Dương | Encrypted reset link secret | Ciphertext at rest, key ngoài DB, không in token vào logs/message |
| R01 | Dương → Lâm | Forgot existing email / unknown email | Cùng HTTP 202 generic; không enumeration qua body hoặc thời gian bất thường |
| R02 | Dương → QA | Same reset token twice | Một success; request còn lại error, không thay password lần hai |
| R03 | Dương → QA | Expired token + wrong purpose | Reject; password/session giữ nguyên |
| R04 | Dương → QA | Successful Staff reset | Revoke live sessions; access token cũ không còn được chấp nhận |
| R05 | Hiếu/Dương → QA | REJECTED reapply proof | giữ user_id, thêm attempt, notification/event đúng một lần, 24h gate |
| A01 | Na Na → Lâm | 1 completed, 1 cancelled sale | revenue/AOV chỉ completed; cancelled count theo sold_at kỳ bán |
| A02 | Na Na → Lâm | Vietnamese day boundary | UTC half-open query; 23:59 vs 00:01 phân đúng ngày kinh doanh |
| A03 | Na Na → Lâm | Division/AOV .5 VND | ROUND_HALF_UP, integer VND, không float rounding |
| A04 | Dương → Na Na | Top products excludes cancelled | sold unit sum, stable tie ordering by product ID |
| A05 | Dương → Lâm | Slow products 0,2,3 sold | 0/2 included, 3 excluded nếu ACTIVE, quantity>0, first_stocked_at>7days |
| A06 | Na Na/Dương → Lâm/AI | Low stock 0,5,6 | 0/5 included, 6 excluded; ACTIVE only, threshold P0=5 |
| A07 | Na Na → Lâm | Dashboard compared direct Analytics | Same numbers; empty dataset returns zero KPIs/no 500 |
| A08 | Na Na → QA | Staff accesses analytics/dashboard | 403, no sensitive aggregate leakage |
| AI01 | Hiếu → Dương | Tool called by Staff | Fail RBAC on each execution, no read query |
| AI02 | Hiếu → Dương | Model asks tool `execute_sql` | No allowlist match, no SQL executed |
| AI03 | Hiếu → Dương | Model passes actor_id/role extra fields | Input rejected; principal-derived identity unmodified |
| AI04 | Hiếu → Dương | Tool limit=100000, invalid dates | Schema rejects; output bounded |
| AI05 | Dương → Lâm | AI model timeout, provider error | Safe error, no internal model/SQL/token surfaced |
| AI06 | Dương → Lâm | Recommendation query | Evidence and period included; no inventory/receipt mutation |
| AI07 | Dương → Lâm | Insufficient sales evidence | `insufficient_data=true`; no invented KPI |
| FE01 | Lâm → Lan Anh | Mock → real dashboard | OpenAPI shape validation; user-visible empty/error/loading states |
| FE02 | Lâm → Lan Anh | Mock → real AI | 403/429/503/insufficient_data UX, status not silently replaced with mock |
| G01 | Hiếu/Lan Anh | RC SHA to main release | Test evidence on same SHA; QA ACK, tech ACK, merge main then post-release smoke |

## Automate without introducing broad new framework

- Backend API/schema tests: FastAPI TestClient against real service and `app.openapi()`; compare canonical endpoint/path/DTO fields, manually approved exceptions documented.
- MySQL integration: `tests/integration/`, dedicated database URL guard, Alembic clean migration, test atomic effects and race with concurrent Session instances.
- Worker: fake SMTP + disposable broker/worker for retry/replay; never send real reset token emails in CI.
- FE: API client mock tests generated/validated from YAML and small end-to-end cases pointing to real backend integration environment.
- Security: Staff/Admin checks, field masking, no secrets in fixture/logs, quota and trusted proxy boundary; load test fixture documented separately.
