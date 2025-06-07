"""
Content Service dependency injection configuration.
"""
from __future__ import annotations

from pathlib import Path

from config import settings
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry, Counter

from services.content_service.implementations.filesystem_content_store import FileSystemContentStore
from services.content_service.implementations.prometheus_content_metrics import (
    PrometheusContentMetrics,
)
from services.content_service.protocols import ContentMetricsProtocol, ContentStoreProtocol


class ContentServiceProvider(Provider):
    """DI provider for Content Service dependencies."""

    @provide(scope=Scope.APP)
    def provide_collector_registry(self) -> CollectorRegistry:
        """Provide Prometheus collector registry."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    def provide_content_metrics(
        self,
        registry: CollectorRegistry,
    ) -> ContentMetricsProtocol:
        """Provide content metrics implementation."""
        content_operations = Counter(
            "content_operations_total",
            "Total content operations",
            ["operation", "status"],
            registry=registry,
        )
        return PrometheusContentMetrics(content_operations)

    @provide(scope=Scope.APP)
    def provide_store_root(self) -> Path:
        """Provide content store root path."""
        return Path(settings.CONTENT_STORE_ROOT_PATH)

    @provide(scope=Scope.APP)
    def provide_content_store(self, store_root: Path) -> ContentStoreProtocol:
        """Provide content store implementation."""
        return FileSystemContentStore(store_root)


