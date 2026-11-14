# Hướng Dẫn Tích Hợp Inventory Service (`T04A653` — `BE-INVENTORY`)

Tài liệu bàn giao dành cho **Hiếu** (tích hợp POS Checkout & Cancel Order) và **Lan Anh** (tích hợp Purchase Receipt Confirm) sử dụng `InventoryService` trong `backend/app/modules/inventory/`.

---

## 1. Nguyên Tắc Transaction (Bắt Buộc)

- `InventoryService` và `InventoryMovementRepository` **KHÔNG BAO GIỜ** gọi `session.commit()`, `session.rollback()`, `session.close()`, `session.begin()` hay `session.begin_nested()`.
- **Application Service gọi (`CheckoutService`, `OrderService`, `ReceiptConfirmService`, `InventoryAdjustmentService`) là chủ sở hữu transaction duy nhất**:
  - Truyền cùng `session: sqlalchemy.orm.Session` vào `InventoryService`.
  - Commit **một lần duy nhất** ở tầng ngoài cùng khi toàn bộ nghiệp vụ thành công.
  - Gọi `session.rollback()` nếu có bất kỳ exception nào xảy ra.

---

## 2. Chữ Ký Hàm & Cách Gọi

Module `app.modules.inventory` cung cấp **2 nhóm API tương thích hoàn toàn** trên cùng một class `InventoryService`:

### 2.1. Nhóm hàm theo Contract `CF-02` (`contracts/python/retailops_core_ports.pyi`)

```python
from app.modules.inventory import (
    CountAdjustment,
    InventoryService,
    StockLine,
)

inventory_service = InventoryService()

# 1. Khóa dòng Product + Inventory theo thứ tự chuẩn (Product ID ASC -> Inventory ID ASC)
locks = inventory_service.lock_for_mutation(session, product_ids=[10, 20])

# 2. Tăng tồn khi Confirm Phiếu Nhập (PURCHASE_CONFIRM)
results = inventory_service.increase_for_receipt(
    session,
    locks=locks,
    receipt_id=receipt.id,
    actor_id=current_user_id,
    lines=[StockLine(product_id=10, quantity=5), StockLine(product_id=20, quantity=3)],
)

# 3. Giảm tồn khi POS Checkout (SALE)
results = inventory_service.decrease_for_checkout(
    session,
    locks=locks,
    order_id=order.id,
    actor_id=current_user_id,
    lines=[StockLine(product_id=10, quantity=2)],
)

# 4. Hoàn tồn khi Hủy Đơn COMPLETED (ORDER_CANCEL)
results = inventory_service.restore_for_cancel(
    session,
    locks=locks,
    order_id=order.id,
    actor_id=current_user_id,
    lines=[StockLine(product_id=10, quantity=2)],
)

# 5. Điều chỉnh tồn kho theo kiểm kê thực tế (ADJUSTMENT - counted_quantity)
adj_result = inventory_service.adjust_to_count(
    session,
    locks=locks,
    actor_id=admin_user_id,
    adjustment=CountAdjustment(
        product_id=10,
        counted_quantity=12,
        expected_stock_version=locks.rows[10].stock_version,
        reason="Kiểm kê cuối kỳ",
    ),
)
```

### 2.2. Entry Point Thống Nhất `apply_stock_change` & Các Hàm Wrapper

```python
from app.modules.inventory import (
    InventoryService,
    MovementType,
    ReferenceType,
    StockChangeItem,
)

inventory_service = InventoryService()

movements = inventory_service.apply_stock_change(
    session,
    items=[
        StockChangeItem(product_id=20, quantity=2),
        StockChangeItem(product_id=10, quantity=3),
    ],
    movement_type=MovementType.DECREASE,   # INCREASE | DECREASE | RETURN | ADJUST
    reference_type=ReferenceType.ORDER,    # RECEIPT | ORDER | ADJUSTMENT
    reference_id=order.id,
    actor_id=current_user_id,
)
# Hoặc gọi ngắn gọn qua wrapper:
# inventory_service.increase(...)
# inventory_service.decrease(...)
# inventory_service.return_stock(...)
# inventory_service.adjust(...)
```

---

## 3. Quy Ước Thứ Tự Khóa (Lock Ordering — `TD-04B`)

### Lý do
Nếu giao dịch A khóa sản phẩm `20` trước rồi đợi khóa sản phẩm `10`, trong khi giao dịch B khóa sản phẩm `10` trước rồi đợi khóa sản phẩm `20`, MySQL InnoDB sẽ xảy ra **Deadlock (`Error 1213`)**.

### Quy tắc bắt buộc
1. **Nếu có chứng từ Header đã tồn tại** (`PurchaseReceipt` khi confirm, `Order` khi cancel): Caller khóa dòng Header trước (`SELECT ... FOR UPDATE`).
2. **Khóa `Product` theo `Product.id` tăng dần (`ASC`)**.
3. **Khóa `Inventory` theo `Inventory.product_id` tăng dần (`ASC`)**.
4. `InventoryService.lock_for_mutation()` và `apply_stock_change()` **tự động gộp các dòng trùng `product_id` và sắp xếp `product_id` tăng dần** trước khi thực hiện `SELECT ... FOR UPDATE`.

### Ví dụ Đúng / Sai

```python
# ✅ ĐÚNG (Trong Checkout của Hiếu):
# Bước 1: Khóa toàn bộ product_ids một lần qua lock_for_mutation (tự động sort [10, 25, 40])
locks = inventory_service.lock_for_mutation(session, product_ids=[40, 10, 25])
# Bước 2: Kiểm tra ACTIVE + viewed_unit_price_vnd + quantity từ snapshot `locks.rows`
# Bước 3: Insert Order + OrderItems, flush() để lấy order.id
# Bước 4: Gọi decrease_for_checkout với cùng `locks` và `session`
inventory_service.decrease_for_checkout(
    session, locks=locks, order_id=order.id, actor_id=actor_id, lines=lines
)
session.commit()

# ❌ SAI:
# Không tự ý SELECT ... FOR UPDATE từng dòng Inventory rời rạc theo thứ tự giỏ hàng của client
# hoặc lưu `StockLockSet` qua biến global / dùng lại ở một Session khác.
```

---

## 4. Bảng Lỗi Nghiệp Vụ & Cách Caller Xử Lý

Tất cả exception của Inventory đều kế thừa từ `app.core.exceptions.AppException` và tự động ánh xạ ra HTTP envelope chuẩn `{code, message, details}`:

| Exception Class | HTTP | `code` | Khi nào xảy ra | Cách Caller xử lý |
|---|---|---|---|---|
| `StockItemNotFoundError` | `404` | `RESOURCE_NOT_FOUND` | `product_id` không tồn tại trong `products` hoặc `inventory` | `session.rollback()`, trả 404 |
| `InsufficientStockError` | `409` | `INSUFFICIENT_STOCK` | Số lượng trừ vượt quá tồn hiện có (`quantity_after < 0`) | `session.rollback()`, trả 409 kèm `details` |
| `StaleStockVersionError` | `409` | `STALE_STOCK_VERSION` | `expected_stock_version` không khớp `inventory.stock_version` | `session.rollback()`, yêu cầu client tải lại tồn kho mới |
| `InactiveProductStockError` | `409` | `INVALID_STATE` | Sản phẩm `INACTIVE` khi nhập hàng hoặc bán hàng | `session.rollback()`, trả 409 |
| `DuplicateMovementError` | `409` | `DUPLICATE_STOCK_MOVEMENT` | Ghi trùng biến động cho cùng `(receipt_id, product_id)` hoặc `(order_id, product_id, kind)` | `session.rollback()`, trả 409 |
| `StockConflictError` | `409` | `STOCK_CONFLICT` | Xung đột cập nhật đồng thời, dùng sai `StockLockSet`, hoặc InnoDB lock timeout/deadlock | `session.rollback()`, có thể retry transaction mới hoặc trả 409 |
| `InventoryValidationError` | `422` | `VALIDATION_ERROR` | `quantity <= 0`, `counted_quantity < 0`, `reason` rỗng, sai `reference_type` | `session.rollback()`, trả 422 |

---

## 5. Quy Tắc Idempotency & Chống Ghi Trùng

1. **Ở tầng DB (`stock_movements`):**
   - `uq_stock_movements_receipt_product (receipt_id, product_id)`: Mỗi sản phẩm trong một phiếu nhập chỉ được cộng kho **tối đa 1 lần**.
   - `uq_stock_movements_order_product_kind (order_id, product_id, kind)`: Mỗi sản phẩm trong một đơn hàng chỉ có tối đa 1 dòng `SALE` và tối đa 1 dòng `ORDER_CANCEL` (chống hoàn kho 2 lần ngay cả khi 2 request cancel gửi 2 `Idempotency-Key` khác nhau).
   - `uq_stock_movements_adjustment_product (adjustment_id, product_id)` và `uq_stock_movements_product_version_after (product_id, stock_version_after)`.
2. **Ở tầng Service:**
   - Khi gọi qua `apply_stock_change` / `increase` / `decrease` / `return_stock` (mặc định `idempotent_replay=True`): nếu retry cùng `(movement_type, reference_id, product_id, actor_id)` với cùng `quantity`, hàm trả về kết quả `StockMovementResult` đã lưu (`movement_created=False`) mà **không cộng/trừ tồn lần hai** và **không tạo movement thứ hai**. Nếu truyền khác số lượng cho cùng `reference_id`, hàm ném `DuplicateMovementError`.
   - Khi gọi qua các hàm `CF-02` (`increase_for_receipt`, `decrease_for_checkout`, `restore_for_cancel`): đặt `idempotent_replay=False` để mọi nỗ lực ghi lần 2 vào cùng chứng từ đều ném `DuplicateMovementError` (`409`), phối hợp chặt chẽ với `IdempotencyExecutor` ở tầng use case.
