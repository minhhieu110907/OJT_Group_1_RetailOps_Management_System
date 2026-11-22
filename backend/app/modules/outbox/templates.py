"""Fixed, non-secret email templates for approval lifecycle events."""

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
        "PURCHASE_DRAFT_CREATED": "RetailOps đã tạo phiếu nhập nháp",
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
