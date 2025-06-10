"""Startup and shutdown setup for Spell Checker Service health API.

This module handles the initialization of metrics and other app-level services
for the Quart-based health API component of the combined service.
"""

from __future__ import annotations

from typing import Any

from dishka import AsyncContainer
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter, Histogram
from quart import Quart

from services.spell_checker_service.config import Settings

logger = create_service_logger("spell_checker_service.startup_setup")


def _create_metrics() -> dict[str, Any]:
    """Create Prometheus metrics for the Spell Checker Service.

    Returns:
        Dictionary of metric instances keyed by metric name
    """
    metrics = {
        "http_requests_total": Counter(
            "spell_checker_http_requests_total",
            "Total HTTP requests to spell checker service",
            ["method", "endpoint", "status_code"],
        ),
        "http_request_duration_seconds": Histogram(
            "spell_checker_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
        ),
        "spell_check_operations_total": Counter(
            "spell_checker_operations_total",
            "Total spell check operations performed",
            ["language", "status"],
        ),
    }
    return metrics


async def initialize_services(app: Quart, settings: Settings, container: AsyncContainer) -> None:
    """Initialize application services and metrics.

    Args:
        app: Quart application instance
        settings: Application settings
        container: DI container for service dependencies
    """
    logger.info("Initializing Spell Checker Service health API components")

    # Create and store metrics in app extensions
    metrics = _create_metrics()
    app.extensions["metrics"] = metrics

    logger.info("Metrics created and stored in app extensions")
    logger.info(f"Available metrics: {list(metrics.keys())}")

    # TODO: Add additional service initialization here
    # - Database connections (if needed)
    # - External service health checks
    # - Cache initialization

    logger.info("Spell Checker Service health API initialization complete")


async def shutdown_services() -> None:
    """Cleanup application services on shutdown.

    Handles graceful shutdown of any resources that need explicit cleanup.
    """
    logger.info("Shutting down Spell Checker Service health API components")

    # TODO: Add cleanup logic here
    # - Close database connections
    # - Cleanup cache resources
    # - Flush pending metrics

    logger.info("Spell Checker Service health API shutdown complete")
