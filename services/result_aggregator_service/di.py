"""Dependency injection configuration for Result Aggregator Service."""
from __future__ import annotations

from typing import AsyncIterator, cast

import aiohttp
from dishka import Provider, Scope, provide
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.redis_set_operations import RedisSetOperations

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.aggregator_service_impl import (
    AggregatorServiceImpl,
)
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.implementations.cache_manager_impl import (
    CacheManagerImpl,
)
from services.result_aggregator_service.implementations.event_processor_impl import (
    EventProcessorImpl,
)
from services.result_aggregator_service.implementations.security_impl import SecurityServiceImpl
from services.result_aggregator_service.implementations.state_store_redis_impl import (
    StateStoreRedisImpl,
)
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.protocols import (
    BatchQueryServiceProtocol,
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventProcessorProtocol,
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
    def provide_metrics(self) -> ResultAggregatorMetrics:
        """Provide metrics instance."""
        return ResultAggregatorMetrics()

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


class DatabaseProvider(Provider):
    """Provider for database components."""

    scope = Scope.APP

    @provide
    def provide_batch_repository(self, settings: Settings) -> BatchRepositoryProtocol:
        """Provide batch repository implementation."""
        return BatchRepositoryPostgresImpl(settings)


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
    def provide_batch_query_service(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol,
        settings: Settings,
    ) -> BatchQueryServiceProtocol:
        """Provide batch query service implementation."""
        return AggregatorServiceImpl(batch_repository, cache_manager, settings)

    @provide
    def provide_security_service(self, settings: Settings) -> SecurityServiceProtocol:
        """Provide security service implementation."""
        return SecurityServiceImpl(
            internal_api_key=settings.INTERNAL_API_KEY,
            allowed_service_ids=settings.ALLOWED_SERVICE_IDS,
        )


# Export all providers
__all__ = [
    "CoreInfrastructureProvider",
    "DatabaseProvider",
    "ServiceProvider",
]
