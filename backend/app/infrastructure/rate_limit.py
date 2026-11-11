"""Atomic Redis fixed-window rate limiting."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from redis.asyncio import Redis

FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    retry_after: int


class RedisFixedWindowRateLimiter:
    """Apply one atomic INCR/EXPIRE/TTL operation per request.

    The window is anchored at the first request of each identity bucket (the
    key is created with a TTL of ``window_seconds`` and is never split by wall
    clock boundaries). An epoch-aligned window would let a client spread a
    burst across a boundary and receive up to ``2 * limit`` requests within a
    few seconds, while also splitting one client's requests over two keys.
    """

    def __init__(self, redis: Redis, namespace: str) -> None:
        self.redis = redis
        self.namespace = namespace

    async def check(
        self,
        *,
        policy: str,
        identity: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        identity_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        key = f"{self.namespace}:{policy}:{identity_digest}"
        response = await self.redis.eval(FIXED_WINDOW_SCRIPT, 1, key, window_seconds)
        count, ttl = int(response[0]), max(1, int(response[1]))
        return RateLimitResult(
            allowed=count <= limit,
            count=count,
            retry_after=ttl,
        )
