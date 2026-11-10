# RETAILOPS CF-2.1 — MÃ LMS & CÁCH COMMIT
**Nguồn mã LMS:** sheet 1 “57 task trong file” của `RetailOps_S2_S3_LMS_Task_Filter_Corrected.xlsx`.
**Phạm vi:** chỉ 57 task chính. Sheet 2 có 17 task ngoài danh sách (bao gồm bonus, kiểm thử và hoàn thiện); **không đưa vào phạm vi Sprint 2/3 hiện tại** và chỉ xét sau khi hoàn tất Sprint 3 theo quyết định của nhóm.
**Quy tắc:** chỉ dùng **mã LMS thật** (`T04...`) khi tra cứu task, dependency, commit và PR; không dùng mã thứ tự nội bộ.

Ví dụ commit đã ghép từ LMS:
```text
feat(inventory): implement stock service [T04A653]
feat(sales): implement checkout [T04A73C]
test(qa): cover sprint 2 e2e [T04A8F3]
```
**Agent:** trước mỗi commit, đọc đúng card task trong `docs/sprint2/` hoặc `docs/sprint3/`, copy `Mã task LMS` từ card; chọn loại commit (`feat`, `fix`, `test`, `docs`, `chore`) và scope phù hợp. Không tự dùng commit mẫu `feat` cho task kiểm thử hay tài liệu.

## Bảng tra mã LMS đủ 57 task

| Sprint | Mã LMS | Task | Owner |
|---|---|---|---|---|
| S2 | `T04A61F` | Phân quyền và duyệt Staff | Nguyễn Minh Hiếu 8 |
| S2 | `T04A639` | Khung Idempotency dùng chung | Nguyễn Minh Hiếu 8 |
| S2 | `T04A653` | Inventory Service | Cao Nguyễn Anh Dương |
| S2 | `T04A66F` | Bộ khung kiểm thử MySQL | Cao Nguyễn Anh Dương |
| S2 | `T04A689` | CI cho Pull Request | Vũ Hoàng Lan Anh |
| S2 | `T04A6A3` | API tra cứu sản phẩm | Phạm Thị Na Na |
| S2 | `T04A6BD` | API tra cứu tồn kho | Phạm Thị Na Na |
| S2 | `T04A6D7` | Tạo và sửa phiếu nhập nháp | Vũ Hoàng Lan Anh |
| S2 | `T04A6F3` | Giao diện duyệt Staff | Vũ Trần Lâm |
| S2 | `T04A70D` | Giao diện danh mục, nhà cung cấp | Nguyễn Minh Tân |
| S2 | `T04A73C` | Checkout và Order Model | Nguyễn Minh Hiếu 8 |
| S2 | `T04A758` | Điều chỉnh tồn kho | Cao Nguyễn Anh Dương |
| S2 | `T04A772` | Hủy nháp và tra cứu phiếu nhập | Vũ Hoàng Lan Anh |
| S2 | `T04A78E` | Lịch sử biến động và cảnh báo tồn thấp | Phạm Thị Na Na |
| S2 | `T04A7A8` | Giỏ hàng POS | Vũ Trần Lâm |
| S2 | `T04A7C3` | Giao diện thao tác phiếu nhập | Nguyễn Minh Tân |
| S2 | `T04A7DF` | Xác nhận phiếu nhập | Cao Nguyễn Anh Dương |
| S2 | `T04A80C` | Hủy đơn và hoàn tồn | Nguyễn Minh Hiếu 8 |
| S2 | `T04A826` | Redis Rate Limiting | Nguyễn Minh Hiếu 8 |
| S2 | `T04A840` | API lịch sử đơn hàng | Phạm Thị Na Na |
| S2 | `T04A869` | Giao diện Checkout | Vũ Trần Lâm |
| S2 | `T04A883` | Giao diện hủy đơn | Vũ Trần Lâm |
| S2 | `T04A89D` | Giao diện tồn kho thiết yếu | Nguyễn Minh Tân |
| S2 | `T04A8B7` | Giao diện lịch sử phiếu nhập | Nguyễn Minh Tân |
| S2 | `T04A8D1` | Kiểm tra Docker và Nginx | Nguyễn Minh Hiếu 8 |
| S2 | `T04A8F3` | Kiểm thử end-to-end Sprint 2 | Vũ Hoàng Lan Anh |
| S3 | `T04A90F` | Transactional Outbox và Email Worker | Nguyễn Minh Hiếu 8 |
| S3 | `T04A92B` | Analytics doanh thu và đơn hàng | Phạm Thị Na Na |
| S3 | `T04A947` | Analytics sản phẩm | Cao Nguyễn Anh Dương |
| S3 | `T04A961` | Hoàn thiện lịch sử và hủy đơn UI | Vũ Trần Lâm |
| S3 | `T04A97C` | Hoàn thiện giao diện tồn kho | Nguyễn Minh Tân |
| S3 | `T04A996` | Tài liệu và UAT | Vũ Hoàng Lan Anh |
| S3 | `T04A9B0` | Kiểm thử giao diện quản lý | Nguyễn Minh Tân |
| S3 | `T04A9CA` | Kiểm thử Auth, Checkout và Cancel | Cao Nguyễn Anh Dương |
| S3 | `T04A9E6` | AI Tool Executor | Nguyễn Minh Hiếu 8 |
| S3 | `T04AA00` | Retry và phục hồi Email Worker | Nguyễn Minh Hiếu 8 |
| S3 | `T04AA1C` | Đặt lại mật khẩu và tích hợp email | Cao Nguyễn Anh Dương |
| S3 | `T04AA36` | Dashboard API | Phạm Thị Na Na |
| S3 | `T04AA50` | Automated Integration Tests | Cao Nguyễn Anh Dương |
| S3 | `T04AA6A` | Responsive và UI States | Nguyễn Minh Tân |
| S3 | `T04AA86` | AI chỉ đọc và Tool Calling | Cao Nguyễn Anh Dương |
| S3 | `T04AAA2` | Đo hiệu năng và xác minh bảo mật | Nguyễn Minh Hiếu 8 |
| S3 | `T04AABC` | Kiểm thử Purchasing và Email | Phạm Thị Na Na |
| S3 | `T04AAD7` | Kiểm thử Product, Order và Analytics | Phạm Thị Na Na |
| S3 | `T04AAF1` | Kiểm thử frontend nghiệp vụ | Vũ Trần Lâm |
| S3 | `T04AB0B` | AI gợi ý nhập hàng | Cao Nguyễn Anh Dương |
| S3 | `T04AB25` | Giao diện Dashboard và AI | Vũ Trần Lâm |
| S3 | `T04AB3F` | Rà soát bảo mật và concurrency | Nguyễn Minh Hiếu 8 |
| S3 | `T04AB59` | Kiểm thử Inventory, Worker và AI | Cao Nguyễn Anh Dương |
| S3 | `T04AB73` | Tích hợp và demo Worker/Redis/AI | Cao Nguyễn Anh Dương |
| S3 | `T04AB8D` | Triển khai bản demo | Nguyễn Minh Hiếu 8 |
| S3 | `T04ABA7` | Release và smoke test | Nguyễn Minh Hiếu 8 |
| S3 | `T04ABC3` | Nghiệm thu và đóng băng release | Vũ Hoàng Lan Anh |
| S3 | `T04ABDD` | Báo cáo QA và tài liệu demo | Vũ Hoàng Lan Anh |
| S3 | `T04ABF9` | Tổng hợp giao diện và bằng chứng QA | Nguyễn Minh Tân |
| S3 | `T04AC15` | Đối soát dữ liệu và báo cáo | Phạm Thị Na Na |
| S3 | `T04AC2F` | Kiểm tra end-to-end frontend | Vũ Trần Lâm |

---

# RETAILOPS CF-2.1 — START HERE
> Bản tinh gọn: nội dung các tài liệu CF-2.0 được hợp nhất, không thay đổi nguồn chuẩn HTTP (`contracts/openapi.yaml`) và Python ABI (`contracts/python/*.pyi`). Các chương bên dưới là phần tham khảo có thể chứa ví dụ chữ ký cũ; khi khác canonical contract, ưu tiên ABI/OpenAPI và mở PR sửa hướng dẫn.


---

## BẮT ĐẦU & NGUYÊN TẮC

# CF-2.0 UPDATE (ưu tiên đọc)

- **57 task giữ nguyên owner/Excel**; chọn mã tham chiếu trong [`contracts/TASK_TO_CONTRACT_INDEX.md`](contracts/API_INTEGRATION.md).
- **HTTP source:** `../contracts/openapi.yaml`; **Backend ABI:** `../contracts/python/retailops_core_ports.pyi`, `retailops_extended_ports.pyi`; **FE types:** `../contracts/typescript/api-client-contract.ts`.
- **Các contract bổ sung:** `contracts/S2_REMAINING_CONTRACTS.md`, `S3_OUTBOX_EMAIL_RESET.md`, `S3_ANALYTICS_DASHBOARD.md`, `S3_AI_EXECUTOR.md`.
- **Agent bắt buộc phân biệt** proposed design và code runtime. Đọc `workflow/DECISION_REGISTER.md`; khi interface pending ACK, đặt PR tài liệu hoặc trao đổi provider/consumer, không tự quyết định.
- **Process:** `workflow/CONTRACT_FREEZE_AND_GIT.md`, `contracts/FRONTEND_MOCK_REAL_HANDOFF.md`.

---

# TỪ SPRINT 2: BẮT ĐẦU TỪ ĐÂY

**Core contract CF-1.0 đã khóa ở mức thiết kế:** [Idempotency, Inventory, Receipt, Checkout](contracts/BACKEND_INTERFACES.md). [Examples provider/consumer](contracts/BACKEND_INTERFACES.md). OpenAPI: `../contracts/openapi.yaml`. Không hiểu `FROZEN DESIGN` thành “code đã merge”. Bốn contract này là cơ sở để làm song song; thay đổi phải có PR contract review cả provider/consumer.

# RetailOps — START HERE: Sprint 2 & Sprint 3

**Mục đích:** Thành viên nhận task + coding agent đọc một bộ docs là biết **làm gì, cái gì cần lấy từ module khác, gọi method/endpoint nào, request/response ra sao, cách mock, cách tích hợp thật và tiêu chí merge**. Không phải bộ biểu mẫu quản lý. **Không sửa phân công 57 task đã chốt.**

**Tình trạng phát hành:** `TEAM-DOCS-CF-1.0-REVIEW-CANDIDATE` (10/11/2026); cần Hiếu + owner + consumer phê duyệt các interface/endpoint mới **trước khi đưa Agent triển khai từ tài liệu này**. Repo `develop` được kiểm tra tại commit `f227164afa02c2ca164ef019db6410f87f43e0d` ngày 10/11; trước coding phải đọc lại HEAD vì code có thể thay đổi.

## Đọc trong 7 phút

1. **Nhận task:** mở [`sprint2/TASK_IMPLEMENTATION_GUIDE.md`](sprint2/TASK_IMPLEMENTATION_GUIDE.md) hoặc [`sprint3/TASK_IMPLEMENTATION_GUIDE.md`](sprint3/TASK_IMPLEMENTATION_GUIDE.md), tìm đúng **tên task + owner** giống Excel; mã `S2-xx/S3-xx` chỉ tham chiếu tài liệu, không phải mã LMS.
2. **Backend:** nếu task gọi module khác, xem [`shared/BE_PORTS.md`](contracts/BACKEND_INTERFACES.md) để lấy **chữ ký/kiểu dữ liệu, transaction rules, exception và ví dụ consumer**. Nếu task expose HTTP, xem [`../contracts/openapi.yaml`](../contracts/openapi.yaml) và [`shared/API_HANDOFF.md`](contracts/API_INTEGRATION.md).
3. **Frontend:** dùng [`../contracts/openapi.yaml`](../contracts/openapi.yaml) để tạo mock/TypeScript DTO; đọc ví dụ request/response và 409 trong [`shared/API_HANDOFF.md`](contracts/API_INTEGRATION.md). Không có API thật vẫn xây UI, nhưng **mock không chứng minh E2E**.
4. **Bắt đầu/merge/bàn giao:** làm theo [`shared/INTEGRATION_PLAYBOOK.md`](START_HERE.md). Một task có `STARTABLE`, `INTEGRATABLE`, `ACCEPTED` khác nhau.
5. **Vướng interface chưa khóa:** xem [`shared/APPROVAL_CHECKLIST.md`](START_HERE.md), ping đúng owner + consumer; không tự phát minh tên hàm/field rồi yêu cầu người khác sửa theo.

## Quy tắc duy nhất cần nhớ

> **Provider chỉ cần bàn giao contract trước, không cần merge toàn bộ feature.** Consumer bắt đầu với mock/fake trên cùng contract. Provider merge code/migration nhỏ theo CI. Consumer chuyển từng endpoint/service call sang real và kiểm thử trong ngày. `ACCEPTED` chỉ khi test thật đạt.

## Ví dụ để hiểu đúng mục tiêu

**Task Dương — Receipt Confirm** cần `ReceiptDraftService` từ Lan Anh, `IdempotencyExecutor` từ Hiếu và Inventory mutation của chính Dương. Ngay sau khi **chữ ký các port và DTO Receipt** được khóa, Dương viết `ConfirmService` với fake Idempotency và fixture Receipt DRAFT; không cần đợi Lan Anh hoàn chỉnh hết list/cancel/history. Khi các PR nền merge, Dương chạy MySQL concurrency trên real implementation.

**Task Tân — Giao diện thao tác phiếu nhập** dùng cùng `ReceiptRead`, `ReceiptVersionRequest` trong YAML; gọi `POST/PATCH /purchase-receipts`, `POST /purchase-receipts/{id}/confirm`, `.../cancel`. Khi chưa có API thật, dùng mock đúng các trạng thái DRAFT/CONFIRMED/CANCELLED và 409. Khi API merge, chỉ đổi adapter, không viết lại component.

**Task Hiếu — Checkout** gọi `InventoryService.lock_for_mutation(...)` rồi `InventoryService.decrease_for_checkout(..., locks=...)` qua cùng SQLAlchemy Session; không viết logic trừ kho riêng. Receipt Confirm và Checkout dùng chung lock hierarchy, đảm bảo Stock Movement không tạo lặp.

## Bản đồ người cung cấp → người sử dụng

| Người cung cấp | Handoff phải có trước | Người sử dụng |
|---|---|---|
| Hiếu | Idempotency method, Approval HTTP DTO, Checkout/Cancel HTTP, `OutboxWriter.append`, AI Executor ABI | Dương, Lan Anh, Lâm, Na Na |
| Dương | Inventory mutation methods, Receipt Confirm HTTP, Product Analytics, AI orchestration | Hiếu, Lan Anh, Na Na, Tân, Lâm |
| Lan Anh | Receipt DRAFT DTO/methods, draft_version rules, QA matrix | Dương, Tân |
| Na Na | Product/Inventory/Movement/Order read APIs, Sales Analytics, Dashboard DTO | Lâm, Tân, Dương |
| Lâm | Shared axios/Auth client + no-silent-mock adapter, FE common components | Tân |
| Tân | Receipt/Inventory UI smoke evidence, frontend edge case catalog | Lâm, Lan Anh |

## Phạm vi và nguồn chân lý

Ưu tiên khi có mâu thuẫn: SRS V1.3 đã được PO/Tech Lead xác nhận → ERD/Technical Decisions đã khóa → hợp đồng được owner/consumer phê duyệt → code thực tế/CI → hướng dẫn và workbook. **Không tự làm trái code hiện tại để ép nó giống candidate.** Nếu SRS/ERD bất đồng thì yêu cầu Hiếu chốt thay đổi chính thức.

Repo nguồn: [SRS](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/blob/develop/docs/requirement/RetailOps_SRS_Approved.md), [ERD](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/blob/develop/docs/database/RetailOps_ERD_V1.0.dbml), [Sprint 1](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/tree/develop/docs/sprint1), [Frontend Design Freeze](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/blob/develop/docs/design/RetailOps_V1.0_Frontend_Handoff_Design_Freeze.md), [`CONTRIBUTING.md`](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/blob/develop/CONTRIBUTING.md).

**Not included:** VAT, discounts, returns/refunds, payments thật, multi-store/warehouse, shift management, AI data writes. Chỉ P0 là release requirement; P1 như custom low-stock threshold chỉ sau P0 gate.

## Những điều **chưa** thể khẳng định từ `develop` đã kiểm tra

- Chỉ thấy Receipt ORM tại `backend/app/modules/purchasing/models.py`, **chưa thấy migration Receipt** trong danh sách Alembic tính đến commit kiểm tra. Không coi Receipt model đã usable trên MySQL mà không chạy clean migration.
- Chưa thấy `idempotency_records`, `outbox_events`, `orders` migration trong cây migrations tại commit kiểm tra; cần tạo/review theo ERD khi đến task.
- Core write paths trong `contracts/openapi.yaml` đã `FROZEN_DESIGN` ở CF-1.0; các paths khác vẫn `PROPOSED`. Không có path mới nào được coi là runtime implemented chỉ vì có trong YAML. Riêng `GET /products` và ProductRead có trong source; filter q/status/category mới là phần mở rộng đề xuất.
- **Outbox Lite** trong ERD chỉ cho một publisher + một sequential worker, không tự nâng thành multi-publisher với leases/fencing.
- Login/Registration ở S1 có thể đã merge nhưng việc reset/reapply và outbox durable cần verify theo task S2/S3, không auto PASS.


---

## GIT, FREEZE, MERGE & HANDOFF

# RetailOps — Quy trình đóng băng contract và Git 2 Sprint cuối

## Một PR docs trước code cross-module

1. Hiếu tạo PR docs **riêng** vào `develop` chứa CF-2.0, sửa liên kết theo repo và đối chiếu code mới nhất.
2. Provider và consumer review interface mình dùng: Dương ↔ Hiếu/ Lan Anh (Inventory); Lan Anh ↔ Dương/Tân (Receipt); Hiếu ↔ Lâm/Na Na (Checkout); Hiếu ↔ Dương (Outbox/AI); Na Na/Dương ↔ Lâm (Analytics).
3. Chốt các dòng `DECISION_REGISTER.md` chưa được SRS/ERD quy định (limit, timeouts, API path thêm mới). **Chỉ đổi sang APPROVED sau khi có PR/SHA và reviewer ACK**; không tuyên bố đã có khi chưa merge.
4. Merge docs PR sau CI docs static, OpenAPI parse, Pydantic schema sample check. Gắn commit SHA của contract vào task PR.

## Từ một task đến E2E

`CONTRACT ACK` → `STARTABLE` (fake/mock allowed) → `PROVIDER PR MERGED` (CI+test) → `REAL API PASS` (consumer confirms) → `MYSQL RACE/E2E PASS` (QA). `MERGED != DONE`.

### PR description copy

```md
Task: <LMS-ID> — <EXCEL TITLE>; Owner: <OWNER>
Contract: <ID> @ <SHA>; Provider → Consumer: <NAMES>
File/path/symbols exposed: <exact function signatures/operationIds>
DB migration: <revision or none>; transaction owner/lock order: <...>
Error handling: <401/403/409/422/429/503 relevant cases>
Tests executed (commands and result): <...>
Mock/Real: <MOCK_ONLY | REAL_API_PASS | MYSQL_RACE_PASS>
Consumer ACK: <PR reviewer or comment>
Blockers / scope exceptions: <...>
```

- Early merge allowed only for backward-compatible foundation PR with migration clean, CI green, review passed, no exposed broken endpoint. Never bypass branch protection.
- One migration head; don't reset real/test persistent data to bypass failing credentials. Clean dedicated test MySQL, run migrations and transaction tests. Code has `get_db_session` that does **not** automatically commit; use case service owns a single commit. Auth dependency may already start implicit transaction: avoid nested `session.begin()` errors.
- Review critical gates: authorization & field masking, idempotency, race/deadlock, rollback, secrets/CSRF, resource bound, performance, error envelope. UI screenshot alone not test evidence.

## 10-minute daily checkpoint

Owner reports task, contract SHA, provider merge SHA, consumer ACK, real/mock status, one blocker and who can unblock it. Lan Anh records in existing Excel `Theo dõi theo ngày`; don't add hidden second project tracker.

## Release

22–23/11 RC deploy → 24/11 real E2E on **same SHA** → Lan Anh QA signoff → Hiếu tech signoff → PR `develop`→`main` → post-main smoke → 25–26/11 hotfix only → 27/11 demo. If fail Critical/High or core P0 scenario missing, do not call release approved.


---

## PLAYBOOK TÍCH HỢP

# RetailOps — Quy trình làm song song và bàn giao không chờ (S2–S3)

**Đối tượng:** cả sáu thành viên + AI coding agents. Áp dụng cùng `CONTRIBUTING.md` hiện hành; chỉ làm việc qua `feature/*` → PR → `develop`, không direct push. Tài liệu này không chuyển ownership.

## 1. Một tính năng có 3 thời điểm, không phải một cột `Depends on`

| Điều kiện | Owner chứng minh gì? | Consumer được làm gì? |
|---|---|---|
| **STARTABLE / Contract Ready** | API schema/port & error scenarios được **owner + consumer duyệt**, sample fixtures | Code song song bằng fake/mock/types; không phụ thuộc provider merge |
| **INTEGRATABLE / Runtime Ready** | Provider PR vào `develop`, CI xanh, DB migration khởi tạo sạch, API thật lên môi trường integration | Chuyển endpoint sang real; chạy smoke + negative cases cùng ngày |
| **ACCEPTED / Verified** | MySQL race/rollback/replay + FE real E2E + owner/QA review | Đóng task/vertical slice, trích evidence cho demo/release |

Không coi “Agent đã viết xong” hoặc “PR xanh” là E2E PASS. Không fake RPC/network/database thành bằng chứng concurrency.

## 2. Handoff 10 phút: provider → consumer

Mỗi API/port cần gửi trong PR description (template copy):

```md
### Contract handoff — <CONTRACT-ID>
- Provider/consumers: ...
- Source: docs/contracts/S2_CORE_CONTRACTS_LOCKED.md / contracts/python/retailops_core_ports.pyi / contracts/openapi.yaml @ <commit-SHA>
- Exported function/class/API: ... (exact spelling + argument/DTO types)
- Changed files and new migrations: ...
- Authentication/authorization & field masking: ...
- Success / expected error (200/201/202, 401/403/409/422, 429/503 as applicable): ...
- Transaction owner & locks: ...
- Mock / fake fixture: ...
- Tests run + outcomes + evidence: ...
- Integration status: MOCK_ONLY / REAL_API_PASS / DB_RACE_PASS
- Consumer acknowledgement and blocker: ...
```

Người viết API chịu trách nhiệm thông báo **chữ ký thật** sau merge. Người dùng API **không tự dịch DTO** hoặc đọc ORM để suy ra JSON. Handoff thiếu chữ ký hoặc status code thì chưa phải Contract Ready.

## 3. Giao việc song song S2 theo ngày — từ tab lịch Excel

| Mốc | Provider giao contract | Consumers bắt đầu ngay bằng mock/fake | Real integration/QA |
|---|---|---|---|
| **10–11/11** | Hiếu AUTH/IDEMP/OutboxWriter; Dương InventoryPort; Lan Anh ReceiptDraft DTO; Na Na Product/Inventory Read | Lâm Approval mock; Lâm POS quote; Tân Receipt editor/stock; Hiếu Checkout fake Inventory; Dương Confirm fake Idem | Khóa schema, owner review; merge nền nhỏ khi đủ gate |
| **12–13/11** | Hiếu Checkout/Order DTO; Dương Adjust; Lan Anh Receipt list/cancel; Na Na Movement | Lâm Checkout & Cancel UI; Tân receipt/history, stock; Na Na OrderRead | Demo 13/11 chỉ từ stable `develop`; không ép phần mới chưa pass vào demo |
| **14–15/11** | Hiếu Cancel; Dương Confirm; Na Na Order History; FE chuyển sang real từng endpoint | FE vẫn có thể hoàn thiện form/error states bằng mock trước khi API có | MySQL `draft->confirm->stock->checkout->cancel` + race/replay |
| **16/11** | Hiếu Nginx/Compose, Lan Anh E2E | Các owner sửa blocker của module mình | QA P0 real API, database invariants và evidence |

## 4. Giao việc song song S3 theo ngày

| Mốc | Provider bàn giao trước | Consumers không phải đợi implementation đầy đủ | Gate |
|---|---|---|---|
| **18–19/11** | Hiếu event envelope Worker + AI Executor ABI draft; Na Na Analytics DTO; Dương Product Analytics | Dương viết AI tools từ interface/fake; Lâm Dashboard mock; Lan Anh UAT | Email event persistent; Analytics read thật; demo 20/11 chỉ stable modules |
| **20–21/11** | Hiếu executor/worker retry; Dương reset/AI read-only; Na Na Dashboard | Lâm Dashboard/AI UI mock→real độc lập từng API; Dương AI reordering advisor từ tool tests | MySQL + broker outage + AI RBAC tests |
| **22–23/11** | Hiếu RC deploy test; Dương demo integration; Lâm frontend E2E | QA dùng đúng RC SHA; không thay code ngầm vào cùng build | security, concurrency, perf evidence, no Critical/High |
| **24/11** | Lan Anh QA signoff → Hiếu tech signoff → release `develop`→`main` → smoke | Mọi người tập trung kiểm lỗi P0 trên **cùng SHA** | release freeze, duy trì 25–26/11 làm buffer |

**Quan trọng:** lịch mốc trong workbook là mốc nghiệm thu, không có nghĩa mọi công việc chỉ bắt đầu đúng ngày đó. Đây là đề xuất workflow, **không sửa tab lịch**.

## 5. Quy tắc Early Merge, tránh tích hợp trễ mà không phá `develop`

1. **PR contract-only** (OpenAPI + ports + tests/samples) trước, cả producer và consumer review. Không đổi ERD/SRS trong PR contract để lách lỗi.
2. **PR nền**: ORM + Alembic migration/DI registration (khi cần) nhỏ và backward compatible, clean upgrade MySQL, một Alembic head, CODEOWNERS/reviewer.
3. **PR implementation**: domain service logic, unit + MySQL integration tests, API route wiring. Tách tiếp nếu thay đổi đủ lớn và có đường code chạy độc lập. Không bật endpoint chưa implement/unsafe bằng cách trả fake thành công.
4. **PR consumer**: frontend/service caller dùng interface đã khóa, bắt đầu bằng fake/mock; chuyển API thật theo endpoint. Không tự đổi field/URL khi provider chưa phản hồi.
5. **Regression**: testcase quan trọng của các module không được skip khi chạy CI. Thời gian review mục tiêu: checkpoint trong cùng ngày, không cam kết merge khi tests/review chưa đạt.

**Migration:** tối thiểu backlog phải kiểm tra Receipt schema/migration từ S1 trước khi Lan Anh triển khai DRAFT API; Outbox và Idempotency migrations theo đúng DBML chốt. Migration phát triển trên branch đồng thời phải rebase lên head đã merge trước khi PR merge. `docker compose down -v` không phải lệnh fix test credentials.

## 6. Bộ test nhận diện contract drift và business risk

| Luồng | Unit/fake | MySQL integration | FE real API |
|---|---|---|---|
| Staff Approval | state transitions/errors | two admins race; approval + outbox event rollback | 403 STAFF; 409 already handled |
| Receipt | draft merge/version; confirm validation | confirm twice/different keys; supplier inactive; lock & rollback | 409 stale version; terminal immutable |
| Checkout/Cancel | price/role/date policy | two checkouts oversell; cancel twice; stock movement atomic; replay | 409 PRICE_CHANGED + new consent; same-key timeout retry |
| Inventory Adjustment | count/version/no-op | count stale, no-op audit, movement unique | STAFF cannot adjust; refetch on stale |
| Analytics | rounding/period/threshold | transaction committed, CANCELLED excluded, stable queries | Admin-only, empty data visualized |
| Email/Worker | event format/retry policy | broker fail / publisher restart / worker replay | no fake email SENT claims |
| AI | allowlist/schema/resource cap | read service only; no unauthorized SQL/write | quota/timeout/error/evidence states |

Phải có positive **và** negative cases. Nếu MySQL unavailable, các DB tests phải fail closed, không tự skip im lặng để tạo PR xanh.

## 7. Daily integration checkpoint: không cần thêm sheet mới

Giữ tab `Theo dõi theo ngày` hiện tại, bổ sung vào **ghi chú/bằng chứng** của task (không tự thêm task/đổi owner):

- Contract status: `DRAFT / FROZEN` kèm PR/SHA.
- Implementation status: `MOCK_ONLY / PROVIDER_MERGED / REAL_API_PASS / MYSQL_RACE_PASS / E2E_PASS`.
- Blocker: cung cấp tên người cần phản hồi, **chữ ký/field/endpoint nào đang thiếu**, thời điểm phát hiện, deadline để unlock.
- Link đến command test, CI run, API trace an toàn và commit SHA.

Cuối ngày, owner báo 1 blocker có thể ảnh hưởng người khác; Tech Lead ưu tiên review các blocker chặn ≥2 consumers hơn những refactor không cấp thiết.

## 8. Quy trình Release tránh circular dependency

Không dùng `T04ABA7 release` làm prerequisite để `T04ABC3 QA signoff` rồi lại đợi QA làm prerequisite release. Luồng đúng:

`22–23/11 RC deployment (Hiếu T04AB8D)` → `24/11 FE/BE E2E on RC SHA (Lâm T04AC2F, các owner)` → `Lan Anh T04ABC3 QA Signoff` → `Hiếu T04ABA7 Tech Signoff / PR to main` → `post-release smoke on main SHA` → `25–26/11 controlled hotfix`.

Nếu bất kỳ P0 thiếu evidence hoặc còn Critical/High, **chưa đóng Release Gate**. Không tự coi mục tiêu hiệu năng là đã đo thực tế.

## 9. Prompt dùng chung cho mọi coding agent

> Bạn là coding agent trong RetailOps. Task được giao có **mã LMS thật** là `<TASK-ID>`; tên và owner lấy nguyên từ Excel. Trước khi sửa hãy đọc `docs/requirement/RetailOps_SRS_Approved.md`, `docs/database/RetailOps_ERD_V1.0.dbml`, `docs/shared/BE_PORTS.md`, `docs/shared/API_HANDOFF.md`, `contracts/openapi.yaml`, `docs/sprint2|sprint3/TASK_IMPLEMENTATION_GUIDE.md` và code `develop` hiện tại. Chỉ code trong ownership; không tự đổi API/service signature đã frozen. Nếu provider chưa merge, tạo consumer adapter/fake đúng contract và test, không duplicate business logic; không dùng mock làm integration pass. Backend mutation cùng SQLAlchemy Session, một commit, MySQL race tests. Chạy đúng lint/tests; báo thay đổi, blockers, outputs và bằng chứng. Không commit `.env`/token; không tự merge. Nếu khác biệt giữa SRS/ERD/contract/code, ghi rõ và yêu cầu owner/Tech Lead duyệt thay đổi trước.


---

## APPROVAL CHECKLIST

# RetailOps — Interface Freeze: Ai phải xác nhận gì trước khi Agent code?

**Mục tiêu:** đóng băng các chữ ký liên task (không phải toàn bộ implementation). **Bốn contract core S2 đã được đóng băng ở mức design trong package CF-1.0**; các dòng khác vẫn cần owner/consumer ký PR. Sau khi ký PR chính thức, đổi `FROZEN DESIGN` → `FROZEN @ <PR/commit>` hoặc `PROPOSED` → `FROZEN @ <PR/commit>`; chưa ký thì chỉ được nghiên cứu/mock tạm, không yêu cầu consumer tin vào tên hàm/path như API chính thức.

| Deadline đề xuất | Contract | Owner phê duyệt | Consumers phải xác nhận | Nội dung phải thống nhất |
|---|---|---|---|---|
| 10/11 | `BE-IDEM` — **FROZEN DESIGN** | Hiếu | Dương | `IdempotencyExecutor.execute`, operation enum, one-tx TD-04C, 409 `REQUEST_IN_PROGRESS` (không dùng 425 trong CF-1.0) |
| 10/11 | `BE-INVENTORY` — **FROZEN DESIGN** | Dương + Hiếu review | Hiếu, Lan Anh | bốn phương thức mutation; `StockLine`, lock order TD-04B, transaction owner |
| 10/11 | `BE-OUTBOX` S2 Writer | Hiếu | Dương | OutboxWriter.append + event types; DBML Outbox Lite, no secret plaintext |
| 10/11 | `HTTP-AUTH` | Hiếu | Lâm | Staff Approval list/approve/reject DTO + 403/409, 200 |
| 10/11 | `HTTP-PRODUCT`, `HTTP-INVENTORY` reads | Na Na | Lâm, Tân | reuse existing `/products`, new filters, safe Inventory/Movement shape |
| 10/11 | `BE-RECEIPT`,`HTTP-RECEIPT` — **FROZEN DESIGN** | Lan Anh + Dương | Tân | Draft/Create/Update/Cancel/Confirm DTO, `draft_version`, 409, Product line normalization |
| 11/11 | `HTTP-ORDER` — **FROZEN DESIGN** | Hiếu | Lâm, Na Na | Checkout/Cancel + OrderRead, PRICE_CHANGED details, idem key lifecycle |
| 11–12/11 | `HTTP-RATE` | Hiếu | Lâm, Dương | SRS limits, trusted proxy, Redis outage policy |
| 18/11 | `BE-OUTBOX` S3 Publisher/Worker | Hiếu | Dương, QA | single publisher, confirms, bounded retry/replay |
| 18/11 | `HTTP-ANALYTICS` | Na Na + Dương | Lâm, AI tools | revenue/timezone/AOV; best/slow sales; low-stock definition |
| 18–19/11 | `BE-AI` | Hiếu | Dương | tool IDs, typed inputs, RBAC per call, result budget and error states |
| 19/11 | `HTTP-AI` / `HTTP-RESET` | Dương (+ Hiếu security review) | Lâm, QA | AI answer/evidence/error; reset lifecycle/no enumeration |
| 22/11 | `DEPLOY` + `GATE-E2E` | Hiếu + Lan Anh | all | release candidate SHA; staging URLs; QA sequence |

## Điều kiện để đánh dấu FROZEN

- [ ] Tên interface/path và Python import path hoặc OpenAPI `operationId` chính xác.
- [ ] DTO có đầy đủ field/type/nullability/range; role/permissions/field-whitelist rõ.
- [ ] Success code, error envelope/code/details được chốt bằng ví dụ có thể chạy.
- [ ] Side effects/transaction boundary và lock order có người chịu trách nhiệm.
- [ ] Provider và ít nhất consumer bị ảnh hưởng review + ghi trong PR.
- [ ] Có fixture/mocks/test để consumer code độc lập.

## Các quyết định cần ghi trong PR trước khi FROZEN (không âm thầm đoán)

1. `SRS AUTH-03` yêu cầu Staff Approval ghi durable Outbox Event trong cùng transaction, trong khi Email Worker S3. **Đã đề xuất hợp lý:** Hiếu làm `outbox_events` schema+Writer trong S2, publisher/worker trong S3. Nhớ kiểm tra Registration đã có `STAFF_REGISTERED` event và reapply/reset events nằm trong phạm vi yêu cầu.
2. `GET /products` **có thật** nhưng search/filter mới chưa có; không tạo route khác với frontend đang dùng.
3. Path mới `/purchase-receipts`/`/orders/checkout`/`/ai/query` và các HTTP status là **contract candidate**; owner/consumer xác nhận trước khi đưa vào implementation.
4. `TD-04E-LITE`: đơn publisher/worker, **không** phê duyệt multiple instance / DB lease/fencing trong scope này.
5. `TD-04C`: Idempotency claim+effect+response trong một transaction, không commit IN_PROGRESS riêng.
6. Release: QA UAT trên RC SHA → Lan Anh signoff → Hiếu signoff → merge `main` → smoke; không có vòng phụ thuộc release ↔ QA.
7. `Receipt` migration còn thiếu so với ORM tại snapshot đã kiểm tra; block PR Receipt API thật cho đến khi migration hợp lệ trên MySQL sạch.
8. Các ngưỡng/field/timeout/email provider trong `TD-04/TD-05` nếu chưa được chốt bằng tài liệu đã phê duyệt thì không được bịa (đặc biệt max receipt items, AI timeout, SMTP provider). Có thể dùng safe conservative caps khi Tech Lead phê duyệt qua PR.
9. `docs/sprint1/RETAILOPS_SPRINT1_CONTRACT.md` có baseline Auth/notification/POS business. Contract mới không được thay đổi behavior S1 ngầm.
10. Mọi mô tả task phải bám **tên task và chủ task trong Excel**, không suy đoán mã LMS để đưa vào commit.


---

## DECISION REGISTER

# CF-2.0 — Decision Register & phê duyệt thực tế

**Nguồn ưu tiên:** SRS V1.3 > ERD V1.0 > PO/Tech Lead approved decisions > CF-2.0 docs > code đang được triển khai. *DRAFT/PROPOSED* không biến thành *APPROVED* chỉ vì xuất hiện trong ZIP. Đây là danh sách ngắn để chốt trong PR docs hôm nay.

| ID | Quyết định | Status ở CF-2.0 | Reviewers | Chứng minh/điều kiện |
|---|---|---|---|---|
| D01 | One DB transaction claim+effect+response, Idem 24h, no claim lease | **SRS/ERD APPROVED** | Hiếu,Dương | TD-04C + MySQL race test |
| D02 | Lock header → Product IDs ASC → Inventory IDs ASC, no nested service commit | **ERD APPROVED** | Hiếu,Dương,Lan Anh | TD-04B + two-client tests |
| D03 | Receipt snapshots + one row/product, version, terminal immutability | **ERD APPROVED** | Dương,Lan Anh,Tân | DBML and migration |
| D04 | Outbox Lite one publisher + one sequential worker, at-least-once; not exactly-once email | **ERD APPROVED** | Hiếu,Dương | TD-04E Lite |
| D05 | Approval event is atomic in S2, S3 supplies publisher/worker | **IMPLEMENTATION SPLIT PROPOSED** | Hiếu,Dương,Lâm | AUTH-03 P0 + S3 ownership preserved |
| D06 | New HTTP paths for inventory, receipt, orders, analytics, AI, reset/reapply | **NEW DESIGN BASELINE, PR ACK REQUIRED** | Providers + FE consumers | `contracts/openapi.yaml`, React mock fixtures |
| D07 | Python core port signatures, Tool IDs, response DTO field names | **NEW DESIGN BASELINE, PR ACK REQUIRED** | Hiếu,Dương,Lan Anh,Na Na | stubs, owner/consumer signoff |
| D08 | Receipt max items, checkout max items, email SMTP provider, AI timeout/tool-turn caps, publisher batch/retry caps | **TBD — SECURITY/PERF PARAMETER REVIEW** | Hiếu + relevant consumer | central config + bounded validation, no fabricated SRS values |
| D09 | Reapply request-proof/confirm path and token lifecycle integration with Auth | **NEW DESIGN BASELINE, PR ACK REQUIRED** | Hiếu,Dương,Lâm | AUTH-01, TD-01 and anti-enumeration tests |
| D10 | Error codes `PRICE_CHANGED`, stale version and exact per-operation 4xx details | **MIXED: SRS RULES + HTTP MAPPING PROPOSED** | Hiếu, Lâm, Dương, Tân | shared errors + snapshots/examples |
| D11 | Dashboard/AI uses Analytics/Inventory read services; AI tools read-only | **SRS APPROVED / SYMBOLS PROPOSED** | Hiếu,Dương,Na Na,Lâm | AI-01..04 and service ports |
| D12 | Release 24/11 QA on RC SHA then main merge & smoke | **PROCESS BASELINE PROPOSED** | Hiếu,Lan Anh,all | release note & CI evidence |

**PR ACK mẫu:** `Contract D07 reviewed, consumer <name> ACK signature <module.func> @ <SHA>; sample fixture + error flow PASS (mock).` Chỉ Hiếu/owner được điều phối breaking contract changes; consumer phải được review.

**Không được coi các thứ sau là DONE:** Service stub `...`, mock API returns, app launches, pytest collected, schema YAML parsed, screenshot Swagger, CI run không có DB test hoặc test bỏ qua. Mỗi task cần evidence phù hợp.


---

## VERIFICATION COVERAGE

# CF-2.0 — Audit kết quả và giới hạn

- **Task cards:** 57 = 26 S2 + 31 S3, owner và mô tả được giữ từ Excel trong CF-1 docs; tra `TASK_TO_CONTRACT_INDEX.md`.
- **HTTP:** OpenAPI includes existing Product GET, planned S2/S3 endpoints and newly documented REAPPLY endpoints. Actual `develop` code only verified for Auth registration/login/refresh/logout, Notifications, Categories/Suppliers, Products and Purchasing models in snapshot.
- **Python:** `retailops_core_ports.pyi` CF1 + `retailops_extended_ports.pyi` CF2 are **interface stubs**, not installed app modules.
- **Schema:** ERD design baseline (not proof migrations applied). Receipt ORM available, Receipt migration not found in reviewed `develop` snapshot. Check newest branch before handoff.
- **Tests:** Script `scripts/check_cf2_package.py` performs syntax/schema reference/count checks; no runtime MySQL, RabbitMQ, Redis, browser E2E or backend contract tests are executed by this package build.
- **Owner approval:** all new Python/HTTP paths and implementation policies require reviewer ACK; see `docs/workflow/DECISION_REGISTER.md`. Avoid premature claims that a ZIP is binding team policy.
- **Unresolved tunables:** max per-command item counts, AI timeouts/max tool turns, email provider, publisher batch/retry/backoff, performance fixture and deployment option are **explicit PR decisions**, not SRS-provided constants.
- **Git status:** No GitHub repository files were modified by this document build. Publish via separate docs PR, then rebase implementation PRs on its SHA.
