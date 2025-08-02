from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from huleedu_service_libs.error_handling.fastapi import (
    register_error_handlers as register_fastapi_error_handlers,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.websocket_service.config import settings
from services.websocket_service.routers import health_routes, websocket_routes
from services.websocket_service.startup_setup import (
    create_di_container,
    setup_dependency_injection,
    setup_tracing,
    start_kafka_consumer,
    stop_kafka_consumer,
)

logger = create_service_logger("websocket.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle."""
    logger.info("Starting WebSocket Service...")

    # Start Kafka consumer
    await start_kafka_consumer(app.state.di_container)

    yield

    # Stop Kafka consumer
    logger.info("Shutting down WebSocket Service...")
    await stop_kafka_consumer()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.SERVICE_NAME,
        version="1.0.0",
        description="WebSocket Service for real-time notifications in HuleEdu",
        lifespan=lifespan,
    )

    # Add CORS middleware for WebSocket upgrade requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Register error handlers
    register_fastapi_error_handlers(app)

    # Include routers
    app.include_router(health_routes.router, tags=["Health"])
    app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket"])

    # Setup Dishka DI
    container = create_di_container()
    setup_dependency_injection(app, container)

    # Store container reference for cleanup
    app.state.di_container = container

    # Setup distributed tracing if enabled
    if settings.ENABLE_TRACING:
        setup_tracing(app)

    return app


app = create_app()
