> **CF-2.0 RULE:** interface chính xác phải tra trong [`TASK_TO_CONTRACT_INDEX`](../contracts/API_INTEGRATION.md) → [`CONTRACT_INDEX`](../contracts/API_INTEGRATION.md); HTTP ở `../../contracts/openapi.yaml`, Python ABI ở `../../contracts/python/*.pyi`, FE ở `../../contracts/typescript/api-client-contract.ts`. Các chữ ký cũ trong card chỉ là mô tả/recipe khi khác canonical interface. Chỉ được gọi APPROVED sau provider+consumer ACK trong PR.

# RetailOps — Hướng dẫn từng task Sprint 3

**Trạng thái:** Contract Implementation Candidate — cần Tech Lead cùng consumers khóa các interface mới trước khi code.

**Nguồn phân công duy nhất:** file Excel được cung cấp 10/11/2026, tabs Sprint 2/Sprint 3 + lịch mốc 2 ngày. Mã LMS của 57 task đã đối chiếu với tab 1 trong Excel; chỉ dùng mã đi kèm từng task.


> **Contract freeze CF-1.0:** với các task Idempotency, Inventory, Receipt, Checkout và Cancel, bắt buộc đọc [`S2_CORE_CONTRACTS_LOCKED.md`](../contracts/BACKEND_INTERFACES.md) **trước** phần ví dụ của card. Nếu chữ ký/HTTP bên dưới khác nguồn đã khóa, **nguồn mới này thắng**; agent phải cập nhật card qua PR, không tự suy đoán. Xem [`CONSUMER_RECIPES.md`](../contracts/BACKEND_INTERFACES.md) để biết consumer gọi provider chính xác như thế nào.

## Cách đọc một task

Mỗi card ghi rõ task cung cấp gì (provider), cần dùng gì (consumer), phương thức/API đề xuất để kết nối và bài test nghiệm thu. Các phương thức mới được định nghĩa tại `../shared/BE_PORTS.md`, API HTTP tại `../../contracts/openapi.yaml` và `../shared/API_HANDOFF.md`. **Mã LMS thật là định danh task duy nhất trong bộ docs.**

## T04A90F — Transactional Outbox và Email Worker

**Mã task LMS (bắt buộc trong commit/PR):** `T04A90F`  
**Tên LMS:** Transactional Outbox và Email Worker  
**Commit mẫu:** `feat(sprint3): implement 01 [T04A90F]`  
**PR:** ghi `T04A90F` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Hiếu · **Mốc trong Excel:** 18–19/11 · **Contract:** `BE-OUTBOX`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Xây dựng MySQL Transactional Outbox; Outbox Publisher chỉ phát sự kiện sau commit. RabbitMQ và Celery Email Worker xử lý bất đồng bộ theo cơ chế at-least-once, không gửi email trong transaction nghiệp vụ.
Phụ thuộc: Cấu trúc và dữ liệu sự kiện từ phê duyệt Staff trong Sprint 2; thống nhất API contract gửi email với Dương và Lan Anh trước 19/11.
Nghiệm thu: Sự kiện không bị mất khi broker/worker ngừng hoạt động và được phát lại sau khi phục hồi; không lộ thông tin bí mật.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 durable OutboxWriter + migration. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `OutboxPublisher.poll_publish; Celery EmailWorker.handle(event_id)`.
- **Bên nhận / giao tiếp:** Dương reset/worker tests; Na Na email tests.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** single publisher/sequential consumer; publisher confirm; duplicate idempotency.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A92B — Analytics doanh thu và đơn hàng

**Mã task LMS (bắt buộc trong commit/PR):** `T04A92B`  
**Tên LMS:** Analytics doanh thu và đơn hàng  
**Commit mẫu:** `feat(sprint3): implement 02 [T04A92B]`  
**PR:** ghi `T04A92B` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Na Na · **Mốc trong Excel:** 18–19/11 · **Contract:** `HTTP-ANALYTICS`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API thống kê doanh thu, số đơn và giá trị đơn trung bình (AOV) theo khoảng thời gian; loại đơn CANCELLED, sử dụng snapshot giá đã commit và chỉ cho ADMIN truy cập.
Phụ thuộc: Cấu trúc dữ liệu Order/Cancel của Hiếu.
Nghiệm thu: Đối soát với đơn hàng và Stock Movement; kiểm thử khoảng thời gian, phân quyền và không tính trùng.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Order/Cancel tables and committed rows. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GET /analytics/sales`.
- **Bên nhận / giao tiếp:** Na Na Dashboard; Lâm Dashboard; AI tools.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** Asia/Ho_Chi_Minh bounds, completed-only revenue/AOV, cancelled counts by sold_at.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A947 — Analytics sản phẩm

**Mã task LMS (bắt buộc trong commit/PR):** `T04A947`  
**Tên LMS:** Analytics sản phẩm  
**Commit mẫu:** `feat(sprint3): implement 03 [T04A947]`  
**PR:** ghi `T04A947` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 18–19/11 · **Contract:** `HTTP-ANALYTICS`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API phân tích sản phẩm bán chạy, bán chậm và tồn thấp theo SRS; xác định bán chậm từ first_stocked_at, tồn lớn hơn 0 và lượng bán không quá 2 đơn vị/30 ngày; thống nhất ngưỡng với Inventory.
Phụ thuộc: Dữ liệu Order/Inventory đã commit; phối hợp đối soát với Na Na.
Nghiệm thu: Kiểm thử MySQL cho sản phẩm không bán, đơn bị hủy, thời điểm nhập đầu tiên và quyền ADMIN.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** OrderItem snapshots; Inventory first_stocked_at. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GET /analytics/products/top; /analytics/products/slow`.
- **Bên nhận / giao tiếp:** Na Na Dashboard; Dương AI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** top excludes cancelled; slow >7days from first stocked, <=2 units/30d.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A961 — Hoàn thiện lịch sử và hủy đơn UI

**Mã task LMS (bắt buộc trong commit/PR):** `T04A961`  
**Tên LMS:** Hoàn thiện lịch sử và hủy đơn UI  
**Commit mẫu:** `feat(sprint3): implement 04 [T04A961]`  
**PR:** ghi `T04A961` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Lâm · **Mốc trong Excel:** 18–19/11 · **Contract:** `HTTP-ORDER,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Hoàn thiện giao diện React lịch sử/chi tiết Order, bộ lọc và giao diện hủy đơn từ Sprint 2; bổ sung hộp thoại nhập lý do và thông báo lỗi theo trạng thái.
Phụ thuộc: API Order/Cancel của Hiếu và Na Na.
Nghiệm thu: Kiểm thử trên dữ liệu thật với ADMIN/STAFF, không cho thao tác hủy ngoài điều kiện; Lâm review frontend.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 Read and Cancel endpoints. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `OrderHistoryPage -> ordersApi.list/get/cancel`.
- **Bên nhận / giao tiếp:** Lâm QA; Lan Anh UAT.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** real API 401/403/409, ownership/time boundary.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A97C — Hoàn thiện giao diện tồn kho

**Mã task LMS (bắt buộc trong commit/PR):** `T04A97C`  
**Tên LMS:** Hoàn thiện giao diện tồn kho  
**Commit mẫu:** `feat(sprint3): implement 05 [T04A97C]`  
**PR:** ghi `T04A97C` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Tân · **Mốc trong Excel:** 18–19/11 · **Contract:** `HTTP-INVENTORY,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện lịch sử Stock Movement, cảnh báo tồn thấp và responsive cho Inventory; chỉ hiển thị dữ liệu đúng phạm vi quyền.
Phụ thuộc: API của Na Na và Stock Movement của Dương.
Nghiệm thu: STAFF không thấy giá vốn; bộ lọc và trạng thái trống/đang tải/lỗi hoạt động đúng; dữ liệu khớp sau nhập, bán và hủy.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Na Na Read/Movement APIs. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `InventoryHistoryPage -> inventoryApi.movements/lowStock`.
- **Bên nhận / giao tiếp:** Tân UI QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** no custom threshold P1, hide restricted fields.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A996 — Tài liệu và UAT

**Mã task LMS (bắt buộc trong commit/PR):** `T04A996`  
**Tên LMS:** Tài liệu và UAT  
**Commit mẫu:** `feat(sprint3): implement 06 [T04A996]`  
**PR:** ghi `T04A996` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Lan Anh · **Mốc trong Excel:** 18–19/11 · **Contract:** `GATE-E2E,DEPLOY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Hoàn thiện README/runbook, hướng dẫn seed và chạy dự án; chuẩn bị các tình huống kiểm thử và danh sách kiểm tra UAT từ đầu Sprint 3; cập nhật bằng chứng liên tục.
Phụ thuộc: Kết quả từ từng người phụ trách và cấu hình Compose thực tế.
Nghiệm thu: Người khác có thể tái lập môi trường demo bằng cấu hình mẫu mà không cần chia sẻ bí mật thật; danh sách lỗi có mức độ và người xử lý.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 QA/real deployment. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `README/runbook + UAT scenarios + defect ledger`.
- **Bên nhận / giao tiếp:** all owners.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** reproducible setup; exact commit evidence.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A9B0 — Kiểm thử giao diện quản lý

**Mã task LMS (bắt buộc trong commit/PR):** `T04A9B0`  
**Tên LMS:** Kiểm thử giao diện quản lý  
**Commit mẫu:** `feat(sprint3): implement 07 [T04A9B0]`  
**PR:** ghi `T04A9B0` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Tân · **Mốc trong Excel:** 18–19/11 · **Contract:** `FE-ADAPTER,GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Kiểm thử giao diện React cho Product, Receipt và Inventory bằng API thật; phân loại lỗi theo người phụ trách và đính kèm hình ảnh/kết quả.
Phụ thuộc: Giao diện và API liên quan đã merge.
Nghiệm thu: Kiểm tra quyền ADMIN/STAFF, HTTP 401/403/409, các trạng thái đang tải/trống và responsive; không lấy kết quả mock làm bằng chứng đạt.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 FE components + mock/real adapter. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Product/Receipt/Inventory real API UI suite`.
- **Bên nhận / giao tiếp:** Lan Anh UAT.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** real API role/error/loading and responsive evidence.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A9CA — Kiểm thử Auth, Checkout và Cancel

**Mã task LMS (bắt buộc trong commit/PR):** `T04A9CA`  
**Tên LMS:** Kiểm thử Auth, Checkout và Cancel  
**Commit mẫu:** `feat(sprint3): implement 08 [T04A9CA]`  
**PR:** ghi `T04A9CA` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 18–19/11 · **Contract:** `TEST-DB`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Bổ sung và chạy kiểm thử hồi quy trên MySQL cho luồng Auth → Checkout → Cancel ngay khi từng PR được merge từ Sprint 2. Dương điều phối kiểm thử; Hiếu sửa lỗi transaction trong các module mình sở hữu.
Phụ thuộc: Auth của Sprint 1, Checkout/Cancel của Sprint 2 và bộ khung kiểm thử.
Nghiệm thu: Kiểm tra HTTP 401/403, thu hồi phiên đăng nhập, Checkout/Cancel đồng thời, tồn không âm và không hoàn kho trùng; lưu bằng chứng CI.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 backend and test harness. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Auth+Checkout+Cancel MySQL regression tests`.
- **Bên nhận / giao tiếp:** Hiếu security.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** concurrent checkout/cancel, RBAC, no duplicate restores.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04A9E6 — AI Tool Executor

**Mã task LMS (bắt buộc trong commit/PR):** `T04A9E6`  
**Tên LMS:** AI Tool Executor  
**Commit mẫu:** `feat(sprint3): implement 09 [T04A9E6]`  
**PR:** ghi `T04A9E6` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Hiếu · **Mốc trong Excel:** 20–21/11 · **Contract:** `BE-AI`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Xây dựng AI Tool Executor phía máy chủ với allowlist, cấu trúc tham số có kiểu, xác thực ADMIN ở từng lần gọi tool, timeout/quota, giới hạn kích thước kết quả và nhật ký kiểm toán; chỉ gọi business service đọc dữ liệu.
Bàn giao sớm: Gửi danh sách tên tool, cấu trúc tham số và API contract lỗi cho Dương trước khi tích hợp LLM, kể cả khi mới có stub.
Nghiệm thu: Kiểm thử prompt injection, giả mạo tool, vượt quyền, tham số không hợp lệ và xử lý lỗi an toàn.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Auth CurrentPrincipal; approved read-only facade. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `AIToolExecutor.execute(tool_id,args,principal,session)`.
- **Bên nhận / giao tiếp:** Dương AI Tool Calling; Lâm UI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** allowlist, typed args, RBAC every tool call, time and result bounds.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AA00 — Retry và phục hồi Email Worker

**Mã task LMS (bắt buộc trong commit/PR):** `T04AA00`  
**Tên LMS:** Retry và phục hồi Email Worker  
**Commit mẫu:** `feat(sprint3): implement 10 [T04AA00]`  
**PR:** ghi `T04AA00` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Hiếu · **Mốc trong Excel:** 20–21/11 · **Contract:** `BE-OUTBOX`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Hoàn thiện cơ chế retry/backoff có giới hạn, consumer idempotent, chống xử lý trùng, dead-letter và replay có kiểm soát cho Outbox → RabbitMQ → Celery.
Phụ thuộc: Luồng Email Worker do Hiếu xây dựng; Dương kiểm thử tích hợp.
Nghiệm thu: Kiểm thử broker ngừng hoạt động/khởi động lại, giao sự kiện trùng và lỗi email tạm thời; không làm mất ý định gửi, không cam kết email bên ngoài exactly-once.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** single-worker Outbox Lite. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Worker retry/backoff/replay and terminal outcome handling`.
- **Bên nhận / giao tiếp:** Dương worker integration.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** broker down/replay safe; no external SMTP exactly-once claim.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AA1C — Đặt lại mật khẩu và tích hợp email

**Mã task LMS (bắt buộc trong commit/PR):** `T04AA1C`  
**Tên LMS:** Đặt lại mật khẩu và tích hợp email  
**Commit mẫu:** `feat(sprint3): implement 11 [T04AA1C]`  
**PR:** ghi `T04AA1C` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 20–21/11 · **Contract:** `HTTP-RESET,BE-OUTBOX`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Chức năng quên/đặt lại mật khẩu Staff bằng token một lần, có hạn sử dụng và không thể tái dùng; gửi email qua adapter/worker. Phục hồi tài khoản ADMIN vẫn thực hiện thủ công theo SRS.
Phụ thuộc: API Auth/session và API contract email do Hiếu cung cấp; có thể bắt đầu bằng adapter email giả lập trước khi Worker hoàn thiện.
Nghiệm thu: Token được lưu dưới dạng hash, không ghi vào log; kiểm thử token hết hạn/đã dùng/replay, rate limiting và không tiết lộ sự tồn tại của email.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** account_action_tokens design; worker event writer. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `AuthResetService.request_reset/consume_reset -> OutboxWriter.append`.
- **Bên nhận / giao tiếp:** Lâm Auth UI; Na Na email tests.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** generic response no enumeration; one-time token and session revocation.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AA36 — Dashboard API

**Mã task LMS (bắt buộc trong commit/PR):** `T04AA36`  
**Tên LMS:** Dashboard API  
**Commit mẫu:** `feat(sprint3): implement 12 [T04AA36]`  
**PR:** ghi `T04AA36` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Na Na · **Mốc trong Excel:** 20–21/11 · **Contract:** `HTTP-ANALYTICS`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: API Dashboard dành riêng cho ADMIN, tổng hợp doanh thu, số đơn và tồn thấp theo cùng định nghĩa, bộ lọc của Analytics.
Phụ thuộc: API Analytics của Na Na/Dương và dữ liệu đã commit.
Nghiệm thu: Đối soát số liệu, kiểm thử phân quyền và bàn giao API contract cho Lâm trước khi tích hợp Dashboard UI.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Na Na SalesAnalytics + Dương ProductAnalytics read. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `GET /dashboard`.
- **Bên nhận / giao tiếp:** Lâm Dashboard and Dương AI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** Admin-only, shared timeframe/threshold semantics.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AA50 — Automated Integration Tests

**Mã task LMS (bắt buộc trong commit/PR):** `T04AA50`  
**Tên LMS:** Automated Integration Tests  
**Commit mẫu:** `feat(sprint3): implement 13 [T04AA50]`  
**PR:** ghi `T04AA50` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 20–21/11 · **Contract:** `TEST-DB,GATE-CI`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Dương duy trì bộ kiểm thử hồi quy MySQL xuyên suốt Sprint 2–3, bổ sung những tình huống P0 còn thiếu cho Receipt, Checkout, Cancel, Inventory, Auth và ranh giới Email/AI.
Phụ thuộc: Bộ khung kiểm thử Sprint 2 và các bài kiểm thử do chủ từng module cung cấp.
Nghiệm thu: Có lệnh chạy và CI đạt, bằng chứng kiểm thử race condition, rollback và idempotency; không thay MySQL bằng SQLite trong các kiểm thử này.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 test harness. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `MySQL concurrency + worker/AI integration regression`.
- **Bên nhận / giao tiếp:** Hiếu PR review; Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** tests run per owned PR, not all deferred.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AA6A — Responsive và UI States

**Mã task LMS (bắt buộc trong commit/PR):** `T04AA6A`  
**Tên LMS:** Responsive và UI States  
**Commit mẫu:** `feat(sprint3): implement 14 [T04AA6A]`  
**PR:** ghi `T04AA6A` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Tân · **Mốc trong Excel:** 20–21/11 · **Contract:** `FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Chuẩn hóa responsive trên thiết bị di động/máy tính, các trạng thái đang tải/trống/lỗi 403/409 và khả năng tiếp cận giao diện ở những màn hình Tân phụ trách; Lâm rà soát tính thống nhất.
Phụ thuộc: Giao diện cốt lõi Sprint 2 và API contract.
Nghiệm thu: Kiểm tra breakpoint, điều hướng bằng bàn phím và nhãn biểu mẫu; không báo thành công nếu API thất bại.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 FE screens + Design Freeze. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Shared responsive/loading/empty/error states`.
- **Bên nhận / giao tiếp:** Lâm QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** keyboard accessibility, no horizontal overflow, real error handling.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AA86 — AI chỉ đọc và Tool Calling

**Mã task LMS (bắt buộc trong commit/PR):** `T04AA86`  
**Tên LMS:** AI chỉ đọc và Tool Calling  
**Commit mẫu:** `feat(sprint3): implement 15 [T04AA86]`  
**PR:** ghi `T04AA86` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 20–21/11 · **Contract:** `BE-AI,HTTP-AI`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Dương tích hợp LLM với AI Tool Executor phía máy chủ do Hiếu xây dựng; mô hình chỉ được đề xuất tool thuộc allowlist, không được cung cấp SQL tự do hoặc tự chọn danh tính người dùng.
Phụ thuộc: Cấu trúc tool/stub bàn giao sớm, xác thực của Executor và API Analytics/Inventory.
Nghiệm thu: Chỉ ADMIN sử dụng được; câu trả lời có dẫn chứng dữ liệu và khoảng thời gian, tuân thủ timeout/quota; xử lý lỗi an toàn, không bịa số liệu.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Hiếu Executor ABI; Analytics/Inventory Read services. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `ReadOnlyAIService.ask(message, principal) -> evidence answer`.
- **Bên nhận / giao tiếp:** Lâm AI UI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** no arbitrary SQL/write and no model-supplied identity.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AAA2 — Đo hiệu năng và xác minh bảo mật

**Mã task LMS (bắt buộc trong commit/PR):** `T04AAA2`  
**Tên LMS:** Đo hiệu năng và xác minh bảo mật  
**Commit mẫu:** `feat(sprint3): implement 16 [T04AAA2]`  
**PR:** ghi `T04AAA2` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Hiếu · **Mốc trong Excel:** 20–21/11 · **Contract:** `PERF,GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Hiếu tạo kịch bản tải 10–20 người dùng đồng thời, đo P95 của API Product/Inventory/Checkout/Receipt/Dashboard; kiểm tra cấu hình bảo mật proxy, cookie và bí mật hệ thống.
Phụ thuộc: API cốt lõi có dữ liệu seed/test; đo ban đầu từ sớm và xác minh lại khi hệ thống ổn định.
Nghiệm thu: Báo cáo số đo trước/sau, kết luận ĐẠT/CHƯA ĐẠT theo ngưỡng SRS; không dùng phỏng đoán thay số đo.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** real APIs and stable fixture. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `P95 Product/Inventory/Checkout/Confirm/Dashboard + security report`.
- **Bên nhận / giao tiếp:** Lan Anh QA; release.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** record hardware/users/seed/workload; targets != actual results.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AABC — Kiểm thử Purchasing và Email

**Mã task LMS (bắt buộc trong commit/PR):** `T04AABC`  
**Tên LMS:** Kiểm thử Purchasing và Email  
**Commit mẫu:** `feat(sprint3): implement 17 [T04AABC]`  
**PR:** ghi `T04AABC` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Na Na · **Mốc trong Excel:** 22–23/11 · **Contract:** `TEST-DB,BE-OUTBOX`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Na Na đối soát trạng thái DRAFT/CONFIRMED/CANCELLED và quá trình tạo sự kiện gửi email/Worker trong tình huống thành công hoặc lỗi; bảo đảm nhật ký không chứa bí mật.
Phụ thuộc: API Receipt và Email Worker.
Nghiệm thu: Bằng chứng chuyển trạng thái và thay đổi tồn đúng một lần; chuyển lỗi cho Dương/Hiếu xử lý, Lan Anh tổng hợp UAT.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Receipt confirmed and Worker real. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Purchasing + Email failure/replay reconciliation suite`.
- **Bên nhận / giao tiếp:** Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** no second stock increase; outbound event intent durable.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AAD7 — Kiểm thử Product, Order và Analytics

**Mã task LMS (bắt buộc trong commit/PR):** `T04AAD7`  
**Tên LMS:** Kiểm thử Product, Order và Analytics  
**Commit mẫu:** `feat(sprint3): implement 18 [T04AAD7]`  
**PR:** ghi `T04AAD7` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Na Na · **Mốc trong Excel:** 20–21/11 · **Contract:** `TEST-DB,HTTP-ANALYTICS`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Na Na kiểm thử API Product/Order/Analytics trên dữ liệu seed và bộ dữ liệu kiểm tra độc lập; ghi lại sai khác kèm bước tái hiện lỗi.
Phụ thuộc: API Product Sprint 1–2, Order của Hiếu, Analytics của Na Na/Dương.
Nghiệm thu: Kiểm tra lọc/phân trang, doanh thu không tính đơn bị hủy, quyền đọc và thống kê khớp dữ liệu đơn đã commit.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** real S2/S3 read endpoints. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Product/Order/Analytics independent reconciliation`.
- **Bên nhận / giao tiếp:** Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** cancelled excluded, pagination stable, snapshot intact.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AAF1 — Kiểm thử frontend nghiệp vụ

**Mã task LMS (bắt buộc trong commit/PR):** `T04AAF1`  
**Tên LMS:** Kiểm thử frontend nghiệp vụ  
**Commit mẫu:** `feat(sprint3): implement 19 [T04AAF1]`  
**PR:** ghi `T04AAF1` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Lâm · **Mốc trong Excel:** 20–21/11 · **Contract:** `GATE-E2E,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Lâm chạy kiểm thử E2E giao diện Auth, POS, Checkout/Cancel trên API thật theo luồng nghiệp vụ; kiểm tra sơ bộ Dashboard dựa trên API contract sẵn có.
Phụ thuộc: Giao diện cốt lõi và API đã merge.
Nghiệm thu: Ghi bằng chứng lỗi, phân quyền, refresh và retry; kiểm thử Dashboard hoàn chỉnh sau khi giao diện được triển khai ngày 22–23/11.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S2 FE + backend merged. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Auth/POS/Checkout/Cancel FE E2E real API`.
- **Bên nhận / giao tiếp:** Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** no mock fallback, refresh and conflict behavior.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AB0B — AI gợi ý nhập hàng

**Mã task LMS (bắt buộc trong commit/PR):** `T04AB0B`  
**Tên LMS:** AI gợi ý nhập hàng  
**Commit mẫu:** `feat(sprint3): implement 20 [T04AB0B]`  
**PR:** ghi `T04AB0B` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 22–23/11 · **Contract:** `BE-AI,HTTP-AI`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Dương xây dựng đề xuất nhập hàng dựa trên tồn thấp và tốc độ bán, kèm nguồn dữ liệu; AI chỉ tư vấn, không tự tạo phiếu nhập hay thay đổi dữ liệu.
Phụ thuộc: Inventory/Analytics đã đối soát và AI Tool Executor chỉ đọc.
Nghiệm thu: Kiểm thử khi dữ liệu ít/thiếu, ngưỡng tồn, quyền ADMIN và dẫn chứng/khoảng thời gian; giữ phạm vi ưu tiên theo SRS, không tự ý loại khỏi kế hoạch.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** AI Executor/read facade, analytics. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `ReadOnlyReorderAdvisor.suggest -> evidence-only DTO`.
- **Bên nhận / giao tiếp:** Lâm AI UI.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** no write action; evidence + insufficient-data state.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AB25 — Giao diện Dashboard và AI

**Mã task LMS (bắt buộc trong commit/PR):** `T04AB25`  
**Tên LMS:** Giao diện Dashboard và AI  
**Commit mẫu:** `feat(sprint3): implement 21 [T04AB25]`  
**PR:** ghi `T04AB25` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Lâm · **Mốc trong Excel:** 22–23/11 · **Contract:** `HTTP-ANALYTICS,HTTP-AI,FE-ADAPTER`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Giao diện React Dashboard với biểu đồ lấy từ API và màn hình trò chuyện AI hiển thị trạng thái xử lý, nguồn dữ liệu, khoảng thời gian và lỗi timeout; hỗ trợ responsive.
Phụ thuộc: API Dashboard của Na Na và API contract AI của Dương/Hiếu; có thể triển khai từ stub ngày 19/11.
Nghiệm thu: Dùng API thật, chỉ ADMIN truy cập; xử lý HTTP 401/403 và trạng thái trống/lỗi; không hiển thị số liệu mock như số liệu thật.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Dashboard HTTP; AI HTTP. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `DashboardPage + AIChatPage via typed API clients`.
- **Bên nhận / giao tiếp:** Lâm FE E2E.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** display evidence/date, timeout/quota and safe errors.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AB3F — Rà soát bảo mật và concurrency

**Mã task LMS (bắt buộc trong commit/PR):** `T04AB3F`  
**Tên LMS:** Rà soát bảo mật và concurrency  
**Commit mẫu:** `feat(sprint3): implement 22 [T04AB3F]`  
**PR:** ghi `T04AB3F` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Hiếu · **Mốc trong Excel:** 22–23/11 · **Contract:** `SECURITY,TEST-DB`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Hiếu tổng hợp bằng chứng rà soát bảo mật và concurrency đã triển khai theo từng PR từ Sprint 2; ưu tiên sửa lỗi Critical/High trước khi phát hành.
Phụ thuộc: Các module đã merge, bộ kiểm thử MySQL và số đo hiệu năng ban đầu.
Nghiệm thu: Kiểm tra Auth/RBAC và quyền theo trường dữ liệu, CSRF/CORS/proxy, oversell/retry/rollback; mọi lỗi còn mở có phân mức nghiêm trọng.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** all P0 merged. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Security/RBAC/CSRF/concurrency sign-off evidence`.
- **Bên nhận / giao tiếp:** Lan Anh release gate.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** no Critical/High; test MySQL concurrency.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AB59 — Kiểm thử Inventory, Worker và AI

**Mã task LMS (bắt buộc trong commit/PR):** `T04AB59`  
**Tên LMS:** Kiểm thử Inventory, Worker và AI  
**Commit mẫu:** `feat(sprint3): implement 23 [T04AB59]`  
**PR:** ghi `T04AB59` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 22–23/11 · **Contract:** `TEST-DB,BE-OUTBOX,BE-AI`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Dương kiểm thử thực tế Inventory, Receipt và Order; kiểm tra Worker khi gián đoạn/phát lại sự kiện, AI khi truy cập trái quyền hoặc vượt giới hạn tool; thu thập bằng chứng.
Phụ thuộc: Inventory Sprint 2, Worker của Hiếu và AI của Dương.
Nghiệm thu: Bất biến dữ liệu được giữ đúng, retry hoạt động theo thiết kế và LLM không gọi công cụ ghi; báo ngay các lỗi chặn Critical/High.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Inventory + worker + AI real. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Inventory/Worker/AI integration and outage suite`.
- **Bên nhận / giao tiếp:** Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** fail-closed AI, no transaction corruption.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AB73 — Tích hợp và demo Worker/Redis/AI

**Mã task LMS (bắt buộc trong commit/PR):** `T04AB73`  
**Tên LMS:** Tích hợp và demo Worker/Redis/AI  
**Commit mẫu:** `feat(sprint3): implement 24 [T04AB73]`  
**PR:** ghi `T04AB73` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Dương · **Mốc trong Excel:** 22–23/11 · **Contract:** `GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Dương điều phối chạy tích hợp E2E cho AI/Redis/Email Worker bằng Docker Compose hiện có; Hiếu vẫn phụ trách hạ tầng và phê duyệt về bảo mật, Executor.
Phụ thuộc: Email Worker/retry của Hiếu và AI chỉ đọc của Dương.
Nghiệm thu: Kiểm thử nhanh luồng E2E, tình huống gián đoạn dịch vụ và nhật ký an toàn; không coi bản demo dùng mock là chức năng hoàn tất.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Hiếu infra + Dương AI. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Compose integrated Worker/Redis/AI demo run`.
- **Bên nhận / giao tiếp:** Hiếu release; Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** worker event to email; AI read-only; outages reproduced.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AB8D — Triển khai bản demo

**Mã task LMS (bắt buộc trong commit/PR):** `T04AB8D`  
**Tên LMS:** Triển khai bản demo  
**Commit mẫu:** `feat(sprint3): implement 25 [T04AB8D]`  
**PR:** ghi `T04AB8D` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Hiếu · **Mốc trong Excel:** 22–23/11 · **Contract:** `DEPLOY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Hiếu chuẩn bị môi trường demo bằng Docker Compose, Nginx phục vụ frontend/API, HTTPS/tunnel nếu cần, biến môi trường/bí mật, health check và bản triển khai thử trước ngày phát hành.
Phụ thuộc: Kết quả kiểm toán network Sprint 2, bản dựng frontend của Lâm và luồng Worker.
Nghiệm thu: Tái lập trên môi trường cô lập, kiểm tra seed/migration, danh sách smoke test, rollback/runbook; không xóa volume phát triển.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Nginx/fullstack/worker, FE build. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Release Candidate deployment with immutable commit SHA`.
- **Bên nhận / giao tiếp:** Lâm frontend E2E; Lan Anh UAT.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** health, migrations, secrets, backup/rollback notes.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04ABA7 — Release và smoke test

**Mã task LMS (bắt buộc trong commit/PR):** `T04ABA7`  
**Tên LMS:** Release và smoke test  
**Commit mẫu:** `feat(sprint3): implement 26 [T04ABA7]`  
**PR:** ghi `T04ABA7` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Hiếu · **Mốc trong Excel:** 24/11 · **Contract:** `DEPLOY,GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Hiếu khóa release candidate, kiểm tra CI, migration, đăng nhập theo vai trò, các luồng nghiệp vụ chính và Worker/AI; tạo PR phát hành từ develop sang main khi đạt điều kiện.
Phụ thuộc: Bằng chứng QA/UAT/bảo mật, không còn lỗi Critical/High.
Nghiệm thu: Danh sách kiểm tra và bản dựng gắn với commit cụ thể; sau 24/11 chỉ merge bản sửa lỗi P0/High đã kiểm thử để chuẩn bị demo.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** QA sign-off T04ABC3 + RC. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Release approval then main deployment smoke`.
- **Bên nhận / giao tiếp:** all.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** same SHA tested/released; no earlier release than QA.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04ABC3 — Nghiệm thu và đóng băng release

**Mã task LMS (bắt buộc trong commit/PR):** `T04ABC3`  
**Tên LMS:** Nghiệm thu và đóng băng release  
**Commit mẫu:** `feat(sprint3): implement 27 [T04ABC3]`  
**PR:** ghi `T04ABC3` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Lan Anh · **Mốc trong Excel:** 24/11 · **Contract:** `GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Lan Anh tổng hợp tiêu chí nghiệm thu P0 theo SRS, kết quả CI/UAT/benchmark, danh sách lỗi và người xử lý, lập biên bản đóng băng phát hành; Hiếu là người phê duyệt kỹ thuật cuối cùng.
Phụ thuộc: Release candidate và bằng chứng kiểm thử của từng người phụ trách.
Nghiệm thu: Không còn lỗi Critical/High, bất biến nghiệp vụ quan trọng đã kiểm chứng; ghi rõ giới hạn và các lưu ý cho demo.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** S3 RC + evidence from all. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `QA/UAT Sign-off and P0 freeze decision`.
- **Bên nhận / giao tiếp:** Hiếu release.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** zero Critical/High; missing evidence blocks release.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04ABDD — Báo cáo QA và tài liệu demo

**Mã task LMS (bắt buộc trong commit/PR):** `T04ABDD`  
**Tên LMS:** Báo cáo QA và tài liệu demo  
**Commit mẫu:** `feat(sprint3): implement 28 [T04ABDD]`  
**PR:** ghi `T04ABDD` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Lan Anh · **Mốc trong Excel:** 24/11 · **Contract:** `GATE-E2E,DEPLOY`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Lan Anh hoàn thiện báo cáo kiểm thử, README/runbook, dữ liệu seed demo và kịch bản trình diễn; lưu ngày merge, commit và phạm vi tính năng đã nghiệm thu.
Phụ thuộc: Bằng chứng E2E, UAT và bản phát hành thử.
Nghiệm thu: Danh sách kiểm tra có liên kết PR/CI, hướng dẫn chạy tại máy cá nhân có thể tái lập và người phụ trách từng phần demo.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** QA sign-off and release SHA. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `QA report, seed/runbook/demo script`.
- **Bên nhận / giao tiếp:** all presenters.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** reproducible demo, known limitations transparent.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04ABF9 — Tổng hợp giao diện và bằng chứng QA

**Mã task LMS (bắt buộc trong commit/PR):** `T04ABF9`  
**Tên LMS:** Tổng hợp giao diện và bằng chứng QA  
**Commit mẫu:** `feat(sprint3): implement 29 [T04ABF9]`  
**PR:** ghi `T04ABF9` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Tân · **Mốc trong Excel:** 24/11 · **Contract:** `FE-ADAPTER,GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Tân chuẩn bị ảnh/video bằng chứng, kiểm tra các màn hình Product/Receipt/Inventory trên API thật và tính responsive.
Phụ thuộc: Các trang frontend đã được Lâm review.
Nghiệm thu: Danh sách trạng thái màn hình, hình ảnh kiểm chứng thực tế và những vấn đề còn lại kèm mức độ nghiêm trọng.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Tân UI tests and app build. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `FE screenshots/videos and UI audit`.
- **Bên nhận / giao tiếp:** Lâm FE lead; Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** screens on real API/build; no mock proof.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AC15 — Đối soát dữ liệu và báo cáo

**Mã task LMS (bắt buộc trong commit/PR):** `T04AC15`  
**Tên LMS:** Đối soát dữ liệu và báo cáo  
**Commit mẫu:** `feat(sprint3): implement 30 [T04AC15]`  
**PR:** ghi `T04AC15` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Na Na · **Mốc trong Excel:** 24/11 · **Contract:** `HTTP-ANALYTICS,GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Na Na đối soát Product/Inventory/Order/Analytics trên dữ liệu demo, bảo đảm số liệu tổng hợp và thống kê không sai lệch khi hủy đơn.
Phụ thuộc: Các module nghiệp vụ đã hoàn thành E2E.
Nghiệm thu: Bảng so sánh kết quả mong đợi với kết quả thực tế, ghi sai khác nếu có; bàn giao dữ liệu phù hợp cho demo.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** real data seed and committed events. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `Reconciliation of orders/inventory/analytics snapshots`.
- **Bên nhận / giao tiếp:** Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** expected-vs-actual numbers, cancelled exclusion.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---

## T04AC2F — Kiểm tra end-to-end frontend

**Mã task LMS (bắt buộc trong commit/PR):** `T04AC2F`  
**Tên LMS:** Kiểm tra end-to-end frontend  
**Commit mẫu:** `feat(sprint3): implement 31 [T04AC2F]`  
**PR:** ghi `T04AC2F` trong tiêu đề hoặc description; dùng chính mã LMS này cho tất cả dependency và tham chiếu task.


**Owner:** Lâm · **Mốc trong Excel:** 24/11 · **Contract:** `FE-ADAPTER,DEPLOY,GATE-E2E`

### Phạm vi công việc (giữ nguyên ý nghĩa bảng phân công)

Đầu ra: Lâm chạy lại E2E frontend trên release candidate cho Auth → POS → Order → Cancel, Receipt/Inventory và Dashboard/AI; kiểm tra tải lại trang SPA qua Nginx.
Phụ thuộc: Frontend/API ổn định và bản triển khai thử của Hiếu.
Nghiệm thu: Kiểm thử nhanh trên các trình duyệt phổ biến, phân quyền ADMIN/STAFF, HTTP 401/403/409; lưu ảnh/bằng chứng và danh sách lỗi chặn.

### Giao tiếp liên task — không được tự đoán

- **Phải đọc/có trước:** Hiếu candidate + merged FE. Contract có thể đủ để bắt đầu unit/mocks; implementation thật phải có trước integration gate.
- **Interface/API cung cấp hoặc sử dụng:** `SPA/nginx full frontend smoke on release candidate`.
- **Bên nhận / giao tiếp:** Lan Anh QA.
- **Nếu interface chưa merge:** dùng fake/adapter khớp chữ ký, schema và test cases; không copy logic nghiệp vụ hoặc tạo endpoint tạm không được duyệt.

### Kiểm thử và Definition of Done

- **Nghiệp vụ/rủi ro bắt buộc:** reload deep routes; 401/403/409; POS/Inventory/Dashboard/AI.
- **Unit/API:** có test success, validation, quyền 401/403, conflict 409 theo endpoint áp dụng; Pydantic `extra="forbid"` khi có request body.
- **Tích hợp:** backend write => MySQL 8 test (transaction/rollback/race); frontend => real API và không fallback mock âm thầm; hạ tầng => khả năng khởi tạo lại và health check.
- **Bàn giao:** PR có mã LMS thật, link contract version, affected files, test command/result, bằng chứng API thật/DB thật khi thích hợp, dependencies đã unblock.

### Quy tắc về trạng thái

- `STARTABLE`: đã có contract/schema frozen (không bắt buộc provider merge hết).
- `INTEGRATABLE`: dependency runtime merge + migration sạch + CI pass.
- `ACCEPTED`: đúng test evidence và QA/consumer xác nhận, không chỉ vì PR xanh.

---
