"""Process-wide Redis client construction and cleanup."""

from redis.asyncio import Redis

from app.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    """Create a bounded lazy connection pool without logging its secret URL."""
    return Redis.from_url(
        settings.redis_url.get_secret_value(),
        max_connections=settings.redis_pool_size,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        retry_on_timeout=False,
        decode_responses=False,
    )
