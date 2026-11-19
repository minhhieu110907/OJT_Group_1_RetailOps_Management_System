"""Atomic Redis per-user and global concurrency guard for AI requests."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.exceptions import DependencyUnavailableError, RateLimitedError

logger = logging.getLogger(__name__)

_ACQUIRE_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', tonumber(ARGV[4]))
local acquired = redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', tonumber(ARGV[2]))
if not acquired then
  return 0
end
local active = redis.call('ZCARD', KEYS[2])
if active >= tonumber(ARGV[3]) then
  redis.call('DEL', KEYS[1])
  return -1
end
redis.call('ZADD', KEYS[2], tonumber(ARGV[5]), ARGV[1])
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[2]) + 5)
return 1
"""

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('DEL', KEYS[1])
end
redis.call('ZREM', KEYS[2], ARGV[1])
return 1
"""


@dataclass(frozen=True)
class AIConcurrencyLease:
    user_id: int
    token: str


class RedisAIConcurrencyGuard:
    """Enforces 1 in-flight AI request per user and a global concurrency cap."""

    def __init__(self, redis: Redis, namespace: str) -> None:
        self.redis = redis
        self.namespace = namespace

    def _user_key(self, user_id: int) -> str:
        return f"{self.namespace}:ai-inflight:user:{user_id}"

    def _global_key(self) -> str:
        return f"{self.namespace}:ai-inflight:global"

    async def acquire(
        self,
        *,
        user_id: int,
        max_concurrent: int,
        ttl_seconds: int,
        now: float | None = None,
    ) -> AIConcurrencyLease:
        current = time.time() if now is None else now
        token = uuid4().hex
        try:
            result = await self.redis.eval(
                _ACQUIRE_LUA,
                2,
                self._user_key(user_id),
                self._global_key(),
                token,
                int(ttl_seconds),
                int(max_concurrent),
                current,
                current + int(ttl_seconds),
            )
        except (RedisError, OSError, TimeoutError) as error:
            raise DependencyUnavailableError() from error

        status_code = int(result)
        if status_code == 0:
            raise RateLimitedError(retry_after=5)
        if status_code == -1:
            raise RateLimitedError(retry_after=5)
        return AIConcurrencyLease(user_id=user_id, token=token)

    async def release(self, lease: AIConcurrencyLease) -> None:
        try:
            await self.redis.eval(
                _RELEASE_LUA,
                2,
                self._user_key(lease.user_id),
                self._global_key(),
                lease.token,
            )
        except (RedisError, OSError, TimeoutError) as error:
            logger.warning(
                "Failed to release AI concurrency lease early: %s",
                type(error).__name__,
            )
