import json

import pytest

from performance.benchmark import (
    classify_status,
    percentile,
    render,
    resolve_path,
    validate_run_safety,
)


def test_percentile_uses_nearest_rank() -> None:
    samples = [float(value) for value in range(1, 101)]
    assert percentile(samples, 50) == 50.0
    assert percentile(samples, 95) == 95.0
    assert percentile(samples, 99) == 99.0
    assert percentile([], 95) is None


def test_only_expected_status_is_business_success() -> None:
    assert classify_status(201, {201}) == "business_success"
    assert classify_status(401, {201}) == "http_401"
    assert classify_status(403, {201}) == "http_403"
    assert classify_status(409, {201}) == "http_409"
    assert classify_status(429, {201}) == "http_429"
    assert classify_status(503, {201}) == "http_5xx"


def test_render_and_setup_extraction() -> None:
    payload = {"receipt": {"id": 9}, "items": [{"version": 3}]}
    context = {
        "receipt_id": resolve_path(payload, "receipt.id"),
        "version": resolve_path(payload, "items.0.version"),
    }
    assert render("/receipts/{{receipt_id}}", context) == "/receipts/9"
    assert render({"expected": "{{version}}"}, context) == {"expected": 3}


def test_safety_requires_real_concurrency_and_fresh_fixture_per_write_run() -> None:
    config = {
        "scenarios": [
            {
                "name": "checkout",
                "requests": 20,
                "request": {"method": "POST"},
            }
        ]
    }
    validate_run_safety(config, [10])
    validate_run_safety(config, [20])
    with pytest.raises(ValueError, match="one concurrency level"):
        validate_run_safety(config, [10, 20])
    with pytest.raises(ValueError, match="fewer requests"):
        validate_run_safety(config, [20, 21])


def test_windows_utf8_bom_configuration_is_accepted(tmp_path) -> None:
    config_path = tmp_path / "workload.json"
    config_path.write_text('{"scenarios": []}', encoding="utf-8-sig")
    assert json.loads(config_path.read_text(encoding="utf-8-sig")) == {"scenarios": []}
