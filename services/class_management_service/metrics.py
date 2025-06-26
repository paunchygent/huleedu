"""Metrics definitions and providers for the Class Management Service."""

from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry, REGISTRY


class MetricsProvider(Provider):
    """Provides Prometheus metrics-related dependencies."""

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide the default Prometheus collector registry."""
        return REGISTRY
