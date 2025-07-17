"""
HuleEdu Structured Logging Utilities using Structlog.

This module provides composable logging utilities built on structlog 25.3.0,
designed for HuleEdu's event-driven microservice architecture.

Key Features:
- Native correlation ID extraction from EventEnvelope
- Async-safe context management with contextvars
- Processor chains for flexible log enrichment
- Environment-based output formatting
- Service autonomy with composable utilities
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog
from common_core.events.envelope import EventEnvelope
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars


def configure_service_logging(
    service_name: str,
    environment: str | None = None,
    log_level: str = "INFO",
) -> None:
    """
    Configure structlog for a HuleEdu service.

    This function sets up the complete logging configuration for a service,
    maintaining compatibility with existing logging calls.

    Args:
        service_name: Name of the service (e.g., "spell-checker-service")
        environment: Environment name (defaults to ENVIRONMENT env var)
        log_level: Logging level (defaults to "INFO")
    """
    if environment is None:
        environment = os.getenv("ENVIRONMENT", "development")

    # Set environment variables for processors
    os.environ.setdefault("SERVICE_NAME", service_name)
    os.environ.setdefault("ENVIRONMENT", environment)

    # Choose processors based on environment
    if environment == "production":
        # Production: JSON output for log aggregation
        processors = [
            merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ],
            ),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Human-readable console output
        processors = [
            merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ],
            ),
            structlog.dev.set_exc_info,
            # Note: format_exc_info removed for pretty exceptions in development
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog
    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def create_service_logger(name: str | None = None) -> Any:
    """
    Create a service logger with optional name binding.

    Args:
        name: Optional logger name (e.g., "worker", "api", "processor")

    Returns:
        A configured structlog BoundLogger instance
    """
    logger = structlog.get_logger()

    if name:
        logger = logger.bind(logger_name=name)

    return logger


def log_event_processing(
    logger: structlog.stdlib.BoundLogger,
    message: str,
    envelope: EventEnvelope,
    **additional_context: Any,
) -> None:
    """
    Log event processing with full context.

    This maintains compatibility with the existing log_event_processing calls
    while adding structured logging capabilities.

    Args:
        logger: The structlog logger instance
        envelope: The EventEnvelope being processed
        message: Log message
        **additional_context: Additional context to include in the log
    """
    # Set correlation context
    clear_contextvars()
    bind_contextvars(
        correlation_id=str(envelope.correlation_id),
        event_id=str(envelope.event_id),
        event_type=envelope.event_type,
        source_service=envelope.source_service,
    )

    # Log with enriched context
    logger.info(
        message,
        event_data_type=type(envelope.data).__name__,
        **additional_context,
    )
