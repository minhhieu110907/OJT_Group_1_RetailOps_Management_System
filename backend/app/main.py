"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a RetailOps FastAPI application."""
    resolved_settings = settings or get_settings()
    application = FastAPI(title=resolved_settings.app_name)
    application.include_router(api_router, prefix=resolved_settings.api_v1_prefix)
    return application
