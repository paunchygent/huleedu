"""BFF Teacher Service - Static file serving and API composition for Vue 3 frontend.

Serves pre-built frontend assets and provides screen-specific API endpoints
that aggregate data from backend services.
"""

from __future__ import annotations

from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from huleedu_service_libs.error_handling.fastapi import (
    register_error_handlers as register_fastapi_error_handlers,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.bff_teacher_service.api.health_routes import router as health_router
from services.bff_teacher_service.api.spa_routes import router as spa_router
from services.bff_teacher_service.api.v1 import router as teacher_router_v1
from services.bff_teacher_service.config import settings
from services.bff_teacher_service.di import BFFTeacherProvider, RequestContextProvider
from services.bff_teacher_service.middleware import CorrelationIDMiddleware

logger = create_service_logger("bff_teacher_service")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.SERVICE_NAME,
        version="0.1.0",
        description="BFF Teacher Service - Serves Vue 3 frontend static assets",
        docs_url="/docs" if settings.is_development() else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_development() else None,
    )

    # Register error handlers
    register_fastapi_error_handlers(app)

    # Add Correlation ID Middleware
    app.add_middleware(CorrelationIDMiddleware)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Include health routes (healthz, favicon)
    app.include_router(health_router)

    # Mount static assets directory (CSS, JS, images)
    # Only mount if directory exists to avoid startup errors
    assets_dir = settings.STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="assets",
        )
        logger.info(f"Mounted static assets from {assets_dir}")
    else:
        logger.warning(f"Assets directory not found: {assets_dir}")

    # Include API routes BEFORE SPA fallback
    # Routes: /bff/v1/teacher/dashboard, etc.
    app.include_router(teacher_router_v1, prefix="/bff/v1/teacher", tags=["Teacher API"])

    # Setup Dishka DI container
    container = make_async_container(
        BFFTeacherProvider(),
        RequestContextProvider(),
        FastapiProvider(),
    )
    setup_dishka(container, app)
    app.state.di_container = container

    # SPA fallback - serve index.html for all unmatched routes
    # This must be registered AFTER API routes and static mounts
    app.include_router(spa_router)

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.bff_teacher_service.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development(),
        log_level=settings.LOG_LEVEL.lower(),
    )
