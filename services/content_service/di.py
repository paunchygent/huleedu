"""
Content Service dependency injection configuration.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry, Counter
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.content_service.config import Settings, settings
from services.content_service.implementations.content_repository_impl import (
    ContentRepository,
)
from services.content_service.implementations.prometheus_content_metrics import (
    PrometheusContentMetrics,
)
from services.content_service.protocols import (
    ContentMetricsProtocol,
    ContentRepositoryProtocol,
)


class ContentServiceProvider(Provider):
    """DI provider for Content Service dependencies."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

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
    def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        """Provide async database engine for Content Service."""
        return create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )

    @provide(scope=Scope.APP)
    def provide_content_repository(
        self,
        engine: AsyncEngine,
    ) -> ContentRepositoryProtocol:
        """Provide database-backed content repository implementation."""
        return ContentRepository(engine)
