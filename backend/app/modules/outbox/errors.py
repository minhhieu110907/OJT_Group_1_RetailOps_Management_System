"""Sanitized Outbox delivery errors used at adapter boundaries."""


class OutboxError(Exception):
    code = "OUTBOX_ERROR"


class TransientEmailError(OutboxError):
    code = "SMTP_TRANSIENT"


class PermanentEmailError(OutboxError):
    code = "SMTP_PERMANENT"


class UnknownEventError(OutboxError):
    code = "OUTBOX_EVENT_MISSING"


class DatabaseUnavailableError(OutboxError):
    code = "OUTBOX_DATABASE_UNAVAILABLE"


class BrokerPublishError(OutboxError):
    code = "BROKER_PUBLISH_FAILED"
