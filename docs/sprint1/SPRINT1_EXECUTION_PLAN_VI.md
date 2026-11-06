# RETAILOPS — KẾ HOẠCH TRIỂN KHAI SPRINT 1

**Ngày chốt:** 06/11/2026. **Mục tiêu chạy thử (preview):** tối 08/11/2026. **Mốc nghiệm thu Sprint:** 10/11/2026.
**Nguồn sự thật (source of truth):** `docs/requirement/RetailOps_SRS_Approved.md`, `docs/database/RetailOps_ERD_V1.0.dbml`, UI Design Freeze và API Contract đi kèm.
**Lưu ý:** Với phần chưa có API Contract được phê duyệt, frontend sử dụng mock, không tự suy diễn schema. Việc đánh dấu task hoàn thành phải tuân thủ yêu cầu LMS và DoD kỹ thuật.

## 1. Người phụ trách và các task đang triển khai

| Người phụ trách | Mã LMS | Đầu ra cần bàn giao | Dependency |
|---|---|---|---|
| Hiếu | T3C9A19 | Models User / StaffApproval / Session / Refresh Token, seed Admin, cấu hình | Alembic baseline |
| Hiếu | T3C9A33 | Staff Registration công khai, Login, Refresh Rotation, Logout | User/Session schema; interface tạo Notification |
| Dương | T3C9B8A | Notification model và Receipt/ReceiptItem models, tách thành các PR độc lập | User/Approval schema, Supplier/Product models |
| Dương | T3C9BA4 | Admin Notification API: danh sách, unread count, mark-read, read-all | Notification model; danh tính Admin đã được xác thực |
| Dương | T3C9AD1 (bàn giao) | Models Product/Inventory/StockMovement đã làm: source code, migration, seed, tests | Category schema |
| Lan Anh | T3C9AEB | Product API: tạo, cập nhật, ngừng/kích hoạt lại | Product model, Category schema, Auth/RBAC Contract |
| Na Na | T3C9D63 | Category/Supplier schema và seed | Database baseline |
| Na Na | T3C9D7D | Category/Supplier API | Schema tương ứng, Auth/RBAC Contract |
| Lâm | T3C9E1A, T3C9E33 | Router, API client, màn hình Auth, xử lý lỗi API và Refresh | Auth Contract; chưa cần Backend thật khi đang dùng mock |
| Tân | T3C9C86 | Product list và UI states; Search/Form triển khai khi dependency sẵn sàng | Product Read Contract; kiến trúc Frontend của Lâm |

**`T3C9C6C` — Wireframe:** UI đã Design Freeze; đổi mô tả/đầu ra thành component/route mapping và UI states, không thiết kế lại.
**`T3C98CD` — Foundation:** Chạy Frontend/Backend local, chứng minh API integration và nộp minh chứng.

## 2. Các luồng phụ thuộc quan trọng, ưu tiên tích hợp sớm

**Luồng Auth:** User/Approval/Session schema + Notification schema → Transaction đăng ký (User + Approval + Notification, một lần commit) → API Approve/Reject tối thiểu (`AUTH-03` hiện thuộc Sprint 2, task `T3C9A4D`; cần phối hợp nếu triển khai sớm) → Staff `ACTIVE` Login → Frontend.

**Luồng Product:** Category schema + Product/Inventory schema → Category Read/Create + Product Create/Read API → Product UI dùng API thật. Supplier CRUD có thể triển khai song song với Product sau khi schema sẵn sàng.

**Luồng Notification:** Notification schema → Notification Service interface → Auth tạo Notification trong cùng SQLAlchemy session/transaction → Dương triển khai List/Read/Mark API → Lâm xây UI Admin (UI duyệt Staff hiện dự kiến ở Sprint 2).

**Luồng Receipt:** Supplier + Product schema → PR Receipt models → các nghiệp vụ Purchasing của Sprint 2. Luồng này không được chặn Product API hoặc Notification API.

## 3. Quy tắc quản lý Alembic migration (bắt buộc)

- Không ai tự tạo Alembic revision cuối cùng từ một head đã cũ rồi merge mà không kiểm tra.
- Chốt dependency của schema và thứ tự migration tại buổi họp ngắn. Thứ tự đề xuất: **A:** Auth + Category/Supplier models nền tảng; **B:** Product/Inventory/StockMovement; **C:** Notifications; **D:** Receipt models. Thứ tự thực tế được điều chỉnh theo dependency, nhưng phải duy trì một Alembic head tuyến tính làm chuẩn.
- Developer có thể viết ORM/schema trên feature branch riêng, nhưng **phải** cập nhật theo `develop` mới nhất và chỉnh lại/rebase migration chưa merge khi cần. Không viết lại migration đã merge lên shared branch hoặc đã triển khai.
- Hiếu điều phối hàng đợi merge migration; xác minh `alembic heads` chỉ có một head, `upgrade head` chạy trên MySQL mới, constraints/indexes đúng và seed chạy lại an toàn.
- Tránh PR quá lớn đồng thời chỉnh tables, routers hoặc Auth internals thuộc ownership của người khác.

## 4. Ownership source code và ranh giới trách nhiệm

- **Hiếu:** Auth, Sessions, danh tính người dùng, JWT/Cookie/Security Middleware, transaction owner của Registration; transaction owner chịu trách nhiệm commit/rollback.
- **Dương:** Notification model/service/API, Receipt model. Notification Service nhận SQLAlchemy session hoặc Unit of Work đang hoạt động từ Auth transaction; **không tự commit** trong `create_for_registration`.
- **Lan Anh:** Product service/router/schema; Product endpoint không tự sửa tồn kho. Tạo Product cùng Inventory row có lượng tồn bằng 0 trong một transaction; kiểm tra Category `ACTIVE` và SKU unique.
- **Na Na:** Category/Supplier service/router/schema; không hard delete dữ liệu còn được tham chiếu trong lịch sử, không tự chuyển sản phẩm đang tồn tại thành `INACTIVE` khi Category bị ngừng sử dụng.
- **Lâm:** Frontend Auth client/router/Refresh dùng chung. **Tân:** Product components. Cả hai cùng dùng mock responses tuân theo Contract trước khi Backend thật sẵn sàng.
- Mặc định AI agent chỉ sửa file thuộc task. Chỉnh sửa cross-cutting phải được Tech Lead review. Không merge trực tiếp vào `main`.

## 5. Lịch merge và kiểm thử theo ngày

**06/11 — Khóa hướng triển khai:** Công bố/thống nhất Contract, chốt DTO/path conventions, thứ tự migration và ownership API. Lâm tạo mock API fixtures; Tân dựng Product UI skeleton. Dương xác định nơi lưu code Product schema đã hoàn thành và bàn giao branch/PR. Mỗi developer tạo feature branch từ `develop` mới nhất và thông báo tên branch.

**07/11 — Merge schema nền tảng:** Merge models/migrations theo dependency. Backend developers viết Service/Router/Tests trên schema ổn định. Lâm hoàn thiện App Shell/Auth Client; Tân xây Product list dùng mock. Review sớm từng PR nhỏ; mở API Read ngay khi dependency đáp ứng.

**Tối 08/11 — Mốc chạy thử (preview):** Chạy `docker compose -f compose.yaml -f compose.local.yaml up -d` trên máy local; xác minh MySQL healthy, Alembic chỉ có một head, Backend Health, các endpoint Category/Product/Notification cốt lõi, Auth Register/Login nếu đã sẵn sàng, cùng Frontend preview bằng mock/API thật. Ghi rõ phần nào còn thiếu. Đây là **preview**, không tự động đồng nghĩa Sprint hoàn tất.

**09/11 — Tích hợp API thật:** Merge các API còn lại, FE chuyển dần từ mock sang API thật, kiểm tra `401/403/409/422`, conflict, xử lý duplicate và tests. Bổ sung Product Form và filter nâng cao khi Backend đã sẵn sàng.

**10/11 — Sprint Quality Gate:** Không mở rộng scope. Tập trung integration, security/regression, lint/build, test logs, minh chứng, review, PR merge và Sprint Review. Nếu task được đặt hạn 11/11, phải điều chỉnh timebox/chuyển task minh bạch trên LMS; không sửa lùi ngày hoặc ghi hoàn thành khi chưa đạt.

## 6. Quy tắc Branch / PR

Tạo feature branch từ `develop` đã cập nhật. Commit message có mã LMS. PR chỉ hướng vào `develop`. Ưu tiên PR nhỏ theo dependency: schema/migration → Service/API → Frontend integration. CI xanh, không còn blocking comments, review đúng Branch Rules, có evidence và acceptance tests. Có thể mở draft/WIP PR để trao đổi sớm nhưng không merge trước DoD. Frontend mock có thể merge sớm nếu được cách ly rõ và không thể vô tình dùng trên production.

**Blocker về GitHub review:** CODEOWNERS hiện chỉ có Tech Lead, trong khi tác giả PR không thể tự approve. Cần chủ động sửa chính sách review trước PR đầu tiên của Hiếu trên protected branch; không bypass Branch Protection hoặc âm thầm nới lỏng toàn bộ ownership rules.

## 7. Definition of Done (DoD) Sprint 1 theo mức rủi ro

- **Schema:** Migration chạy từ MySQL sạch, xác minh FK/unique/check/index, seed idempotent và `alembic current == heads`.
- **CRUD API:** Request validation, authorization chỉ cho Admin `ACTIVE` ở mutation, kiểm soát ownership/field, negative tests, DB integration tests, không hard delete dữ liệu lịch sử còn tham chiếu, HTTP errors nhất quán.
- **Auth:** Hash password an toàn, email canonicalization + unique, chặn Pending/Rejected, lỗi Login không làm lộ sự tồn tại tài khoản, session validity, Refresh Rotation và replay/concurrency handling, Cookie/CSRF/Origin đúng thiết kế, không log secret.
- **Notification:** Tạo cùng transaction đăng ký, `approval_request_id` unique, retry không tạo trùng, Admin-only List/Read/Count/Mark, không truy cập notification của tài khoản khác.
- **Frontend:** Mock khớp OpenAPI, có UI states (loading/empty/error/403/409), Auth Guard không được coi là security boundary, không lưu access JWT trong localStorage, lint/build PASS.

## 8. Các blocker phải báo sớm

1. Code Product/Stock schema cùng migration đã hoàn thành của Dương hiện nằm ở đâu? Tính đến 06/11, code đó chưa nằm trên `develop`.
2. Approval API đang được giao cho Sprint 2; cần quyết định owner/mốc bàn giao sớm nếu muốn chạy thử đầy đủ Register → Approve → Login.
3. Product Search/Detail đầy đủ đang thuộc Na Na trong Sprint 2 (`T3C9D97`), nhưng Product UI của Tân thuộc Sprint 1: cần chỉ định owner cho Product List/Read tối thiểu ở Sprint 1, hoặc xác nhận dùng mock đến Sprint 2.
4. Task Notification + Receipt models (`T3C9B8A`) không được biến thành một migration/PR quá lớn vượt qua nhiều domain độc lập.
5. Exact paths/DTOs của Auth/Catalog API phải được phê duyệt, không để AI agent tự đoán. Tài liệu Contract đi kèm mới là bản dự thảo ban đầu.
