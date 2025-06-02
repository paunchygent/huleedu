"""Dishka dependency injection providers for CJ Assessment Service."""

from __future__ import annotations

from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from .config import Settings
from .config import settings as service_settings


class CJAssessmentServiceProvider(Provider):
    """Dishka provider for CJ Assessment Service dependencies."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide application settings."""
        return service_settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return CollectorRegistry()

    # More providers will be added in later phases for:
    # - AIOKafkaProducer
    # - aiohttp.ClientSession
    # - ContentClientProtocol
    # - LLMInteractionProtocol
    # - CJDatabaseProtocol
    # - CJEventPublisherProtocol
