"""Authenticated DEC-14 HTTP benchmark runner for isolated RetailOps test data."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import socket
import subprocess
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

SUCCESS_CLASS = "business_success"


def percentile(values: list[float], percent: int) -> float | None:
    """Return a nearest-rank percentile, or None when no successes exist."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percent / 100 * len(ordered)) - 1)
    return round(ordered[index], 3)


def classify_status(status_code: int, expected: set[int]) -> str:
    if status_code in expected:
        return SUCCESS_CLASS
    if status_code in {401, 403, 409, 429}:
        return f"http_{status_code}"
    if status_code >= 500:
        return "http_5xx"
    return "unexpected_http"


def resolve_path(document: Any, dotted_path: str) -> Any:
    current = document
    for part in dotted_path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def render(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if value.startswith("{{") and value.endswith("}}"):
            key = value[2:-2]
            if key in context:
                return context[key]
        rendered = value
        for key, replacement in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(replacement))
        return rendered
    if isinstance(value, list):
        return [render(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render(item, context) for key, item in value.items()}
    return value


def validate_run_safety(config: dict[str, Any], concurrency_levels: list[int]) -> None:
    """Reject configurations that cannot exercise or safely isolate the load."""
    scenarios = config.get("scenarios", [])
    if not scenarios:
        raise ValueError("At least one benchmark scenario is required")
    for concurrency in concurrency_levels:
        for scenario in scenarios:
            if scenario["requests"] < concurrency:
                raise ValueError(
                    f"{scenario['name']} has fewer requests than concurrency "
                    f"{concurrency}"
                )
    has_writes = any(
        scenario["request"]["method"].upper() != "GET" for scenario in scenarios
    )
    if has_writes and len(concurrency_levels) != 1:
        raise ValueError(
            "Write workloads require one concurrency level per run so each level "
            "can start from a restored fixture"
        )


@dataclass(frozen=True)
class Observation:
    latency_ms: float
    status_code: int
    classification: str
    server_ms: float | None


async def request_once(
    client: httpx.AsyncClient,
    request: dict[str, Any],
    context: dict[str, Any],
    token: str,
    *,
    timed: bool,
) -> tuple[Observation, httpx.Response]:
    headers = render(request.get("headers", {}), context)
    headers["Authorization"] = f"Bearer {token}"
    started = time.perf_counter()
    kwargs: dict[str, Any] = {"headers": headers}
    if "body" in request:
        kwargs["json"] = render(request["body"], context)
    response = await client.request(
        request["method"], render(request["path"], context), **kwargs
    )
    latency_ms = (time.perf_counter() - started) * 1_000 if timed else 0.0
    server_value = response.headers.get("Server-Timing-Ms")
    expected = set(request.get("expected_statuses", [200]))
    return (
        Observation(
            latency_ms=round(latency_ms, 3),
            status_code=response.status_code,
            classification=classify_status(response.status_code, expected),
            server_ms=float(server_value) if server_value else None,
        ),
        response,
    )


async def run_scenario(
    client: httpx.AsyncClient,
    scenario: dict[str, Any],
    concurrency: int,
) -> dict[str, Any]:
    token_env = scenario["token_env"]
    token = os.environ.get(token_env, "")
    if not token:
        raise ValueError(f"Missing bearer token environment variable: {token_env}")
    request = scenario["request"]
    setup = scenario.get("setup")
    if (
        request["method"].upper() != "GET"
        and not setup
        and not scenario.get("write_safe")
    ):
        raise ValueError(f"Write scenario {scenario['name']} must declare write_safe")

    for warmup_index in range(scenario.get("warmup_requests", 0)):
        if setup:
            break
        context = {"request_id": f"warmup-{warmup_index}-{uuid.uuid4().hex}"}
        observation, _ = await request_once(
            client, request, context, token, timed=False
        )
        if observation.classification != SUCCESS_CLASS:
            raise RuntimeError(
                f"Warm-up failed for {scenario['name']}: {observation.status_code}"
            )

    semaphore = asyncio.Semaphore(concurrency)

    async def prepare(sequence: int) -> tuple[dict[str, Any], Observation | None]:
        async with semaphore:
            context: dict[str, Any] = {
                "sequence": sequence,
                "request_id": f"bench-{sequence}-{uuid.uuid4().hex}",
            }
            if setup:
                setup_observation, setup_response = await request_once(
                    client, setup["request"], context, token, timed=False
                )
                if setup_observation.classification != SUCCESS_CLASS:
                    return context, Observation(
                        0, setup_observation.status_code, "setup_failed", None
                    )
                payload = setup_response.json()
                for key, path in setup.get("extract", {}).items():
                    context[key] = resolve_path(payload, path)
            return context, None

    prepared = await asyncio.gather(
        *(prepare(index) for index in range(scenario["requests"]))
    )

    async def execute(context: dict[str, Any]) -> Observation:
        async with semaphore:
            observation, _ = await request_once(
                client, request, context, token, timed=True
            )
            return observation

    runnable = [context for context, error in prepared if error is None]
    setup_errors = [error for _, error in prepared if error is not None]
    started = time.perf_counter()
    measured = await asyncio.gather(*(execute(context) for context in runnable))
    elapsed = time.perf_counter() - started
    observations = [*setup_errors, *measured]
    successful = [
        item.latency_ms for item in observations if item.classification == SUCCESS_CLASS
    ]
    server_samples = [
        item.server_ms for item in observations if item.server_ms is not None
    ]
    distribution = Counter(item.classification for item in observations)
    p95 = percentile(successful, 95)
    target_ms = scenario["target_p95_ms"]
    return {
        "name": scenario["name"],
        "group": scenario["group"],
        "concurrency": concurrency,
        "requests": len(observations),
        "successful_requests": len(successful),
        "status_distribution": dict(sorted(distribution.items())),
        "p50_ms": percentile(successful, 50),
        "p95_ms": p95,
        "p99_ms": percentile(successful, 99),
        "server_p95_ms": percentile(server_samples, 95),
        "throughput_rps": round(len(measured) / elapsed, 3) if elapsed else None,
        "error_rate": round(1 - len(successful) / len(observations), 6),
        "target_p95_ms": target_ms,
        "verdict": "PASS"
        if p95 is not None and p95 <= target_ms and len(successful) == len(observations)
        else "FAIL",
    }


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


async def run(args: argparse.Namespace) -> dict[str, Any]:
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    validate_run_safety(config, args.concurrency)
    parsed = urlsplit(args.base_url)
    is_loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if not args.isolated_test_data:
        raise ValueError("Refusing writes without --isolated-test-data")
    if not is_loopback and not args.allow_remote_test_target:
        raise ValueError("Remote targets require --allow-remote-test-target")
    timeout = httpx.Timeout(config.get("timeout_seconds", 30.0))
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), timeout=timeout
    ) as client:
        results = []
        for concurrency in args.concurrency:
            for scenario in config["scenarios"]:
                results.append(await run_scenario(client, scenario, concurrency))
    return {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "commit_sha": git_sha(),
            "base_url": args.base_url,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "dataset": config["dataset"],
            "isolated_test_data_acknowledged": True,
        },
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--concurrency", type=int, nargs="+", choices=range(1, 21), default=[10, 20]
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--isolated-test-data", action="store_true")
    parser.add_argument("--allow-remote-test-target", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run(args))
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
