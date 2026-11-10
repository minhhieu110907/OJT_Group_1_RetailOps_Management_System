# RetailOps V1.0 — Bộ tài liệu Sprint 2–3 (CF-2.4 Final, bản chờ duyệt)

**Mục đích:** cung cấp hướng dẫn triển khai cho 57 task LMS (26 Sprint 2, 31 Sprint 3). Không bao gồm 17 task bonus tab 2. Phiên bản này là **ứng viên chốt**, chưa có provider–consumer ACK, chưa được merge GitHub.

## Đường dẫn bắt đầu

- `docs/START_HERE.md` — bắt đầu từ đây, bảng task LMS, dependency và sổ quyết định.
- `docs/sprint2/TASK_IMPLEMENTATION_GUIDE.md` — hướng dẫn 26 task Sprint 2.
- `docs/sprint3/TASK_IMPLEMENTATION_GUIDE.md` — hướng dẫn 31 task Sprint 3.
- `docs/contracts/BACKEND_INTERFACES.md` — giao tiếp backend, transaction và lock.
- `docs/contracts/API_INTEGRATION.md` — giao tiếp HTTP, FE mock/real, read API.
- `docs/contracts/ASYNC_AI_CONTRACTS.md` — Outbox, Worker, Password Reset và AI.

## Nguồn contract máy đọc

- `contracts/openapi.yaml`: đặc tả HTTP đề xuất cho API chưa triển khai; API Product đã đối chiếu tại SHA pin trong `contracts/develop_product_api_baseline.json`.
- `contracts/python/*.pyi`: bản thiết kế interface Python, không phải module có thể import để chạy thật.
- `contracts/typescript/api-client-contract.ts`: kiểu dữ liệu tham chiếu phía FE.
- `contracts/ai_tool_schemas.json`: JSON Schema 4 AI tools; giới hạn kỹ thuật đã chốt tại CF-2.4 nhưng provider–consumer ACK và test vẫn chờ.
- `contracts/task_dependencies.json`: 57 task và 124 quan hệ tích hợp; các điều kiện STARTABLE / INTEGRATABLE / ACCEPTED.
- `contracts/lms_task_baseline.json`: snapshot mã LMS từ Excel tab 1, giữ provenance.

## Chạy kiểm tra từ thư mục gốc của gói/repository

Cài phụ thuộc (trong môi trường riêng của dự án): `python -m pip install PyYAML jsonschema`.

```bash
python scripts/check_cf23_contracts.py
python scripts/check_cf2_package.py
python scripts/check_contract_package.py
```

Kết quả PASS chứng minh cấu trúc tài liệu, fixtures và một số quy tắc tĩnh; **không chứng minh** MySQL concurrency, HTTP runtime, email gửi thật, AI authorization hay FE E2E. CI phải chạy trên đúng SHA định merge.

## Quy tắc hợp nhất

Chỉ đưa `docs/`, `contracts/` và các script kiểm tra vào repository; **không thay README.md chính của repo** bằng README này. Các contract `PROPOSED` chỉ trở thành `APPROVED` khi có provider–consumer ACK trên PR, kèm SHA và test evidence. Chỉ dùng mã LMS thật trong commit, không tự đổi ownership.


## Quyết định kỹ thuật vừa chốt
- AI: tổng 15s mặc định, ≤3 tool calls, ≤32 KiB dữ liệu tool, 1 in-flight/user và global bound; ADMIN/read-only.
- Email: 1 publisher và 1 worker, ≤25 events/batch, poll 5s; 1+3 retry transient 30/120/300s + jitter, permanent FAILED; SMTP timeout 10s + TLS.
- Phân biệt `published_at` (broker-confirm) với `outcome=SENT` (SMTP accept); không cam kết exactly-once.
- Các interface thiết kế vẫn chờ provider–consumer ACK; không thay đổi mã LMS, SRS hoặc ownership.
