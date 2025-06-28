"""Dependency injection configuration for Result Aggregator Service."""
from typing import AsyncIterator, cast

import aiohttp
from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from huleedu_service_libs.kafka_bus import KafkaBus
# DLQ handling is BOS responsibility, not individual services
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient

from .config import Settings
from .implementations.aggregator_service_impl import AggregatorServiceImpl
from .implementations.batch_repository_postgres_impl import BatchRepositoryPostgresImpl
from .implementations.cache_manager_impl import CacheManagerImpl
from .implementations.event_processor_impl import EventProcessorImpl
from .implementations.security_impl import SecurityServiceImpl
from .implementations.state_store_redis_impl import StateStoreRedisImpl
from .kafka_consumer import ResultAggregatorKafkaConsumer
from .metrics import ResultAggregatorMetrics
from .protocols import (
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
    async def provide_kafka_bus(self, settings: Settings) -> AsyncIterator[KafkaBus]:
        """Provide Kafka bus instance."""
        kafka_bus = KafkaBus(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group_id=settings.KAFKA_CONSUMER_GROUP_ID,
            auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
            enable_auto_commit=False,  # Manual commits for reliability
            session_timeout_ms=settings.KAFKA_SESSION_TIMEOUT_MS,
            max_poll_records=settings.KAFKA_MAX_POLL_RECORDS
        )
        await kafka_bus.start()
        try:
            yield kafka_bus
        finally:
            await kafka_bus.stop()
    
    @provide
    async def provide_redis_client(self, settings: Settings) -> AsyncIterator[RedisClientProtocol]:
        """Provide Redis client instance."""
        redis_client = RedisClient(
            client_id=f"ras-{settings.SERVICE_NAME}",
            redis_url=settings.REDIS_URL
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
        kafka_bus: KafkaBus,
        redis_client: RedisClientProtocol,
        metrics: ResultAggregatorMetrics,
        settings: Settings
    ) -> ResultAggregatorKafkaConsumer:
        """Provide Kafka consumer instance."""
        from dishka import AsyncContainer
        container = from_context(AsyncContainer)
        
        return ResultAggregatorKafkaConsumer(
            kafka_bus=kafka_bus,
            redis_client=redis_client,
            container=container,
            metrics=metrics
        )


class DatabaseProvider(Provider):
    """Provider for database components."""
    
    @provide(scope=Scope.APP)
    async def provide_engine(self, settings: Settings) -> AsyncIterator[AsyncEngine]:
        """Provide database engine."""
        engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            echo=False
        )
        
        # Create tables if they don't exist
        from .models_db import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        try:
            yield engine
        finally:
            await engine.dispose()
    
    @provide(scope=Scope.APP)
    def provide_session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """Provide session factory."""
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    @provide(scope=Scope.REQUEST)
    async def provide_session(
        self,
        session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        """Provide database session."""
        async with session_factory() as session:
            yield session


class RepositoryProvider(Provider):
    """Provider for repository implementations."""
    
    scope = Scope.REQUEST
    
    @provide
    def provide_batch_repository(
        self,
        session: AsyncSession
    ) -> BatchRepositoryProtocol:
        """Provide batch repository implementation."""
        return BatchRepositoryPostgresImpl(session)


class ServiceProvider(Provider):
    """Provider for service implementations."""
    
    scope = Scope.REQUEST
    
    @provide
    def provide_state_store(
        self,
        redis_client: RedisClientProtocol,
        settings: Settings
    ) -> StateStoreProtocol:
        """Provide state store implementation."""
        return StateStoreRedisImpl(redis_client, settings.REDIS_CACHE_TTL_SECONDS)
    
    @provide
    def provide_cache_manager(
        self,
        redis_client: RedisClientProtocol,
        settings: Settings
    ) -> CacheManagerProtocol:
        """Provide cache manager implementation."""
        return CacheManagerImpl(redis_client, settings.REDIS_CACHE_TTL_SECONDS)
    
    @provide
    def provide_event_processor(
        self,
        batch_repository: BatchRepositoryProtocol,
        state_store: StateStoreProtocol,
        metrics: ResultAggregatorMetrics
    ) -> EventProcessorProtocol:
        """Provide event processor implementation."""
        return EventProcessorImpl(batch_repository, state_store, metrics)
    
    @provide
    def provide_batch_query_service(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol,
        settings: Settings
    ) -> BatchQueryServiceProtocol:
        """Provide batch query service implementation."""
        return AggregatorServiceImpl(batch_repository, cache_manager, settings)
    
    @provide
    def provide_security_service(
        self,
        settings: Settings
    ) -> SecurityServiceProtocol:
        """Provide security service implementation."""
        return SecurityServiceImpl(settings)


# Export all providers
__all__ = [
    "CoreInfrastructureProvider",
    "DatabaseProvider",
    "RepositoryProvider",
    "ServiceProvider"
]