"""
Shared metrics module for Entitlements Service.

This module implements the singleton pattern to prevent registry conflicts
following the proven pattern from Essay Lifecycle Service and other working services.
"""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import REGISTRY, Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine

logger = create_service_logger("entitlements_service.metrics")

# Global metrics instances (created once, shared across components)
_metrics: dict[str, Any] | None = None


def get_metrics(database_metrics: DatabaseMetrics | None = None) -> dict[str, Any]:
    """Thread-safe singleton pattern for metrics initialization."""
    global _metrics
    if _metrics is None:
        _metrics = _create_metrics(database_metrics)
    return _metrics


def _create_metrics(database_metrics: DatabaseMetrics | None = None) -> dict[str, Any]:
    """
    Create all metrics instances with shared registry.

    Creates both HTTP service metrics and business intelligence metrics
    for Entitlements Service observability.
    """
    registry = REGISTRY

    metrics = {
        # HTTP Service Metrics (MANDATORY for middleware compatibility)
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
        
        # Business Intelligence Metrics - Credit Operations
        "credit_checks_total": Counter(
            "entitlements_credit_checks_total",
            "Total number of credit checks performed",
            ["result", "source"],  # result: allowed/denied, source: user/org
            registry=registry,
        ),
        "credit_consumption_total": Counter(
            "entitlements_credit_consumption_total",
            "Total credits consumed",
            ["metric", "source"],  # metric: operation type, source: user/org
            registry=registry,
        ),
        "credit_adjustments_total": Counter(
            "entitlements_credit_adjustments_total",
            "Total manual credit adjustments",
            ["subject_type", "adjustment_type"],  # adjustment_type: addition/deduction
            registry=registry,
        ),
        
        # Rate Limiting Metrics
        "rate_limit_checks_total": Counter(
            "entitlements_rate_limit_checks_total",
            "Total number of rate limit checks",
            ["metric", "result"],  # result: allowed/blocked
            registry=registry,
        ),
        "rate_limit_violations_total": Counter(
            "entitlements_rate_limit_violations_total",
            "Total rate limit violations",
            ["metric"],
            registry=registry,
        ),
        
        # Policy Management Metrics
        "policy_loads_total": Counter(
            "entitlements_policy_loads_total",
            "Total policy configuration loads",
            ["source"],  # source: file/cache
            registry=registry,
        ),
        "policy_cache_hits_total": Counter(
            "entitlements_policy_cache_hits_total",
            "Total policy cache hits",
            registry=registry,
        ),
        "policy_cache_misses_total": Counter(
            "entitlements_policy_cache_misses_total",
            "Total policy cache misses",
            registry=registry,
        ),
        
        # Performance Metrics
        "credit_check_duration": Histogram(
            "entitlements_credit_check_duration_seconds",
            "Duration of credit check operations",
            ["source"],
            registry=registry,
        ),
        "credit_consumption_duration": Histogram(
            "entitlements_credit_consumption_duration_seconds",
            "Duration of credit consumption operations",
            registry=registry,
        ),
        "policy_lookup_duration": Histogram(
            "entitlements_policy_lookup_duration_seconds",
            "Duration of policy lookups",
            ["cache_hit"],  # cache_hit: true/false
            registry=registry,
        ),
        
        # Balance Tracking Metrics
        "current_balances": Counter(
            "entitlements_current_balances_total",
            "Current credit balances by subject",
            ["subject_type"],
            registry=registry,
        ),
    }

    # Add database metrics if provided
    if database_metrics:
        db_metrics = database_metrics.get_metrics()
        metrics.update(db_metrics)
        logger.info("Database metrics integrated into Entitlements Service metrics")

    return metrics


def setup_entitlements_service_database_monitoring(
    engine: AsyncEngine,
    service_name: str,
) -> DatabaseMetrics:
    """Set up database monitoring for Entitlements Service.

    Args:
        engine: Database engine to monitor
        service_name: Service name for metrics labels

    Returns:
        DatabaseMetrics instance for the service
    """
    return setup_database_monitoring(
        engine=engine,
        service_name=service_name,
    )