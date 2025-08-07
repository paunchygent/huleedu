"""Dependency injection configuration for Result Aggregator Service."""

from __future__ import annotations

from datetime import timedelta
from typing import AsyncIterator, cast

import aiohttp
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.outbox import OutboxRepositoryProtocol, PostgreSQLOutboxRepository
from huleedu_service_libs.protocols import (
    AtomicRedisClientProtocol,
    KafkaPublisherProtocol,
    RedisClientProtocol,
)
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.redis_set_operations import RedisSetOperations
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.aggregator_service_impl import (
    AggregatorServiceImpl,
)
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.implementations.bos_client_impl import (
    BatchOrchestratorClientImpl,
)
from services.result_aggregator_service.implementations.bos_data_transformer import (
    BOSDataTransformer,
)
from services.result_aggregator_service.implementations.cache_manager_impl import (
    CacheManagerImpl,
)
from services.result_aggregator_service.implementations.event_processor_impl import (
    EventProcessorImpl,
)
from services.result_aggregator_service.implementations.event_publisher_impl import (
    ResultEventPublisher,
)
from services.result_aggregator_service.implementations.outbox_manager import OutboxManager
from services.result_aggregator_service.implementations.security_impl import SecurityServiceImpl
from services.result_aggregator_service.implementations.state_store_redis_impl import (
    StateStoreRedisImpl,
)
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer
from services.result_aggregator_service.metrics import (
    ResultAggregatorMetrics,
    setup_result_aggregator_database_monitoring,
)
from services.result_aggregator_service.protocols import (
    BatchOrchestratorClientProtocol,
    BatchQueryServiceProtocol,
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventProcessorProtocol,
    EventPublisherProtocol,
    OutboxManagerProtocol,
    SecurityServiceProtocol,
    StateStoreProtocol,
)

logger = create_service_logger("result_aggregator.di")


class CoreInfrastructureProvider(Provider):
    """Provider for core infrastructure components."""

    scope = Scope.APP

    @provide
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return Settings()

    @provide
    def provide_metrics(self, database_metrics: DatabaseMetrics) -> ResultAggregatorMetrics:
        """Provide metrics instance with database metrics integration."""
        return ResultAggregatorMetrics(database_metrics=database_metrics)

    @provide
    async def provide_http_session(self) -> AsyncIterator[aiohttp.ClientSession]:
        """Provide HTTP client session."""
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            yield session

    @provide
    async def provide_redis_client(self, settings: Settings) -> AsyncIterator[RedisClientProtocol]:
        """Provide Redis client instance."""
        redis_client = RedisClient(
            client_id=f"ras-{settings.SERVICE_NAME}", redis_url=settings.REDIS_URL
        )
        await redis_client.start()
        try:
            yield cast(RedisClientProtocol, redis_client)
        finally:
            await redis_client.stop()

    # DLQ handling removed - this is BOS responsibility

    @provide
    def provide_kafka_consumer(
        self,
        settings: Settings,
        redis_client: RedisClientProtocol,
        metrics: ResultAggregatorMetrics,
        event_processor: EventProcessorProtocol,
    ) -> ResultAggregatorKafkaConsumer:
        """Provide Kafka consumer instance."""
        return ResultAggregatorKafkaConsumer(
            settings=settings,
            redis_client=redis_client,
            event_processor=event_processor,
            metrics=metrics,
        )

    @provide
    def provide_collector_registry(self) -> CollectorRegistry:
        """Provide the default Prometheus collector registry."""
        return REGISTRY

    @provide
    async def provide_kafka_bus(self, settings: Settings) -> AsyncIterator[KafkaBus]:
        """Provide KafkaBus instance for event publishing."""
        kafka_bus = KafkaBus(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=f"{settings.SERVICE_NAME}-publisher",
        )
        await kafka_bus.start()
        try:
            yield kafka_bus
        finally:
            await kafka_bus.stop()

    @provide
    def provide_circuit_breaker(self, settings: Settings) -> CircuitBreaker:
        """Provide circuit breaker for Kafka publisher resilience."""
        return CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=timedelta(seconds=30),
            expected_exception=Exception,
            name="kafka_publisher_circuit",
        )

    @provide
    def provide_kafka_publisher(
        self, kafka_bus: KafkaBus, circuit_breaker: CircuitBreaker, settings: Settings
    ) -> KafkaPublisherProtocol:
        """Provide resilient Kafka publisher with circuit breaker pattern."""
        return ResilientKafkaPublisher(
            delegate=kafka_bus,
            circuit_breaker=circuit_breaker,
            fallback_handler=None,
            retry_interval=30,
        )


class DatabaseProvider(Provider):
    """Provider for database components."""

    scope = Scope.APP

    @provide
    def provide_batch_repository(
        self, settings: Settings, database_metrics: DatabaseMetrics, engine: AsyncEngine
    ) -> BatchRepositoryProtocol:
        """Provide batch repository implementation with metrics."""
        return BatchRepositoryPostgresImpl(settings, database_metrics, engine)

    @provide
    def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        """Provide database engine for metrics setup."""
        return create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    @provide
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics monitoring for result aggregator service."""
        return setup_result_aggregator_database_monitoring(
            engine=engine, service_name=settings.SERVICE_NAME
        )

    @provide
    def provide_outbox_repository(self, engine: AsyncEngine) -> OutboxRepositoryProtocol:
        """Provide outbox repository for transactional outbox pattern."""
        return PostgreSQLOutboxRepository(engine)


# RepositoryProvider removed - batch repository is now provided in DatabaseProvider


class ServiceProvider(Provider):
    """Provider for service implementations."""

    scope = Scope.APP

    @provide
    def provide_state_store(
        self, redis_client: RedisClientProtocol, settings: Settings
    ) -> StateStoreProtocol:
        """Provide state store implementation."""
        return StateStoreRedisImpl(redis_client, settings.REDIS_CACHE_TTL_SECONDS)

    @provide
    def provide_redis_set_operations(
        self, redis_client: RedisClientProtocol, settings: Settings
    ) -> RedisSetOperations:
        """Provide Redis SET operations."""
        client = cast(RedisClient, redis_client)
        return RedisSetOperations(client.client, f"ras-{settings.SERVICE_NAME}")

    @provide
    def provide_cache_manager(
        self,
        redis_client: RedisClientProtocol,
        redis_set_ops: RedisSetOperations,
        settings: Settings,
    ) -> CacheManagerProtocol:
        """Provide cache manager implementation."""
        return CacheManagerImpl(redis_client, redis_set_ops, settings.REDIS_CACHE_TTL_SECONDS)

    @provide
    def provide_event_processor(
        self,
        batch_repository: BatchRepositoryProtocol,
        state_store: StateStoreProtocol,
        cache_manager: CacheManagerProtocol,
    ) -> EventProcessorProtocol:
        """Provide event processor implementation."""
        return EventProcessorImpl(batch_repository, state_store, cache_manager)

    @provide
    def provide_bos_data_transformer(self) -> BOSDataTransformer:
        """Provide BOS data transformer."""
        return BOSDataTransformer()

    @provide
    def provide_bos_client(
        self, settings: Settings, http_session: aiohttp.ClientSession
    ) -> BatchOrchestratorClientProtocol:
        """Provide BOS client implementation."""
        return BatchOrchestratorClientImpl(settings, http_session)

    @provide
    def provide_batch_query_service(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol,
        bos_client: BatchOrchestratorClientProtocol,
        bos_transformer: BOSDataTransformer,
        settings: Settings,
    ) -> BatchQueryServiceProtocol:
        """Provide batch query service implementation."""
        return AggregatorServiceImpl(
            batch_repository, cache_manager, bos_client, bos_transformer, settings
        )

    @provide
    def provide_security_service(self, settings: Settings) -> SecurityServiceProtocol:
        """Provide security service implementation."""
        return SecurityServiceImpl(
            internal_api_key=settings.INTERNAL_API_KEY,
            allowed_service_ids=settings.ALLOWED_SERVICE_IDS,
        )

    @provide
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: RedisClientProtocol,
        settings: Settings,
    ) -> OutboxManagerProtocol:
        """Provide outbox manager for reliable event publishing."""
        # Cast RedisClientProtocol to AtomicRedisClientProtocol as they are compatible
        atomic_redis = cast(AtomicRedisClientProtocol, redis_client)
        return OutboxManager(outbox_repository, atomic_redis, settings)

    @provide
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManagerProtocol,
        settings: Settings,
    ) -> EventPublisherProtocol:
        """Provide event publisher for Result Aggregator Service.
        
        Note: NotificationProjector will be added in Session 3.1.
        """
        return ResultEventPublisher(
            outbox_manager=outbox_manager,
            settings=settings,
            notification_projector=None,  # Will be added in Session 3.1
        )


# Export all providers
__all__ = [
    "CoreInfrastructureProvider",
    "DatabaseProvider",
    "ServiceProvider",
]
