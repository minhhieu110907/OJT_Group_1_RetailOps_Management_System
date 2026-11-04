"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure a RetailOps FastAPI application."""
    settings = get_settings()
    application = FastAPI(title=settings.app_name)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
