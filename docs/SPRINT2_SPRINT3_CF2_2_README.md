# RetailOps — Sprint 2 & Sprint 3 CF-2.2 (Compact — LMS-only task identifiers)

**57 task chính; 17 task tab 2 để sau Sprint 3.** Không thay đổi ownership, tiến độ hoặc code repository.

## Sáu tài liệu Markdown chính

1. [`docs/START_HERE.md`](START_HERE.md) — Mã LMS 57 task, commit/PR, quy trình, decisions.
2. [`docs/sprint2/TASK_IMPLEMENTATION_GUIDE.md`](sprint2/TASK_IMPLEMENTATION_GUIDE.md) — 26 task, mỗi card có mã LMS thật, hướng dẫn và test.
3. [`docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md`](sprint3/TASK_IMPLEMENTATION_GUIDE.md) — 31 task, mỗi card có mã LMS thật.
4. [`docs/contracts/BACKEND_INTERFACES.md`](contracts/BACKEND_INTERFACES.md) — Idempotency, Inventory, Receipt, Checkout, Python ports và tests.
5. [`docs/contracts/API_INTEGRATION.md`](contracts/API_INTEGRATION.md) — FE mock/real, endpoints, analytics, 57-task contract index.
6. [`docs/contracts/ASYNC_AI_CONTRACTS.md`](contracts/ASYNC_AI_CONTRACTS.md) — Outbox, Email Worker, Password Reset, AI and S3 tests.

## Những file kỹ thuật vẫn giữ riêng

- `contracts/openapi.yaml` (tại thư mục gốc repository): nguồn chuẩn HTTP.
- `contracts/python/*.pyi`: nguồn chuẩn Python service interfaces.
- `contracts/typescript/*.ts`: reference types Frontend.
- `contracts/examples/*.json`: fixtures mock, tests.
- `scripts/*.py`: kiểm tra nội bộ của gói nguồn, có thể cần cập nhật path sau tinh gọn.

**Quan trọng:** 6 file Markdown là tài liệu được gộp để dễ đọc; các hợp đồng mới vẫn cần provider/consumer xác nhận qua PR trước khi coi là IMPLEMENTED/APPROVED. Hướng dẫn cũ có thể mô tả chữ ký khác với `.pyi`; `.pyi` và OpenAPI là canonical, không tự suy đoán.

## Quy ước định danh CF-2.2

Toàn bộ 57 task và mọi tham chiếu nội bộ đã chuyển sang **mã LMS thật `T04...`**. Không sử dụng mã thứ tự Sprint làm định danh task. Mẫu commit: `feat(inventory): implement stock service [T04A653]`. Tab 2 (bonus) không thuộc phạm vi hai Sprint.


## Lưu ý trước khi merge

Các contract mới là **design baseline đề xuất**, chưa phải bằng chứng đã implement. Provider/consumer cần đối chiếu `.pyi` + OpenAPI và review trên PR. Không dùng docs này để bỏ qua SRS, ERD, code hiện tại hoặc CI.
