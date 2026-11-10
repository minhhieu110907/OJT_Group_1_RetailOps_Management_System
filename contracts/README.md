# Các file contract kỹ thuật CF-2.3 (bản review)

- `openapi.yaml`: HTTP contract cho Sprint 2–3; `FROZEN_DESIGN` chỉ là chuẩn thiết kế, còn provider/consumer cần ACK.
- `python/retailops_core_ports.pyi`, `python/retailops_extended_ports.pyi`: Python ABI có kiểu; không phải implementation runtime.
- `typescript/api-client-contract.ts`: reference types và query interface cho frontend.
- `ai_tool_schemas.json`: input/output JSON Schema của 4 tool read-only; limits đang chờ xác nhận.
- `task_dependencies.json`: 57 records STARTABLE/INTEGRATABLE/ACCEPTED, 124 quan hệ DAG.
- `lms_task_baseline.json`: snapshot 57 mã task/tên/owner/Sprint lấy từ tab 1 Excel, kèm SHA-256 file nguồn.
- `develop_product_api_baseline.json`: query Product Search/Sort đã đối chiếu source code `develop` đúng SHA; không phải HTTP runtime proof.
- `examples/*.json`: 18 JSON fixtures; 16 đối chiếu OpenAPI JSON Schema, 1 AI args schema và 1 event envelope cơ bản.

**Kiểm tra:** `python scripts/check_cf23_contracts.py` rồi chạy hai script kiểm tra cấu trúc cũ. Chúng không chứng minh MySQL concurrency, RabbitMQ worker, E2E hoặc quyền runtime. Trước merge phải review quyết định còn mở tại `docs/START_HERE.md`.
