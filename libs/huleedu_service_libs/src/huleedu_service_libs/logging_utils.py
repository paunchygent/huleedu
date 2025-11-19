"""
HuleEdu Structured Logging Utilities using Structlog.

This module provides composable logging utilities built on structlog 25.3.0,
designed for HuleEdu's event-driven microservice architecture.

Key Features:
- Native correlation ID extraction from EventEnvelope
- Async-safe context management with contextvars
- Processor chains for flexible log enrichment
- Environment-based output formatting
- Optional file-based logging with rotation
- Service autonomy with composable utilities
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from common_core.events.envelope import EventEnvelope
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.typing import Processor


def add_service_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Add OpenTelemetry service context to all logs.

    This processor adds service.name and deployment.environment fields
    to align with OpenTelemetry semantic conventions, enabling
    OTEL-native tooling integration and consistent service identification.

    Fields added:
    - service.name: Logical service name (from SERVICE_NAME env var)
    - deployment.environment: Environment (development/staging/production)

    Args:
        logger: The logger instance (unused but required by structlog)
        method_name: The logging method name (unused but required by structlog)
        event_dict: The log event dictionary to enrich

    Returns:
        Enriched event dictionary with service context fields
    """
    event_dict["service.name"] = os.getenv("SERVICE_NAME", "unknown")
    event_dict["deployment.environment"] = os.getenv("ENVIRONMENT", "development")
    return event_dict


def configure_service_logging(
    service_name: str,
    environment: str | None = None,
    log_level: str = "INFO",
    log_to_file: bool | None = None,
    log_file_path: str | None = None,
) -> None:
    """
    Configure structlog for a HuleEdu service.

    This function sets up the complete logging configuration for a service,
    maintaining compatibility with existing logging calls. Optionally enables
    file-based logging with automatic rotation.

    Args:
        service_name: Name of the service (e.g., "spell-checker-service")
        environment: Environment name (defaults to ENVIRONMENT env var)
        log_level: Logging level (defaults to "INFO")
        log_to_file: Enable file-based logging (defaults to LOG_TO_FILE env var)
        log_file_path: Path to log file (defaults to LOG_FILE_PATH env var
            or /app/logs/{service_name}.log)

    Environment Variables:
        LOG_FORMAT: Output format - "json" for JSON, "console" for human-readable (default: console)
        LOG_TO_FILE: Enable file logging (default: false)
        LOG_FILE_PATH: Custom log file path (default: /app/logs/{service_name}.log)
        LOG_MAX_BYTES: Max bytes per log file before rotation (default: 104857600 = 100MB)
        LOG_BACKUP_COUNT: Number of backup log files to keep (default: 10)
    """
    if environment is None:
        environment = os.getenv("ENVIRONMENT", "development")

    # Set environment variables for processors
    os.environ.setdefault("SERVICE_NAME", service_name)
    os.environ.setdefault("ENVIRONMENT", environment)

    # Determine if file logging is enabled
    if log_to_file is None:
        log_to_file = os.getenv("LOG_TO_FILE", "false").lower() in ("true", "1", "yes")

    # Determine log format: check LOG_FORMAT env var first, then fall back to environment
    log_format = os.getenv("LOG_FORMAT", "").lower()
    use_json = log_format == "json" or (not log_format and environment == "production")

    # Choose processors based on format
    if use_json:
        # JSON output for log aggregation (Docker containers, production)
        processors: list[Processor] = [
            merge_contextvars,
            add_service_context,  # Add OTEL service context
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
        # Human-readable console output (local development, tests)
        processors = [
            merge_contextvars,
            add_service_context,  # Add OTEL service context
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

    # Build list of handlers (always include stdout)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # Add file handler if enabled
    if log_to_file:
        if log_file_path is None:
            log_file_path = os.getenv("LOG_FILE_PATH", f"/app/logs/{service_name}.log")

        # Ensure log directory exists
        log_file = Path(log_file_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Get rotation settings from environment
        max_bytes = int(os.getenv("LOG_MAX_BYTES", "104857600"))  # 100MB default
        backup_count = int(os.getenv("LOG_BACKUP_COUNT", "10"))  # 10 files default

        # Create rotating file handler
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    # Configure standard library logging with all handlers
    logging.basicConfig(
        format="%(message)s",
        handlers=handlers,
        level=getattr(logging, log_level.upper()),
        force=True,  # Force reconfiguration if already configured
    )

    # Configure structlog
    structlog.configure(
        processors=processors,
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
