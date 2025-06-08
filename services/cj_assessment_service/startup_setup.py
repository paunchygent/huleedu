"""Startup and shutdown logic for CJ Assessment Service."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CollectorRegistry, Counter, Histogram
from quart import Quart

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.protocols import CJRepositoryProtocol

logger = create_service_logger("cj_assessment_service.startup")


async def initialize_services(app: Quart, settings: Settings, container) -> None:
    """Initialize database schema and metrics (DI container already initialized in app.py)."""
    try:

        # Initialize database schema directly (following BOS/ELS pattern)
        async with container() as request_container:
            database = await request_container.get(CJRepositoryProtocol)
            await database.initialize_db_schema()
            logger.info("Database schema initialized successfully")

            # Initialize metrics with DI registry and store in app context
            registry = await request_container.get(CollectorRegistry)
            metrics = _create_metrics(registry)

            # Store metrics in app context (proper Quart pattern)
            app.extensions = getattr(app, "extensions", {})
            app.extensions["metrics"] = metrics

        logger.info(
            "CJ Assessment Service DI container and quart-dishka integration "
            "initialized successfully."
        )
    except Exception as e:
        logger.critical(f"Failed to initialize CJ Assessment Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown the service."""
    try:
        logger.info("CJ Assessment Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


def _create_metrics(registry: CollectorRegistry) -> dict:
    """Create Prometheus metrics instances."""
    return {
        "request_count": Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry,
        ),
        "request_duration": Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry,
        ),
        "cj_assessment_operations": Counter(
            "cj_assessment_operations_total",
            "Total CJ assessment operations",
            ["operation", "status"],
            registry=registry,
        ),
        "llm_api_calls": Counter(
            "llm_api_calls_total",
            "Total LLM API calls",
            ["provider", "model", "status"],
            registry=registry,
        ),
    }
