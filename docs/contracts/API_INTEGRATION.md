# RETAILOPS CF-2.1 — API INTEGRATION
> Bản tinh gọn: nội dung các tài liệu CF-2.0 được hợp nhất, không thay đổi nguồn chuẩn HTTP (`contracts/openapi.yaml`) và Python ABI (`contracts/python/*.pyi`). Các chương bên dưới là phần tham khảo có thể chứa ví dụ chữ ký cũ; khi khác canonical contract, ưu tiên ABI/OpenAPI và mở PR sửa hướng dẫn.


---

## HỢP ĐỒNG HTTP / MASTER CONTRACT INDEX

# RetailOps CF-2.0 — Contract Index (one canonical file per interface)

| ID | Owner → Consumers | Authority | Canonical reference |
|---|---|---|---|
| CF-01 Idempotency | Hiếu → Dương, Hiếu | SRS/ERD + CF1 typed design | `S2_CORE_CONTRACTS_LOCKED.md`, `contracts/python/retailops_core_ports.pyi` |
| CF-02 Inventory mutation | Dương → Hiếu, Lan Anh | SRS/ERD + CF1 typed design | `S2_CORE_CONTRACTS_LOCKED.md`, `.pyi` |
| CF-03 Receipt | Lan Anh Draft / Dương Confirm → Tân | SRS/ERD + CF1 design | `S2_CORE_CONTRACTS_LOCKED.md`, `contracts/openapi.yaml` |
| CF-04 Checkout/Cancel | Hiếu → Lâm, Na Na | SRS/ERD + CF1 design | `S2_CORE_CONTRACTS_LOCKED.md`, `contracts/openapi.yaml` |
| CF-05 Approval & registration email | Hiếu → Lâm, Dương | SRS required / path proposed | `S2_REMAINING_CONTRACTS.md`, `contracts/openapi.yaml` |
| CF-06 Read/Movement/Low Stock | Na Na → Tân/Lâm/Dương | Product existing / filters proposed | `S2_REMAINING_CONTRACTS.md`, `contracts/openapi.yaml` |
| CF-07 Redis/Proxy | Hiếu → All | SRS approved / code config validate | `S2_REMAINING_CONTRACTS.md` |
| CF-08 Outbox/Worker | Hiếu → Dương, QA | ERD Lite approved / signatures proposed | `S3_OUTBOX_EMAIL_RESET.md`, `contracts/python/retailops_extended_ports.pyi` |
| CF-09 Reset/Reapply | Dương + Hiếu security → Lâm | SRS approved / new paths proposed | `S3_OUTBOX_EMAIL_RESET.md`, `contracts/openapi.yaml` |
| CF-10 Analytics/Dashboard | Na Na + Dương → Lâm, AI | SRS approved / method/paths proposed | `S3_ANALYTICS_DASHBOARD.md`, `contracts/openapi.yaml` |
| CF-11 AI Tool Executor | Hiếu → Dương | SRS approved / Tool IDs proposed | `S3_AI_EXECUTOR.md`, `contracts/python/retailops_extended_ports.pyi` |
| CF-12 FE adapters | Lâm/Tân → QA | Contract use | `FRONTEND_MOCK_REAL_HANDOFF.md`, `contracts/typescript/api-client-contract.ts` |
| CF-13 CI/Release | Hiếu/Lan Anh → all | Delivery gate | `../workflow/CONTRACT_FREEZE_AND_GIT.md` |

**No duplicated source of truth:** OpenAPI YAML owns HTTP; Python `.pyi` owns proposed BE ABI; referenced markdown explains invariants/usage; Excel owns task assignments; real code and test evidence determine implementation status.


---

## TASK TO CONTRACT INDEX

# RETAILOPS CF-2.0 — Task → Contract Handoff Index (57/57)

**Cách dùng:** Excel là baseline phân công; các mã `S2-xx/S3-xx` chỉ là ID tham chiếu trong bộ docs, **không phải LMS ID**. Bảng này dẫn tới đúng card và contract để agent không tự đoán. Nếu method string của card cũ khác ABI mới, **`contracts/python/*.pyi` và `contracts/openapi.yaml` thắng**, mở PR sửa card; không tạo chữ ký thứ hai.

| Task | Owner | Hợp đồng | Provider/consumer interface phải đọc |
|---|---|---|---|
| [T04A61F — Phân quyền và duyệt Staff](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `HTTP-AUTH,BE-OUTBOX` | StaffApprovalService.decide(session, approval_id, decision, reason, actor_id); OutboxWriter.append(...). |
| [T04A639 — Khung Idempotency dùng chung](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `BE-IDEM` | IdempotencyExecutor.execute(session, *, actor_id, operation, idempotency_key, request_identity, command) — xem CF-01. |
| [T04A653 — Inventory Service](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `BE-INVENTORY` | InventoryService.lock_for_mutation(session, *, product_ids) → các phương thức increase_for_receipt/decrease_for_checkout/restore_for_cancel/adjust_to_count(session, *, locks=StockL |
| [T04A66F — Bộ khung kiểm thử MySQL](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `TEST-DB` | pytest fixture mysql_test_session và deterministic concurrency harness. |
| [T04A689 — CI cho Pull Request](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lan Anh | `GATE-CI` | GitHub Actions jobs: Ruff, unit, MySQL integration, clean Alembic migration, security, FE lint/build. |
| [T04A6A3 — API tra cứu sản phẩm](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `HTTP-PRODUCT` | GET /products?q=&category_id=&status=&page=&page_size=; GET /products/{id}. |
| [T04A6BD — API tra cứu tồn kho](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `HTTP-INVENTORY` | GET /inventory; GET /inventory/{product_id}. |
| [T04A6D7 — Tạo và sửa phiếu nhập nháp](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lan Anh | `HTTP-RECEIPT,BE-RECEIPT` | ReceiptDraftService.create_draft / update_draft; POST/PATCH /purchase-receipts. |
| [T04A6F3 — Giao diện duyệt Staff](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `HTTP-AUTH,FE-ADAPTER` | StaffApprovalPage -> staffApprovalsApi.list/approve/reject. |
| [T04A70D — Giao diện danh mục, nhà cung cấp](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `HTTP-MASTER,FE-ADAPTER` | CategoryPage/SupplierPage -> existing categories/suppliers client. |
| [T04A73C — Checkout và Order Model](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `HTTP-ORDER,BE-IDEM,BE-INVENTORY` | CheckoutService.checkout(session, actor_id, items, key); POST /orders/checkout. |
| [T04A758 — Điều chỉnh tồn kho](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `HTTP-INVENTORY,BE-IDEM,BE-INVENTORY` | InventoryService.lock_for_mutation → adjust_to_count(session, *, locks, actor_id, adjustment); POST /inventory/{product_id}/adjustments. |
| [T04A772 — Hủy nháp và tra cứu phiếu nhập](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lan Anh | `HTTP-RECEIPT,BE-RECEIPT` | ReceiptDraftService.cancel_draft / list_receipts / get_receipt. |
| [T04A78E — Lịch sử biến động và cảnh báo tồn thấp](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `HTTP-INVENTORY` | GET /stock-movements; GET /inventory/low-stock. |
| [T04A7A8 — Giỏ hàng POS](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `HTTP-PRODUCT,HTTP-ORDER,FE-ADAPTER` | usePosCart + productsApi.list -> checkoutApi.checkout. |
| [T04A7C3 — Giao diện thao tác phiếu nhập](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `HTTP-RECEIPT,FE-ADAPTER` | ReceiptEditor -> receiptsApi.create/update/confirm/cancel. |
| [T04A7DF — Xác nhận phiếu nhập](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `HTTP-RECEIPT,BE-INVENTORY,BE-IDEM` | ReceiptConfirmService.confirm(session, *, actor_id, receipt_id, expected_draft_version, idempotency_key) — xem CF-03. |
| [T04A80C — Hủy đơn và hoàn tồn](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `HTTP-ORDER,BE-INVENTORY,BE-IDEM` | CancelOrderService.cancel(session, order_id, actor_id, reason, key). |
| [T04A826 — Redis Rate Limiting](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `HTTP-RATE` | RedisRateLimiter rules and 429/503 response contract. |
| [T04A840 — API lịch sử đơn hàng](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `HTTP-ORDER` | GET /orders; GET /orders/{order_id}. |
| [T04A869 — Giao diện Checkout](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `HTTP-ORDER,FE-ADAPTER` | checkoutApi.checkout(items, key) + PRICE_CHANGED flow. |
| [T04A883 — Giao diện hủy đơn](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `HTTP-ORDER,FE-ADAPTER` | ordersApi.cancel(orderId,reason,key); ordersApi.get(orderId). |
| [T04A89D — Giao diện tồn kho thiết yếu](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `HTTP-INVENTORY,FE-ADAPTER` | inventoryApi.list/adjust and stock-version form. |
| [T04A8B7 — Giao diện lịch sử phiếu nhập](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `HTTP-RECEIPT,FE-ADAPTER` | receiptsApi.list/get; status UI. |
| [T04A8D1 — Kiểm tra Docker và Nginx](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `DEPLOY` | Docker Compose + Nginx /api/v1 proxy, SPA fallback and trusted headers. |
| [T04A8F3 — Kiểm thử end-to-end Sprint 2](../sprint2/TASK_IMPLEMENTATION_GUIDE.md) | Lan Anh | `GATE-E2E` | Receipt DRAFT -> CONFIRMED -> Inventory -> Checkout -> Cancel; Approval/Auth. |
| [T04A90F — Transactional Outbox và Email Worker](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `BE-OUTBOX` | OutboxPublisher.poll_publish; Celery EmailWorker.handle(event_id). |
| [T04A92B — Analytics doanh thu và đơn hàng](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `HTTP-ANALYTICS` | GET /analytics/sales. |
| [T04A947 — Analytics sản phẩm](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `HTTP-ANALYTICS` | GET /analytics/products/top; /analytics/products/slow. |
| [T04A961 — Hoàn thiện lịch sử và hủy đơn UI](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `HTTP-ORDER,FE-ADAPTER` | OrderHistoryPage -> ordersApi.list/get/cancel. |
| [T04A97C — Hoàn thiện giao diện tồn kho](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `HTTP-INVENTORY,FE-ADAPTER` | InventoryHistoryPage -> inventoryApi.movements/lowStock. |
| [T04A996 — Tài liệu và UAT](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Lan Anh | `GATE-E2E,DEPLOY` | README/runbook + UAT scenarios + defect ledger. |
| [T04A9B0 — Kiểm thử giao diện quản lý](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `FE-ADAPTER,GATE-E2E` | Product/Receipt/Inventory real API UI suite. |
| [T04A9CA — Kiểm thử Auth, Checkout và Cancel](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `TEST-DB` | Auth+Checkout+Cancel MySQL regression tests. |
| [T04A9E6 — AI Tool Executor](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `BE-AI` | AIToolExecutor.execute(tool_id,args,principal,session). |
| [T04AA00 — Retry và phục hồi Email Worker](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `BE-OUTBOX` | Worker retry/backoff/replay and terminal outcome handling. |
| [T04AA1C — Đặt lại mật khẩu và tích hợp email](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `HTTP-RESET,BE-OUTBOX` | AuthResetService.request_reset/consume_reset -> OutboxWriter.append. |
| [T04AA36 — Dashboard API](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `HTTP-ANALYTICS` | GET /dashboard. |
| [T04AA50 — Automated Integration Tests](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `TEST-DB,GATE-CI` | MySQL concurrency + worker/AI integration regression. |
| [T04AA6A — Responsive và UI States](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `FE-ADAPTER` | Shared responsive/loading/empty/error states. |
| [T04AA86 — AI chỉ đọc và Tool Calling](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `BE-AI,HTTP-AI` | ReadOnlyAIService.ask(message, principal) -> evidence answer. |
| [T04AAA2 — Đo hiệu năng và xác minh bảo mật](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `PERF,GATE-E2E` | P95 Product/Inventory/Checkout/Confirm/Dashboard + security report. |
| [T04AABC — Kiểm thử Purchasing và Email](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `TEST-DB,BE-OUTBOX` | Purchasing + Email failure/replay reconciliation suite. |
| [T04AAD7 — Kiểm thử Product, Order và Analytics](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `TEST-DB,HTTP-ANALYTICS` | Product/Order/Analytics independent reconciliation. |
| [T04AAF1 — Kiểm thử frontend nghiệp vụ](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `GATE-E2E,FE-ADAPTER` | Auth/POS/Checkout/Cancel FE E2E real API. |
| [T04AB0B — AI gợi ý nhập hàng](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `BE-AI,HTTP-AI` | ReadOnlyReorderAdvisor.suggest -> evidence-only DTO. |
| [T04AB25 — Giao diện Dashboard và AI](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `HTTP-ANALYTICS,HTTP-AI,FE-ADAPTER` | DashboardPage + AIChatPage via typed API clients. |
| [T04AB3F — Rà soát bảo mật và concurrency](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `SECURITY,TEST-DB` | Security/RBAC/CSRF/concurrency sign-off evidence. |
| [T04AB59 — Kiểm thử Inventory, Worker và AI](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `TEST-DB,BE-OUTBOX,BE-AI` | Inventory/Worker/AI integration and outage suite. |
| [T04AB73 — Tích hợp và demo Worker/Redis/AI](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Dương | `GATE-E2E` | Compose integrated Worker/Redis/AI demo run. |
| [T04AB8D — Triển khai bản demo](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `DEPLOY` | Release Candidate deployment with immutable commit SHA. |
| [T04ABA7 — Release và smoke test](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Hiếu | `DEPLOY,GATE-E2E` | Release approval then main deployment smoke. |
| [T04ABC3 — Nghiệm thu và đóng băng release](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Lan Anh | `GATE-E2E` | QA/UAT Sign-off and P0 freeze decision. |
| [T04ABDD — Báo cáo QA và tài liệu demo](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Lan Anh | `GATE-E2E,DEPLOY` | QA report, seed/runbook/demo script. |
| [T04ABF9 — Tổng hợp giao diện và bằng chứng QA](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Tân | `FE-ADAPTER,GATE-E2E` | FE screenshots/videos and UI audit. |
| [T04AC15 — Đối soát dữ liệu và báo cáo](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Na Na | `HTTP-ANALYTICS,GATE-E2E` | Reconciliation of orders/inventory/analytics snapshots. |
| [T04AC2F — Kiểm tra end-to-end frontend](../sprint3/TASK_IMPLEMENTATION_GUIDE.md) | Lâm | `FE-ADAPTER,DEPLOY,GATE-E2E` | SPA/nginx full frontend smoke on release candidate. |


---

## S2 REMAINING CONTRACTS

# RETAILOPS — CF-2.0 | Hợp đồng còn lại Sprint 2

**Áp dụng:** cả nhóm; owner phê duyệt là người trong Excel; bản này là **contract design freeze candidate**. Contract core S2 giữ nguyên trong `S2_CORE_CONTRACTS_LOCKED.md` + `contracts/python/retailops_core_ports.pyi`. HTTP schema là `contracts/openapi.yaml`. Không khẳng định endpoint mới đã có trong code.

## A. Staff Approval — Hiếu → Lâm; Outbox Writer Hiếu

- **Code đang có:** `User`, `StaffApprovalRequest`, `UserRole`, `UserStatus` trong `backend/app/modules/auth/models.py`; `CurrentPrincipal`, `require_active_admin` trong `auth/dependencies.py`. S1 có register/login; phần approve/reject chưa có ở commit được kiểm tra.
- **HTTP:** `GET /api/v1/staff-approvals?status=PENDING&page=1&page_size=20`, `POST /staff-approvals/{id}/approve` body `{}`, `POST .../{id}/reject` body `{reason:string}`. `200 ApprovalRead` theo OpenAPI; 401 chưa đăng nhập, 403 không ADMIN, 404 ID không tồn tại, 409 khi đã quyết định/stale. Không tự phát minh vai trò MANAGER hoặc khóa/mở khóa Staff.
- **Service port (đề xuất chữ ký chính thức):** `StaffApprovalService.list(session, *, status, page, page_size) -> ApprovalPage`; `decide(session, *, actor_id, approval_id, decision: Literal['APPROVED','REJECTED'], reason: str | None) -> ApprovalRead`.
- **Transaction:** lock approval request + Staff user theo thứ tự cố định, kiểm tra pending, đổi trạng thái User tương ứng, đóng approval request, `OutboxWriter.append(..., event_type='STAFF_APPROVED'/'STAFF_REJECTED')`, một commit ở `StaffApprovalService`. Race 2 ADMIN: chính xác một transition thành công, một 409; event không nhân đôi. Broker/email offline không rollback quyết định đã commit.
- **Đừng bỏ quên AUTH-01:** Registration hợp lệ phải ghi event `STAFF_REGISTERED` bền vững khi Outbox Writer đã được thêm. Trường hợp REJECTED reapply phải xác thực quyền kiểm soát email; giữ nguyên User ID, tối đa một lần/24 giờ, không tạo trùng notification; phải bổ sung integration tests và endpoint dưới contract Auth ở S3 hoặc trước P0 signoff nếu flow được nghiệm thu. Hành vi đã có trong SRS, không tự cắt scope.
- **Handoff FE:** Lâm mock từ `ApprovalPage`/`ApprovalRead`; 403 không hiện chức năng ADMIN; 409 refresh list; không dùng UI ẩn nút làm RBAC. Consumer ACK bằng contract test.

## B. Product Search, Inventory Read, Low Stock, Movement — Na Na → Lâm/Tân/Dương

- **Giữ endpoint đang tồn tại** `GET /api/v1/products`, `GET /products/{id}` và schema `ProductRead`: `id,category_id,sku,name,status,sale_price_vnd,quantity,stock_version,created_at,updated_at`. Không làm endpoint `/product-search` mới. S2 thêm bounded `q`, `category_id`, `status`, stable sorting/id tie-breaker; response `{items,total,page,page_size}`.
- **InventoryReadService:** `list(session, *, filters: InventoryQuery) -> Page[InventoryRead]`, `get(session, *, product_id:int)->InventoryRead`, `low_stock(session, *, page:int,page_size:int)->Page[LowStockItem]`; READ-ONLY, không lock/mutate/commit. HTTP `GET /inventory`, `/inventory/{product_id}`, `/inventory/low-stock` theo OpenAPI; phải đăng ký route tĩnh `/low-stock` trước dynamic `/{product_id}`.
- **StockMovementReadService:** `list(session, *, filters: MovementQuery, actor_role:str)->Page[StockMovementRead]` phục vụ `GET /stock-movements`, stable keyset/page ordering. Với Staff, whitelist SKU, kind, quantity, timestamp, reference; **không lộ giá nhập, giá vốn, reason kiểm kê, actor PII**; Admin thấy trường phù hợp SRS. Vì API chung cùng DTO, default public-safe fields; trường nhạy cảm chỉ được trả qua schema Admin explicit nếu thực sự cần.
- **Threshold P0:** Product ACTIVE và `quantity <= 5` (bao gồm 0). `INV-05` custom threshold là P1; không thêm UI cấu hình/ngưỡng DB vào P0. Một định nghĩa áp dụng Inventory, Analytics, Dashboard, AI. Không lưu logic ngưỡng trùng ở nhiều service.
- **Dữ liệu:** inventory đã có ORM ở `products/models.py` và migration Product/Inventory; Na Na **không chờ** Dương làm Inventory mutation. Không SELECT N+1 cho list. Page bound 1..100; SQL filter phải parameterized, không sort trên tên cột do user đưa vào nếu chưa allowlist.

## C. Purchasing Draft/History — Lan Anh → Dương/Tân

- Các port `ReceiptDraftService.create_draft/update_draft/cancel_draft`, `ReceiptConfirmService.confirm` và `ReceiptRead` nằm ở contract core. **Dương confirm dùng DTO do Lan Anh cung cấp**, không tạo lớp ReceiptRead khác.
- `DRAFT` không đổi tồn; cùng Product + cùng Unit Cost gộp quantity; cùng Product + Unit Cost khác trả 422. `purchase_receipt_items` khóa `(receipt_id,product_id)` nên không chứa hai hàng một Product khác giá. Tính `total_vnd` ở backend (int VND); không tin tổng FE gửi lên.
- Confirm: ADMIN, `Idempotency-Key`, expected `draft_version`; lock header → lock Product/Inventory theo ID tăng dần; kiểm tra Supplier/Product ACTIVE; tăng kho và movement trong một transaction; snapshot Product/Supplier theo ERD; terminal immutable. Cancel Draft: `expected_draft_version`, không mutation inventory, terminal immutable.
- **Release dependency cần xử lý:** ORM Receipt tồn tại nhưng thời điểm kiểm tra `develop` chưa có revision tạo Receipt tables. Dương/owner schema S1 bàn giao migration đầu S2, một Alembic head, clean MySQL upgrade; Lan Anh có thể dùng unit fake trước đó, không công bố REAL_API_PASS.
- **FE:** Tân dùng `ReceiptRead/ReceiptPage` với mock adapter; query lọc ở `GET /purchase-receipts`; 409 stale phải refresh receipt và hỏi người dùng, không tự gửi lại request ghi trên version cũ.

## D. Checkout, Order Read và FE POS — Hiếu/Na Na → Lâm

- `POST /orders/checkout` trả 201 `OrderRead(COMPLETED)`; fail `PRICE_CHANGED` trả 409 và `changed_items`; không tạo order/movement; UI chỉ retry **key mới** sau khi người bán xác nhận giá mới. Network timeout không rõ kết quả: retry **cùng key/payload**.
- Order GET (`/orders`, `/orders/{id}`) do Na Na, dùng snapshot OrderItem; Staff được đọc mọi Order; cancel permission tách riêng tại `POST /orders/{id}/cancel` (Hiếu). Admin cancel cùng ngày VN; Staff cùng ngày VN + owner + không quá 15 phút. Cùng order/khác key hủy đồng thời chỉ được hoàn kho một lần.
- Giỏ hàng POS của Lâm là state local báo giá, không reserve stock. FE và BE cùng dùng các trường `viewed_unit_price_vnd` và `sale_price_vnd`, không đổi tên thành `price` không có trong schema.

## E. Redis & Reverse Proxy — Hiếu → tất cả HTTP callers

- Rate-limit SRS: login 5/phút/IP & 20/giờ/account; register 5/60s/IP; forgot 3/giờ/IP và email; refresh 10/phút/session; AI 10/phút/user; business 120/phút/user. Tính distinct keys và lưu Redis TTL; tránh key chứa email plaintext bằng digest phù hợp. HTTP 429 chuẩn `{code:'RATE_LIMITED',message,details}` + `Retry-After` khi có.
- Redis down: public Auth và AI **fail-closed**; POS và nghiệp vụ nội bộ được tiếp tục **chỉ khi** live session/RBAC vẫn kiểm tra được với MySQL. Không fail-open Auth để demo cho nhanh.
- Client IP chỉ tin trusted proxy chain do Nginx/Cloudflare cấu hình; không tin X-Forwarded-For tùy ý. Docker/Nginx phải dùng HTTPS, cookies, CSRF/Origin, secrets ngoài repo. Contract đã có handler lỗi chuẩn trong `app.core.exceptions`.

## GATE cho Sprint 2

1. Approval transaction + Outbox append atomic; race approve/reject.
2. Receipt migration trên MySQL sạch; draft stale/cancel/confirm double-request.
3. Checkout 2 request tranh tồn, idempotency replay, rollback, cancel two keys/next-day.
4. Read endpoints chống lộ cost/reason và không N+1; FE mock → real từng API.
5. 401/403/409/422/429/503 mô tả đúng khi áp dụng, không chép lỗi không thể xảy ra vào acceptance.


---

## API HANDOFF

# RetailOps — Hợp đồng HTTP giữa Backend ↔ Frontend

**Status: CORE S2 FROZEN DESIGN (CF-1.0); các API khác CANDIDATE.** (không tự coi endpoint mới đã code). Machine-readable contract: [`../../contracts/openapi.yaml`](../../contracts/openapi.yaml). Khi được owner + consumer duyệt và PR merge, YAML trở thành nguồn dữ liệu chung để BE test response, FE tạo types/mocks. Markdown này giải thích ngữ nghĩa và tình huống khó; **không phát minh thêm field** ngoài YAML.

## 0. Xem contract authoritative trước

Receipt/Checkout/Cancel/Inventory mutation: [`../contracts/S2_CORE_CONTRACTS_LOCKED.md`](BACKEND_INTERFACES.md). JSON sample chạy thử: `contracts/examples/`. Python backend dùng `.pyi`. Xung đột thì contract frozen thắng và phải sửa chéo tài liệu qua PR.

## 1. Convention bắt buộc

- Prefix API `GET/POST/PATCH /api/v1/...` (theo `app/main.py` và cấu hình); response success resource trực tiếp, list `{items,total,page,page_size}`; `page>=1`, `1<=page_size<=100`.
- Auth: Bearer access token do frontend giữ trong memory; refresh token HttpOnly cookie theo Auth S1; ADMIN/STAFF được kiểm tại Backend bằng principal verified MySQL session, không tin role do FE gửi.
- JSON `snake_case`, tiền VND integer (`bigint` trên MySQL), timestamp UTC ISO-8601; ngày kinh doanh và sale analytics phân kỳ `Asia/Ho_Chi_Minh`. Không gửi VAT, discount, payment_method, refund, return, warehouse_id, AI write action.
- Error envelope thật trong code: `{ "code": "...", "message": "...", "details": null | object | array }` (xem `app/core/exception_handlers.py`). Không tự bịa body `{success,error}`.
- `Idempotency-Key` bắt buộc khi Checkout, Confirm Receipt, Cancel Order và Inventory Adjustment. FE phải giữ nguyên key khi retry **cùng ý định + cùng payload**; thay key khi người dùng tạo **ý định mới** (vd. nhận giá mới); không sinh key mới với cùng lệnh chưa rõ kết quả.
- Không gửi `stock_version`, `quantity` vào Product Create/Patch: Inventory mutation qua Inventory Service duy nhất.

## 2. Những endpoint đã có trên `develop` vs mới đề xuất

**Đã xác thực bằng source**:

| Source | Endpoint / DTO | Trạng thái |
|---|---|---|
| `backend/app/modules/products/router.py` | `GET /products`, `GET /products/{id}`, `POST /products`, `PATCH /products/{id}`, `PATCH /products/{id}/status` | CÓ TRONG CODE; `GET /products` hiện chỉ nhận `page`, `page_size` |
| `backend/app/modules/auth/router.py` | `POST /auth/register`, `/auth/login`, `GET /auth/csrf`, `POST /auth/refresh`, `POST /auth/logout` | CÓ TRONG CODE |
| `backend/app/modules/notifications/router.py` | `GET /admin/notifications`, `.../unread-count`, `PATCH .../read`, `.../read-all` | CÓ TRONG CODE |
| `backend/app/modules/purchasing/models.py` | `purchase_receipts`, `purchase_receipt_items` ORM | CÓ ORM; chưa xác minh migration đã merge |

**Cần khóa trước code**: toàn bộ API mới trong `openapi.yaml`, kể cả tên `/purchase-receipts` (không được tự đổi thành `/receipts`), `GET /products` filters mới, `POST /orders/checkout` và `POST /ai/query`. Các URL này là **đề xuất thống nhất**, không phải khẳng định hiện có.

## 3. Bảng API provider/consumer

| Provider (owner) | HTTP API (contract candidate) | Consumers |
|---|---|---|
| Hiếu | `GET /staff-approvals`, `POST /staff-approvals/{id}/approve`, `.../reject` | Lâm Approval UI |
| Na Na | `GET /products` (filter/search extension), `/inventory`, `/inventory/{id}`, `/stock-movements`, `/inventory/low-stock` | Lâm POS; Tân Inventory, Product UI; Dương AI |
| Lan Anh | `GET/POST /purchase-receipts`, `GET/PATCH /purchase-receipts/{id}`, `POST .../{id}/cancel` | Tân Receipt UI; Dương Confirm |
| Dương | `POST /purchase-receipts/{id}/confirm`, `POST /inventory/{id}/adjustments` | Tân Receipt/Inventory UI; Lan Anh QA |
| Hiếu | `POST /orders/checkout`, `POST /orders/{id}/cancel` | Lâm POS/Order UI; Na Na Order Read |
| Na Na | `GET /orders`, `GET /orders/{id}`, `/analytics/sales`, `/dashboard` | Lâm Order/Dashboard; Dương AI |
| Dương | `GET /analytics/products/top`, `GET /analytics/products/slow`, `POST /ai/query`, `POST /auth/forgot-password`, `POST /auth/reset-password` | Lâm Dashboard/AI/Auth UI; Hiếu Executor |

`/ai/query` public HTTP endpoint may be owned by Dương orchestration but MUST delegate tool execution to Hiếu's server-side Executor. Các permission/limits của Executor không lấy từ model-generated arguments.

## 4. Payload quyết định để FE mock và BE implement cùng một cách

### A. Staff Approval — Hiếu → Lâm

Request:

```http
POST /api/v1/staff-approvals/25/approve
Authorization: Bearer <access-token>
```

Response 200 là `ApprovalRead`: `id`, `user_id`, `attempt_no`, `status="APPROVED"`, `requested_at`, `decided_by`, `decided_at`, `decision_reason`; **không trả mật khẩu/token**. Từ chối dùng `POST .../reject` body `{"reason":"Không đáp ứng yêu cầu"}`. `403` với STAFF; `409 INVALID_STATE` nếu hồ sơ đã xử lý; race hai Admin chỉ một transition thành công. Durable Outbox event ghi **cùng transaction**, không báo email SENT khi worker chưa chạy.

### B. Receipt Draft / Confirm — Lan Anh ↔ Dương → Tân

```json
// POST /api/v1/purchase-receipts (ADMIN)
{"supplier_id":4,"items":[
  {"product_id":12,"quantity":3,"unit_cost_vnd":40000},
  {"product_id":12,"quantity":2,"unit_cost_vnd":40000}
]}
```

Backend chuẩn hóa thành một item quantity=5; `total_vnd=200000`; `status="DRAFT"`, `draft_version=1`, **Inventory unchanged**. Cùng Product, hai giá nhập khác nhau phải `422`, không tự tính trung bình.

```http
POST /api/v1/purchase-receipts/78/confirm
Idempotency-Key: logical-confirm-intent-123456
Content-Type: application/json

{"expected_draft_version":3}
```

Confirm chỉ khi DRAFT và version=3; lock Receipt header trước rồi lock products/inventory theo ID tăng dần; update Receipt + Inventory + Movement + idem result trong **một transaction**. 409 khi stale version/terminal, replay cùng key+payload không tăng tồn hai lần. `POST .../cancel` của **DRAFT** chỉ nhận `expected_draft_version`, không dùng chung nghiệp vụ hoàn kho/receipt reversal.

### C. Checkout / PRICE_CHANGED — Hiếu → Lâm, Na Na

```json
// POST /api/v1/orders/checkout; Header: Idempotency-Key: <stable-intent-key>
{"items":[{"product_id":12,"quantity":2,"viewed_unit_price_vnd":65000}]}
```

**Success 201:** `OrderRead`: `id`, `status="COMPLETED"`, `total_vnd`, `created_by`, `sold_at`, `items[]` có `sku_snapshot`, `product_name_snapshot`, `quantity`, `unit_price_vnd`, `line_total_vnd`. Checkout ghi `orders/order_items`, giảm tồn, Movement, idempotency response trong một transaction. Không nhận tổng giá client như nguồn sự thật.

**409 PRICE_CHANGED** — chốt dạng sau trước merge, bao gồm danh sách item đổi giá để FE hiển thị:

```json
{
  "code":"PRICE_CHANGED",
  "message":"Giá sản phẩm đã thay đổi. Vui lòng xác nhận lại.",
  "details":{"changed_items":[
    {"product_id":12,"viewed_unit_price_vnd":65000,"current_unit_price_vnd":70000}
  ]}
}
```

Không tạo Order hoặc Movement khi 409. FE cập nhật giá và hỏi người dùng xác nhận; chỉ khi họ xác nhận mới **tạo ý định mới/key mới**. Khi timeout chưa biết kết quả: giữ nguyên key và payload, **không** tự gửi lệnh mới.

### D. Cancel Order — Hiếu → Lâm, Na Na

```http
POST /api/v1/orders/82/cancel
Idempotency-Key: logical-cancel-intent-123456
Content-Type: application/json

{"reason":"Khách không mua nữa"}
```

STAFF chỉ cancel **Order do mình tạo**, trong **15 phút** và **cùng ngày kinh doanh Asia/Ho_Chi_Minh**; ADMIN cancel bất kỳ COMPLETED order nào trong **cùng ngày**. Success 200 Order `status="CANCELLED"` và hoàn tồn đúng một lần. Khác key vẫn không được restore lại một Order đã CANCELLED. Staff được **đọc mọi Order**, khác với quyền cancel.

### E. Inventory Count Adjustment — Dương → Tân

```http
POST /api/v1/inventory/12/adjustments
Idempotency-Key: inventory-adjust-intent-1234
Content-Type: application/json

{"counted_quantity":7,"expected_stock_version":4,"reason":"Kiểm kê cuối ngày"}
```

Admin only. Nếu tồn đang 7, version 4 thì trả audit result và `movement_created=false`, **không bump version**. Nếu tồn đã thay đổi/version cũ: 409, FE phải refetch và yêu cầu xác nhận lại, không silent retry với bản đếm cũ. Staff chỉ xem stock, không được gọi adjustment.

### F. Analytics / Dashboard / AI — Na Na, Dương → Lâm

`GET /analytics/sales`: revenue và AOV **chỉ tính Order đang COMPLETED**; số CANCELLED được quy về kỳ `sold_at`, không `cancelled_at`; tiền nguyên VND, AOV ROUND_HALF_UP. `GET /analytics/products/slow`: ACTIVE, quantity>0, `first_stocked_at` > 7 ngày, số bán ≤2 trong 30 ngày, loại mọi đơn đã CANCELLED. Low-stock P0 threshold=5 dùng chung Inventory/Dashboard/AI.

`POST /ai/query` body `{"message":"Hàng nào sắp hết?"}` → `{answer,evidence:[{source,period,summary}],insufficient_data}`. Chỉ Admin; UI không tự gọi tool hoặc SQL, không hiển thị stack trace, credentials và internal tool names. Ở đây AI chỉ tư vấn, **không tạo Receipt**.

## 5. API mock ↔ real FE — phương thức sử dụng

**Một bộ types sinh từ cùng OpenAPI**, rồi `features/.../api.ts` bọc Axios; mock dùng đúng DTO/schema; không copy interface tự định nghĩa ở từng component. Có thể dùng generator TS/OpenAPI sau khi nhóm chọn dependency phù hợp; không bắt buộc bổ sung tool mới trong đợt đầu nếu làm chậm Sprint.

```ts
// Pseudo-client shape; adapt paths to the existing frontend structure after inspection.
export type CheckoutIntent = {
  items: Array<{ product_id: number; quantity: number; viewed_unit_price_vnd: number }>;
};

export async function checkout(intent: CheckoutIntent, idempotencyKey: string) {
  return apiClient.post('/orders/checkout', intent, {
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}
```

- FE có `VITE_API_MODE=mock|real` **chỉ như một đề xuất cấu hình dev**. Trên integration / CI E2E / demo bắt buộc `real`, không bắt lỗi network rồi tự chuyển `mock` (đã từng là vấn đề Sprint 1).
- Khi khai báo FastAPI router cho Inventory, **đăng ký đường dẫn tĩnh `/inventory/low-stock` trước `/inventory/{product_id}`** để tránh path động bắt nhầm `low-stock` thành product ID và trả 422 sai. Path tests phải bao phủ trường hợp này.
- Mock frontend phải trả `401/403/409/422/429/503`, không chỉ 200; state `loading/empty/error/conflict` phải test. `409 PRICE_CHANGED` cần dữ liệu `changed_items` giống trên.
- Mỗi khi provider merge API, consumer chuyển **riêng endpoint ấy** sang real, smoke test ngày đó. Link PR + commit SHA trong daily handoff. Không cần chờ toàn bộ backend Sprint.
- Network timeout `Checkout`: không tự xoá key cho đến khi có bằng chứng request chắc chắn thất bại không tạo effect hoặc user bắt đầu một ý định mới; rủi ro duplicate nếu auto-generate key trên mỗi retry.

## 6. Không được làm theo docs nếu gặp trường hợp này

Nếu OpenAPI khác SRS/ERD, code hiện tại đang có path/DTO khác, thiếu migration hoặc provider chưa review contract: **dừng phần tích hợp phụ thuộc, báo owner/Tech Lead**, nhưng tiếp tục phần UI/fake/unit có thể làm độc lập. Không để Agent thay đổi domain/schema qua một PR frontend để giải quyết bất đồng.


---

## FRONTEND MOCK-REAL HANDOFF

# RetailOps — FE contract: Mock-to-Real không đổi hành vi

**Lâm:** Staff Approval, POS/Checkout, Cancel/History, Dashboard/AI. **Tân:** Products/Category/Supplier, Receipt, Inventory/Movement. **Providers:** Hiếu, Dương, Lan Anh, Na Na.

## One-source rule

- HTTP định nghĩa ở `contracts/openapi.yaml` (path, `operationId`, types, required, status, auth); `contracts/typescript/api-client-contract.ts` là **reference types/adapter** cho các nghiệp vụ quan trọng, không thay OpenAPI và không phải code đã được build.
- Mock được sinh/tạo từ OpenAPI schema + `contracts/examples/` cố định; không duy trì JSON tùy tiện ở từng React component. Bắt đầu FE bằng `MockRetailOpsApi` implement `RetailOpsApi`; switch bằng cấu hình môi trường build/test explicit: `mock` hoặc `real`.
- Client gửi `Authorization: Bearer <access JWT in memory>`; refresh token cookie HttpOnly/Secure tự đi qua credentials khi gọi refresh, áp dụng CSRF/Origin theo Auth S1; **không lưu access JWT vào localStorage**. Không gửi business user ID từ FE thay authenticated identity.

## Bàn giao từng endpoint, không chờ toàn module

1. Provider gửi contract SHA, fixture, path/method, required fields, status/errors, RBAC; consumer ACK trước coding.
2. FE hoàn thiện loading/empty/401/403/409/422/429/503 và retry UX qua mock adapter. E2E mock chỉ mang nhãn `MOCK PASS`.
3. Provider PR merge `develop` + migration/test PASS; FE bật real adapter **chỉ cho endpoint đó** tại integration environment. Không mix mock âm thầm cho nghiệp vụ đã real.
4. Consumer xác nhận response bằng schema validator + test trong React; báo contract drift với sample trace không có secret. Provider sửa implementation nếu contract đúng; đổi contract phải review cả consumer.
5. Lan Anh xác nhận `REAL API PASS` rồi `E2E PASS`; bản demo chỉ dùng endpoint đã được xác minh.

## Danh sách scenarios FE bắt buộc

| FE screen | Success | Failure UX |
|---|---|---|
| Approval (Lâm) | 200 approve/reject, refresh list | STAFF 403, stale 409, pending badge |
| POS (Lâm) | 201 Order COMPLETED | `PRICE_CHANGED` 409 → confirm giá mới; unclear timeout → retry same key; inactive/stock 409 |
| Cancel (Lâm) | 200 CANCELLED, update history | Not owner, over 15min, next VN day, already cancelled; never force retry with new key |
| Receipt (Tân) | Draft, edit, confirm, cancel | 409 draft_version stale → refresh; terminal immutable; cost fields ADMIN-only |
| Inventory (Tân) | list, low stock, adjustment Admin | stale stock_version 409, STAFF cannot adjustment, no-op count audit |
| Dashboard (Lâm) | numbers = API analytics | empty dataset, 403 STAFF, timezone/date filter |
| AI (Lâm) | evidence panel + text | loading “Đang xử lý dữ liệu...”, 429 quota, 503 unavailable, insufficient data, safe copy |
| Reset (Lâm/owner FE shared) | generic forgot acknowledgement, valid reset | never expose whether email exists; token invalid/expired |

## Example wrapper behavior (illustrative, not implementation)

```ts
async function submitCheckout(api: RetailOpsApi, intent: {payload: CheckoutRequest, key: string}) {
  try { return await api.checkout(intent.payload, intent.key); }
  catch (e) {
    // If uncertainty is network-only: preserve intent.payload + intent.key for user retry.
    // 409 PRICE_CHANGED: show new prices; only create a new key AFTER explicit user consent.
    // 401/403/409/422: display appropriate state; never silently retry destructive command.
    throw e;
  }
}
```

Never call backend `POST /orders/checkout` automatically twice with different keys during one user intent. Do not accept frontend mock status as real integration evidence.


---

## ANALYTICS DASHBOARD

# RETAILOPS CF-2.0 — Analytics & Dashboard Contracts

**Providers:** Na Na — sales analytics + Dashboard façade; Dương — product analytics. **Consumers:** Lâm (FE), Dương (AI orchestration). Nguồn HTTP: `contracts/openapi.yaml`; Python typed ports: `contracts/python/retailops_extended_ports.pyi`. Không thêm Redis cache cho P0 nếu không có invalidation đã kiểm chứng.

## Cấu trúc service — một nguồn định nghĩa KPI

```python
SalesAnalyticsService.summary(session, *, period: Period) -> SalesSummary
ProductAnalyticsService.top(session, *, period: Period, page: int, page_size: int) -> ProductAnalyticsPage
ProductAnalyticsService.slow(session, *, as_of_utc: datetime, page: int, page_size: int) -> ProductAnalyticsPage
ProductAnalyticsService.low_stock(session, *, page: int, page_size: int) -> LowStockPage
DashboardService.read(session, *, period: Period) -> DashboardRead
```

`DashboardService` **gọi service analytics/read**, không sao chép SQL tính doanh thu. AI Executor cũng dùng các read service đã có, không có định nghĩa KPI riêng trong prompt/LLM.

## Quy tắc nghiệp vụ P0

- **Revenue/AOV:** chỉ Orders ở trạng thái `COMPLETED` tính vào doanh thu và mẫu số AOV. `CANCELLED` loại hoàn toàn khỏi revenue & completed count; cancelled count quy về **ngày bán ban đầu `sold_at`**, không theo `cancelled_at`. Tiền int VND, `ROUND_HALF_UP` AOV. Empty period: revenue 0, AOV 0, no divide-by-zero.
- **Period:** ngày kinh doanh ở `Asia/Ho_Chi_Minh` (SRS); normalize `[start_utc,end_utc)` bằng conversion tại boundary, query UTC indexes `orders.sold_at`; không dùng `DATE(sold_at)` trong WHERE nếu làm mất index usage. Start/end query payload phải rõ ISO offset/timezone.
- **Top:** chỉ `order_items` của Orders hiện còn COMPLETED, sắp xếp sold_units DESC rồi Product ID ASC. Default 7 ngày; snapshot unit_price/line_total của OrderItem, không dùng giá Product hiện tại.
- **Slow:** Product ACTIVE, tồn >0, `first_stocked_at` đã hơn 7 ngày, sold_units 30 ngày <=2 (bao gồm 0). Không thay bằng `products.created_at` hoặc mặc định Product age 30 ngày.
- **Low stock:** Product ACTIVE, `quantity <= 5` trong P0; INV-05 per-product custom threshold và ANA-05 export CSV là P1, không được đưa vào critical path khi P0 chưa pass.
- **Privacy/RBAC:** Analytics/Dashboard **ADMIN-only**. Product/Inventory reads dành cho active ADMIN/STAFF với masking Stock Movement; không cho Staff gọi Analytics qua AI tool proxy.
- **Performance:** SRS P95 Sales/Product/Inventory read <=300ms đối với Product/Inventory, Dashboard <=1500ms; chỉ kết luận PASS khi có workload và fixture 10–20 concurrent thật. Bắt buộc tránh N+1 query theo page.

## HTTP response contract

- `GET /analytics/sales` → `SalesSummary {period_start,period_end_exclusive,revenue_vnd,completed_orders,cancelled_orders,aov_vnd}`.
- `GET /analytics/products/top`, `/analytics/products/slow` → `ProductAnalyticsPage {items,total,page,page_size}`.
- `GET /dashboard` → `DashboardRead {sales,low_stock_count,top_products}`.
- Lâm dùng cùng TS models OpenAPI. Dương AI tool chuyển response bằng DTO typed, không gửi SQL query/raw ORM cho LLM.

## Handoff/Tests

- Na Na cung cấp JSON fixture có 1 order COMPLETED, 1 CANCELLED, 1 checkout trong boundary 23:59 VN; AOV rounding fixture. Dương cung cấp product sold 0, 2, 3, first stocked 6/8 ngày, zero stock fixture.
- Tất cả query trên MySQL 8, check rights 401/403, stable ordering, empty page, page_size >100 bị 422; Dashboard số liệu khớp Analytics trực tiếp. Contract test điều chỉnh nếu response spec chưa tương đương code real.
