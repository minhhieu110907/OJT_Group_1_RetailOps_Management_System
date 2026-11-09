"""Atomic Redis fixed-window rate limiting."""

from __future__ import annotations

import hashlib
import time
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
    """Apply one atomic INCR/EXPIRE/TTL operation per request."""

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
        now: float | None = None,
    ) -> RateLimitResult:
        current_time = time.time() if now is None else now
        window = int(current_time) // window_seconds
        remaining = window_seconds - (int(current_time) % window_seconds)
        identity_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        key = f"{self.namespace}:{policy}:{identity_digest}:{window}"
        response = await self.redis.eval(FIXED_WINDOW_SCRIPT, 1, key, remaining)
        count, ttl = int(response[0]), max(1, int(response[1]))
        return RateLimitResult(
            allowed=count <= limit,
            count=count,
            retry_after=ttl,
        )
