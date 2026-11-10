# RETAILOPS CF-2.1 — BACKEND INTERFACES
> Bản tinh gọn: nội dung các tài liệu CF-2.0 được hợp nhất, không thay đổi nguồn chuẩn HTTP (`contracts/openapi.yaml`) và Python ABI (`contracts/python/*.pyi`). Các chương bên dưới là phần tham khảo có thể chứa ví dụ chữ ký cũ; khi khác canonical contract, ưu tiên ABI/OpenAPI và mở PR sửa hướng dẫn.


---

## S2 CORE CONTRACTS

# RETAILOPS V1.0 — SPRINT 2 CORE CONTRACT FREEZE (CF-1.0)

**Ngày chốt tài liệu:** 10/11/2026 · **Phạm vi:** bốn contract liên task: `BE-IDEM`, `BE-INVENTORY`, `BE-RECEIPT/HTTP-RECEIPT`, `BE-CHECKOUT/HTTP-ORDER`. **Trạng thái:** **FROZEN AS DESIGN BASELINE IN THIS PACKAGE** theo quyết định yêu cầu khóa contract; **chưa merge repo, chưa chứng minh đã implemented, chưa thay thế code/API runtime**. Người cung cấp + ít nhất một consumer vẫn phải review PR tài liệu trước khi triển khai trên branch chung. Những tham số chưa có trong SRS/ERD (timeout cụ thể, giới hạn số dòng, provider email...) được để `TBD — explicit approval`, không tự mặc định.

**Thứ tự nguồn:** [SRS](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/blob/develop/docs/requirement/RetailOps_SRS_Approved.md) → [ERD](https://github.com/minhhieu110907/OJT_Group_1_RetailOps_Management_System/blob/develop/docs/database/RetailOps_ERD_V1.0.dbml) → tài liệu quyết định được PO/Tech Lead chấp thuận → file này → code mới. Nếu repo code hiện tại xung đột, mở PR bảo trì/migration hoặc change request; không sửa âm thầm SRS/ERD.

**Phân biệt:** Chữ ký Python ở đây là **interface cần cung cấp**, không khẳng định các module/class hiện đã tồn tại. File machine-readable: `contracts/python/retailops_core_ports.pyi`. Chỉ định HTTP chính xác và request/response trong `contracts/openapi.yaml`. Các consumer có thể viết fake dựa trên contract ngay; chỉ được đánh dấu REAL-API-PASS sau khi PR provider merge, migration và MySQL test thực thi.

## CF-01 — BE-IDEM: IdempotencyExecutor (Hiếu → Hiếu, Dương)

### Chữ ký phải bàn giao

```python
from typing import Callable, Mapping, TypeVar, Generic
from dataclasses import dataclass
from enum import StrEnum
from sqlalchemy.orm import Session

T = TypeVar("T")

class IdempotencyOperation(StrEnum):
    CHECKOUT = "CHECKOUT"
    CONFIRM_RECEIPT = "CONFIRM_RECEIPT"
    CANCEL_ORDER = "CANCEL_ORDER"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"

@dataclass(frozen=True)
class CommandOutcome(Generic[T]):
    status_code: int        # 200..499; đã được chuẩn hóa để trả HTTP
    body: T                # DTO đã serialize an toàn, không phải ORM

class IdempotencyExecutor:
    def execute(
        self, session: Session, *, actor_id: int,
        operation: IdempotencyOperation,
        idempotency_key: str,
        request_identity: Mapping[str, object],
        command: Callable[[], CommandOutcome[T]],
    ) -> CommandOutcome[T]: ...
```

**Input `request_identity`** chuẩn hóa gồm `{operation, resource_id nếu có, body}`. Dùng canonical JSON (sort keys, separators ổn định, không có float/NaN; amount/quantity là số nguyên); fingerprint `SHA-256`. `idempotency_key` là opaque unique intent key do frontend tạo **một lần cho mỗi ý định**, ví dụ `crypto.randomUUID()`; phía server kiểm soát độ dài 16–128 ký tự ASCII thuộc `[A-Za-z0-9._:-]`. `key_digest` 32-byte HMAC-SHA-256 với khóa bí mật giữ ngoài DB là **quy tắc bảo vệ được chốt cho package**, không lưu raw key trong DB/log. Không lấy email/user_id từ request body thay authenticated principal.

**Mô hình transaction duy nhất — TD-04C Option A đã chốt trong ERD:** `INSERT claim` → gọi `command()` tạo side effects → serialize outcome → lưu status/body/completed_at/expires_at cùng transaction → **một commit của use case owner**. Không commit `IN_PROGRESS` riêng; không claim lease. Với key+payload trùng, replay nguyên HTTP status/body đã commit. Cùng key khác payload: `409 IDEMPOTENCY_KEY_REUSED`. Hai request đồng thời: chỉ một thực thi, caller còn lại chờ hữu hạn đến commit hoặc `409 REQUEST_IN_PROGRESS`; không giữ transaction vô hạn. Trả `REQUEST_IN_PROGRESS` không có nghĩa thao tác đầu tiên thất bại: FE phải giữ nguyên key khi retry. Vòng đời 24h tính từ `completed_at`, dọn bản ghi hết hạn có kiểm soát. Nếu khóa đã hết hạn và record bị dọn, cùng key có thể trở thành ý định mới; FE không được tái sử dụng key cũ sau khoảng này.

**Chi tiết quan trọng:** `PRICE_CHANGED` là một business refusal `409` có `changed_items` an toàn, có thể ghi outcome 409 dưới key trong transaction **không tạo Order/Movement**; FE muốn xác nhận giá mới phải tạo **key mới** và payload mới. Các lỗi chưa xác thực/quyền/parse body cần bị từ chối trước claim; lỗi SQL, 500, deadlock không tạo bản ghi thành công và rollback toàn bộ. `request_identity` không đưa refresh token, password, secret vào fingerprint/log.

**Use case owner chịu commit**. Do `get_current_principal` có thể đã truy vấn MySQL trên cùng Session, **không cứng nhắc `with session.begin()` sau dependency** khi SQLAlchemy đã autobegin; tuân convention có một `commit()` duy nhất tại service top-level (sau serialization) và `rollback()` khi exception. Không để repo/Inventory/Idempotency commit. Sai lệch này phải được contract test bắt.

**Consumer:** Hiếu `CheckoutService.checkout`, `OrderService.cancel`; Dương `ReceiptConfirmService.confirm`, `InventoryAdjustmentService.adjust`. Dương **không tự thiết kế bảng idem thứ hai**. Thử bắt buộc: same key/same payload replay, same key/different payload 409, hai request đồng thời một effect, lỗi giữa order và movement rollback, retry sau timeout, khác user/operation khác namespace, duplicate key không in key trong log.

## CF-02 — BE-INVENTORY: InventoryService (Dương → Hiếu, Dương; Lan Anh dùng qua Receipt)

### Interface an toàn khi nhiều mutation cùng sản phẩm

```python
from dataclasses import dataclass
from typing import Sequence, Mapping
from sqlalchemy.orm import Session

@dataclass(frozen=True)
class StockLine:
    product_id: int
    quantity: int                  # nguyên dương; cùng product phải gộp ở caller

@dataclass(frozen=True)
class LockedStock:
    product_id: int
    sku: str
    name: str
    status: str                    # ACTIVE / INACTIVE
    sale_price_vnd: int
    quantity: int
    stock_version: int

@dataclass(frozen=True)
class StockLockSet:
    rows: Mapping[int, LockedStock]  # snapshot lấy dưới SELECT ... FOR UPDATE

@dataclass(frozen=True)
class StockResult:
    product_id: int
    quantity: int
    stock_version: int

@dataclass(frozen=True)
class CountAdjustment:
    product_id: int
    counted_quantity: int
    expected_stock_version: int
    reason: str

@dataclass(frozen=True)
class AdjustmentResult:
    stock: StockResult
    audit_id: int
    movement_created: bool

class InventoryService:
    def lock_for_mutation(
        self, session: Session, *, product_ids: Sequence[int]
    ) -> StockLockSet: ...
    def increase_for_receipt(
        self, session: Session, *, locks: StockLockSet,
        receipt_id: int, actor_id: int, lines: Sequence[StockLine]
    ) -> list[StockResult]: ...
    def decrease_for_checkout(
        self, session: Session, *, locks: StockLockSet,
        order_id: int, actor_id: int, lines: Sequence[StockLine]
    ) -> list[StockResult]: ...
    def restore_for_cancel(
        self, session: Session, *, locks: StockLockSet,
        order_id: int, actor_id: int, lines: Sequence[StockLine]
    ) -> list[StockResult]: ...
    def adjust_to_count(
        self, session: Session, *, locks: StockLockSet,
        actor_id: int, adjustment: CountAdjustment
    ) -> AdjustmentResult: ...
```

**Chốt thứ tự khóa TD-04B:** với command có receipt/order hiện hữu, caller khóa **header** trước; `lock_for_mutation` khóa **Product ID tăng dần**, sau đó **Inventory ID tăng dần**, trong cùng MySQL transaction; mọi `apply_*` dùng chính `locks` đó và **không lấy lock chéo ngoài thứ tự**. Checkout chưa có Order header thì lấy Product/Inventory locks trước, kiểm tra giá, mới INSERT Order/OrderItems. `locks` chỉ hợp lệ trong cùng Session/transaction, không cache, không lưu qua request. Nếu implementation chọn lock theo batch, phải chứng minh thứ tự thực tế bằng MySQL concurrency test; truy vấn `ORDER BY` không tự bảo đảm row-lock acquisition order trong mọi query plan.

**Hành vi:** không stock âm; mỗi lần mutation không-no-op tăng `stock_version` đúng 1 cho mỗi product, thêm `stock_movements` cùng transaction; `first_stocked_at` set khi lần đầu tồn chuyển lên dương (không reset); dữ liệu cập nhật phải đúng SKU snapshot và FK nguồn. `increase` chỉ khi Receipt DRAFT được caller confirm; `decrease` chỉ cho Order COMPLETED mới; `restore` chỉ sau caller xác minh Order COMPLETED chuyển CANCELLED hợp lệ; bảo vệ unique `(order_id, product_id, kind)` cả khi khác idem key. `adjust_to_count` với expected version stale trả `409 STALE_STOCK_VERSION`; nếu counted bằng current vẫn tạo audit nhưng **không movement và không tăng version**. Nghiệp vụ mutation không được `commit()`, không trả raw ORM.

**Security:** quyền ADMIN/STAFF và eligibility kiểm tra tại orchestration dưới identity backend; actor_id không được lấy tùy ý từ FE/LLM. Staff chỉ đọc quantity, movement an toàn; không lộ unit_cost hoặc internal audit details.

**Consumer nào gọi hàm gì?**

| Consumer/task | Phương thức và điều kiện | Provider phải giao |
|---|---|---|
| Hiếu Checkout | `lock_for_mutation` → kiểm tra tất cả ACTIVE, giá đã xem, sufficient stock → `decrease_for_checkout` sau insert Order+Items | `StockLockSet`, errors và fixture two-checkout-race |
| Dương Receipt Confirm | lock Receipt DRAFT/version → `lock_for_mutation` → kiểm tra Supplier/Product ACTIVE → status/Items snapshot → `increase_for_receipt` | lock hierarchy, movement source FK và test confirm-vs-checkout |
| Hiếu Cancel | lock Order COMPLETED và điều kiện 15 phút/ngày VN → `lock_for_mutation` → status CANCELLED → `restore_for_cancel` | chống double-restock với key khác, test admin/staff |
| Dương Adjustment | `lock_for_mutation` → `adjust_to_count` | stale version 409, no-op audit case |

**Độc lập frontend:** Na Na đọc `inventory` từ ORM hiện có; không cần đợi mutation service hoàn thành để code GET. UI không giả định stock được giữ khi thêm vào giỏ.

## CF-03 — BE/HTTP-RECEIPT (Lan Anh Draft; Dương Confirm; Tân UI)

### Python names & responsibility (giữ import tách file)

```python
# Các path mới do PR triển khai tạo, không phải file đang có.
# backend/app/modules/purchasing/draft_service.py
class ReceiptDraftService:
    def create_draft(self, session: Session, *, actor_id: int, supplier_id: int,
                     items: Sequence[ReceiptLineInput]) -> ReceiptRead: ...
    def update_draft(self, session: Session, *, actor_id: int, receipt_id: int,
                     expected_draft_version: int,
                     supplier_id: int | None,
                     items: Sequence[ReceiptLineInput] | None) -> ReceiptRead: ...
    def cancel_draft(self, session: Session, *, actor_id: int, receipt_id: int,
                     expected_draft_version: int) -> ReceiptRead: ...

# backend/app/modules/purchasing/confirm_service.py
class ReceiptConfirmService:
    def confirm(self, session: Session, *, actor_id: int, receipt_id: int,
                expected_draft_version: int,
                idempotency_key: str) -> ReceiptRead: ...
```

`ReceiptLineInput = {product_id:int,quantity:int,unit_cost_vnd:int}`; `ReceiptRead` trả đầy đủ `id, supplier_id, supplier_name_snapshot, status, draft_version, total_vnd, created_by, closed_by, created_at, updated_at, closed_at, items[]`; mỗi item `product_id, sku_snapshot, product_name_snapshot, quantity, unit_cost_vnd, line_total_vnd`. Chữ ký new code phải theo `.pyi` và OpenAPI; `supplier_id=None`/`items=None` nghĩa **không cập nhật**, còn JSON `null` **bị 422** nếu field hiện diện; Pydantic phân biệt omitted bằng `model_fields_set`. `items:[]` 422. Ngưỡng max lines/size chưa được chuẩn hóa trong SRS/ERD → có guard vận hành chờ owner phê duyệt, không tự viết ra số 'đã chốt'.

**HTTP path & success:**

| Method | Path dưới `/api/v1` | Body chính | Success | Quyền |
|---|---|---|---|---|
| POST | `/purchase-receipts` | `{supplier_id,items:[...]}` | `201 ReceiptRead(DRAFT)` | ADMIN |
| PATCH | `/purchase-receipts/{receipt_id}` | `{expected_draft_version,supplier_id?,items?}` | `200 ReceiptRead` | ADMIN |
| POST | `/purchase-receipts/{receipt_id}/cancel` | `{expected_draft_version}` | `200 ReceiptRead(CANCELLED)` | ADMIN |
| POST | `/purchase-receipts/{receipt_id}/confirm` | `{expected_draft_version}` + `Idempotency-Key` | `200 ReceiptRead(CONFIRMED)` | ADMIN |
| GET | `/purchase-receipts`, `/{receipt_id}` | filters/ID | `200 Page/ReceiptRead` | ADMIN |

**SRS PUR-02/03/04 rules:** DRAFT không thay đổi inventory; duplicate Product+same unit_cost phải gộp quantity, duplicate Product+khác cost `422`, mọi tính tiền số nguyên VND (`line_total = qty*cost`, `total = sum`). Khi chỉnh DRAFT phải lock header và check expected version, tăng `draft_version` khi mutation được chấp nhận. Confirm phải idempotent, `supplier` + `products` ACTIVE, tất cả Stock/Movement/Receipt terminal trong một commit. CONFIRMED/CANCELLED không thể sửa lại. Cancel Draft không làm thay đổi stock. Snapshot Supplier/Product theo ERD tại terminal; không sửa history khi source đổi tên. Stale version trả `409 RECEIPT_VERSION_CONFLICT` và payload an toàn chỉ chứa version mới nhất nếu caller có quyền.

**Integration gating:** Receipt ORM hiện có ở `backend/app/modules/purchasing/models.py` nhưng snapshot `develop` chưa có migration tương ứng, nên **Dương/Hiếu điều phối migration** trước khi chạy real DB tests; Lan Anh có thể viết draft service/test fake và Tân có thể làm UI/mock trong khi đợi migration. Lan Anh và Dương không cùng mở PR sửa một router file; chia router hoặc PR integration nhỏ sau review.

**Test bắt buộc:** concurrent update same draft (one wins), edit CONFIRMED 409, stale confirm 409 no stock, supplier/product INACTIVE rollback, duplicate line cost, two idempotent confirms one stock increment, cancel DRAFT no movement, no cost leakage to STAFF, MySQL clean migration.

## CF-04 — BE/HTTP-ORDER CHECKOUT & CANCEL (Hiếu → Lâm, Na Na; dùng Dương Inventory)

### Service API

```python
# backend/app/modules/sales/service.py — new module theo planned work
class CheckoutService:
    def checkout(self, session: Session, *, actor_id: int,
                 idempotency_key: str, items: Sequence[CheckoutLine]) -> OrderRead: ...

class OrderService:
    def cancel(self, session: Session, *, actor_id: int, actor_role: str,
               order_id: int, reason: str, idempotency_key: str) -> OrderRead: ...
```

`CheckoutLine={product_id:int, quantity:int, viewed_unit_price_vnd:int}`. Duplicate Product trong cart gộp quantity **chỉ khi cùng viewed price**; nếu khác viewed price, reject validation và yêu cầu refresh giá. Backend không lấy giá bán từ payload để tính Order: sau lock đọc `products.sale_price_vnd`, so sánh giá người dùng đã xem. Các tiền là int VND, snapshot name/SKU/unit_price/line total tại lúc bán, Order tạo **COMPLETED ngay** trong transaction, không thêm `PAYMENT/PENDING/VAT/DISCOUNT` ngoài scope.

| Method | Path | Request | Success | Quyền |
|---|---|---|---|---|
| POST | `/orders/checkout` | `{items:[{product_id,quantity,viewed_unit_price_vnd}]}` + `Idempotency-Key` | `201 OrderRead(COMPLETED)` | ADMIN/STAFF |
| POST | `/orders/{order_id}/cancel` | `{reason}` + `Idempotency-Key` | `200 OrderRead(CANCELLED)` | ADMIN/STAFF theo điều kiện |
| GET | `/orders`, `/orders/{order_id}` | filter/id | `200 OrderPage/OrderRead` | ADMIN/STAFF xem tất cả |

**PRICE_CHANGED:** 409 `{code:"PRICE_CHANGED",message:"...",details:{changed_items:[{product_id,viewed_unit_price_vnd,current_unit_price_vnd}]}}`. Không tạo Order, không thay tồn, không movement. Khi UI nhận lỗi này: hiển thị giá mới, yêu cầu người dùng xác nhận; tạo **payload mới + key mới**. Retry lỗi network không rõ kết quả: **giữ nguyên key và payload** để truy hồi outcome, không tự bấm double-checkout bằng key mới.

**Cancel trong SRS SALE-04:** Staff chỉ cancel order tự tạo nếu còn `COMPLETED`, `now <= sold_at+15min` **và cùng ngày kinh doanh Asia/Ho_Chi_Minh**; Admin cancel bất kỳ COMPLETED trong cùng ngày VN, không cần cùng owner và không bị ràng buộc 15 phút. Cùng transaction: khóa Order header → kiểm điều kiện dưới lock → khóa Product/Inventory sorted → chuyển CANCELLED với reason, cancelled_by/at → `restore_for_cancel`, movement. Hai request cancel với **hai key khác nhau** vẫn chỉ được hoàn kho một lần. Order GET cho Staff vẫn đọc mọi đơn; quyền cancel riêng biệt. Không dùng frontend ẩn nút như biện pháp phân quyền.

**Mẫu orchestration chuẩn (trình tự thực tế, không phải code chạy ngay):**

```python
# User/session đã được xác thực; session đã có thể autobegin.
try:
    outcome = idem.execute(
        session,
        actor_id=principal.user.id,
        operation=IdempotencyOperation.CHECKOUT,
        idempotency_key=key,
        request_identity={"operation":"CHECKOUT", "body": normalized_payload},
        command=lambda: checkout_command(session, principal.user.id, normalized_payload),
    )
    session.commit()  # ONLY transaction owner; COMMIT succeeds before returning HTTP
except Exception:
    session.rollback()
    raise
return JSONResponse(status_code=outcome.status_code, content=outcome.body)
```

`checkout_command` thực hiện: (1) `lock_for_mutation(sorted product_ids)`; (2) validate ACTIVE + giá đã xem + sufficient quantity từ snapshot; (3) tạo Order và items, `flush()`; (4) `decrease_for_checkout(session,locks,order_id,actor_id,lines)`; (5) tạo `OrderRead` đã serialize. Không tự `commit()` trong nested functions. Nếu `PRICE_CHANGED`, `command()` trả `CommandOutcome(409, safe error body)`; không tạo Order/movement, `idem` có thể persist 409 refusal; 500/DB failure phải rollback claim + effects. Transaction closure ở top-level (vì Auth query có thể autobegin) thay vì tự lồng `session.begin()`.

**MySQL test vector tối thiểu:** concurrent checkout cùng 1 Product stock=1 → một 201, một controlled 409 và stock=0; crash sau Order row trước Movement → Order/Item/Stock/Movement/Idem đều rollback; same key+body replay 201; same key diff price/body 409; simultaneous cancel different keys → một cancel, một 409 và stock restored once; Staff cancel other owner 403, after 15min/next VN date 409/403 theo policy; Admin next VN date forbidden; Product INACTIVE reject; browser retry logic.

## Bảng lỗi đã khóa cho bốn contract

| HTTP | `code` | Áp dụng | Consumer xử lý |
|---|---|---|---|
| 401 | `UNAUTHENTICATED`, `SESSION_INVALID` | Protected API | Refresh hợp lệ hoặc login |
| 403 | `FORBIDDEN` | Role/ownership | Không retry như lỗi network |
| 404 | `RESOURCE_NOT_FOUND` | Không có tài nguyên | Hiển thị không tồn tại |
| 409 | `IDEMPOTENCY_KEY_REUSED` | Cùng key khác payload | New intent → key mới; báo lỗi |
| 409 | `REQUEST_IN_PROGRESS` | Duplicate cùng key chưa có outcome | Giữ key, retry có backoff ngắn |
| 409 | `PRICE_CHANGED` | Giá bán đổi so với payload | User xác nhận giá → **key mới** |
| 409 | `INSUFFICIENT_STOCK` | Tồn thiếu tại lock | Refresh stock, không tự retry checkout |
| 409 | `STALE_STOCK_VERSION` | CountAdjustment stale | Reload tồn/version |
| 409 | `RECEIPT_VERSION_CONFLICT` | DRAFT version stale | Reload Receipt/version |
| 409 | `INVALID_STATE` | Terminal receipt/order | Reload trạng thái |
| 422 | `VALIDATION_ERROR` | DTO hoặc business input | Sửa field/bản ghi |
| 429 | `RATE_LIMITED` | Rate limit | Respect `Retry-After` |
| 503 | `DEPENDENCY_UNAVAILABLE` | Infra unavailable theo chính sách | Không fallback mock khi đang real API |

Envelope lỗi chuẩn hiện có trong `backend/app/core/exception_handlers.py` = `{code,message,details}`; không trả raw exception/SQL/stack trace. Riêng `PRICE_CHANGED.details` có schema trong OpenAPI. Không gắn `429/503` lên mọi endpoint nếu không có logic vận hành tương ứng; OpenAPI response listing là các khả năng, phải có test thực tế trước khi coi implemented.

## Path registration cho FastAPI tránh shadowing

Khi implement `GET /inventory/low-stock` và `GET /inventory/{product_id}`, route **tĩnh** `/low-stock` phải được đăng ký **trước** route động `/{product_id}`; nếu không `/low-stock` có thể bị match vào `product_id` và 422 thay vì gọi đúng handler. Tương tự áp dụng các route tĩnh `read-all`, `unread-count`, `checkout` trước dynamic segments khi cùng prefix. OpenAPI YAML liệt kê contract nhưng **không tự đảm bảo thứ tự đăng ký FastAPI**; phải có API integration test thực tế cho các URL này.

## Gate và change control

1. Contract file + `.pyi` + `openapi.yaml` phải nhất quán; khi đổi method, path, dtype, lỗi phải có một PR contract trước consumer code migration.
2. `CONTRACT-FROZEN` = tài liệu chốt tên interface; **KHÔNG đồng nghĩa runtime-implemented**.
3. `PROVIDER-READY` = schema/migration + service test + PR merge `develop`.
4. `CONSUMER-REAL-PASS` = FE/BE test real integration theo đúng API, rollback/race trên MySQL.
5. Dương/Hiếu/Lan Anh/Lâm/Tân review chéo theo bảng owner–consumer; QA (Lan Anh) lưu evidence. `develop` green không thay test thật.


---

## BACKEND PORTS & TYPES

# RetailOps — Hợp đồng interface giữa các module Backend (S2–S3)

**Status: APPROVAL CANDIDATE; chưa phải source code đã triển khai.** Đây là những chữ ký đề xuất để **provider và consumer cùng code từ ngày đầu**. Trước khi merge `docs/` này, Hiếu + chủ module + người tiêu thụ phải review và xác nhận. Sau khi `FROZEN`, thay đổi tên hàm/DTO/invariant phải có PR contract và sự đồng ý của consumers; không để AI Agent tự đổi chữ ký. Hệ thống hiện là **Modular Monolith**, không giả làm microservices hay tự thêm HTTP nội bộ.

**Nguồn thiết kế đã kiểm chứng**: `docs/requirement/RetailOps_SRS_Approved.md`, `docs/database/RetailOps_ERD_V1.0.dbml`, `docs/sprint1/RETAILOPS_SPRINT1_CONTRACT.md`; code `develop` có `backend/app/modules/auth/dependencies.py` (`CurrentPrincipal`, `get_current_active_user`, `require_active_admin`), `backend/app/modules/products/schemas.py` (`ProductRead`, `ProductListResponse`), `backend/app/modules/purchasing/models.py` (Receipt ORM, chưa có API). **Không coi các interface bên dưới đã tồn tại trong repo.**

## 1. Quy ước module, transaction và lỗi

- Router tiếp nhận HTTP, xác thực/RBAC và parse request → service điều phối nghiệp vụ → repository đọc/ghi qua **cùng `sqlalchemy.orm.Session`**; một use case chỉ có **một transaction owner**, không commit trong Inventory/Outbox/Repo.
- `raise` domain exception chuẩn từ `app.core.exceptions` (`ConflictError(code, message, details)`, `ResourceNotFoundError`, `ForbiddenError`, `DomainValidationError`) thay vì trả `JSONResponse` bên trong service. Lỗi bất ngờ rollback và 500 đã làm sạch.
- MySQL InnoDB bảo vệ invariant; Redis không thay thế unique/row locks. Với mutation đa sản phẩm: khóa header chứng từ/đơn (nếu có) → Product theo ID tăng dần → Inventory theo ID tăng dần; kiểm tra trạng thái dưới lock, thao tác tồn và movement cùng transaction. Nếu implementation thực tế muốn thay đổi thứ tự: cần contract change + MySQL race tests.
- Không sửa ORM/migration đã merge; bổ sung Alembic từ đúng head. `idempotency_records` và `outbox_events` chưa có trong cây migration được kiểm tra 10/11.

## 2–4. BE-IDEM, BE-INVENTORY, BE-RECEIPT, BE-CHECKOUT — **FROZEN**

**Nguồn duy nhất cho bốn contract nền:** [`../contracts/S2_CORE_CONTRACTS_LOCKED.md`](BACKEND_INTERFACES.md) và [`../../contracts/python/retailops_core_ports.pyi`](../../contracts/python/retailops_core_ports.pyi). Phần cũ tại đây đã được thay bằng liên kết để tránh hai chữ ký trái nhau. **Quan trọng:** Inventory có bước `lock_for_mutation()` trả `StockLockSet` bắt buộc; Idempotency dùng `idempotency_key`, `request_identity`, `command`, không tự `commit()`.

## 5. BE-OUTBOX — Durable Event Writer, Publisher và Email Worker (owner: Hiếu)

**Chia đúng hai phần mà không chuyển ownership:** S2 có `OutboxWriter.append` + outbox migration để Approval ghi event trong transaction; S3 mới có publisher, RabbitMQ/Celery worker/retry. Nếu S1 Registration chưa ghi event bền vững thì bổ sung integration đúng event `STAFF_REGISTERED`, không tự đánh dấu tất cả email đã gửi.

```python
from typing import Literal
from datetime import datetime
EventType = Literal["STAFF_REGISTERED", "STAFF_APPROVED", "STAFF_REJECTED", "PASSWORD_RESET", "STAFF_REAPPLY_PROOF"]

class OutboxWriter:
    def append(
        self, session: Session, *, subject_user_id: int,
        event_type: EventType, payload: dict, available_at_utc: datetime,
        secret_ciphertext: bytes | None = None, secret_expires_at_utc: datetime | None = None,
    ) -> bytes:  # stored binary(16) event ID
        ...  # no commit, no publish, no SMTP
```

- DBML Outbox Lite: `id binary(16)`, `event_type`, `subject_user_id`, `payload` metadata có phiên bản và không nhạy cảm, `secret_ciphertext` là AEAD ciphertext cho one-time link, **không chứa token plaintext trong payload/log**. Không làm sai code bằng việc lưu token plaintext cho tiện.
- Publisher **một instance** polls `published_at IS NULL AND available_at <= UTC_NOW`, publish RabbitMQ với publisher confirm, rồi set `published_at`; crash ở khe giữa hai bước có thể publish lặp. Worker **một consumer tuần tự** kiểm tra event ID và outcome, idempotent về trạng thái nội bộ; retry có giới hạn, không hứa email SMTP external exactly-once. **Không tự thêm multi-publisher lease/fencing** (ngoài TD-04E-LITE đã chốt).
- Không gửi email trong transaction nghiệp vụ; broker hỏng không làm rollback hành vi Approval đã commit. Password reset link token cần cơ chế giải mã one-time ciphertext + expiry/tombstone và key management ngoài DB.

## 6. BE-AI — AI Executor và service gọi model (owners: Hiếu/Dương)

**Hiếu** sở hữu executor bảo mật, **Dương** sở hữu orchestration LLM + tool calling và gợi ý nhập hàng. Giao tiếp nội module, không cần HTTP giữa các service.

```python
from dataclasses import dataclass
from typing import Mapping, Any

@dataclass(frozen=True)
class ToolContext:
    actor_id: int
    actor_role: str  # derived from authenticated CurrentPrincipal, never model input
    request_id: str

@dataclass(frozen=True)
class ToolResult:
    tool_id: str
    data: Mapping[str, Any]
    source_period: str | None

class AIToolExecutor:
    def execute(
        self, session: Session, *, tool_id: str,
        arguments: Mapping[str, Any], context: ToolContext,
    ) -> ToolResult: ...
```

**Danh mục tool ID V1 đề xuất, cần khóa trước Dương code:** `get_sales_summary`, `get_top_products`, `get_slow_products`, `get_low_stock`. Các tool chỉ gọi Analytics/Inventory read services đã authorize; input schema có giới hạn ngày/page/size; result count và byte size bounded, timeout và max tool calls/request. Không nhận `user_id`, `is_admin`, SQL, URL, file path từ model; không được trao một connection tuỳ ý cho model. Không expose tool ABI trong API client FE: FE chỉ gọi `POST /ai/query` và hiển thị câu trả lời cùng evidence.

## 7. READ APIs: sử dụng lại service/repository, không tạo bản sao nghiệp vụ

- `products.ProductService.list_products/get_product` đang tồn tại, và `ProductRead` trong `backend/app/modules/products/schemas.py` gồm `id,category_id,sku,name,status,sale_price_vnd,quantity,stock_version,created_at,updated_at`. Na Na **mở rộng cùng endpoint `/products`** với `q/category/status`, không dựng `/product-search` cạnh tranh.
- `InventoryReadService.list/get/low_stock`, `MovementReadService.list` là interface **đề xuất**. Đây là SELECT từ `inventory` + `products` + `stock_movements`, không cần đợi `InventoryService` mutation hoàn chỉnh. Staff không nhận cost, internal reason, personal fields.
- `OrderReadService.list/get` được xây từ Order ORM + DTO đã khóa, không phải chờ Cancel mới bắt đầu. Staff được **đọc mọi Order** theo SRS; **chỉ Cancel Order của chính mình** trong thời hạn. Không áp cùng ownership filter cho GET và CANCEL.
- Analytics và Dashboard trả tổng hợp **dữ liệu đã commit**, query set-based trên MySQL, không gọi LLM để tính doanh thu. `T04A92B` revenue và `T04A947` product analytics có thể làm song song; `T04AA36` Dashboard là façade đọc, không duplicate logic tính toán.

## 8. Ai cần làm gì trước để unblock người khác

| Khi nào | Provider | Handoff đủ để consumer bắt đầu | Consumer | Bằng chứng |
|---|---|---|---|---|
| 10/11 | Hiếu | BE-IDEM, BE-OUTBOX writer + AUTH Approval HTTP | Dương, Lâm | interface doc frozen, fixture/error examples |
| 10/11 | Dương | BE-INVENTORY + lock hierarchy + fail semantics | Hiếu, Lan Anh | exact Python signature + test fake |
| 10/11 | Lan Anh | Receipt Draft/Confirm shared DTO + draft_version | Dương, Tân | OpenAPI examples + Pydantic schemas |
| 10/11 | Na Na | Product/Inventory Read DTO/filter contract | Lâm, Tân | OpenAPI schemas + sample mock |
| 11/11 | Hiếu | Checkout/Order/Cancel HTTP DTO and error envelopes | Lâm, Na Na | OpenAPI scenarios |
| 18/11 | Hiếu | AI Executor tool ABI + Outbox Lite event envelope | Dương | JSON schema + adapter stub |
| 18–19/11 | Na Na/Dương | Analytics/Product Tool input-output | Lâm, AI | response samples + data fixture |

**Mốc bàn giao là proposal; không đổi lịch task trong sheet.** Một contract được coi là “freeze” khi provider+consumer xác nhận qua PR. Nếu chưa freeze, không được yêu cầu consumer đoán rồi sau đó tự chịu lỗi tích hợp.


---

## CONSUMER RECIPES

# RetailOps — Recipes: mỗi người gọi dependency như thế nào?

**Hướng dẫn chạy cùng với** `S2_CORE_CONTRACTS_LOCKED.md`; đây là ví dụ orchestration, không phải code hiện đã có. Mọi lời gọi trong cùng một use case dùng chung `Session`, không service con tự `commit()`.

## Dương — implement `InventoryService` để Hiếu dùng

1. Tạo `backend/app/modules/inventory/{models,repository,service,schemas}.py` phù hợp codebase và ERD; không duplicate model `Inventory` trong `products/models.py` đã tồn tại.
2. Expose `InventoryService.lock_for_mutation(session, product_ids)` và bốn methods cùng signature trong `contracts/python/retailops_core_ports.pyi`.
3. Viết fake dùng được trong Checkout/Confirm tests. Dùng `StockLockSet` chứa ảnh chụp dưới lock; real service chỉ update row qua **cùng transaction**, bắt source FK đúng trước Stock Movement.
4. Contract tests: `stock_version`, `first_stocked_at`, negative quantity, no-op audit, two checkout/cancel concurrent, deadlock rollback.

## Hiếu — Checkout trong lúc Dương chưa merge Inventory

```python
# Fake cấp bởi contract để test orchestration độc lập (ví dụ minh họa):
class FakeInventoryService:
    def lock_for_mutation(self, session, *, product_ids):
        return StockLockSet(rows={12: LockedStock(12,"SKU12","Demo","ACTIVE",65000,3,5)})
    def decrease_for_checkout(self, session, *, locks, order_id, actor_id, lines):
        assert all(locks.rows[x.product_id].quantity >= x.quantity for x in lines)
        return [StockResult(12, 1, 6)]
```

Khi merge provider: không đổi API của consumer. Thay fake qua DI fixture bằng `InventoryService()` và chạy MySQL integration trên schema đã migrated. Không chấp nhận fake test thay thế race/locking/rollback.

## Lan Anh → Dương → Tân — Receipt

- **Lan Anh** viết `ReceiptDraftService`, response `ReceiptRead`, stale-version conflict, `GET/POST/PATCH` Draft và cancel; bàn giao shared DTO/Test fixture.
- **Dương** viết `ReceiptConfirmService.confirm` và gọi `idem.execute` + `inventory.lock_for_mutation` + `inventory.increase_for_receipt`. Không đổi create/update signature của Lan Anh; không sửa độc lập `router.py` đang mở PR cùng Lan Anh.
- **Tân** dùng `contracts/openapi.yaml` để mock UI; gọi `POST /purchase-receipts/{id}/confirm` với header key. Khi API real được merge: kiểm thử 409 stale, confirmed readonly, cancel draft no stock, 401/403. Không hiển thị unit_cost cho STAFF; toàn bộ Purchasing dành cho ADMIN.

## Lâm — POS Checkout/Cancel

```ts
// Minh họa caller/client integration. Một checkout intent giữ nguyên key đến khi resolved.
const intentKey = crypto.randomUUID();
const payload = {
  items: [{ product_id: 12, quantity: 2, viewed_unit_price_vnd: 65000 }],
};
await api.post("/orders/checkout", payload, {
  headers: { "Idempotency-Key": intentKey },
});
// Network timeout => retry cùng key + cùng payload (không tạo intent thứ hai).
// 409 PRICE_CHANGED => hiển thị current price; chỉ sau khi user xác nhận,
// tạo payload và key mới; không tự bán tiếp ở giá khác.
```

Giỏ POS chỉ là báo giá, không giữ tồn. Không fallback sang mock khi API real lỗi `503` hoặc backend offline. Adapter mock/real tường minh theo cấu hình, UI hiển thị lỗi an toàn và phát hiện mismatch bằng contract test.

## Na Na — Order History / Analytics

Dùng `OrderRead` trong OpenAPI, query `orders`+`order_items` đã commit, không lấy giá hiện tại của Product để hiển thị đơn lịch sử; STAFF được xem mọi order, nhưng cancel theo role/ownership. `S3` revenue/AOV/top chỉ tính `COMPLETED`, loại `CANCELLED`; canceled count thuộc ngày bán ban đầu, timezone Asia/Ho_Chi_Minh. Không tạo định nghĩa tính doanh thu thứ hai trong Dashboard và AI.

## Hiếu → Dương — Outbox + AI Sprint 3

Hiếu bàn giao `OutboxWriter.append` (S2), `AIToolExecutor.execute` và event/task schema (S3) theo `docs/shared/BE_PORTS.md`. Dương chỉ orchestration gọi typed tools; tuyệt đối không gửi SQL/url bất kỳ từ model. Với Worker, Outbox Lite **một publisher, một worker tuần tự**; broker unavailable không được làm rollback business đã commit. `outbox_events` và token reset/reapply không chứa plaintext secrets.

## Handoff là điều kiện hết blocker, không phải tin nhắn “code xong”

Provider gửi link PR/commit + location import + exact signature + OpenAPI/schema version + fake/test-fixture + lỗi đã chốt + cách chạy tests. Consumer trả lời `ACK` sau khi chạy contract tests/mock. Khi Provider API merge `develop`, consumer chuyển sang real API và ghi bằng chứng. Mọi thay đổi breaking phải thông báo owner/consumer qua PR contract trước; không sửa silently qua agent.


---

## CONTRACT TEST MATRIX S2

# RetailOps — Bốn contract CF-1.0: Test vectors và acceptance gate

**Không đánh dấu PASS khi chỉ có fake/mock hoặc copy một lệnh test chưa chạy.** Provider tự viết tests, consumer xác minh bằng fake khi chưa merge và MySQL thật khi provider merge. QA chỉ nghiệm thu với bằng chứng commit SHA/migration/test environment.

| ID | Case (Given → When) | Expected (Then) | Owner/consumer | Lớp test |
|---|---|---|---|---|
| ID-01 | 1 key, payload A checkout lặp lại | Replay nguyên 201/body, chỉ 1 Order/Movement | Hiếu / Lâm | MySQL + API |
| ID-02 | Cùng key checkout payload B khác | 409 IDEMPOTENCY_KEY_REUSED, không side effects mới | Hiếu / Lâm | MySQL |
| ID-03 | 2 concurrent requests cùng key | Chỉ 1 command; duplicate replay hoặc 409 REQUEST_IN_PROGRESS | Hiếu / Dương | MySQL race |
| ID-04 | DB fail sau khi ghi Order trước Movement | Rollback Order/Items/Stock/Movement/idempotency record | Hiếu / Dương | MySQL fault injection |
| ID-05 | Cùng raw key ở 2 user/operation | Namespace độc lập, không đọc kết quả actor khác | Hiếu / Dương | API auth + MySQL |
| INV-01 | Stock 1, hai checkout mỗi 1 | 1 thành công, 1 INSUFFICIENT_STOCK; stock >=0 | Dương / Hiếu | MySQL race |
| INV-02 | Receipt confirm đồng thời checkout | Total final = old + received - sold, movement/version mỗi mutation | Dương / Hiếu | MySQL race |
| INV-03 | Adjustment version stale | 409 STALE_STOCK_VERSION; no change | Dương / Tân | MySQL + UI |
| INV-04 | Adjustment same count | Audit row, không movement, không tăng version | Dương / QA | MySQL |
| INV-05 | STAFF xem movements | Không có unit_cost, reason nội bộ, PII | Na Na / Tân | API permission |
| PUR-01 | DRAFT lines cùng Product+same cost | Gộp quantity, integer total | Lan Anh / Tân | API + MySQL |
| PUR-02 | DRAFT lines cùng Product+different cost | 422; không tạo/sửa chứng từ | Lan Anh / Tân | API |
| PUR-03 | Hai update cùng draft_version | Một thành công, một 409 RECEIPT_VERSION_CONFLICT | Lan Anh / Tân | MySQL race |
| PUR-04 | Confirm same idem key lặp | Một tăng kho, replay 200, one movement per product | Dương / Lan Anh | MySQL race |
| PUR-05 | Confirm Supplier INACTIVE hoặc Product INACTIVE | Full rollback Receipt/Stock/Movement/Idem | Dương / Lan Anh | MySQL |
| PUR-06 | Cancel DRAFT | CANCELLED, không tăng tồn; không được confirm sau đó | Lan Anh / Tân | API + MySQL |
| SALE-01 | Viewed price khác current price sau lock | 409 PRICE_CHANGED details; không Order/Stock/Movement | Hiếu / Lâm | MySQL + UI |
| SALE-02 | Lâm click confirm new price | New payload+key mới; không tự retry old intent | Hiếu / Lâm | Browser E2E |
| SALE-03 | Timeout khi Checkout outcome chưa rõ | Retry cùng payload/key; không duplicate sale | Hiếu / Lâm | Browser + API |
| SALE-04 | STAFF cancel order người khác | 403; unchanged | Hiếu / Lâm | API |
| SALE-05 | STAFF cancel sau 15 phút hoặc ngày VN mới | Từ chối; không hoàn tồn | Hiếu / Lâm | MySQL + boundary time |
| SALE-06 | ADMIN cancel order quá 15 phút, cùng ngày VN | Cho phép; hoàn tồn một lần | Hiếu / Lâm | MySQL |
| SALE-07 | ADMIN cancel order ngày VN khác | Từ chối | Hiếu / QA | Boundary time |
| SALE-08 | Cancel cùng Order, 2 key khác | Chỉ 1 200; stock restore once, other INVALID_STATE | Hiếu / Dương | MySQL race |
| ROUTE-01 | GET /inventory/low-stock | 200 LowStockPage (không route dynamic /{product_id}) | Na Na / Tân | FastAPI integration |
| ROUTE-02 | GET /orders?status=CANCELLED với STAFF | 200 list gồm mọi Order, không lọc chỉ own | Na Na / Lâm | API auth |

## Nguyên tắc test implementation

- MySQL 8/InnoDB, **mỗi thread/request dùng `Session` riêng**, barrier để bắt đầu cùng thời điểm; không share SQLAlchemy Session giữa threads.
- Inject lỗi trong cùng transaction rồi đo lại DB state bằng session khác; test chính xác FK/unique/index, stock_version, committed outcome.
- Cleanup chỉ trên `retailops_test` user và schema được safeguard; không chạy `docker compose down -v` như lệnh test.
- Frontend mock phải tái tạo cả 409, 401, 403, pending request, timeout. Khi API real merge, switch sang real và ghi bằng chứng; không tự fallback mock.
- Các tests này là **acceptance criteria**, chưa phải kết quả PASS; không đưa số P95 mục tiêu thành benchmark đạt nếu chưa đo.
