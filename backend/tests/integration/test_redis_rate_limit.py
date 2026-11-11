"""Integration evidence for the atomic fixed-window Redis implementation."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter

pytestmark = [pytest.mark.integration, pytest.mark.redis_integration]


@pytest.fixture
async def redis_client() -> Redis:
    url = os.getenv("RETAILOPS_TEST_REDIS_URL")
    if not url:
        pytest.skip("RETAILOPS_TEST_REDIS_URL is required")
    client = Redis.from_url(
        url,
        max_connections=8,
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=False,
    )
    await client.ping()
    yield client
    await client.aclose()


@pytest.mark.anyio
async def test_atomic_concurrent_increment_and_independent_buckets(
    redis_client: Redis,
) -> None:
    namespace = f"retailops:test:{uuid4().hex}"
    limiter = RedisFixedWindowRateLimiter(redis_client, namespace)
    common = {
        "policy": "registration",
        "identity": "203.0.113.10",
        "limit": 5,
        "window_seconds": 5,
    }
    results = await asyncio.gather(*(limiter.check(**common) for _ in range(20)))
    other = await limiter.check(
        policy="registration",
        identity="203.0.113.11",
        limit=5,
        window_seconds=5,
    )

    assert sorted(result.count for result in results) == list(range(1, 21))
    assert sum(result.allowed for result in results) == 5
    assert other.count == 1
    assert other.allowed is True
    await redis_client.delete(
        *[key async for key in redis_client.scan_iter(f"{namespace}:*")]
    )


@pytest.mark.anyio
async def test_sequential_burst_shares_single_anchored_bucket_with_full_ttl(
    redis_client: Redis,
) -> None:
    namespace = f"retailops:test:{uuid4().hex}"
    limiter = RedisFixedWindowRateLimiter(redis_client, namespace)
    try:
        results = [
            await limiter.check(
                policy="registration",
                identity="198.51.100.30",
                limit=5,
                window_seconds=60,
            )
            for _ in range(6)
        ]
        keys = [key async for key in redis_client.scan_iter(f"{namespace}:*")]

        assert [result.allowed for result in results] == [True] * 5 + [False]
        assert len(keys) == 1
        assert int(await redis_client.get(keys[0])) == 6
        assert 55 <= await redis_client.ttl(keys[0]) <= 60
        assert 55 <= results[-1].retry_after <= 60
    finally:
        keys = [key async for key in redis_client.scan_iter(f"{namespace}:*")]
        if keys:
            await redis_client.delete(*keys)


@pytest.mark.anyio
async def test_ttl_expiration_starts_a_fresh_counter(redis_client: Redis) -> None:
    limiter = RedisFixedWindowRateLimiter(redis_client, f"retailops:test:{uuid4().hex}")
    first = await limiter.check(
        policy="registration",
        identity="198.51.100.20",
        limit=1,
        window_seconds=1,
    )
    await asyncio.sleep(1.1)
    second = await limiter.check(
        policy="registration",
        identity="198.51.100.20",
        limit=1,
        window_seconds=1,
    )

    assert first.count == 1
    assert second.count == 1
