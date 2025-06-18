"""Dependency injection configuration for File Service using Dishka."""

from __future__ import annotations

from aiohttp import ClientSession
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from prometheus_client import CollectorRegistry

from services.file_service.config import Settings, settings
from services.file_service.content_validator import FileContentValidator
from services.file_service.implementations.content_service_client_impl import (
    DefaultContentServiceClient,
)
from services.file_service.implementations.event_publisher_impl import DefaultEventPublisher
from services.file_service.implementations.text_extractor_impl import DefaultTextExtractor
from services.file_service.protocols import (
    ContentServiceClientProtocol,
    ContentValidatorProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)


class CoreInfrastructureProvider(Provider):
    """Provider for core infrastructure dependencies (settings, metrics, Kafka, HTTP)."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        """Provide Kafka bus for event publishing."""
        kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}-producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> ClientSession:
        """Provide HTTP client session."""
        return ClientSession()


class ServiceImplementationsProvider(Provider):
    """Provider for service implementation dependencies."""

    @provide(scope=Scope.APP)
    def provide_content_service_client(
        self, http_session: ClientSession, settings: Settings
    ) -> ContentServiceClientProtocol:
        """Provide Content Service client implementation."""
        return DefaultContentServiceClient(http_session, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, kafka_bus: KafkaBus, settings: Settings
    ) -> EventPublisherProtocol:
        """Provide event publisher implementation."""
        return DefaultEventPublisher(kafka_bus, settings)

    @provide(scope=Scope.APP)
    def provide_text_extractor(self) -> TextExtractorProtocol:
        """Provide text extractor implementation."""
        return DefaultTextExtractor()

    @provide(scope=Scope.APP)
    def provide_content_validator(self, settings: Settings) -> ContentValidatorProtocol:
        """Provide content validator implementation."""
        return FileContentValidator(
            min_length=settings.MIN_CONTENT_LENGTH, max_length=settings.MAX_CONTENT_LENGTH
        )
