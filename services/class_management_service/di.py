from __future__ import annotations

from datetime import timedelta

from aiokafka.errors import KafkaError
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from services.class_management_service.config import Settings, settings
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
from services.class_management_service.metrics import (
    CmsMetrics,
    setup_class_management_database_monitoring,
)
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

    @provide(scope=Scope.APP)
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics monitoring for class management service."""
        return setup_class_management_database_monitoring(
            engine=engine, service_name=settings.SERVICE_NAME
        )


class RepositoryProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_class_repository(
        self,
        settings: Settings,
        engine: AsyncEngine,
        database_metrics: DatabaseMetrics,
    ) -> ClassRepositoryProtocol[UserClass, Student]:
        if settings.ENVIRONMENT == "test" or settings.USE_MOCK_REPOSITORY:
            return MockClassRepositoryImpl[UserClass, Student]()
        return PostgreSQLClassRepositoryImpl[UserClass, Student](engine, database_metrics)


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
    ) -> KafkaPublisherProtocol:
        """Provide Kafka bus for event publishing with optional circuit breaker protection."""
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

        # Register with app shutdown via weakref to avoid circular references
        # Store the shutdown function for cleanup
        if not hasattr(self, "_redis_shutdown_handlers"):
            self._redis_shutdown_handlers = []
        self._redis_shutdown_handlers.append(_shutdown_redis)

        return redis_client

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        kafka_bus: KafkaPublisherProtocol,
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

    async def shutdown_resources(self) -> None:
        """Shutdown Redis and other async resources managed by this provider."""
        if hasattr(self, "_redis_shutdown_handlers"):
            for shutdown_handler in self._redis_shutdown_handlers:
                try:
                    await shutdown_handler()
                except Exception as e:
                    # Log but don't raise to ensure all resources are cleaned up
                    from huleedu_service_libs.logging_utils import create_service_logger

                    logger = create_service_logger("cms.di.shutdown")
                    logger.error(f"Failed to shutdown Redis connection: {e}")
            self._redis_shutdown_handlers.clear()


class MetricsProvider(Provider):
    """Provides Prometheus metrics-related dependencies."""

    @provide(scope=Scope.APP)
    def provide_metrics(self, database_metrics: DatabaseMetrics) -> CmsMetrics:
        """Provide an application-scoped instance of the metrics container."""
        return CmsMetrics(database_metrics=database_metrics)

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide the default Prometheus collector registry."""
        return REGISTRY


def create_container() -> AsyncContainer:
    """Create and configure the application's dependency injection container."""
    # Store provider reference for cleanup
    global _service_provider
    _service_provider = ServiceProvider()

    return make_async_container(
        DatabaseProvider(),
        RepositoryProvider(),
        _service_provider,
        MetricsProvider(),
    )


# Global reference for cleanup
_service_provider: ServiceProvider | None = None


async def shutdown_container_resources() -> None:
    """Shutdown async resources managed by providers."""
    global _service_provider
    if _service_provider:
        await _service_provider.shutdown_resources()
