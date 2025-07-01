from __future__ import annotations

from datetime import timedelta
from typing import AsyncGenerator, cast

from aiokafka.errors import KafkaError
from config import Settings, settings
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from services.class_management_service.implementations.class_management_service_impl import (
    ClassManagementServiceImpl,
)
from services.class_management_service.implementations.class_repository_mock_impl import (
    MockClassRepositoryImpl,
)
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.implementations.event_publisher_impl import (
    DefaultClassEventPublisherImpl,
)
from services.class_management_service.metrics import CmsMetrics
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import (
    ClassEventPublisherProtocol,
    ClassManagementServiceProtocol,
    ClassRepositoryProtocol,
)


class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_engine(self, settings: Settings) -> AsyncEngine:
        return create_async_engine(settings.DATABASE_URL)

    @provide(scope=Scope.APP)
    def provide_sessionmaker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def provide_session(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session


class RepositoryProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def provide_class_repository(
        self, settings: Settings, session: AsyncSession
    ) -> ClassRepositoryProtocol[UserClass, Student]:
        if settings.ENVIRONMENT == "test" or settings.USE_MOCK_REPOSITORY:
            return MockClassRepositoryImpl[UserClass, Student]()
        return PostgreSQLClassRepositoryImpl[UserClass, Student](session)


class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return settings

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
    ) -> KafkaBus:
        """Provide Kafka bus for event publishing with optional circuit breaker protection."""
        # Create base KafkaBus instance
        base_kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}-producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )

        # Wrap with circuit breaker protection if enabled
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
            kafka_bus = ResilientKafkaPublisher(
                delegate=base_kafka_bus,
                circuit_breaker=kafka_circuit_breaker,
                retry_interval=30,
            )
        else:
            # Use base KafkaBus without circuit breaker
            kafka_bus = base_kafka_bus

        await kafka_bus.start()
        return kafka_bus

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

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        kafka_bus: KafkaBus,
        redis_client: AtomicRedisClientProtocol,
    ) -> ClassEventPublisherProtocol:
        return DefaultClassEventPublisherImpl(kafka_bus, redis_client)

    @provide(scope=Scope.REQUEST)
    def provide_class_management_service(
        self,
        repo: ClassRepositoryProtocol[UserClass, Student],
        publisher: ClassEventPublisherProtocol,
    ) -> ClassManagementServiceProtocol[UserClass, Student]:
        return ClassManagementServiceImpl[UserClass, Student](
            repo=repo,
            event_publisher=publisher,
            user_class_type=UserClass,
            student_type=Student,
        )


class MetricsProvider(Provider):
    """Provides Prometheus metrics-related dependencies."""

    @provide(scope=Scope.APP)
    def provide_metrics(self) -> CmsMetrics:
        """Provide an application-scoped instance of the metrics container."""
        return CmsMetrics()

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide the default Prometheus collector registry."""
        return REGISTRY


def create_container() -> AsyncContainer:
    """Create and configure the application's dependency injection container."""
    return make_async_container(
        DatabaseProvider(),
        RepositoryProvider(),
        ServiceProvider(),
        MetricsProvider(),
    )
