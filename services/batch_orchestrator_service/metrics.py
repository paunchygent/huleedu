"""Shared metrics module for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Histogram

logger = create_service_logger("bos.metrics")

_metrics: Optional[Dict[str, Any]] = None

def get_metrics() -> Dict[str, Any]:
    """Get or create shared metrics instances (Singleton Pattern)."""
    global _metrics
    if _metrics is None:
        logger.info("Initializing shared BOS metrics registry.")
        _metrics = _create_metrics()
    return _metrics

def _create_metrics() -> Dict[str, Any]:
    """Create all Prometheus metrics for BOS."""
    try:
        metrics = {
            # Standard HTTP Metrics
            "http_requests_total": Counter(
                "bos_http_requests_total",
                "Total HTTP requests to Batch Orchestrator Service",
                ["method", "endpoint", "status_code"],
                registry=REGISTRY,
            ),
            "http_request_duration_seconds": Histogram(
                "bos_http_request_duration_seconds",
                "HTTP request duration in seconds for BOS",
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
                buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60), # Meaningful buckets
                registry=REGISTRY,
            ),
            "orchestration_commands_total": Counter(
                "huleedu_orchestration_commands_total",
                "Total commands sent by BOS to specialized services.",
                ["command_type", "target_service", "batch_id"],
                registry=REGISTRY,
            ),
        }
        return metrics
    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(f"Metrics already registered: {e}. This can happen in test environments.")
            # In a running service this indicates an architectural issue, but we allow it for test runners.
            return {}
        raise

def get_http_metrics() -> Dict[str, Any]:
    """Get metrics required by the HTTP API component."""
    all_metrics = get_metrics()
    return {
        "http_requests_total": all_metrics.get("http_requests_total"),
        "http_request_duration_seconds": all_metrics.get("http_request_duration_seconds"),
        "pipeline_execution_total": all_metrics.get("pipeline_execution_total"), # For tracking requests that start pipelines
    }

def get_kafka_consumer_metrics() -> Dict[str, Any]:
    """Get metrics required by the Kafka consumer component."""
    all_metrics = get_metrics()
    return {
        "phase_transition_duration_seconds": all_metrics.get("phase_transition_duration_seconds"),
        "orchestration_commands_total": all_metrics.get("orchestration_commands_total"),
    }
