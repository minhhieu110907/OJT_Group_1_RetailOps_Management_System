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
        try:
            return RenderedEmail(
                subject=self._SUBJECTS[event.event_type],
                text=self._BODIES[event.event_type],
            )
        except KeyError as error:
            raise ValueError("Unsupported email event type") from error
