"""Startup setup utilities for Result Aggregator Service."""

from __future__ import annotations

import asyncio
import signal
from typing import Any

from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware,
)
from huleedu_service_libs.quart_app import HuleEduApp
from prometheus_client import start_http_server

from services.result_aggregator_service.config import Settings


async def initialize_tracing(app: HuleEduApp) -> None:
    """Initialize OpenTelemetry tracing with Jaeger."""
    logger = create_service_logger("result_aggregator.startup")
    try:
        tracer = init_tracing("result_aggregator_service")
        setup_tracing_middleware(app, tracer)
        logger.info("Result Aggregator Service tracing initialized successfully")
    except Exception as e:
        logger.critical("Failed to initialize tracing: %s", e, exc_info=True)
        raise


def setup_metrics_endpoint(app: HuleEduApp) -> None:
    """Setup Prometheus metrics endpoint on separate port."""
    logger = create_service_logger("result_aggregator.startup")

    @app.before_serving
    async def start_metrics_server() -> None:
        """Start metrics server before serving."""
        # Get settings from app config or use defaults
        settings = Settings()

        # Start Prometheus metrics server
        start_http_server(settings.METRICS_PORT)
        logger.info(f"Metrics server started on port {settings.METRICS_PORT}")


def setup_signal_handlers(app: HuleEduApp) -> None:
    """Setup graceful shutdown signal handlers."""
    logger = create_service_logger("result_aggregator.startup")

    async def graceful_shutdown() -> None:
        """Perform graceful shutdown."""
        logger.info("Initiating graceful shutdown...")

        # Close container resources
        await app.container.close()

        logger.info("Graceful shutdown complete")

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        asyncio.create_task(app.shutdown())  # Schedule async shutdown

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
