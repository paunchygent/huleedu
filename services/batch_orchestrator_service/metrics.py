"""Shared metrics module for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

logger = create_service_logger("batch_orchestrator_service.metrics")

_metrics: dict[str, Any] | None = None


def get_metrics(database_metrics: Optional[DatabaseMetrics] = None) -> dict[str, Any]:
    """Get or create shared metrics instances (Singleton Pattern)."""
    global _metrics
    if _metrics is None:
        logger.info("Initializing shared Batch Orchestrator Service metrics registry.")
        _metrics = _create_metrics(database_metrics)
    return _metrics


def _create_metrics(database_metrics: Optional[DatabaseMetrics] = None) -> dict[str, Any]:
    """Create all Prometheus metrics for Batch Orchestrator Service."""
    try:
        metrics = {
            # Standard HTTP Metrics
            "http_requests_total": Counter(
                "batch_orchestrator_service_http_requests_total",
                "Total HTTP requests to Batch Orchestrator Service",
                ["method", "endpoint", "status_code"],
                registry=REGISTRY,
            ),
            "http_request_duration_seconds": Histogram(
                "batch_orchestrator_service_http_request_duration_seconds",
                "HTTP request duration in seconds for Batch Orchestrator Service",
                ["method", "endpoint"],
                registry=REGISTRY,
            ),
            # NEW Business Intelligence Metrics
            "pipeline_execution_total": Counter(
                "huleedu_pipeline_execution_total",
                "Total count of pipeline executions, labeled by type and outcome.",
                ["pipeline_type", "outcome", "batch_id"],
                registry=REGISTRY,
            ),
            "phase_transition_duration_seconds": Histogram(
                "huleedu_phase_transition_duration_seconds",
                "Duration of phase transitions orchestrated by BOS.",
                ["from_phase", "to_phase", "batch_id"],
                buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60),  # Meaningful buckets
                registry=REGISTRY,
            ),
            "orchestration_commands_total": Counter(
                "huleedu_orchestration_commands_total",
                "Total commands sent by BOS to specialized services.",
                ["command_type", "target_service", "batch_id"],
                registry=REGISTRY,
            ),
            # Circuit Breaker Metrics
            "circuit_breaker_state": Gauge(
                "batch_orchestrator_service_circuit_breaker_state",
                "Circuit breaker state (0=closed, 1=open, 2=half_open)",
                ["service", "circuit_name"],
                registry=REGISTRY,
            ),
            "circuit_breaker_state_changes": Counter(
                "batch_orchestrator_service_circuit_breaker_state_changes_total",
                "Total circuit breaker state changes",
                ["service", "circuit_name", "from_state", "to_state"],
                registry=REGISTRY,
            ),
            "circuit_breaker_calls_total": Counter(
                "batch_orchestrator_service_circuit_breaker_calls_total",
                "Total circuit breaker calls",
                ["service", "circuit_name", "result"],
                registry=REGISTRY,
            ),
        }

        # Add database metrics if provided
        if database_metrics:
            db_metrics = database_metrics.get_metrics()
            metrics.update(db_metrics)
            logger.info("Database metrics integrated into Batch Orchestrator Service metrics")

        return metrics
    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(
                f"Metrics already registered: {e} – reusing existing collectors from REGISTRY.",
            )
            existing = _get_existing_metrics()
            # Add database metrics to existing if provided
            if database_metrics:
                db_metrics = database_metrics.get_metrics()
                existing.update(db_metrics)
            return existing
        raise


def get_http_metrics() -> dict[str, Any]:
    """Get metrics required by the HTTP API component."""
    all_metrics = get_metrics()
    return {
        "http_requests_total": all_metrics.get("http_requests_total"),
        "http_request_duration_seconds": all_metrics.get("http_request_duration_seconds"),
        "pipeline_execution_total": all_metrics.get(
            "pipeline_execution_total",
        ),  # For tracking requests that start pipelines
    }


def _get_existing_metrics() -> dict[str, Any]:
    """Return already-registered collectors from the global REGISTRY.

    Falling back to an empty dict disables metrics entirely. This helper looks up the
    collectors by their canonical metric names so middleware and services keep
    working even when the module is imported more than once (common during tests).
    """

    from prometheus_client import REGISTRY

    name_map = {
        "http_requests_total": "batch_orchestrator_service_http_requests_total",
        "http_request_duration_seconds": "batch_orchestrator_service_http_request_duration_seconds",
        "pipeline_execution_total": "huleedu_pipeline_execution_total",
        "phase_transition_duration_seconds": "huleedu_phase_transition_duration_seconds",
        "orchestration_commands_total": "huleedu_orchestration_commands_total",
        # Circuit Breaker Metrics
        "circuit_breaker_state": "batch_orchestrator_service_circuit_breaker_state",
        "circuit_breaker_state_changes": (
            "batch_orchestrator_service_circuit_breaker_state_changes_total"
        ),
        "circuit_breaker_calls_total": "batch_orchestrator_service_circuit_breaker_calls_total",
    }

    existing: dict[str, Any] = {}
    registry_collectors = getattr(REGISTRY, "_names_to_collectors", None)
    for logical_key, metric_name in name_map.items():
        try:
            if registry_collectors and metric_name in registry_collectors:
                existing[logical_key] = registry_collectors[metric_name]
            else:
                for collector in REGISTRY.collect():
                    if collector.name == metric_name:
                        existing[logical_key] = collector
                        break
        except Exception as exc:  # pragma: no cover
            logger.error("Error retrieving BOS metric '%s': %s", metric_name, exc)

    return existing


def get_kafka_consumer_metrics() -> dict[str, Any]:
    """Get metrics required by the Kafka consumer component."""
    all_metrics = get_metrics()
    return {
        "phase_transition_duration_seconds": all_metrics.get("phase_transition_duration_seconds"),
        "orchestration_commands_total": all_metrics.get("orchestration_commands_total"),
    }


def get_circuit_breaker_metrics() -> dict[str, Any]:
    """Get metrics required by circuit breaker components."""
    all_metrics = get_metrics()
    return {
        "circuit_breaker_state": all_metrics.get("circuit_breaker_state"),
        "circuit_breaker_state_changes": all_metrics.get("circuit_breaker_state_changes"),
        "circuit_breaker_calls_total": all_metrics.get("circuit_breaker_calls_total"),
    }


def get_database_metrics() -> dict[str, Any]:
    """Get database metrics dictionary for integration with DatabaseMetrics.

    Returns:
        Dictionary containing database-related metrics from the service
    """
    all_metrics = get_metrics()
    return {
        "pipeline_execution_total": all_metrics.get("pipeline_execution_total"),
        "phase_transition_duration_seconds": all_metrics.get("phase_transition_duration_seconds"),
        "orchestration_commands_total": all_metrics.get("orchestration_commands_total"),
        "circuit_breaker_state": all_metrics.get("circuit_breaker_state"),
        "circuit_breaker_state_changes": all_metrics.get("circuit_breaker_state_changes"),
        "circuit_breaker_calls_total": all_metrics.get("circuit_breaker_calls_total"),
    }


def setup_batch_orchestrator_database_monitoring(
    engine: AsyncEngine,
    service_name: str = "batch_orchestrator_service",
    existing_metrics: Optional[Dict[str, Any]] = None,
) -> DatabaseMetrics:
    """
    Setup comprehensive database monitoring for Batch Orchestrator Service.

    Args:
        engine: SQLAlchemy async engine for batch orchestrator database
        service_name: Service name for metrics labeling
        existing_metrics: Optional existing metrics dictionary to extend

    Returns:
        DatabaseMetrics instance configured for batch orchestration operations
    """
    return setup_database_monitoring(engine, service_name, existing_metrics)
