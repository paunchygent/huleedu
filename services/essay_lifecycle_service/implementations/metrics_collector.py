"""
Metrics collector implementation for Essay Lifecycle Service.

Implements MetricsCollector protocol for Prometheus metrics collection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

from protocols import MetricsCollector


class DefaultMetricsCollector(MetricsCollector):
    """Default implementation of MetricsCollector protocol."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.registry = registry
        self._setup_metrics()

    def _setup_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        from prometheus_client import Counter, Histogram

        self.state_transitions = Counter(
            "essay_state_transitions_total",
            "Total number of essay state transitions",
            ["from_status", "to_status"],
            registry=self.registry,
        )

        self.processing_duration = Histogram(
            "essay_processing_duration_seconds",
            "Time spent processing operations",
            ["operation"],
            registry=self.registry,
        )

        self.operation_counter = Counter(
            "essay_operations_total",
            "Total number of operations performed",
            ["operation", "status"],
            registry=self.registry,
        )

    def record_state_transition(self, from_status: str, to_status: str) -> None:
        """Record a state transition metric."""
        self.state_transitions.labels(from_status=from_status, to_status=to_status).inc()

    def record_processing_time(self, operation: str, duration_ms: float) -> None:
        """Record processing time for an operation."""
        self.processing_duration.labels(operation=operation).observe(duration_ms / 1000.0)

    def increment_counter(self, metric_name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        labels = labels or {}

        if metric_name == "operations":
            self.operation_counter.labels(**labels).inc()
