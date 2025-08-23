from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from huleedu_service_libs.error_handling.fastapi import (
    register_error_handlers as register_fastapi_error_handlers,
)
from services.api_gateway_service.app.startup_setup import (
    create_di_container,
    setup_dependency_injection,
    setup_standard_metrics_middleware,
    setup_tracing_and_middleware,
)
from services.api_gateway_service.config import settings

from ..routers import batch_routes, class_routes, file_routes, status_routes
from ..routers.health_routes import router as health_router
from .middleware import CorrelationIDMiddleware
from .rate_limiter import limiter


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.SERVICE_NAME,
        version="1.0.0",
        description=(
            "HuleEdu API Gateway - Secure client-facing API for Svelte 5 + Vite "
            "frontend integration"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={
            "name": "HuleEdu Development Team",
            "url": "https://github.com/huledu/huledu-reboot",
        },
        license_info={
            "name": "MIT",
        },
    )

    # Register error handlers
    register_fastapi_error_handlers(app)

    # Add Correlation ID Middleware (must be early in chain)
    app.add_middleware(CorrelationIDMiddleware)

    # Add Development Middleware (only in development environment)
    if settings.is_development():
        from .middleware import DevelopmentMiddleware

        app.add_middleware(DevelopmentMiddleware, settings=settings)

    # Setup distributed tracing and tracing middleware (second in chain)
    setup_tracing_and_middleware(app)

    # Setup standard HTTP metrics middleware (third in chain)
    setup_standard_metrics_middleware(app)

    # Add Rate Limiting Middleware
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded: {exc.detail}"},
        )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Include routers
    app.include_router(health_router, tags=["Health"])
    app.include_router(class_routes.router, prefix="/v1", tags=["Classes"])
    app.include_router(status_routes.router, prefix="/v1", tags=["Status"])
    app.include_router(batch_routes.router, prefix="/v1", tags=["Batches"])
    app.include_router(file_routes.router, prefix="/v1", tags=["Files"])

    # Include development routes (only in development environment)
    if settings.is_development():
        from ..routers import dev_routes

        app.include_router(dev_routes.router, prefix="/dev", tags=["Development"])

    # Setup Dishka DI
    container = create_di_container()
    setup_dependency_injection(app, container)

    # Store container reference for cleanup
    app.state.di_container = container

    return app


app = create_app()
