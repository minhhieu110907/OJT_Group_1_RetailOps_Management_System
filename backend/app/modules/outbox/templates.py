"""Fixed, non-secret email templates for approval lifecycle events."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.modules.outbox.models import OutboxEvent


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str


class EmailTemplateRegistry:
    _SUBJECTS = {
        "STAFF_REGISTERED": "RetailOps đã nhận yêu cầu đăng ký",
        "STAFF_APPROVED": "Tài khoản RetailOps đã được phê duyệt",
        "STAFF_REJECTED": "Kết quả yêu cầu đăng ký RetailOps",
        "STAFF_LOCKED": "Tài khoản RetailOps của bạn đã bị khóa",
        "STAFF_UNLOCKED": "Tài khoản RetailOps của bạn đã được mở khóa",
        "PURCHASE_DRAFT_CREATED": "RetailOps đã tạo phiếu nhập nháp",
        "PURCHASE_RECEIPT_CONFIRMED": "RetailOps đã xác nhận phiếu nhập kho",
        "LOW_STOCK_ALERT": "RetailOps cảnh báo sản phẩm sắp hết hàng",
    }
    _BODIES = {
        "STAFF_REGISTERED": (
            "RetailOps đã nhận yêu cầu đăng ký của bạn. "
            "Vui lòng chờ quản trị viên xem xét."
        ),
        "STAFF_APPROVED": (
            "Yêu cầu đăng ký của bạn đã được phê duyệt. "
            "Bạn có thể đăng nhập vào RetailOps."
        ),
        "STAFF_REJECTED": (
            "Yêu cầu đăng ký của bạn chưa được phê duyệt. "
            "Vui lòng liên hệ quản trị viên nếu cần hỗ trợ."
        ),
        "STAFF_LOCKED": (
            "Tài khoản nhân viên RetailOps của bạn đã bị quản trị viên tạm khóa. "
            "Vui lòng liên hệ quản trị viên nếu cần hỗ trợ."
        ),
        "STAFF_UNLOCKED": (
            "Tài khoản nhân viên RetailOps của bạn đã được quản trị viên mở khóa. "
            "Bạn có thể đăng nhập lại vào hệ thống."
        ),
    }

    def render(self, event: OutboxEvent) -> RenderedEmail:
        if event.event_type == "PURCHASE_DRAFT_CREATED":
            receipt_id = (event.payload or {}).get("receipt_id")
            if type(receipt_id) is not int or receipt_id <= 0:
                raise ValueError("Invalid purchase draft payload")
            return RenderedEmail(
                subject=self._SUBJECTS["PURCHASE_DRAFT_CREATED"],
                text=(
                    f"Phiếu nhập nháp #{receipt_id} đã được tạo (trạng thái DRAFT, "
                    "chưa cộng tồn kho).\n"
                    "Vui lòng vào mục Quản lý nhập hàng trên RetailOps để kiểm tra "
                    "đơn giá và xác nhận phiếu khi hàng về kho."
                ),
            )
        if event.event_type == "PURCHASE_RECEIPT_CONFIRMED":
            receipt_id = (event.payload or {}).get("receipt_id")
            if type(receipt_id) is not int or receipt_id <= 0:
                raise ValueError("Invalid purchase confirmed payload")
            return self.render_purchase_confirmed(
                receipt_id=receipt_id,
                supplier_name=None,
                total_vnd=None,
                items=(),
            )
        if event.event_type == "LOW_STOCK_ALERT":
            low_stock_count = (event.payload or {}).get("low_stock_count")
            if type(low_stock_count) is not int or low_stock_count <= 0:
                raise ValueError("Invalid low stock alert payload")
            return self.render_low_stock_alert(
                low_stock_count=low_stock_count,
                items=(),
            )
        try:
            return RenderedEmail(
                subject=self._SUBJECTS[event.event_type],
                text=self._BODIES[event.event_type],
            )
        except KeyError as error:
            raise ValueError("Unsupported email event type") from error

    def render_password_reset(self, *, reset_link: str) -> RenderedEmail:
        """Render password reset email containing the one-time reset link."""
        return RenderedEmail(
            subject="Đặt lại mật khẩu tài khoản RetailOps",
            text=(
                "Bạn đã yêu cầu đặt lại mật khẩu tài khoản RetailOps.\n"
                "Vui lòng truy cập liên kết một lần sau để đặt mật khẩu mới:\n"
                f"{reset_link}\n"
                "Nếu bạn không thực hiện yêu cầu này, hãy bỏ qua email này."
            ),
        )

    def render_purchase_confirmed(
        self,
        *,
        receipt_id: int,
        supplier_name: str | None,
        total_vnd: int | None,
        items: Sequence[Mapping[str, object]],
    ) -> RenderedEmail:
        """Render confirmation email with confirmed purchase receipt details."""
        lines = [
            f"Phiếu nhập kho #{receipt_id} đã được XÁC NHẬN (CONFIRMED) "
            "và đã cộng tồn kho vào hệ thống RetailOps.",
        ]
        if supplier_name:
            lines.append(f"Nhà cung cấp: {supplier_name}")
        if items:
            lines.append("\nDanh sách sản phẩm đã nhập:")
            for idx, item in enumerate(items, start=1):
                sku = item.get("sku", "")
                name = item.get("name", "")
                qty = int(item.get("quantity") or 0)
                unit_cost = int(item.get("unit_cost_vnd") or 0)
                line_total = int(item.get("line_total_vnd") or 0)
                lines.append(
                    f"  {idx}. [{sku}] {name} — SL: {qty:,} x "
                    f"{unit_cost:,} VNĐ = {line_total:,} VNĐ"
                )
        if total_vnd is not None:
            lines.append(f"\nTổng giá trị phiếu nhập: {int(total_vnd):,} VNĐ")
        lines.append(
            "\nBạn có thể kiểm tra chi tiết tại mục Quản lý nhập hàng trên RetailOps."
        )
        return RenderedEmail(
            subject=f"RetailOps đã xác nhận phiếu nhập kho #{receipt_id}",
            text="\n".join(lines),
        )

    def render_low_stock_alert(
        self,
        *,
        low_stock_count: int,
        items: Sequence[Mapping[str, object]],
        threshold: int = 5,
    ) -> RenderedEmail:
        """Render low-stock alert email summarizing products below threshold."""
        lines = [
            f"Cảnh báo tồn kho RetailOps: Hiện có {low_stock_count} sản phẩm "
            f"đang ở mức tồn kho thấp (<= {threshold} sản phẩm).",
        ]
        if items:
            lines.append("\nDanh sách sản phẩm cần chú ý nhập thêm:")
            for idx, item in enumerate(items, start=1):
                sku = item.get("sku", "")
                name = item.get("name", "")
                qty = int(item.get("quantity") or 0)
                status_note = "Hết hàng" if qty == 0 else f"Còn {qty}"
                lines.append(f"  {idx}. [{sku}] {name} — {status_note}")
        lines.append(
            "\nVui lòng truy cập Trợ lý AI / Bảng gợi ý nhập hàng thông minh "
            "trên RetailOps để tạo phiếu nhập nháp nhanh."
        )
        return RenderedEmail(
            subject=(f"RetailOps cảnh báo {low_stock_count} sản phẩm sắp hết hàng"),
            text="\n".join(lines),
        )
