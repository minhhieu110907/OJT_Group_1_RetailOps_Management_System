"""Testable SMTP transport with bounded network operations."""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings
from app.modules.outbox.errors import PermanentEmailError, TransientEmailError
from app.modules.outbox.templates import RenderedEmail


class EmailTransport(Protocol):
    def send(self, *, recipient: str, email: RenderedEmail) -> None: ...


class SmtpEmailTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, recipient: str, email: RenderedEmail) -> None:
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_address
        message["To"] = recipient
        message["Subject"] = email.subject
        message.set_content(email.text)
        try:
            with smtplib.SMTP(
                self.settings.require_smtp_host(),
                self.settings.smtp_port,
                timeout=self.settings.smtp_timeout_seconds,
            ) as client:
                client.ehlo()
                if self.settings.smtp_starttls:
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                if self.settings.smtp_username:
                    if self.settings.smtp_password is None:
                        raise PermanentEmailError("SMTP password is missing")
                    client.login(
                        self.settings.smtp_username,
                        self.settings.smtp_password.get_secret_value(),
                    )
                client.send_message(message)
        except smtplib.SMTPRecipientsRefused as error:
            raise PermanentEmailError("SMTP recipient was refused") from error
        except smtplib.SMTPAuthenticationError as error:
            raise PermanentEmailError("SMTP authentication failed") from error
        except smtplib.SMTPResponseException as error:
            if 400 <= error.smtp_code < 500:
                raise TransientEmailError("SMTP transient response") from error
            raise PermanentEmailError("SMTP permanent response") from error
        except (
            TimeoutError,
            ConnectionError,
            OSError,
            smtplib.SMTPServerDisconnected,
        ) as error:
            raise TransientEmailError("SMTP connection failed") from error
