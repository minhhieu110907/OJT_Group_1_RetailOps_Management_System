> **Nguồn chuẩn:** `.pyi` cho Python ABI; `contracts/openapi.yaml` cho HTTP. Agent phải sửa mọi ví dụ mâu thuẫn trước khi code, không tự chọn chữ ký. Các contract còn PENDING cần ACK của provider + consumer.

# RetailOps — Hướng dẫn từng task Sprint 2

**Trạng thái:** Bản đề xuất triển khai contract — cần Tech Lead cùng consumers khóa các interface mới trước khi code.

**Nguồn phân công duy nhất:** file Excel được cung cấp 10/11/2026, tabs Sprint 2/Sprint 3 + lịch mốc 2 ngày. Mã LMS của 57 task đã đối chiếu với tab 1 trong Excel; chỉ dùng mã đi kèm từng task.


> **Tình trạng:** hợp đồng lõi là FROZEN_DESIGN, **không có nghĩa runtime đã triển khai hoặc provider/consumer đã ký nhận**.


## Cách đọc một task

Mỗi card ghi rõ task cung cấp gì (provider), cần dùng gì (consumer), phương thức/API đề xuất để kết nối và bài test nghiệm thu. Các phương thức mới được định nghĩa tại `../../contracts/python/*.pyi`, API HTTP tại `../../contracts/openapi.yaml` và phần diễn giải trong `../contracts/API_INTEGRATION.md`. **Mã LMS thật là định danh task duy nhất trong bộ docs.**

## T04A61F — Phân quyền và duyệt Staff

**Bàn giao bắt buộc:** Hiếu sở hữu `OutboxWriter.append` + event envelope + migration Outbox tối thiểu **trong Sprint 2**. Auth Register đã có trên S1 phải bổ sung hook durable `STAFF_REGISTERED` trong transaction tạo Staff, duyệt/từ chối ghi `STAFF_APPROVED`/`STAFF_REJECTED`. Không được phụ thuộc Worker Sprint 3 để commit nghiệp vụ S2. Dương/QA nhận event schema và kiểm thử rollback, retry không sinh event trùng.


**Mã task LMS (bắt buộc trong commit/PR):** `T04A61F`  
**Tên LMS:** Phân quyền và duyệt Staff  
**Commit mẫu:** `feat(backend): phân quyền và duyệt staff [T04A61F]`  
**PR:** ghi `T04A61F` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Hiếu · **Mốc trong Excel:** 10–11/11 · **Contract:** `HTTP-AUTH,BE-OUTBOX`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Xây dựng API để Admin duyệt hoặc từ chối đăng ký Staff; kiểm tra RBAC và trạng thái ACTIVE, bảo đảm chuyển trạng thái nhất quán; ghi sự kiện vào Outbox trong cùng transaction và chuẩn bị migration từ Sprint 2.
Phụ thuộc: Nền tảng Auth của Sprint 1; thống nhất cấu trúc sự kiện với hạng mục Outbox của Sprint 3.
Nghiệm thu: Kiểm thử quyền ADMIN/STAFF, các yêu cầu duyệt đồng thời, không phát sinh thông báo hoặc sự kiện trùng; có PR và bằng chứng kiểm thử.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S1 Auth User/StaffApproval, outbox_events migration. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `StaffApprovalService.decide(session, approval_id, decision, reason, actor_id); OutboxWriter.append(...)`.
- **Bên nhận / giao tiếp:** Lâm StaffApprovalPage; Dương Email reset; Admin notifications.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A61F` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-AUTH, BE-OUTBOX` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** S2 owns OutboxWriter + event schema; absolutely no S3 Worker dependency. S1 register needs STAFF_REGISTERED backfill hook. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** race: chỉ 1 decision thắng; event trong cùng commit; role ADMIN.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A639 — Khung Idempotency dùng chung

**Mã task LMS (bắt buộc trong commit/PR):** `T04A639`  
**Tên LMS:** Khung Idempotency dùng chung  
**Commit mẫu:** `feat(backend): khung idempotency dùng chung [T04A639]`  
**PR:** ghi `T04A639` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Hiếu · **Mốc trong Excel:** 10–11/11 · **Contract:** `BE-IDEM`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Xây dựng cơ chế idempotency dùng chung với phạm vi người dùng; hỗ trợ trả lại kết quả cũ, lỗi 409 khi dữ liệu khác, xử lý yêu cầu đồng thời và lưu kết quả 24 giờ. Cung cấp migration và thành phần dùng chung cho Checkout, Receipt Confirm, Cancel và Inventory Adjustment.
Bàn giao sớm: Thống nhất API contract và cách tích hợp trước khi các module bắt đầu triển khai nghiệp vụ.
Nghiệm thu: Kiểm thử tích hợp trên MySQL cho retry, yêu cầu trùng, dữ liệu thay đổi và truy cập đồng thời.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** MySQL 8, SRS ENG-03, ERD TD-04C. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `IdempotencyExecutor.execute(session, *, actor_id, operation, idempotency_key, request_identity, command)` — xem CF-01.
- **Bên nhận / giao tiếp:** Hiếu Checkout/Cancel; Dương Confirm/Adjust.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A639` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `BE-IDEM` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** replay/collision/race/rollback trên MySQL; một commit.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A653 — Inventory Service

**Bàn giao bắt buộc:** Dương bổ sung StockMovement ORM + migration tuyến tính (ngoài Product/Inventory đã có), `stock_version`, unique movement/source, thứ tự lock Product ID tăng → Inventory ID tăng; consumer dùng cùng `Session` và service không commit ẩn. Hiếu review migration và concurrency test MySQL.


**Mã task LMS (bắt buộc trong commit/PR):** `T04A653`  
**Tên LMS:** Inventory Service  
**Commit mẫu:** `feat(backend): inventory service [T04A653]`  
**PR:** ghi `T04A653` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Dương · **Mốc trong Excel:** 10–11/11 · **Contract:** `BE-INVENTORY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Xây dựng Inventory Service với giao diện thống nhất cho tăng, giảm, hoàn và điều chỉnh tồn; sử dụng stock_version, Stock Movement và cơ chế khóa. Transaction do module gọi điều phối, Service không tự commit độc lập.
Bàn giao: Gửi giao diện sử dụng và quy ước thứ tự khóa cho Hiếu, Lan Anh trước khi tích hợp Checkout và Receipt.
Nghiệm thu: Kiểm thử trên MySQL bảo đảm tồn không âm, rollback nguyên tử và mỗi biến động chỉ được ghi đúng một lần.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Product/Inventory/StockMovement ORM; ERD TD-04B. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `InventoryService.lock_for_mutation(session, *, product_ids)` → các phương thức `increase_for_receipt/decrease_for_checkout/restore_for_cancel/adjust_to_count(session, *, locks=StockLockSet, ...)` — xem CF-02.
- **Bên nhận / giao tiếp:** Hiếu Checkout/Cancel; Dương Confirm/Adjust; Na Na Read.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A653` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `BE-INVENTORY` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** StockMovement ORM + Alembic migration not found on develop; Dương to implement in this task, rather than assume S1 finished. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** khóa tăng ID; nonnegative; movement/version atomic; no hidden commit.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A66F — Bộ khung kiểm thử MySQL

**Mã task LMS (bắt buộc trong commit/PR):** `T04A66F`  
**Tên LMS:** Bộ khung kiểm thử MySQL  
**Commit mẫu:** `feat(backend): bộ khung kiểm thử mysql [T04A66F]`  
**PR:** ghi `T04A66F` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Dương · **Mốc trong Excel:** 10–11/11 · **Contract:** `TEST-DB`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Xây dựng bộ kiểm thử tích hợp pytest dùng riêng database retailops_test, gồm fixture, dọn dữ liệu sau kiểm thử và công cụ kiểm thử race condition trên MySQL 8; tài liệu hóa cách chạy tại máy cá nhân và trong CI.
Phối hợp: Mỗi người phụ trách module tự viết kiểm thử liên quan; Dương duy trì bộ khung và kiểm thử hồi quy dùng chung.
Nghiệm thu: Bài kiểm thử mẫu chạy đạt; có cơ chế ngăn kết nối nhầm database phát triển.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** existing integration database_guard; MySQL test user riêng. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `pytest fixture mysql_test_session và deterministic concurrency harness`.
- **Bên nhận / giao tiếp:** mọi Backend; Lan Anh CI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A66F` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `TEST-DB` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** fail closed nếu sai DB; rollback/race thật.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A689 — CI cho Pull Request

**Mã task LMS (bắt buộc trong commit/PR):** `T04A689`  
**Tên LMS:** CI cho Pull Request  
**Commit mẫu:** `ci(ci): ci cho pull request [T04A689]`  
**PR:** ghi `T04A689` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lan Anh · **Mốc trong Excel:** 10–11/11 · **Contract:** `GATE-CI`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Kiểm tra và hoàn thiện workflow CI hiện có cho Pull Request: lint, kiểm thử đơn vị, kiểm thử tích hợp MySQL, migration và các bước kiểm tra bảo mật phù hợp; thể hiện rõ kết quả trước khi merge vào develop.
Phụ thuộc: Bộ khung kiểm thử của Dương; Hiếu review khi có thay đổi hạ tầng.
Nghiệm thu: PR mẫu chạy đạt các bước kiểm tra bắt buộc; không bỏ qua bước kiểm tra và không làm lộ thông tin bí mật.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** existing workflows; Dương DB harness. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GitHub Actions jobs: Ruff, unit, MySQL integration, clean Alembic migration, security, FE lint/build`.
- **Bên nhận / giao tiếp:** mọi PR.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A689` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `GATE-CI` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** CI lint/unit start from existing workflows without T04A66F; MySQL job added after harness. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** required checks phản ánh thực thi thật, không job skip giả.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A6A3 — API tra cứu sản phẩm

**Đã có trên develop `cd1a6d3451a8`:** Product router đã hỗ trợ `search` (KHÔNG dùng `q`), `category_id`, `status`, `sort` whitelist và pagination. Na Na đối chiếu runtime và test bổ sung; không xây lại endpoint thứ hai.


**Mã task LMS (bắt buộc trong commit/PR):** `T04A6A3`  
**Tên LMS:** API tra cứu sản phẩm  
**Commit mẫu:** `feat(backend): api tra cứu sản phẩm [T04A6A3]`  
**PR:** ghi `T04A6A3` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Na Na · **Mốc trong Excel:** 10–11/11 · **Contract:** `HTTP-PRODUCT`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API danh sách và chi tiết sản phẩm, tìm theo tên/SKU, lọc và phân trang; thống nhất cấu trúc phản hồi với frontend.
Phụ thuộc: API Product/Category của Sprint 1; phối hợp cấu trúc dữ liệu với Lâm và Tân.
Nghiệm thu: Kiểm thử API, bộ lọc, phân trang; backend không trả giá vốn hoặc trường nhạy cảm cho STAFF.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Product/Category S1, ProductRead hiện có. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GET /products?search=&category_id=&status=&page=&page_size=; GET /products/{id}`.
- **Bên nhận / giao tiếp:** Lâm POS; Tân Product/Category; Na Na Dashboard.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A6A3` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-PRODUCT` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** read DTO khớp ProductRead; lọc & paging ổn định, RBAC.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A6BD — API tra cứu tồn kho

**Mã task LMS (bắt buộc trong commit/PR):** `T04A6BD`  
**Tên LMS:** API tra cứu tồn kho  
**Commit mẫu:** `feat(backend): api tra cứu tồn kho [T04A6BD]`  
**PR:** ghi `T04A6BD` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Na Na · **Mốc trong Excel:** 10–11/11 · **Contract:** `HTTP-INVENTORY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API chỉ đọc danh sách tồn kho theo sản phẩm, danh mục và trạng thái; trả số lượng và stock_version cho ADMIN/STAFF theo quyền.
Phụ thuộc: Mô hình và giao diện Inventory Service của Dương; thống nhất bộ lọc với Tân.
Nghiệm thu: Kiểm thử phân trang, trạng thái, phân quyền và tính chính xác của dữ liệu sau các Stock Movement.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Inventory ORM hiện có; không cần mutation service hoàn chỉnh. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GET /inventory; GET /inventory/{product_id}`.
- **Bên nhận / giao tiếp:** Tân inventory UI; Lâm POS; Analytics.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A6BD` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-INVENTORY` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Inventory Read starts from existing ORM without mutation service (T04A653). Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** quantity/version chính xác; không lộ field nội bộ.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A6D7 — Tạo và sửa phiếu nhập nháp

**Điều kiện migration:** PurchaseReceipt ORM từ S1 đã có nhưng migration chưa thấy trên baseline. Dương bàn giao migration còn tồn từ Sprint 1 (Hiếu review) trước khi Lan Anh chạy real integration; Lan Anh vẫn có thể viết DTO/fake trước.


**Mã task LMS (bắt buộc trong commit/PR):** `T04A6D7`  
**Tên LMS:** Tạo và sửa phiếu nhập nháp  
**Commit mẫu:** `feat(backend): tạo và sửa phiếu nhập nháp [T04A6D7]`  
**PR:** ghi `T04A6D7` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lan Anh · **Mốc trong Excel:** 10–11/11 · **Contract:** `HTTP-RECEIPT,BE-RECEIPT`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API tạo và sửa phiếu nhập DRAFT; gộp các dòng có cùng Product và Unit Cost, từ chối cùng Product nhưng khác Unit Cost; kiểm soát draft_version.
Phụ thuộc: API Supplier/Product hiện có; thống nhất API contract xác nhận phiếu với Dương.
Nghiệm thu: Kiểm thử MySQL/API cho phiên bản cũ trả 409, số lượng và đơn giá hợp lệ; DRAFT không thay đổi tồn kho.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Receipt ORM + migration cần xác minh; Supplier/Product models. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `ReceiptDraftService.create_draft / update_draft; POST/PATCH /purchase-receipts`.
- **Bên nhận / giao tiếp:** Dương Confirm; Tân Receipt UI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A6D7` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-RECEIPT, BE-RECEIPT` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Receipt ORM exists but migration absent on develop; S1 carryover migration owned by Dương, Hiếu reviews. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** gộp item same product+price; conflict khác giá; version stale; DRAFT không đổi tồn.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A6F3 — Giao diện duyệt Staff

**Mã task LMS (bắt buộc trong commit/PR):** `T04A6F3`  
**Tên LMS:** Giao diện duyệt Staff  
**Commit mẫu:** `feat(frontend): giao diện duyệt staff [T04A6F3]`  
**PR:** ghi `T04A6F3` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lâm · **Mốc trong Excel:** 10–11/11 · **Contract:** `HTTP-AUTH,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện Admin xem, duyệt và từ chối đăng ký Staff; thể hiện các trạng thái đang tải, trống, lỗi và xử lý HTTP 401/403/409.
Phụ thuộc: API phân quyền và phê duyệt của Hiếu; sử dụng Axios/Auth dùng chung.
Nghiệm thu: Kiểm thử trên API thật với vai trò ADMIN/STAFF; không lấy kết quả mock làm bằng chứng thành công; Lâm review frontend.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** AUTH contract; Axios/Auth S1. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `StaffApprovalPage -> staffApprovalsApi.list/approve/reject`.
- **Bên nhận / giao tiếp:** Hiếu approval API; Lan Anh UAT.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A6F3` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-AUTH, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A61F` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** real API 401/403/409; no silent mock fallback.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A70D — Giao diện danh mục, nhà cung cấp

**Mã task LMS (bắt buộc trong commit/PR):** `T04A70D`  
**Tên LMS:** Giao diện danh mục, nhà cung cấp  
**Commit mẫu:** `feat(frontend): giao diện danh mục, nhà cung cấp [T04A70D]`  
**PR:** ghi `T04A70D` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Tân · **Mốc trong Excel:** 10–11/11 · **Contract:** `HTTP-MASTER,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện React quản lý Category và Supplier, hỗ trợ CRUD/trạng thái, kiểm tra dữ liệu biểu mẫu, bảng dữ liệu và thông báo lỗi.
Phụ thuộc: API Category/Supplier đã merge; tái sử dụng các component dùng chung theo hướng dẫn của Lâm.
Nghiệm thu: Thao tác trên API thật, xử lý trạng thái đang tải/trống và lỗi 409/403; PR frontend được Lâm review.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S1 master-data endpoints. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `CategoryPage/SupplierPage -> existing categories/suppliers client`.
- **Bên nhận / giao tiếp:** Lâm FE shared; Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A70D` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-MASTER, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** ADMIN edits, STAFF restrictions, loading/error/empty on real API.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A73C — Checkout và Order Model

**Mã task LMS (bắt buộc trong commit/PR):** `T04A73C`  
**Tên LMS:** Checkout và Order Model  
**Commit mẫu:** `feat(backend): checkout và order model [T04A73C]`  
**PR:** ghi `T04A73C` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Hiếu · **Mốc trong Excel:** 12–13/11 · **Contract:** `HTTP-ORDER,BE-IDEM,BE-INVENTORY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Checkout nguyên tử tạo Order ở trạng thái COMPLETED, cập nhật Inventory và Stock Movement, lưu snapshot giá, xử lý PRICE_CHANGED với HTTP 409; bảo đảm idempotency khi retry và rollback an toàn.
Bàn giao sớm: Gửi API contract yêu cầu/phản hồi và mã lỗi từ 10–11/11 để Lâm triển khai giao diện.
Phụ thuộc: Inventory Service của Dương và khung idempotency của Hiếu.
Nghiệm thu: Kiểm thử yêu cầu đồng thời và rollback trên MySQL.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** IdempotencyExecutor + Inventory port + Product. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `CheckoutService.checkout(session, actor_id, items, key); POST /orders/checkout`.
- **Bên nhận / giao tiếp:** Lâm checkout/cart; Na Na Order history/Analytics.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A73C` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-ORDER, BE-IDEM, BE-INVENTORY` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A639`, `T04A653` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** PRICE_CHANGED 409 without mutations; one Order + movement/stock commit.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A758 — Điều chỉnh tồn kho

**Mã task LMS (bắt buộc trong commit/PR):** `T04A758`  
**Tên LMS:** Điều chỉnh tồn kho  
**Commit mẫu:** `feat(backend): điều chỉnh tồn kho [T04A758]`  
**PR:** ghi `T04A758` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Dương · **Mốc trong Excel:** 12–13/11 · **Contract:** `HTTP-INVENTORY,BE-IDEM,BE-INVENTORY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API kiểm kê theo số lượng thực tế và expected_stock_version; ghi audit, chỉ tạo Stock Movement khi có chênh lệch; thao tác không làm thay đổi tồn không được tăng stock_version.
Phụ thuộc: Inventory Service của Dương và khung idempotency của Hiếu.
Nghiệm thu: Kiểm thử trên MySQL cho phiên bản cũ trả 409, thao tác không làm thay đổi tồn, cập nhật đồng thời và phân quyền ADMIN.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Inventory port + IdempotencyExecutor. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `InventoryService.lock_for_mutation` → `adjust_to_count(session, *, locks, actor_id, adjustment)`; POST `/inventory/{product_id}/adjustments`.
- **Bên nhận / giao tiếp:** Tân adjustment form; Na Na Movement read.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A758` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-INVENTORY, BE-IDEM, BE-INVENTORY` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A639`, `T04A653` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** stale 409, no-op audit only, same-tx event/stock, Admin-only.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A772 — Hủy nháp và tra cứu phiếu nhập

**Mã task LMS (bắt buộc trong commit/PR):** `T04A772`  
**Tên LMS:** Hủy nháp và tra cứu phiếu nhập  
**Commit mẫu:** `feat(backend): hủy nháp và tra cứu phiếu nhập [T04A772]`  
**PR:** ghi `T04A772` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lan Anh · **Mốc trong Excel:** 12–13/11 · **Contract:** `HTTP-RECEIPT,BE-RECEIPT`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API hủy phiếu nhập còn DRAFT khi phiên bản hợp lệ; API danh sách/chi tiết có lọc, sắp xếp và phân trang, bảo toàn dữ liệu lịch sử.
Phụ thuộc: Cấu trúc và API phiếu nhập nháp của Lan Anh.
Nghiệm thu: Kiểm thử thao tác hủy lặp và chuyển trạng thái, phiên bản cũ trả 409; phiếu CONFIRMED bất biến và không thay đổi tồn kho khi hủy nháp.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Receipt Draft DTO from Lan Anh. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `ReceiptDraftService.cancel_draft / list_receipts / get_receipt`.
- **Bên nhận / giao tiếp:** Tân Receipt list; Dương confirm.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A772` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-RECEIPT, BE-RECEIPT` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A6D7` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** no stock change on cancel; terminal immutability; stale 409.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A78E — Lịch sử biến động và cảnh báo tồn thấp

**Mã task LMS (bắt buộc trong commit/PR):** `T04A78E`  
**Tên LMS:** Lịch sử biến động và cảnh báo tồn thấp  
**Commit mẫu:** `feat(backend): lịch sử biến động và cảnh báo tồn thấp [T04A78E]`  
**PR:** ghi `T04A78E` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Na Na · **Mốc trong Excel:** 12–13/11 · **Contract:** `HTTP-INVENTORY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API lịch sử Stock Movement theo nguyên tắc append-only và cảnh báo tồn thấp với ngưỡng P0 mặc định là 5; loại bỏ trường nhạy cảm theo vai trò.
Phụ thuộc: Inventory Service và cấu trúc Stock Movement của Dương.
Nghiệm thu: Kiểm thử ADMIN/STAFF, dữ liệu chính xác sau nhập/bán/hủy; không lộ giá vốn hoặc lý do nội bộ.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** StockMovement model, Inventory read. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GET /stock-movements; GET /inventory/low-stock`.
- **Bên nhận / giao tiếp:** Tân inventory UI; Dashboard; AI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A78E` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-INVENTORY` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A6BD`, `T04A653` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Low-stock read starts from Inventory ORM; movement history real integration needs StockMovement migration (T04A653). Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** append only; threshold=5 P0; STAFF DTO excludes internal reason/cost.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A7A8 — Giỏ hàng POS

**Mã task LMS (bắt buộc trong commit/PR):** `T04A7A8`  
**Tên LMS:** Giỏ hàng POS  
**Commit mẫu:** `feat(frontend): giỏ hàng pos [T04A7A8]`  
**PR:** ghi `T04A7A8` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lâm · **Mốc trong Excel:** 12–13/11 · **Contract:** `HTTP-PRODUCT,HTTP-ORDER,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện React giỏ hàng POS, gộp sản phẩm trùng, thêm/sửa/xóa số lượng, tính tổng tạm tính và báo lỗi khi sản phẩm INACTIVE.
Phụ thuộc: API contract tra cứu sản phẩm; phối hợp sớm với Hiếu về dữ liệu yêu cầu Checkout.
Nghiệm thu: Kiểm thử thao tác bằng bàn phím, nhập biểu mẫu và trạng thái lỗi; không coi sản phẩm trong giỏ là đã được giữ tồn.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** ProductRead and checkout request frozen, backend not required yet. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `usePosCart + productsApi.list -> checkoutApi.checkout`.
- **Bên nhận / giao tiếp:** Hiếu Checkout; Lâm Checkout UI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A7A8` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-PRODUCT, HTTP-ORDER, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A6A3` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Cart starts from Product read and agreed Checkout DTO; no Checkout implementation is needed to start. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** local quote only, no reservation, dedup and positive quantity.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A7C3 — Giao diện thao tác phiếu nhập

**Mã task LMS (bắt buộc trong commit/PR):** `T04A7C3`  
**Tên LMS:** Giao diện thao tác phiếu nhập  
**Commit mẫu:** `feat(frontend): giao diện thao tác phiếu nhập [T04A7C3]`  
**PR:** ghi `T04A7C3` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Tân · **Mốc trong Excel:** 12–13/11 · **Contract:** `HTTP-RECEIPT,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện React tạo/sửa phiếu nhập DRAFT, xác nhận/hủy và hiển thị phiên bản; phân biệt rõ thao tác trên phiếu nháp và phiếu đã xác nhận.
Phụ thuộc: Lan Anh bàn giao API contract tạo/hủy nháp; Dương bàn giao API contract xác nhận phiếu.
Nghiệm thu: Kiểm thử trên API thật, xử lý phiên bản cũ trả 409, quyền ADMIN; không cộng tồn trước khi xác nhận phiếu.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Receipt DTO + version/error contract. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `ReceiptEditor -> receiptsApi.create/update/confirm/cancel`.
- **Bên nhận / giao tiếp:** Lan Anh draft; Dương confirm.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A7C3` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-RECEIPT, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A6D7`, `T04A772`, `T04A7DF` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** UI mock from Receipt DTO; real confirm action only once T04A7DF endpoint lands. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** draft_version conflict, terminal read-only, real API smoke.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A7DF — Xác nhận phiếu nhập

**Mã task LMS (bắt buộc trong commit/PR):** `T04A7DF`  
**Tên LMS:** Xác nhận phiếu nhập  
**Commit mẫu:** `feat(backend): xác nhận phiếu nhập [T04A7DF]`  
**PR:** ghi `T04A7DF` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Dương · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-RECEIPT,BE-INVENTORY,BE-IDEM`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Xác nhận Receipt nguyên tử bằng expected_version và khóa idempotency; chuyển DRAFT → CONFIRMED, tăng tồn, ghi Stock Movement đúng một lần và không cho sửa phiếu sau xác nhận.
Phụ thuộc: Phiếu DRAFT của Lan Anh, Inventory Service của Dương và khung idempotency của Hiếu.
Nghiệm thu: Kiểm thử yêu cầu đồng thời, retry và rollback trên MySQL; đặc biệt không cộng tồn kho hai lần. Hiếu review transaction, Lan Anh thực hiện UAT.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Lan Anh Draft model/migration + Inventory port + Idempotency. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `ReceiptConfirmService.confirm(session, *, actor_id, receipt_id, expected_draft_version, idempotency_key)` — xem CF-03.
- **Bên nhận / giao tiếp:** Tân confirm UI; Lan Anh UAT.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A7DF` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-RECEIPT, BE-INVENTORY, BE-IDEM` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A6D7`, `T04A639`, `T04A653` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** concurrent confirm exactly one effect; lock header first; snapshot frozen.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A80C — Hủy đơn và hoàn tồn

**Mã task LMS (bắt buộc trong commit/PR):** `T04A80C`  
**Tên LMS:** Hủy đơn và hoàn tồn  
**Commit mẫu:** `feat(backend): hủy đơn và hoàn tồn [T04A80C]`  
**PR:** ghi `T04A80C` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Hiếu · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-ORDER,BE-INVENTORY,BE-IDEM`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API hủy Order có lý do, người thực hiện và mốc ngày theo giờ Việt Nam; STAFF chỉ được hủy đơn của mình trong 15 phút và cùng ngày, ADMIN được hủy mọi đơn COMPLETED trong ngày; hoàn tồn đúng một lần.
Phụ thuộc: Checkout/Order, Inventory Service và cơ chế idempotency.
Nghiệm thu: Kiểm thử hủy đồng thời, retry, ranh giới 15 phút/ngày, phân quyền, tồn kho và audit trên MySQL.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Order Model + Inventory restore + Idempotency. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `OrderService.cancel(session, order_id, actor_id, reason, key)`.
- **Bên nhận / giao tiếp:** Lâm cancel UI; Na Na Order history.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A80C` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-ORDER, BE-INVENTORY, BE-IDEM` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A73C`, `T04A639`, `T04A653` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** STAFF 15min same VN business day and owner; Admin same day; restore once.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A826 — Redis Rate Limiting

**Tái sử dụng code:** RedisFixedWindowRateLimiter và giới hạn Register 5/60s đã có trên develop; việc S2 là mở rộng Login/Refresh/Forgot/AI/Business theo SRS INF-02, kiểm trusted proxy và fail-closed/fail-safe. Không tạo limiter song song.


**Mã task LMS (bắt buộc trong commit/PR):** `T04A826`  
**Tên LMS:** Redis Rate Limiting  
**Commit mẫu:** `feat(backend): redis rate limiting [T04A826]`  
**PR:** ghi `T04A826` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Hiếu · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-RATE`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Rà soát phần Redis rate limiting đã có từ Sprint 1, bổ sung các endpoint còn thiếu theo SRS (login/refresh/forgot/AI/business); kiểm tra trusted proxy và chính sách fail-closed cho Auth công khai/AI.
Phụ thuộc: Redis hiện hữu; review cấu hình forwarded headers của Nginx.
Nghiệm thu: Kiểm thử giới hạn, HTTP 429, Redis ngừng hoạt động và giả mạo IP; không viết lại module đã hoạt động đúng.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S1 Redis code; trusted proxy config. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `RedisRateLimiter rules and 429/503 response contract`.
- **Bên nhận / giao tiếp:** Auth, AI, all FE clients.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A826` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-RATE` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** limits per SRS; 503 fail-closed public Auth/AI on Redis outage.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A840 — API lịch sử đơn hàng

**Mã task LMS (bắt buộc trong commit/PR):** `T04A840`  
**Tên LMS:** API lịch sử đơn hàng  
**Commit mẫu:** `feat(backend): api lịch sử đơn hàng [T04A840]`  
**PR:** ghi `T04A840` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Na Na · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-ORDER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API danh sách/chi tiết Order, lọc theo ngày/trạng thái, sắp xếp, phân trang và trả dữ liệu theo quyền truy cập.
Phụ thuộc: Cấu trúc Checkout/Order của Hiếu; có thể bắt đầu từ API contract giả lập.
Nghiệm thu: Kiểm thử snapshot giá, trạng thái CANCELLED và quyền sở hữu khi hủy; không trả dữ liệu nhạy cảm ngoài phạm vi quyền.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Order ORM/snapshot contract, not Cancel implementation. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GET /orders; GET /orders/{order_id}`.
- **Bên nhận / giao tiếp:** Lâm Order UI; Na Na Analytics.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A840` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-ORDER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A73C` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Order read from T04A73C schema; no hard wait on Cancel T04A80C. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** STAFF read all, cancel authorization separate; stable pagination.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A869 — Giao diện Checkout

**Mã task LMS (bắt buộc trong commit/PR):** `T04A869`  
**Tên LMS:** Giao diện Checkout  
**Commit mẫu:** `feat(frontend): giao diện checkout [T04A869]`  
**PR:** ghi `T04A869` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lâm · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-ORDER,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện POS gửi Checkout đến API thật; giữ ổn định khóa idempotency khi retry cùng một ý định mua, yêu cầu xác nhận giá mới khi PRICE_CHANGED; thể hiện trạng thái đang xử lý, lỗi và ngăn gửi trùng.
Phụ thuộc: API contract Checkout của Hiếu; có thể triển khai giao diện trước khi API hoàn thiện.
Nghiệm thu: Chỉ tạo một Order COMPLETED, không gửi giao dịch hai lần; xử lý HTTP 409/401 và retry khi lỗi mạng.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Checkout OpenAPI spec and cart data. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `checkoutApi.checkout(items, key) + PRICE_CHANGED flow`.
- **Bên nhận / giao tiếp:** Hiếu Checkout.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A869` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-ORDER, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A73C`, `T04A7A8` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** persist same key per intent, new key on reprice/reconfirmation.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A883 — Giao diện hủy đơn

**Mã task LMS (bắt buộc trong commit/PR):** `T04A883`  
**Tên LMS:** Giao diện hủy đơn  
**Commit mẫu:** `feat(frontend): giao diện hủy đơn [T04A883]`  
**PR:** ghi `T04A883` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lâm · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-ORDER,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện hủy đơn cơ bản, nhập lý do và xác nhận; cập nhật trạng thái sau khi hủy, xử lý lỗi 409/403 và chỉ hiển thị thao tác phù hợp với vai trò.
Phụ thuộc: API contract Cancel của Hiếu và API danh sách Order của Na Na.
Nghiệm thu: Hủy qua API thật, tồn kho được hoàn đúng sau khi tải lại; không báo thành công khi API thất bại.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Cancel HTTP contract and Order read. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `ordersApi.cancel(orderId,reason,key); ordersApi.get(orderId)`.
- **Bên nhận / giao tiếp:** Hiếu Cancel; Lan Anh UAT.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A883` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-ORDER, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A80C`, `T04A840` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** safe permission UI, backend guard authoritative, 409 handling.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A89D — Giao diện tồn kho thiết yếu

**Mã task LMS (bắt buộc trong commit/PR):** `T04A89D`  
**Tên LMS:** Giao diện tồn kho thiết yếu  
**Commit mẫu:** `feat(frontend): giao diện tồn kho thiết yếu [T04A89D]`  
**PR:** ghi `T04A89D` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Tân · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-INVENTORY,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện React danh sách tồn kho, số lượng/phiên bản, biểu mẫu kiểm kê dành cho ADMIN và thông báo phiên bản đã cũ; STAFF chỉ có quyền xem.
Phụ thuộc: API tồn kho của Na Na và API điều chỉnh tồn của Dương.
Nghiệm thu: Kiểm thử bằng API thật, phân quyền, trạng thái đang tải/trống/lỗi; số lượng cập nhật đúng sau nhập và bán.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Inventory Read and Adjustment contracts. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `inventoryApi.list/adjust and stock-version form`.
- **Bên nhận / giao tiếp:** Dương adjustment; Na Na read.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A89D` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-INVENTORY, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A6BD`, `T04A758`, `T04A78E` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** STAFF read-only; 409 stale forces refresh and reconfirm.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A8B7 — Giao diện lịch sử phiếu nhập

**Mã task LMS (bắt buộc trong commit/PR):** `T04A8B7`  
**Tên LMS:** Giao diện lịch sử phiếu nhập  
**Commit mẫu:** `feat(frontend): giao diện lịch sử phiếu nhập [T04A8B7]`  
**PR:** ghi `T04A8B7` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Tân · **Mốc trong Excel:** 14–15/11 · **Contract:** `HTTP-RECEIPT,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện danh sách/chi tiết Receipt, bộ lọc, trạng thái DRAFT/CONFIRMED/CANCELLED và responsive cơ bản.
Phụ thuộc: API của Lan Anh và Dương.
Nghiệm thu: Kiểm tra dữ liệu sau xác nhận/hủy; không hiển thị thao tác trái trạng thái hoặc quyền truy cập.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Receipt list/detail contract. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `receiptsApi.list/get; status UI`.
- **Bên nhận / giao tiếp:** Lan Anh Receipt API; Dương Confirm.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A8B7` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `HTTP-RECEIPT, FE-ADAPTER` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A772`, `T04A7DF` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** real data statuses, no mutation action on terminal receipt.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A8D1 — Kiểm tra Docker và Nginx

**Mã task LMS (bắt buộc trong commit/PR):** `T04A8D1`  
**Tên LMS:** Kiểm tra Docker và Nginx  
**Commit mẫu:** `feat(backend): kiểm tra docker và nginx [T04A8D1]`  
**PR:** ghi `T04A8D1` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Hiếu · **Mốc trong Excel:** 16/11 · **Contract:** `DEPLOY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Kiểm toán cấu hình Docker Compose và network từ 10–11/11; bảo vệ MySQL volume, khắc phục lỗi Docker DNS, cấu hình trusted proxy và định tuyến SPA/API; bảo đảm Backend không bị công khai ngoài chủ đích.
Phụ thuộc: Phương án phục vụ React của Lâm và cấu hình Compose/Nginx đang dùng.
Nghiệm thu: Cuối Sprint 2 khởi tạo thử từ môi trường Compose cô lập, kiểm tra migration/seed/health check/rollback và ghi runbook; không xóa volume phát triển.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** existing compose/frontend build. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Docker Compose + Nginx /api/v1 proxy, SPA fallback and trusted headers`.
- **Bên nhận / giao tiếp:** all FE/BE, E2E and release.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A8D1` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `DEPLOY` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ không có task S2/S3 bắt buộc; kiểm tra baseline Sprint 1 (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Proxy/cookie/trusted-header audit should start 10-11 Nov; final smoke 16 Nov. Keep official milestone. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** volume preservation, health, proxy spoof tests, no exposed DB.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A8F3 — Kiểm thử end-to-end Sprint 2

**Mã task LMS (bắt buộc trong commit/PR):** `T04A8F3`  
**Tên LMS:** Kiểm thử end-to-end Sprint 2  
**Commit mẫu:** `test(qa): kiểm thử end-to-end sprint 2 [T04A8F3]`  
**PR:** ghi `T04A8F3` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Người phụ trách:** Lan Anh · **Mốc trong Excel:** 16/11 · **Contract:** `GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Lan Anh điều phối thu thập bằng chứng kiểm thử từ từng người ngay khi có PR; chạy E2E luồng tạo DRAFT → CONFIRMED → tăng tồn → Checkout → hủy/hoàn tồn, cùng xác thực và phân quyền.
Phụ thuộc: Các module backend/frontend cốt lõi đã merge và CI đạt.
Nghiệm thu: Xác nhận dữ liệu đúng, kiểm thử HTTP 409/retry/race condition/rollback; lập danh sách lỗi chặn, người xử lý và biên bản kết thúc Sprint 2.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** merged real API + MySQL 8 + FE. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Receipt DRAFT -> CONFIRMED -> Inventory -> Checkout -> Cancel; Approval/Auth`.
- **Bên nhận / giao tiếp:** all six owners.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.


**Cổng dependency cho `T04A8F3` (theo `contracts/task_dependencies.json` — chờ duyệt):**

- **STARTABLE:** khóa `GATE-E, E` với provider/consumer; có thể viết unit test và adapter fake/mock mà không chờ tất cả PR.
- **INTEGRATABLE:** đã có mã từ `T04A61F`, `T04A6D7`, `T04A73C`, `T04A758`, `T04A772`, `T04A7DF`, `T04A80C`, `T04A6F3`, `T04A7C3`, `T04A869`, `T04A883`, `T04A89D`, `T04A8B7`, `T04A8D1` (nếu áp dụng), schema/migration cần thiết và CI; gọi API/DB thật. **Không coi mock PASS là xong task.**
- **ACCEPTED:** Consumer integrates real after provider PR; QA/CI evidence as applicable. Có kết quả test cho trường hợp đúng, lỗi, quyền truy cập và concurrency/rollback khi là write path; QA/consumer ACK.

### Kiểm thử và điều kiện hoàn thành (Definition of Done)

- **Nghiệp vụ/rủi ro bắt buộc:** evidence on exact commit; 403,409,replay,concurrency,rollback.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---
