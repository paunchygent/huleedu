"""Startup setup utilities for Result Aggregator Service."""

from __future__ import annotations

from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware,
)
from huleedu_service_libs.quart_app import HuleEduApp


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
