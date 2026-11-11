import math

import pytest

from app.core.exceptions import DomainValidationError
from app.modules.idempotency.validation import (
    canonical_json,
    key_digest,
    request_digest,
    serialize_response_body,
    validate_idempotency_key,
)


@pytest.mark.parametrize(
    "key",
    ["short", "a" * 129, "a" * 15 + " ", "é" * 16, "a" * 15 + "/"],
)
def test_rejects_invalid_keys_without_echoing_them(key: str) -> None:
    with pytest.raises(DomainValidationError) as caught:
        validate_idempotency_key(key)
    assert key not in str(caught.value)


def test_accepts_openapi_key_alphabet_and_bounds() -> None:
    assert validate_idempotency_key("A0._:-abcdefghij") == "A0._:-abcdefghij"
    assert validate_idempotency_key("a" * 128) == "a" * 128


def test_canonical_json_is_deterministic() -> None:
    left = {"operation": "CHECKOUT", "body": {"b": [2, 1], "a": True}}
    right = {"body": {"a": True, "b": [2, 1]}, "operation": "CHECKOUT"}
    assert canonical_json(left) == canonical_json(right)
    assert request_digest(left) == request_digest(right)


@pytest.mark.parametrize(
    "payload",
    [
        {"value": 1.5},
        {"value": math.nan},
        {"value": math.inf},
        {1: "non-string-key"},
        {"value": object()},
        {"body": {"password": "forbidden"}},
        {"token": "forbidden"},
        {"access_token": "forbidden"},
        {"client-secret": "forbidden"},
    ],
)
def test_request_identity_rejects_unsafe_values(payload: dict[object, object]) -> None:
    with pytest.raises(DomainValidationError):
        canonical_json(payload)  # type: ignore[arg-type]


def test_hmac_digest_is_keyed_and_stable() -> None:
    key = "0123456789abcdef"
    assert key_digest(key, b"a" * 32) == key_digest(key, b"a" * 32)
    assert key_digest(key, b"a" * 32) != key_digest(key, b"b" * 32)


@pytest.mark.parametrize("value", [{"x": object()}, {"x": 1.2}])
def test_response_rejects_non_json_safe_values(value: object) -> None:
    with pytest.raises(DomainValidationError):
        serialize_response_body(value)


def test_response_size_is_bounded() -> None:
    with pytest.raises(DomainValidationError, match="size limit"):
        serialize_response_body({"value": "x" * 100}, max_bytes=32)
