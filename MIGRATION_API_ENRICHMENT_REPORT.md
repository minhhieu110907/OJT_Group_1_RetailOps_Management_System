# Báo cáo Database Extension & API Enrichment

Ngày lập: 2026-11-16
Phạm vi nghiệp vụ: AUTH-01, SALE-02, SALE-05, ENG-03, GOV-03, QA-01; liên kết triển khai T04A61F, T04A6A3, T04A73C, T04A80C, T04A840.

## A. Baseline

- Git base SHA: `ed52c74b134c98ea511c5fbf28665b209f83b67e` (`origin/develop`).
- Branch: `feature/backend-profile-product-api-enrichment`.
- Alembic revision cũ: `20261113_01`.
- Alembic revision mới/HEAD: `20261116_01`.
- Chỉ tạo một revision mới; không sửa migration đã merge.
- Bảng bị tác động DDL: `products`, `users`.
- API read/query bị tác động nhưng không thêm cột: categories, orders, staff approvals.
- Không chạy migration trên database ứng dụng/production.

## B. Schema diff

| Bảng | Cột mới | Kiểu | Nullable | Default |
|---|---|---|---|---|
| products | image_url | VARCHAR(500) | Có | Không |
| users | full_name | VARCHAR(120) | Có | Không |

- Không thêm index/constraint mới; naming convention hiện hữu không bị thay đổi.
- Không thêm lại `categories.description`; cột này đã có từ `20261113_01`.
- Test upgrade từ revision cũ tạo một Product và một User legacy: số hàng mỗi bảng trước/sau là 1 → 1; hai giá trị mới đều `NULL`.
- Test downgrade xác nhận hai cột bị xóa. Downgrade làm mất mọi dữ liệu đã ghi trong hai cột.
- MySQL DDL có implicit commit và Alembic log xác nhận “Will assume non-transactional DDL”; không giả định rollback DDL nguyên tử.

## C. API diff

| Endpoint/response | Thay đổi | Tương thích |
|---|---|---|
| POST/PATCH/GET /products | `image_url: string \| null` | Create omitted → NULL; PATCH omitted giữ nguyên; PATCH null xóa |
| POST /auth/register | Request tùy chọn `full_name` | FE hiện tại chỉ gửi email/password vẫn hợp lệ; HTTP 202 giữ nguyên |
| Auth/User responses được duyệt | `full_name: string \| null` | User cũ trả null |
| GET/POST/PATCH categories | `product_count: integer` | Response additive; pagination/filter total không đổi |
| Order list/detail/checkout/cancel | `created_by_name`, `cancelled_by_name` | Response additive, nullable |
| GET staff approvals | `full_name: string \| null` | Email, pagination, Admin-only giữ nguyên |

Ví dụ:

```json
{"image_url":"https://cdn.example.com/products/sku-1.png"}
```

```json
{"full_name":"Nguyen Van A","email":"staff@example.com","password":"***"}
```

Tên actor trong read list/detail là `users.full_name` hiện tại. Snapshot idempotency mới lưu tên tại lúc tạo response; snapshot lịch sử thiếu trường được deserialize thành `null`, không sửa digest/payload đã commit.

## D. Quality evidence

| Evidence | Kết quả |
|---|---|
| Ruff toàn backend | PASS |
| Corrective targeted API/schema/contract | PASS — 85 tests |
| Backend regression không external integration | PASS cuối — 510 tests, 156 deselected, 2 warnings có sẵn |
| MySQL targeted integration | PASS cuối — 48 tests |
| Clean migration harness | PASS |
| Alembic heads/history | PASS — một HEAD `20261116_01` |
| Alembic current --check-heads | PASS trên DB Docker sạch |
| Alembic check / metadata drift | PASS — “No new upgrade operations detected” |
| git diff --check | PASS |
| MySQL | 8.4 image, InnoDB |

MySQL suite gồm migration upgrade/downgrade, Product CRUD/image null, registration/approval/RBAC, category product count + `EXPLAIN FORMAT=JSON`, checkout/cancel/idempotency/concurrency và order read. Test persisted idempotency rows chứng minh snapshot checkout/cancel lịch sử thiếu hai trường tên replay thành `null`, còn snapshot mới giữ tên tại lúc commit. Một lần chạy trung gian phát hiện eager join mở rộng lock của cancel; implementation đã đổi để mutation chỉ lock Order, còn read explicit eager-load actor; rerun toàn suite PASS.

## E. Security & Performance

- `image_url` chỉ nhận URL tuyệt đối HTTPS, tối đa 500 ký tự; từ chối HTTP, javascript, data, file và URL sai. Backend không fetch/proxy nên không mở SSRF path mới.
- `full_name` trim, dài 1–120 nếu có; cấm whitespace-only; không suy đoán từ email.
- Email normalization, password hashing, JWT claims, session lifecycle, anti-enumeration và HTTP 202 không đổi.
- Staff approval vẫn Admin-only; Staff/unauthenticated không được mở rộng quyền.
- Category list dùng aggregate subquery + outer join; test chứng minh đúng 2 SELECT cho một trang, không tăng theo số category.
- Order list/detail explicit eager-load creator/canceller; không N+1.
- Order cancel lock query dùng `lazyload` actor relations để không tăng lock footprint hoặc đổi transaction boundary.
- Request digest và response snapshot idempotency lịch sử không bị sửa.
- Runtime OpenAPI và frozen OpenAPI được đối chiếu tự động cho các DTO enrichment; mọi trường `required` đều có trong `properties`.

## F. Risks & Recovery

- MySQL ALTER TABLE implicit commit: nếu DDL dừng giữa hai ALTER, có thể tạo partial schema. Phải kiểm tra schema/Alembic revision trước khi retry; không stamp mù.
- Trước deploy cần backup có kiểm chứng restore và cửa sổ bảo trì phù hợp. Recovery ưu tiên restore nếu migration dở dang.
- Downgrade xóa `users.full_name` và `products.image_url`, mất dữ liệu không phục hồi nếu không có backup.
- FE hiện tại có trường UI `fullName` nhưng real API adapter vẫn chỉ gửi `email,password`; backend tương thích, song muốn lưu tên ngay khi đăng ký thì FE cần task đồng bộ contract riêng.
- Snapshot idempotency cũ trả hai tên là null theo quyết định bảo toàn response lịch sử.

## G. Decision

- **READY FOR PR**: Có implementation, docs, lint, regression, MySQL integration, clean migration và drift evidence.
- **NOT READY FOR DEPLOY**: Chưa có Tech Lead review/approval, backup-restore rehearsal và staging rollout evidence. Không chạy production migration trong task này.
