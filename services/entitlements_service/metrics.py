"""Metrics configuration for Entitlements Service.

This module provides service-specific metrics setup following established patterns
for database monitoring and business metrics collection.
"""

from __future__ import annotations

from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from prometheus_client import CollectorRegistry, Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncEngine


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


class EntitlementsMetrics:
    """Business metrics for Entitlements Service."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialize metrics collectors."""
        self.registry = registry or CollectorRegistry()

        # Credit operation metrics
        self.credit_checks_total = Counter(
            "entitlements_credit_checks_total",
            "Total number of credit checks performed",
            ["result", "source"],  # result: allowed/denied, source: user/org
            registry=self.registry,
        )

        self.credit_consumption_total = Counter(
            "entitlements_credit_consumption_total",
            "Total credits consumed",
            ["metric", "source"],  # metric: operation type, source: user/org
            registry=self.registry,
        )

        self.credit_adjustments_total = Counter(
            "entitlements_credit_adjustments_total",
            "Total manual credit adjustments",
            ["subject_type", "adjustment_type"],  # adjustment_type: addition/deduction
            registry=self.registry,
        )

        # Rate limiting metrics
        self.rate_limit_checks_total = Counter(
            "entitlements_rate_limit_checks_total",
            "Total number of rate limit checks",
            ["metric", "result"],  # result: allowed/blocked
            registry=self.registry,
        )

        self.rate_limit_violations_total = Counter(
            "entitlements_rate_limit_violations_total",
            "Total rate limit violations",
            ["metric"],
            registry=self.registry,
        )

        # Policy metrics
        self.policy_loads_total = Counter(
            "entitlements_policy_loads_total",
            "Total policy configuration loads",
            ["source"],  # source: file/cache
            registry=self.registry,
        )

        self.policy_cache_hits_total = Counter(
            "entitlements_policy_cache_hits_total",
            "Total policy cache hits",
            registry=self.registry,
        )

        self.policy_cache_misses_total = Counter(
            "entitlements_policy_cache_misses_total",
            "Total policy cache misses",
            registry=self.registry,
        )

        # Performance metrics
        self.credit_check_duration = Histogram(
            "entitlements_credit_check_duration_seconds",
            "Duration of credit check operations",
            ["source"],
            registry=self.registry,
        )

        self.credit_consumption_duration = Histogram(
            "entitlements_credit_consumption_duration_seconds",
            "Duration of credit consumption operations",
            registry=self.registry,
        )

        self.policy_lookup_duration = Histogram(
            "entitlements_policy_lookup_duration_seconds",
            "Duration of policy lookups",
            ["cache_hit"],  # cache_hit: true/false
            registry=self.registry,
        )

        # Balance metrics
        self.current_balances = Counter(
            "entitlements_current_balances_total",
            "Current credit balances by subject",
            ["subject_type"],
            registry=self.registry,
        )

    def record_credit_check(self, result: str, source: str) -> None:
        """Record a credit check operation."""
        self.credit_checks_total.labels(result=result, source=source).inc()

    def record_credit_consumption(self, metric: str, source: str, amount: int) -> None:
        """Record credit consumption."""
        self.credit_consumption_total.labels(metric=metric, source=source).inc(amount)

    def record_credit_adjustment(
        self, subject_type: str, adjustment_type: str, amount: int
    ) -> None:
        """Record manual credit adjustment."""
        self.credit_adjustments_total.labels(
            subject_type=subject_type, adjustment_type=adjustment_type
        ).inc(abs(amount))

    def record_rate_limit_check(self, metric: str, result: str) -> None:
        """Record rate limit check."""
        self.rate_limit_checks_total.labels(metric=metric, result=result).inc()

    def record_rate_limit_violation(self, metric: str) -> None:
        """Record rate limit violation."""
        self.rate_limit_violations_total.labels(metric=metric).inc()

    def record_policy_load(self, source: str) -> None:
        """Record policy configuration load."""
        self.policy_loads_total.labels(source=source).inc()

    def record_policy_cache_hit(self) -> None:
        """Record policy cache hit."""
        self.policy_cache_hits_total.inc()

    def record_policy_cache_miss(self) -> None:
        """Record policy cache miss."""
        self.policy_cache_misses_total.inc()
