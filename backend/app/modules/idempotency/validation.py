"""Strict validation and canonicalization for idempotency identities/outcomes."""

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

from app.core.exceptions import DomainValidationError

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{16,128}$", re.ASCII)
SENSITIVE_NAMES = frozenset(
    {"authorization", "credential", "credentials", "password", "secret", "token"}
)
DEFAULT_MAX_RESPONSE_BYTES = 65_536


def validate_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or KEY_PATTERN.fullmatch(value) is None:
        raise DomainValidationError(
            "Idempotency-Key must contain 16-128 allowed ASCII characters."
        )
    return value


def _json_safe(value: object, *, reject_sensitive_names: bool) -> object:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise DomainValidationError("Floating-point JSON values are not supported.")
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DomainValidationError("JSON object keys must be strings.")
            name_parts = set(re.split(r"[^a-z0-9]+", key.casefold()))
            if reject_sensitive_names and name_parts & SENSITIVE_NAMES:
                raise DomainValidationError(
                    "Request identity contains a forbidden sensitive field."
                )
            normalized[key] = _json_safe(
                item, reject_sensitive_names=reject_sensitive_names
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item, reject_sensitive_names=reject_sensitive_names)
            for item in value
        ]
    raise DomainValidationError("Value is not JSON-safe.")


def canonical_json(value: Mapping[str, object]) -> bytes:
    if not isinstance(value, Mapping):
        raise DomainValidationError("Request identity must be an object.")
    normalized = _json_safe(value, reject_sensitive_names=True)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def request_digest(value: Mapping[str, object]) -> bytes:
    return hashlib.sha256(canonical_json(value)).digest()


def key_digest(key: str, secret: bytes) -> bytes:
    validate_idempotency_key(key)
    if len(secret) < 32:
        raise RuntimeError("Idempotency HMAC secret must contain at least 32 bytes")
    return hmac.digest(secret, key.encode("ascii"), "sha256")


def serialize_response_body(
    value: Any, *, max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
) -> object:
    normalized = _json_safe(value, reject_sensitive_names=False)
    encoded = json.dumps(
        normalized, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise DomainValidationError("Response body exceeds the idempotency size limit.")
    return normalized
