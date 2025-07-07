"""Dependency injection configuration for Essay Lifecycle Service using Dishka."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from datetime import timedelta

from aiohttp import ClientSession
from aiokafka.errors import KafkaError
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from opentelemetry.trace import Tracer
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.config import settings as app_settings
from services.essay_lifecycle_service.implementations.batch_command_handler_impl import (
    DefaultBatchCommandHandler,
)
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker,
)
from services.essay_lifecycle_service.implementations.batch_phase_coordinator_impl import (
    DefaultBatchPhaseCoordinator,
)
from services.essay_lifecycle_service.implementations.cj_assessment_command_handler import (
    CJAssessmentCommandHandler,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.implementations.event_publisher import DefaultEventPublisher
from services.essay_lifecycle_service.implementations.future_services_command_handlers import (
    FutureServicesCommandHandler,
)
from services.essay_lifecycle_service.implementations.metrics_collector import (
    DefaultMetricsCollector,
)
from services.essay_lifecycle_service.implementations.service_request_dispatcher import (
    DefaultSpecializedServiceRequestDispatcher,
)
from services.essay_lifecycle_service.implementations.service_result_handler_impl import (
    DefaultServiceResultHandler,
)
from services.essay_lifecycle_service.implementations.spellcheck_command_handler import (
    SpellcheckCommandHandler,
)
from services.essay_lifecycle_service.metrics import setup_essay_lifecycle_database_monitoring
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    BatchEssayTracker,
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
    EventPublisher,
    MetricsCollector,
    ServiceResultHandler,
    SpecializedServiceRequestDispatcher,
)
from services.essay_lifecycle_service.state_store import SQLiteEssayStateStore


class CoreInfrastructureProvider(Provider):
    """Provider for core infrastructure dependencies (settings, metrics, Kafka, HTTP)."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return app_settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_tracer(self) -> Tracer:
        """Provide OpenTelemetry tracer."""
        from opentelemetry import trace

        return trace.get_tracer("essay_lifecycle_service")

    @provide(scope=Scope.APP)
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry."""
        registry = CircuitBreakerRegistry()

        # Only register circuit breakers if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            # Future: Add more circuit breakers here as needed
            # e.g., for Content Service, external APIs, etc.
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
        """Provide Redis client for idempotency and pub/sub operations."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis", redis_url=settings.REDIS_URL
        )
        await redis_client.start()

        # Register shutdown finalizer to prevent connection leaks
        async def _shutdown_redis() -> None:
            await redis_client.stop()

        # TODO Note: In production, this would be registered with the app lifecycle
        # For now, we rely on container cleanup

        # RedisClient implements all AtomicRedisClientProtocol methods
        return cast(AtomicRedisClientProtocol, redis_client)

    @provide(scope=Scope.APP)
    def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        """Provide database engine for metrics setup."""
        from sqlalchemy.ext.asyncio import create_async_engine
        
        return create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
        )

    @provide(scope=Scope.APP)
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics monitoring for essay lifecycle service."""
        return setup_essay_lifecycle_database_monitoring(
            engine=engine, service_name=settings.SERVICE_NAME
        )

    @provide(scope=Scope.APP)
    async def provide_essay_repository(
        self, settings: Settings, database_metrics: DatabaseMetrics, engine: AsyncEngine
    ) -> EssayRepositoryProtocol:
        """
        Provide essay repository implementation with environment-based selection.

        Uses SQLite for development/testing and PostgreSQL for production,
        following the same pattern as BOS BatchRepositoryProtocol.
        """
        if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
            # Development/testing: use SQLite implementation
            store = SQLiteEssayStateStore(
                database_path=settings.DATABASE_PATH, timeout=settings.DATABASE_TIMEOUT
            )
            await store.initialize()
            return store
        else:
            # Production: use PostgreSQL implementation with database metrics
            postgres_repo = PostgreSQLEssayRepository(settings, database_metrics, engine)
            await postgres_repo.initialize_db_schema()
            return postgres_repo


class ServiceClientsProvider(Provider):
    """Provider for external service client implementations."""

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
        batch_tracker: BatchEssayTracker,
    ) -> EventPublisher:
        """Provide event publisher implementation with Redis support and batch tracking."""
        return DefaultEventPublisher(kafka_bus, settings, redis_client, batch_tracker)

    @provide(scope=Scope.APP)
    def provide_metrics_collector(self, registry: CollectorRegistry) -> MetricsCollector:
        """Provide metrics collector implementation."""
        return DefaultMetricsCollector(registry)

    @provide(scope=Scope.APP)
    def provide_specialized_service_request_dispatcher(
        self, kafka_bus: KafkaPublisherProtocol, settings: Settings
    ) -> SpecializedServiceRequestDispatcher:
        """Provide specialized service request dispatcher implementation."""
        return DefaultSpecializedServiceRequestDispatcher(kafka_bus, settings)


class CommandHandlerProvider(Provider):
    """Provider for command handler implementations."""

    @provide(scope=Scope.APP)
    def provide_spellcheck_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> SpellcheckCommandHandler:
        """Provide spellcheck command handler implementation."""
        return SpellcheckCommandHandler(repository, request_dispatcher, event_publisher)

    @provide(scope=Scope.APP)
    def provide_cj_assessment_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> CJAssessmentCommandHandler:
        """Provide CJ assessment command handler implementation."""
        return CJAssessmentCommandHandler(repository, request_dispatcher, event_publisher)

    @provide(scope=Scope.APP)
    def provide_future_services_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> FutureServicesCommandHandler:
        """Provide future services command handler implementation."""
        return FutureServicesCommandHandler(repository, request_dispatcher, event_publisher)

    @provide(scope=Scope.APP)
    def provide_batch_command_handler(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        cj_assessment_handler: CJAssessmentCommandHandler,
        future_handler: FutureServicesCommandHandler,
    ) -> BatchCommandHandler:
        """Provide batch command handler implementation."""
        return DefaultBatchCommandHandler(spellcheck_handler, cj_assessment_handler, future_handler)


class BatchCoordinationProvider(Provider):
    """Provider for batch coordination and tracking implementations."""

    @provide(scope=Scope.APP)
    def provide_batch_coordination_handler(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        event_publisher: EventPublisher,
    ) -> BatchCoordinationHandler:
        """Provide batch coordination handler implementation."""
        return DefaultBatchCoordinationHandler(batch_tracker, repository, event_publisher)

    @provide(scope=Scope.APP)
    def provide_batch_essay_tracker(self) -> BatchEssayTracker:
        """Provide batch essay tracker implementation."""
        return DefaultBatchEssayTracker()

    @provide(scope=Scope.APP)
    def provide_batch_phase_coordinator(
        self,
        repository: EssayRepositoryProtocol,
        event_publisher: EventPublisher,
    ) -> BatchPhaseCoordinator:
        """Provide batch phase coordinator implementation."""
        return DefaultBatchPhaseCoordinator(repository, event_publisher)

    @provide(scope=Scope.APP)
    def provide_service_result_handler(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
    ) -> ServiceResultHandler:
        """Provide service result handler implementation."""
        return DefaultServiceResultHandler(repository, batch_coordinator)
