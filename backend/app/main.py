"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.infrastructure.redis import create_redis_client


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a RetailOps FastAPI application."""
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        redis = create_redis_client(resolved_settings)
        application.state.rate_limiter = RedisFixedWindowRateLimiter(
            redis, resolved_settings.rate_limit_namespace
        )
        try:
            yield
        finally:
            await redis.aclose()

    application = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    register_exception_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_allowlist,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-CSRF-Token"],
    )
    application.include_router(api_router, prefix=resolved_settings.api_v1_prefix)
    return application
