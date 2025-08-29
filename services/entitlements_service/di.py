"""Dependency injection providers for Entitlements Service.

This module provides Dishka container configuration with proper scoping
following established patterns for APP and REQUEST scopes.
"""

from __future__ import annotations

from datetime import timedelta

from aiokafka.errors import KafkaError
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol, RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.entitlements_service.config import Settings
from huleedu_service_libs.outbox.manager import OutboxManager
from services.entitlements_service.protocols import (
    CreditManagerProtocol,
    EntitlementsRepositoryProtocol,
    EventPublisherProtocol,
    PolicyLoaderProtocol,
    RateLimiterProtocol,
)


class CoreProvider(Provider):
    """Core infrastructure providers with proper scoping."""

    scope = Scope.APP

    @provide
    def provide_settings(self) -> Settings:
        """Provide service settings as singleton."""
        return Settings()

    @provide
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox and metrics."""
        return settings.SERVICE_NAME

    @provide
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return REGISTRY

    @provide
    def provide_database_metrics(self, engine: AsyncEngine) -> DatabaseMetrics:
        """Provide database metrics monitoring for Entitlements Service."""
        # Import here to avoid circular dependencies
        from services.entitlements_service.metrics import (
            setup_entitlements_service_database_monitoring,
        )

        return setup_entitlements_service_database_monitoring(
            engine=engine, service_name="entitlements_service"
        )

    @provide
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry."""
        registry = CircuitBreakerRegistry()

        # Only register circuit breakers if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            # Register Redis circuit breaker for rate limiting
            redis_circuit_breaker = CircuitBreaker(
                name=f"{settings.SERVICE_NAME}.redis",
                failure_threshold=3,
                recovery_timeout=timedelta(seconds=30),
                success_threshold=2,
                expected_exception=Exception,  # Redis connection errors
            )
            registry.register("redis", redis_circuit_breaker)

        return registry

    @provide
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client for policy caching and rate limiting."""
        client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await client.start()
        return client

    @provide
    async def provide_kafka_publisher(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaPublisherProtocol:
        """Provide Kafka publisher for event publishing with optional circuit breaker protection."""
        # Create base KafkaBus instance
        base_kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID,
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
            kafka_publisher = ResilientKafkaPublisher(base_kafka_bus, kafka_circuit_breaker)
        else:
            kafka_publisher = base_kafka_bus

        return kafka_publisher

    @provide
    def provide_session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """Provide database session factory."""
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )


class ImplementationProvider(Provider):
    """Implementation providers for concrete classes."""

    scope = Scope.REQUEST

    @provide
    def provide_repository(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> EntitlementsRepositoryProtocol:
        """Provide repository implementation based on configuration."""
        if settings.USE_MOCK_REPOSITORY:
            # Import here to avoid circular dependencies
            from services.entitlements_service.implementations.mock_repository_impl import (
                MockEntitlementsRepositoryImpl,
            )

            return MockEntitlementsRepositoryImpl()
        else:
            # Import here to avoid circular dependencies
            from services.entitlements_service.implementations.repository_impl import (
                EntitlementsRepositoryImpl,
            )

            return EntitlementsRepositoryImpl(session_factory)

    @provide
    def provide_policy_loader(
        self,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> PolicyLoaderProtocol:
        """Provide policy loader implementation."""
        # Import here to avoid circular dependencies
        from services.entitlements_service.implementations.policy_loader_impl import (
            PolicyLoaderImpl,
        )

        return PolicyLoaderImpl(
            redis_client=redis_client,
            config_path=settings.POLICY_FILE,
            cache_ttl=settings.POLICY_CACHE_TTL,
        )

    @provide
    def provide_rate_limiter(
        self,
        redis_client: AtomicRedisClientProtocol,
        policy_loader: PolicyLoaderProtocol,
        settings: Settings,
    ) -> RateLimiterProtocol:
        """Provide rate limiter implementation."""
        # Import here to avoid circular dependencies
        from services.entitlements_service.implementations.rate_limiter_impl import RateLimiterImpl

        return RateLimiterImpl(
            redis_client=redis_client,
            policy_loader=policy_loader,
            enabled=settings.RATE_LIMIT_ENABLED,
        )

    @provide
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager implementation."""
        return OutboxManager(
            outbox_repository=outbox_repository,
            redis_client=redis_client,
            service_name=settings.SERVICE_NAME,
        )

    @provide
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> EventPublisherProtocol:
        """Provide event publisher implementation."""
        # Import here to avoid circular dependencies
        from services.entitlements_service.implementations.event_publisher_impl import (
            EventPublisherImpl,
        )

        return EventPublisherImpl(
            outbox_manager=outbox_manager,
            settings=settings,
        )


class ServiceProvider(Provider):
    """Business logic service providers."""

    scope = Scope.REQUEST

    @provide
    def provide_credit_manager(
        self,
        repository: EntitlementsRepositoryProtocol,
        policy_loader: PolicyLoaderProtocol,
        rate_limiter: RateLimiterProtocol,
        event_publisher: EventPublisherProtocol,
    ) -> CreditManagerProtocol:
        """Provide credit manager implementation."""
        # Import here to avoid circular dependencies
        from services.entitlements_service.implementations.credit_manager_impl import (
            CreditManagerImpl,
        )

        return CreditManagerImpl(
            repository=repository,
            policy_loader=policy_loader,
            rate_limiter=rate_limiter,
            event_publisher=event_publisher,
        )


class EntitlementsServiceProvider(Provider):
    """Service-specific providers with engine dependency."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize with database engine."""
        super().__init__()
        self.engine = engine

    scope = Scope.APP

    @provide
    def provide_engine(self) -> AsyncEngine:
        """Provide the database engine passed during initialization."""
        return self.engine
