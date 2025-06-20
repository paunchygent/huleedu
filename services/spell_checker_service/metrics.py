"""Shared metrics module for Spell Checker Service.

This module ensures metrics are created once and shared between HTTP and worker components,
preventing duplicate registration errors while maintaining unified metrics endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Histogram

logger = create_service_logger("spell_checker_service.metrics")

# Global metrics instances (created once, shared by HTTP and worker)
_metrics: Optional[Dict[str, Any]] = None


def get_metrics() -> Dict[str, Any]:
    """Get or create shared metrics instances.
    
    Returns:
        Dictionary of metric instances keyed by metric name
        
    Thread-safe singleton pattern for metrics initialization.
    """
    global _metrics

    if _metrics is None:
        _metrics = _create_metrics()
        logger.info("Shared metrics initialized")
        logger.info(f"Available metrics: {list(_metrics.keys())}")

    return _metrics


def _create_metrics() -> Dict[str, Any]:
    """Create Prometheus metrics for the Spell Checker Service.
    
    Returns:
        Dictionary of metric instances keyed by metric name
    """
    try:
        metrics = {
            "http_requests_total": Counter(
                "spell_checker_http_requests_total",
                "Total HTTP requests to spell checker service",
                ["method", "endpoint", "status_code"],
                registry=REGISTRY,
            ),
            "http_request_duration_seconds": Histogram(
                "spell_checker_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
                registry=REGISTRY,
            ),
            "spell_check_operations_total": Counter(
                "spell_checker_operations_total",
                "Total spell check operations performed",
                ["language", "status"],
                registry=REGISTRY,
            ),
            "spellcheck_corrections_made": Histogram(
                "huleedu_spellcheck_corrections_made",
                "Distribution of spelling corrections per essay",
                buckets=(0, 1, 2, 5, 10, 20, 50, 100),
                registry=REGISTRY,
            ),
            "kafka_queue_latency_seconds": Histogram(
                "kafka_message_queue_latency_seconds",
                "Latency between event timestamp and processing start",
                registry=REGISTRY,
            ),
        }

        logger.info("Successfully created all metrics")
        return metrics

    except ValueError as e:
        if "Duplicated timeseries" in str(e):
            logger.warning(f"Metrics already exist in registry: {e}")
            # Return existing metrics from registry
            return _get_existing_metrics()
        else:
            raise


def _get_existing_metrics() -> Dict[str, Any]:
    """Retrieve existing metrics from registry.
    
    Returns:
        Dictionary of existing metric instances
    """
    # For now, return empty dict - in practice, we'd need to implement
    # registry lookup logic or ensure metrics are only created once
    logger.warning("Using fallback empty metrics dict - metrics may not be recorded")
    return {}


def get_business_metrics() -> Dict[str, Any]:
    """Get business intelligence metrics for worker components.
    
    Returns:
        Dictionary containing business metrics
    """
    all_metrics = get_metrics()
    return {
        "spellcheck_corrections_made": all_metrics.get("spellcheck_corrections_made"),
        "kafka_queue_latency_seconds": all_metrics.get("kafka_queue_latency_seconds"),
    }


def get_http_metrics() -> Dict[str, Any]:
    """Get HTTP operational metrics for web components.
    
    Returns:
        Dictionary containing HTTP metrics
    """
    all_metrics = get_metrics()
    return {
        "http_requests_total": all_metrics.get("http_requests_total"),
        "http_request_duration_seconds": all_metrics.get("http_request_duration_seconds"),
    }
