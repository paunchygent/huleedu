"""Dependency injection configuration for File Service using Dishka."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from aiohttp import ClientSession
from aiokafka.errors import KafkaError
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.file_service.config import Settings, settings
from services.file_service.content_validator import FileContentValidator
from services.file_service.implementations.batch_state_validator import BOSBatchStateValidator
from services.file_service.implementations.content_service_client_impl import (
    DefaultContentServiceClient,
)
from services.file_service.implementations.event_publisher_impl import DefaultEventPublisher
from services.file_service.implementations.file_repository_impl import MinimalFileRepository
from services.file_service.implementations.outbox_manager import OutboxManager
from services.file_service.implementations.text_extractor_impl import StrategyBasedTextExtractor
from services.file_service.metrics import METRICS
from services.file_service.protocols import (
    BatchStateValidatorProtocol,
    ContentServiceClientProtocol,
    ContentValidatorProtocol,
    EventPublisherProtocol,
    FileRepositoryProtocol,
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
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry."""
        registry = CircuitBreakerRegistry()

        # Only register circuit breakers if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            # Future: Add more circuit breakers here as needed
            pass

        return registry

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaPublisherProtocol:
        """Provide Kafka bus for event publishing with optional circuit breaker protection."""
        print("DEBUG: CoreInfrastructureProvider.provide_kafka_bus() called - using REAL Kafka!")
        # Create base KafkaBus instance
        base_kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}-producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )

        # Wrap with circuit breaker protection if enabled
        kafka_publisher: KafkaPublisherProtocol
        if settings.CIRCUIT_BREAKER_ENABLED:
            kafka_circuit_breaker = CircuitBreaker(
                name=f"{settings.SERVICE_NAME}.kafka_producer",
                failure_threshold=settings.KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=timedelta(seconds=settings.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
                success_threshold=settings.KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                expected_exception=KafkaError,
            )
            circuit_breaker_registry.register("kafka_producer", kafka_circuit_breaker)

            # Create resilient wrapper using composition
            kafka_publisher = ResilientKafkaPublisher(
                delegate=base_kafka_bus,
                circuit_breaker=kafka_circuit_breaker,
                retry_interval=30,
            )
        else:
            # Use base KafkaBus without circuit breaker
            kafka_publisher = base_kafka_bus

        await kafka_publisher.start()
        return kafka_publisher

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

        return redis_client

    @provide(scope=Scope.APP)
    async def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        """Provide async database engine for File Service."""
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,  # Set to True for SQL debugging
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
        )
        return engine

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox configuration."""
        return settings.SERVICE_NAME


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
    def provide_file_repository(
        self,
        engine: AsyncEngine,
    ) -> FileRepositoryProtocol:
        """Provide minimal file repository implementation."""
        return MinimalFileRepository(engine)

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager for reliable event publishing."""
        return OutboxManager(outbox_repository, redis_client, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> EventPublisherProtocol:
        """Provide event publisher implementation using TRUE OUTBOX PATTERN."""
        return DefaultEventPublisher(outbox_manager, settings)

    @provide(scope=Scope.APP)
    def provide_text_extractor(self) -> TextExtractorProtocol:
        """Provide strategy-based text extractor implementation."""
        return StrategyBasedTextExtractor()

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
