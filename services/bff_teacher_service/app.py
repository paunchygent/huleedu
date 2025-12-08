"""BFF Teacher Service - Static file serving and API composition for Vue 3 frontend.

Serves pre-built frontend assets and provides screen-specific API endpoints
that aggregate data from backend services.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from huleedu_service_libs.error_handling.fastapi import (
    register_error_handlers as register_fastapi_error_handlers,
)
from huleedu_service_libs.logging_utils import create_service_logger
from starlette.middleware.base import BaseHTTPMiddleware

from services.bff_teacher_service.api.v1 import router as teacher_router_v1
from services.bff_teacher_service.config import settings

logger = create_service_logger("bff_teacher_service")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure every request has a correlation ID."""

    async def dispatch(  # type: ignore[override, no-untyped-def]
        self, request: Request, call_next
    ):
        """Extract or generate correlation ID and store in request state."""
        x_correlation_id = request.headers.get("X-Correlation-ID")
        if x_correlation_id:
            try:
                correlation_id = UUID(x_correlation_id)
            except ValueError:
                correlation_id = uuid4()
        else:
            correlation_id = uuid4()

        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        return response


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

    # Health check endpoint following Rule 072 format
    @app.get("/healthz", tags=["Health"])
    async def health_check() -> dict[str, str | dict]:
        """Health check endpoint following Rule 072 format."""
        static_dir_exists = settings.STATIC_DIR.exists()
        index_exists = (settings.STATIC_DIR / "index.html").exists()
        assets_dir_exists = (settings.STATIC_DIR / "assets").exists()

        checks = {
            "static_dir_exists": static_dir_exists,
            "index_exists": index_exists,
            "assets_dir_exists": assets_dir_exists,
        }

        # Service is healthy if frontend is built, degraded if missing
        all_checks_pass = all(checks.values())
        overall_status = "healthy" if all_checks_pass else "degraded"

        return {
            "service": "bff_teacher_service",
            "status": overall_status,
            "message": f"BFF Teacher Service is {overall_status}",
            "version": "0.1.0",
            "checks": checks,
            "dependencies": {
                "frontend_build": {
                    "status": "available" if index_exists else "missing",
                    "note": "Run 'pdm run fe-build' to build frontend"
                    if not index_exists
                    else "Frontend assets ready",
                }
            },
        }

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

    # Serve favicon directly
    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse | JSONResponse:
        """Serve favicon."""
        favicon_path = settings.STATIC_DIR / "favicon.svg"
        if favicon_path.exists():
            return FileResponse(favicon_path, media_type="image/svg+xml")
        return JSONResponse(status_code=404, content={"detail": "Favicon not found"})

    # Include API routes BEFORE SPA fallback
    # Routes: /bff/v1/teacher/dashboard, etc.
    app.include_router(teacher_router_v1, prefix="/bff/v1/teacher", tags=["Teacher API"])

    # SPA fallback - serve index.html for all unmatched routes
    # This must be registered AFTER API routes and static mounts
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse | JSONResponse:  # noqa: ARG001
        """Serve SPA index.html for client-side routing."""
        index_path = settings.STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Frontend not built. Run: pdm run fe-build",
                "static_dir": str(settings.STATIC_DIR),
            },
        )

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
