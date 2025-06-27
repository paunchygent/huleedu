"""Dependency injection configuration for File Service using Dishka."""

from __future__ import annotations

from typing import Any, cast

from aiohttp import ClientSession
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from prometheus_client import REGISTRY, CollectorRegistry

from services.file_service.config import Settings, settings
from services.file_service.content_validator import FileContentValidator
from services.file_service.implementations.batch_state_validator import BOSBatchStateValidator
from services.file_service.implementations.content_service_client_impl import (
    DefaultContentServiceClient,
)
from services.file_service.implementations.event_publisher_impl import DefaultEventPublisher
from services.file_service.implementations.text_extractor_impl import DefaultTextExtractor
from services.file_service.metrics import METRICS
from services.file_service.protocols import (
    BatchStateValidatorProtocol,
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
        """Provide the global Prometheus metrics registry shared across collectors."""
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_metrics(self) -> dict[str, Any]:
        """Provide shared Prometheus metrics dictionary."""
        return METRICS

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

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client for pub/sub operations."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()

        # Register shutdown finalizer to prevent connection leaks
        async def _shutdown_redis() -> None:
            await redis_client.stop()

        # TODO Note: In production, this would be registered with the app lifecycle
        # For now, we rely on container cleanup

        return cast(AtomicRedisClientProtocol, redis_client)


class ServiceImplementationsProvider(Provider):
    """Provider for service implementation dependencies."""

    @provide(scope=Scope.APP)
    def provide_content_service_client(
        self,
        http_session: ClientSession,
        settings: Settings,
    ) -> ContentServiceClientProtocol:
        """Provide Content Service client implementation."""
        return DefaultContentServiceClient(http_session, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        kafka_bus: KafkaBus,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
    ) -> EventPublisherProtocol:
        """Provide event publisher implementation with Redis support."""
        return DefaultEventPublisher(kafka_bus, settings, redis_client)

    @provide(scope=Scope.APP)
    def provide_text_extractor(self) -> TextExtractorProtocol:
        """Provide text extractor implementation."""
        return DefaultTextExtractor()

    @provide(scope=Scope.APP)
    def provide_content_validator(self, settings: Settings) -> ContentValidatorProtocol:
        """Provide content validator implementation."""
        return FileContentValidator(
            min_length=settings.MIN_CONTENT_LENGTH,
            max_length=settings.MAX_CONTENT_LENGTH,
        )

    @provide(scope=Scope.APP)
    def provide_batch_state_validator(
        self,
        http_session: ClientSession,
        settings: Settings,
    ) -> BatchStateValidatorProtocol:
        """Provide batch state validator implementation."""
        return BOSBatchStateValidator(http_session, settings)
