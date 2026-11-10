# RetailOps CF-2.4 — Bắt đầu triển khai Sprint 2 và Sprint 3
> **BASELINE KỸ THUẬT CF-2.4 — đã được Tech Lead chốt các tham số vận hành ngày 10/11/2026.** Tình trạng quyết định kỹ thuật khác với trạng thái phê duyệt interface: mọi hợp đồng provider–consumer mới vẫn phải được hai phía xác nhận qua PR, và không được coi `FROZEN_DESIGN` là API đã triển khai.

## 1. Phạm vi và nguồn chuẩn
**Phạm vi đã khóa:** một cửa hàng/kho; ADMIN/STAFF; 57 task LMS (26 S2, 31 S3) theo tab 1 Excel. 17 task tab 2 để sau Sprint 3, nhưng không được hoãn kiểm thử chất lượng P0 chỉ vì LMS có task tương tự ở tab 2.
- **Không bổ sung** VAT, chiết khấu, hoàn trả/hoàn tiền, thanh toán thật, nhiều kho/ca hoặc AI ghi dữ liệu.
- **SRS:** `docs/requirement/RetailOps_SRS_Approved.md`; **ERD:** `docs/database/RetailOps_ERD_V1.0.dbml` trên `develop`.
- **Nguồn chuẩn HTTP:** `contracts/openapi.yaml`; **nguồn chuẩn BE:** `contracts/python/*.pyi`; **FE reference:** `contracts/typescript/api-client-contract.ts`.
- **Schema AI máy đọc:** `contracts/ai_tool_schemas.json`; **dependency 57 task:** `contracts/task_dependencies.json`.
- **Mẫu payload:** `contracts/examples/`; **code đã merge** có thể khác đặc tả đề xuất, khi đó phải đối chiếu router/schema và sửa docs trước khi code consumer.
- **Mốc đối chiếu Product runtime:** `develop` `cd1a6d3451a88bd890e76c14944a98329152c325` (cập nhật snapshot nếu HEAD thay đổi).

## 2. Sáu tài liệu cần đọc (không phải đọc hết từ đầu)
| Tài liệu | Ai cần đọc |
|---|---|
| `docs/START_HERE.md` | Cả nhóm — Git, mã task, dependency, quality gates và quyết định còn mở |
| `docs/sprint2/TASK_IMPLEMENTATION_GUIDE.md` | Những ai triển khai Sprint 2 — tìm theo `T04...` |
| `docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md` | Những ai triển khai Sprint 3 — tìm theo `T04...` |
| `docs/contracts/BACKEND_INTERFACES.md` | Backend provider + consumer, transaction, locks, Python ports |
| `docs/contracts/API_INTEGRATION.md` | Backend/Frontend, HTTP contract, read query, mock→real |
| `docs/contracts/ASYNC_AI_CONTRACTS.md` | Worker, Reset, AI Executor và kiểm thử bảo mật |

## 3. Từ một task LMS đến PR có thể merge
1. Chọn đúng **mã LMS** trong bảng dưới; kiểm tra owner và phạm vi theo Excel, không dùng mã Sprint nội bộ làm định danh.
2. Đọc task card rồi đọc `.pyi`/OpenAPI và fixture có liên quan. Nếu contract còn PENDING, provider + consumer xác nhận trước khi phụ thuộc vào một chữ ký mới.
3. Khi **STARTABLE**, phát triển song song bằng fake/mock đúng contract; không tạo API tạm khác nhau giữa các agent.
4. Khi **INTEGRATABLE**, rebase/pull `develop`, chạy Alembic clean upgrade, real-API integration và MySQL tests (đối với write). Đổi FE sang adapter real, tuyệt đối không silent fallback mock.
5. Khi **ACCEPTED**, gửi test evidence, provider/consumer ACK, QA ACK cho đường P0. `CI PASS` hoặc `PR merged` **không tự động nghĩa là DONE**.
6. Commit: `feat(inventory): thêm StockMovement và migration [T04A653]`; `test(qa): kiểm thử E2E Sprint 2 [T04A8F3]`; `docs(contracts): chuẩn hóa API tìm kiếm [T04A6A3]`. Chỉ dùng một mã LMS thật ứng với công việc.

**PR mô tả tối thiểu:** Mã LMS · phạm vi · mã commit SHA của contract · provider/consumer · migrations · test commands và kết quả · real/mock status · ảnh hưởng bảo mật/concurrency · quyết định đang chờ.

## 4. Ma trận dependency 57 task — bản đề xuất chờ duyệt
**Quy tắc đọc:** STARTABLE chỉ cần contract ACK để dùng fake/mock; cột runtime là điều kiện **tích hợp thật**, không ngăn người khác bắt đầu. ACCEPTED còn yêu cầu kiểm thử nghiệp vụ cụ thể trong task card, không chỉ đủ tên dependency.

| Mã LMS | Sprint | Task | Owner | Contract để STARTABLE | Runtime để INTEGRATABLE | Gate cần lưu ý |
|---|---|---|---|---|---|---|
| `T04A61F` | 2 | Phân quyền và duyệt Staff | Hiếu | HTTP-AUTH, BE-OUTBOX | Nền tảng S1 / độc lập | S2 owns OutboxWriter + event schema; absolutely no S3 Worker dependency. S1 register needs STAFF_REGISTERED backfill hook. |
| `T04A639` | 2 | Khung Idempotency dùng chung | Hiếu | BE-IDEM | Nền tảng S1 / độc lập | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A653` | 2 | Inventory Service | Dương | BE-INVENTORY | Nền tảng S1 / độc lập | StockMovement ORM + Alembic migration not found on develop; Dương to implement in this task, rather than assume S1 finished. |
| `T04A66F` | 2 | Bộ khung kiểm thử MySQL | Dương | TEST-DB | Nền tảng S1 / độc lập | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A689` | 2 | CI cho Pull Request | Lan Anh | GATE-CI | Nền tảng S1 / độc lập | CI lint/unit start from existing workflows without T04A66F; MySQL job added after harness. |
| `T04A6A3` | 2 | API tra cứu sản phẩm | Na Na | HTTP-PRODUCT | Nền tảng S1 / độc lập | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A6BD` | 2 | API tra cứu tồn kho | Na Na | HTTP-INVENTORY | Nền tảng S1 / độc lập | Inventory Read starts from existing ORM without mutation service (T04A653). |
| `T04A6D7` | 2 | Tạo và sửa phiếu nhập nháp | Lan Anh | HTTP-RECEIPT, BE-RECEIPT | Nền tảng S1 / độc lập | Receipt ORM exists but migration absent on develop; S1 carryover migration owned by Dương, Hiếu reviews. |
| `T04A6F3` | 2 | Giao diện duyệt Staff | Lâm | HTTP-AUTH, FE-ADAPTER | `T04A61F` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A70D` | 2 | Giao diện danh mục, nhà cung cấp | Tân | HTTP-MASTER, FE-ADAPTER | Nền tảng S1 / độc lập | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A73C` | 2 | Checkout và Order Model | Hiếu | HTTP-ORDER, BE-IDEM, BE-INVENTORY | `T04A639`, `T04A653` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A758` | 2 | Điều chỉnh tồn kho | Dương | HTTP-INVENTORY, BE-IDEM, BE-INVENTORY | `T04A639`, `T04A653` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A772` | 2 | Hủy nháp và tra cứu phiếu nhập | Lan Anh | HTTP-RECEIPT, BE-RECEIPT | `T04A6D7` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A78E` | 2 | Lịch sử biến động và cảnh báo tồn thấp | Na Na | HTTP-INVENTORY | `T04A6BD`, `T04A653` | Low-stock read starts from Inventory ORM; movement history real integration needs StockMovement migration (T04A653). |
| `T04A7A8` | 2 | Giỏ hàng POS | Lâm | HTTP-PRODUCT, HTTP-ORDER, FE-ADAPTER | `T04A6A3` | Cart starts from Product read and agreed Checkout DTO; no Checkout implementation is needed to start. |
| `T04A7C3` | 2 | Giao diện thao tác phiếu nhập | Tân | HTTP-RECEIPT, FE-ADAPTER | `T04A6D7`, `T04A772`, `T04A7DF` | UI mock from Receipt DTO; real confirm action only once T04A7DF endpoint lands. |
| `T04A7DF` | 2 | Xác nhận phiếu nhập | Dương | HTTP-RECEIPT, BE-INVENTORY, BE-IDEM | `T04A6D7`, `T04A639`, `T04A653` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A80C` | 2 | Hủy đơn và hoàn tồn | Hiếu | HTTP-ORDER, BE-INVENTORY, BE-IDEM | `T04A73C`, `T04A639`, `T04A653` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A826` | 2 | Redis Rate Limiting | Hiếu | HTTP-RATE | Nền tảng S1 / độc lập | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A840` | 2 | API lịch sử đơn hàng | Na Na | HTTP-ORDER | `T04A73C` | Order read from T04A73C schema; no hard wait on Cancel T04A80C. |
| `T04A869` | 2 | Giao diện Checkout | Lâm | HTTP-ORDER, FE-ADAPTER | `T04A73C`, `T04A7A8` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A883` | 2 | Giao diện hủy đơn | Lâm | HTTP-ORDER, FE-ADAPTER | `T04A80C`, `T04A840` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A89D` | 2 | Giao diện tồn kho thiết yếu | Tân | HTTP-INVENTORY, FE-ADAPTER | `T04A6BD`, `T04A758`, `T04A78E` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A8B7` | 2 | Giao diện lịch sử phiếu nhập | Tân | HTTP-RECEIPT, FE-ADAPTER | `T04A772`, `T04A7DF` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A8D1` | 2 | Kiểm tra Docker và Nginx | Hiếu | DEPLOY | Nền tảng S1 / độc lập | Proxy/cookie/trusted-header audit should start 10-11 Nov; final smoke 16 Nov. Keep official milestone. |
| `T04A8F3` | 2 | Kiểm thử end-to-end Sprint 2 | Lan Anh | GATE-E, E | `T04A61F`, `T04A6D7`, `T04A73C`, `T04A758`, `T04A772`, `T04A7DF`, `T04A80C`, `T04A6F3`, `T04A7C3`, `T04A869`, `T04A883`, `T04A89D`, `T04A8B7`, `T04A8D1` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A90F` | 3 | Transactional Outbox và Email Worker | Hiếu | BE-OUTBOX | `T04A61F` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A92B` | 3 | Analytics doanh thu và đơn hàng | Na Na | HTTP-ANALYTICS | `T04A73C`, `T04A80C` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A947` | 3 | Analytics sản phẩm | Dương | HTTP-ANALYTICS | `T04A73C`, `T04A653`, `T04A80C` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A961` | 3 | Hoàn thiện lịch sử và hủy đơn UI | Lâm | HTTP-ORDER, FE-ADAPTER | `T04A840`, `T04A80C`, `T04A883` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A97C` | 3 | Hoàn thiện giao diện tồn kho | Tân | HTTP-INVENTORY, FE-ADAPTER | `T04A78E`, `T04A89D` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A996` | 3 | Tài liệu và UAT | Lan Anh | GATE-E, E, DEPLOY | `T04A8F3` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A9B0` | 3 | Kiểm thử giao diện quản lý | Tân | FE-ADAPTER, GATE-E, E | `T04A70D`, `T04A7C3`, `T04A89D`, `T04A97C` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A9CA` | 3 | Kiểm thử Auth, Checkout và Cancel | Dương | TEST-DB | `T04A61F`, `T04A73C`, `T04A80C` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04A9E6` | 3 | AI Tool Executor | Hiếu | BE-AI | Nền tảng S1 / độc lập | ABI freeze/hand-off 18-19 Nov before actual coding slot 20-21 Nov; consumer can fake executor. |
| `T04AA00` | 3 | Retry và phục hồi Email Worker | Hiếu | BE-OUTBOX | `T04A90F` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AA1C` | 3 | Đặt lại mật khẩu và tích hợp email | Dương | HTTP-RESET, BE-OUTBOX | `T04A61F`, `T04A90F` | Reset service can code with OutboxWriter and fake worker; email E2E requires publisher/worker T04A90F. |
| `T04AA36` | 3 | Dashboard API | Na Na | HTTP-ANALYTICS | `T04A92B`, `T04A947`, `T04A78E` | Can implement revenue + low-stock partial façade early, but DashboardRead.top_products required; full API acceptance waits Product Analytics T04A947. |
| `T04AA50` | 3 | Automated Integration Tests | Dương | TEST-DB, GATE-CI | `T04A66F`, `T04A90F`, `T04A9E6` | Test skeleton and DB harness can start before Worker/AI implementation; real tests wait provider merges. |
| `T04AA6A` | 3 | Responsive và UI States | Tân | FE-ADAPTER | `T04A961`, `T04A97C` | Responsive/error states can start from FE Design Freeze; full smoke waits UI merged. |
| `T04AA86` | 3 | AI chỉ đọc và Tool Calling | Dương | BE-AI, HTTP-AI | `T04A9E6`, `T04A92B`, `T04A947`, `T04A78E` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AAA2` | 3 | Đo hiệu năng và xác minh bảo mật | Hiếu | PERF, GATE-E, E | `T04A8F3`, `T04AA36` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AABC` | 3 | Kiểm thử Purchasing và Email | Na Na | TEST-DB, BE-OUTBOX | `T04A7DF`, `T04A90F`, `T04AA00`, `T04AA1C` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AAD7` | 3 | Kiểm thử Product, Order và Analytics | Na Na | TEST-DB, HTTP-ANALYTICS | `T04A6A3`, `T04A73C`, `T04A92B`, `T04A947` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AAF1` | 3 | Kiểm thử frontend nghiệp vụ | Lâm | GATE-E, E, FE-ADAPTER | `T04A869`, `T04A883`, `T04A961` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AB0B` | 3 | AI gợi ý nhập hàng | Dương | BE-AI, HTTP-AI | `T04AA86`, `T04A947` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AB25` | 3 | Giao diện Dashboard và AI | Lâm | HTTP-ANALYTICS, HTTP-AI, FE-ADAPTER | `T04AA36`, `T04AA86`, `T04AB0B` | Dashboard shell can start with HTTP contract; AI/recommendation panels attach later. Do not block all UI on T04AB0B. |
| `T04AB3F` | 3 | Rà soát bảo mật và concurrency | Hiếu | SECURITY, TEST-DB | `T04A9CA`, `T04AA50`, `T04A653` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AB59` | 3 | Kiểm thử Inventory, Worker và AI | Dương | TEST-DB, BE-OUTBOX, BE-AI | `T04A653`, `T04A90F`, `T04A9E6`, `T04AA86` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AB73` | 3 | Tích hợp và demo Worker/Redis/AI | Dương | GATE-E, E | `T04AA00`, `T04AA86`, `T04AB0B` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AB8D` | 3 | Triển khai bản demo | Hiếu | DEPLOY | `T04A8D1` | Candidate deployment can start without all services; full release candidate must contain every in-scope P0 and pass QA. |
| `T04ABA7` | 3 | Release và smoke test | Hiếu | DEPLOY, GATE-E, E | `T04AB8D`, `T04ABC3` | 24 Nov: cannot deploy main until QA signoff on SAME RC SHA; afterwards run post-main smoke. |
| `T04ABC3` | 3 | Nghiệm thu và đóng băng release | Lan Anh | GATE-E, E | `T04A996`, `T04AAD7`, `T04AAF1`, `T04AB3F`, `T04AB59`, `T04AC15`, `T04AC2F` | Must collect FE E2E T04AC2F and reconciliation T04AC15 before signoff, even if scheduled same day. |
| `T04ABDD` | 3 | Báo cáo QA và tài liệu demo | Lan Anh | GATE-E, E, DEPLOY | `T04ABC3`, `T04ABA7` | QA report final SHA after release; initial report can be drafted earlier. |
| `T04ABF9` | 3 | Tổng hợp giao diện và bằng chứng QA | Tân | FE-ADAPTER, GATE-E, E | `T04A9B0`, `T04AA6A` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AC15` | 3 | Đối soát dữ liệu và báo cáo | Na Na | HTTP-ANALYTICS, GATE-E, E | `T04A92B`, `T04A947`, `T04AA36`, `T04AAD7` | Consumer integrates real after provider PR; QA/CI evidence as applicable. |
| `T04AC2F` | 3 | Kiểm tra end-to-end frontend | Lâm | FE-ADAPTER, DEPLOY, GATE-E, E | `T04AB25`, `T04AB8D` | Candidate FE real E2E must happen before QA signoff T04ABC3; coordinate early on 24 Nov. |

**Máy kiểm tra:** `python scripts/check_cf23_contracts.py` xác minh đủ 57 task LMS, owner/tên giữa card và JSON, 124 quan hệ phụ thuộc và 0 chu trình cứng. Các quan hệ này là đề xuất cần nhóm duyệt trước khi trở thành kế hoạch bắt buộc.

## 5. Các dependency ngoài 57 task cần ownership rõ
| Gate | Owner | Tác vụ nhận bàn giao / chứng cứ |
|---|---|---|
| Receipt ORM tồn từ Sprint 1 nhưng chưa có Alembic migration trên baseline | **Dương** (carry-over S1), Hiếu review | `T04A6D7` Lan Anh và `T04A7DF` Dương, MySQL upgrade sạch |
| StockMovement ORM/migration và lock hierarchy | **Dương**, trong `T04A653` | Checkout `T04A73C`, Confirm `T04A7DF`, Adjustment `T04A758` và movement read `T04A78E` |
| Idempotency table + transaction API | **Hiếu**, `T04A639` | Checkout/Confirm/Cancel/Adjustment; MySQL 2-request race + replay + rollback |
| Minimal OutboxWriter + outbox migration | **Hiếu**, `T04A61F` | Approval/Registration emit durable events ngay trong S2. **Không chờ** Worker S3 `T04A90F`. |
| Order/OrderItem/movement migration | **Hiếu**, `T04A73C` | Order History `T04A840`, Analytics `T04A92B`, real Checkout E2E |
| Staff Registration S1 hook `STAFF_REGISTERED` | **Hiếu**, tích hợp trong `T04A61F` | Dương `T04A90F`, QA `T04AABC`; không nhân bản Notification khi retry |
| Broker Publisher/Email Handler | **Hiếu**, `T04A90F` | Password reset `T04AA1C`, Email tests `T04AABC`; idempotent event_id, broker outage recovery |
| UI Dashboard thành công đầy đủ | **Na Na** `T04AA36`, **Dương** `T04A947` | Có số doanh thu và top_products thật; không coi mock hoặc phần doanh thu đã là Dashboard ACCEPTED |

## 6. Bất biến nghiệp vụ và Security Gate (giữ nguyên SRS/ERD)
- **Auth:** 15 phút access JWT, phiên tối đa 8 giờ, refresh rotation, HttpOnly Secure cookie + CSRF/Origin, revoke session phía server, RBAC và field-level scope backend. REJECTED reapply cần email proof và giới hạn 1 lần/24h. Admin reset thủ công.
- **Inventory:** header (nếu có) → Product IDs tăng → Inventory IDs tăng trong cùng MySQL transaction; mọi mutation trừ no-op có StockMovement và tăng stock_version. No-op adjustment chỉ audit.
- **Receipt:** gộp duplicate Product cùng Unit Cost; khác giá thì reject. DRAFT có expected version, CONFIRMED/CANCELLED bất biến; Confirm tăng kho đúng 1 lần và yêu cầu idempotency key.
- **Checkout:** tạo `COMPLETED` và trừ kho nguyên tử. 409 `PRICE_CHANGED` không sinh Order/Movement; xác nhận giá mới rồi dùng key mới. Retry network chưa biết outcome dùng **cùng key + body**.
- **Cancel:** STAFF chỉ đơn do mình tạo ≤15 phút cùng ngày VN, ADMIN mọi đơn COMPLETED cùng ngày; hoàn tồn đúng một lần, lý do bắt buộc; không có refund.
- **Analytics:** doanh thu chỉ tính COMPLETED; CANCELLED thống kê theo sold_at, không theo cancelled_at; tiền int VND, AOV ROUND_HALF_UP; sản phẩm bán chậm theo first_stocked_at >7 ngày và bán ≤2 trong 30 ngày.
- **Outbox Lite:** một publisher, một worker tuần tự; confirm broker trước khi `published_at`, email at-least-once với dedupe/retry; không cam kết external SMTP exactly-once; token email không ở log hoặc outbox plaintext.
- **AI:** chỉ ADMIN, read-only tool allowlist, validate JSON Schema và principal ở từng tool call; không SQL/URL tùy ý; Tech Lead đã chốt deadline tổng mặc định 15 giây, tối đa 3 tool calls, tối đa 32 KiB dữ liệu tool cho mỗi request, 1 request đang thực thi/user và giới hạn tổng đồng thời của toàn hệ thống được cấu hình.
- **Proxy/Redis:** tin cậy forwarded headers từ chuỗi proxy được cấu hình; Auth công khai/AI fail closed khi Redis down, POS chỉ tiếp tục nếu MySQL-backed auth/session còn an toàn.

## 7. Sổ quyết định cần ký trên PR docs trước khi đánh dấu APPROVED
| Chủ đề | Đề xuất hiện tại | Người phải xác nhận | Trạng thái |
|---|---|---|---|
| Product Search/Sort | `search`, `sort`, `category_id`, `status`, `page`, `page_size` theo router đã merge | Na Na ↔ Lâm/Tân | Code baseline verified, consumer ACK pending |
| Receipt History date filter | `from_date/to_date` YYYY-MM-DD ngày VN, lọc `created_at` UTC half-open, sort created_at/id DESC | Lan Anh ↔ Tân, Hiếu | PROPOSED |
| Order History tìm kiếm/date | `search` exact Order ID hoặc SKU snapshot; lọc `sold_at` ngày VN, sort sold_at/id DESC | Na Na ↔ Lâm/Hiếu | PROPOSED |
| Inventory/movement filters và trường nhạy cảm | `in_stock`, `kind`, serializers ADMIN/STAFF riêng; Staff không nhận giá vốn/adjustment reason | Na Na ↔ Tân/Hiếu | PROPOSED |
| AI tool schemas/budgets | 4 tool JSON Schemas; `limit` 1..20, `days` 1..90; deadline tổng 15s, tối đa 3 tool calls, 32 KiB tool data/request; giới hạn đồng thời theo user và tổng hệ thống | Hiếu ↔ Dương | TECH-BASELINE CHỐT; consumer ACK pending |
| Worker/Email | 1 publisher + 1 worker tuần tự, batch ≤25 / 5s, 1+3 attempts, backoff 30/120/300s + bounded jitter, SMTP timeout 10s, TLS + env secrets, phân loại lỗi retry/permanent | Hiếu ↔ Dương/QA | TECH-BASELINE CHỐT; consumer ACK pending; retention còn mở |
| Bounded request sizes | số item tối đa receipt/checkout, giới hạn date window và paging | Hiếu + owner API/FE | PROPOSED |
| Release & QA SHA | RC 22–23/11, E2E/đối soát 24/11, QA/Tech signoff rồi mới merge main | Hiếu ↔ Lan Anh/Lâm/Na Na | PROPOSED |

**ACK bắt buộc ghi ở PR:** contract ID/path · provider · ít nhất một consumer · quyết định và SHA · test contract đi kèm. Không ghi APPROVED nếu chưa có bằng chứng.

### Baseline kỹ thuật đã được Tech Lead chốt; các điều kiện ACK còn cần thực hiện

**Đã chốt ở mức thiết kế kỹ thuật ngày 10/11/2026:** các giá trị AI và Email/Outbox dưới đây, cùng quy tắc SMTP at-least-once, không thêm microservices/distributed lease. **Chưa chốt dưới danh nghĩa Product Owner:** những con số không có trong SRS. **Vẫn cần consumer ACK trên PR**, đối chiếu implementation và test; các đề xuất cho Receipt/Order History, giới hạn 50 dòng và thời gian giữ dữ liệu chỉ chuyển sang APPROVED sau khi được owner xác nhận.

Những con số dưới đây không phải các điều khoản tự có trong SRS. Phần **AI, Outbox và Email** đã được Tech Lead quyết định làm baseline để code theo cấu hình tập trung, nhưng chưa có nghĩa provider/consumer đã phê duyệt PR hay chạy test. Các nội dung còn ghi **CẦN ACK** không được Agent tự diễn giải thành yêu cầu mới.

| Quyết định | Mặc định tôi đề xuất | Rủi ro / đánh đổi | Người xác nhận |
|---|---|---|---|
| Receipt History date filter | Ngày VN, khoảng `[from_date 00:00, to_date + 1 ngày 00:00)`; lọc `created_at`, tối đa 366 ngày | Cần convert UTC đúng, tránh bỏ sót giờ biên | Lan Anh + Tân |
| Order History search/date | `search` khớp chính xác Order ID hoặc SKU snapshot; date filter theo `sold_at` ngày VN, cửa sổ 366 ngày | Query `EXISTS` cho SKU để tránh nhân dòng; cần index / EXPLAIN khi dữ liệu lớn | Na Na + Lâm + Hiếu |
| Checkout/Receipt tối đa số dòng | Tối đa 50 Product khác nhau mỗi request, `page_size <= 100` | Giới hạn UX và request size để tránh DB locks quá lâu | Hiếu + Dương + Lan Anh + Lâm/Tân |
| AI request budget — **CHỐT KỸ THUẬT** | Deadline tổng **15 giây mặc định** (cấu hình environment), tối đa **3 tool calls/request**, dữ liệu từ tất cả tool ≤ **32 KiB/request**, 1 AI request đang thực thi/user, có giới hạn tổng đồng thời toàn ứng dụng | Deadline truyền xuyên suốt model→tool→DB; hủy/timeout phải giải phóng slot; trả lỗi an toàn khi không đủ dữ liệu | Hiếu + Dương |
| AI query range — **CHỐT KỸ THUẬT** | `days` 1–90; `limit` 1–20; tổng khoảng ngày ≤366 ngày khi nhận `start_date/end_date` | Bounded SQL và output, không truy vấn vô hạn từ model | Hiếu + Dương |
| Outbox Publisher — **CHỐT KỸ THUẬT** | Một publisher, batch ≤25 event, poll mặc định 5s; RabbitMQ publisher confirm **trước** `published_at` | `published_at` là **đã broker nhận**, không phải email `SENT`; crash sau broker confirm có thể publish trùng | Hiếu + Dương |
| Email retry và chống trùng — **CHỐT KỸ THUẬT** | 1 attempt đầu + tối đa 3 retries; backoff 30/120/300s + jitter có giới hạn; chỉ retry lỗi tạm (mất kết nối, timeout, SMTP 4xx tạm); lỗi vĩnh viễn (5xx permanent, địa chỉ sai, auth/config) → FAILED | MySQL event_id dedup/terminal state; SMTP timeout có thể đã gửi; không cam kết external exactly-once | Hiếu + Dương + Lan Anh |
| Email transport / secrets — **CHỐT KỸ THUẬT** | SMTP provider qua env, TLS bắt buộc, timeout mỗi lần thử **10s**; không hard-code credentials; reset token không lưu plaintext trong outbox/log; worker bỏ qua token hết hạn trước khi gửi | Phải test outage, invalid credentials, expired token; chưa chỉ định nhà cung cấp SMTP cụ thể | Hiếu + Dương |

### Ràng buộc chống triển khai lệch — AI & Email
- **AI deadline:** deadline là ngân sách tổng cho xác thực, model, executor và mỗi tool; không cấp lại 15 giây cho từng bước. Cấu hình tập trung, mặc định 15s. Khi hết hạn, không gọi thêm tool và phải trả `503`/lỗi AI an toàn; không dựng KPI thiếu căn cứ.
- **AI concurrency:** khóa theo actor và quota tổng phải có TTL/finally cleanup khi request timeout hoặc worker crash; không đặt khóa vô hạn. Redis lỗi thì AI fail closed theo SRS; mọi tool gọi vẫn phải kiểm ADMIN trên server.
- **Email delivery:** `published_at` chỉ được đánh dấu sau RabbitMQ publisher-confirm; `outcome=SENT`/`finished_at` chỉ được ghi sau SMTP accept. Chỉ tăng attempt và chuyển trạng thái theo transaction an toàn, không được trả lời public dựa vào trạng thái email. `event_id` là khóa dedup, vẫn có cửa sổ gửi trùng nếu SMTP accept xong nhưng worker crash.
- **Retry:** phân biệt transient/permanent; jitter chỉ lệch nhẹ quanh backoff, không thêm retry không giới hạn. Đối với reset/reapply, kiểm `secret_expires_at` trước SMTP send; hết hạn thì terminal `SKIPPED` theo enum outcome hiện có (audit lý do hết hạn không chứa token), không gửi link vô hiệu.
- **Triển khai:** vẫn một publisher/worker tuần tự. Không tự thêm lease/fencing, nhiều worker, microservices hoặc retry framework phức tạp.
- **Còn cần ACK:** lựa chọn provider SMTP, retention/cleanup theo ERD & pháp lý triển khai, cách hiện thực giới hạn concurrency toàn hệ thống và consumer signoff. Ghi rõ trên PR; chưa có bằng chứng thì không gắn nhãn “IMPLEMENTED/TESTED”.

**Chú ý:** `T04A61F` (Approval) và S1 Auth phải ghi Outbox event bền vững trong transaction; `T04A90F` chỉ tiêu thụ sau commit trong Sprint 3. Không biến Worker thành dependency cứng của Approval. Khi đã ACK giá trị mới, cập nhật OpenAPI/`.pyi`/tests cùng PR và bảo đảm không tạo contract drift.


## 8. Nhịp release — bảo vệ ngày demo 27/11
- **22–23/11:** triển khai release candidate (RC) trên môi trường demo và pin commit SHA, kiểm secrets/Nginx/health/migrations.
- **24/11 trước nghiệm thu:** Lâm hoàn tất FE real E2E `T04AC2F`, Na Na đối soát `T04AC15`, Dương kiểm Worker/AI, Hiếu kiểm Security/Concurrency.
- **Sau E2E:** Lan Anh QA signoff `T04ABC3` trên đúng RC SHA → Hiếu Tech signoff → merge `main` → Hiếu smoke `T04ABA7` và ghi bằng chứng SHA deploy.
- **25–26/11:** buffer có kiểm soát; hotfix phải chạy lại tests ảnh hưởng và ghi SHA mới. **27/11:** demo.

## 9. Các lệnh kiểm tra trước khi gửi PR
```bash
python scripts/check_cf23_contracts.py
python scripts/check_cf2_package.py
python scripts/check_contract_package.py
```
Các script này kiểm tra tài liệu, **không chứng minh MySQL race, HTTP runtime, RabbitMQ/Email hoặc FE E2E**. CI backend/frontend và integration phải chạy trên SHA mới, không tái sử dụng kết quả của commit cũ.

**Quyết định merge docs:** Chỉ khi P0 drift đã được sửa, docs tests PASS và các contract liên quan có provider–consumer ACK. Phạm vi P1 chưa ký phải được đánh dấu PROPOSED có owner, không giả nhận là đã khóa.
