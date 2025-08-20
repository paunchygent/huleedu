"""Dependency injection configuration for Essay Lifecycle Service using Dishka."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from datetime import timedelta

from aiohttp import ClientSession
from aiokafka.errors import KafkaError
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from opentelemetry.trace import Tracer
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

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
from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.implementations.batch_phase_coordinator_impl import (
    DefaultBatchPhaseCoordinator,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.cj_assessment_command_handler import (
    CJAssessmentCommandHandler,
)
from services.essay_lifecycle_service.implementations.consumer_health_monitor_impl import (
    ConsumerHealthMonitorImpl,
)
from services.essay_lifecycle_service.implementations.consumer_recovery_manager_impl import (
    ConsumerRecoveryManagerImpl,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.implementations.metrics_collector import (
    DefaultMetricsCollector,
)
from services.essay_lifecycle_service.implementations.mock_essay_repository import (
    MockEssayRepository,
)
from services.essay_lifecycle_service.implementations.nlp_command_handler import (
    NlpCommandHandler,
)
from services.essay_lifecycle_service.implementations.outbox_manager import OutboxManager
from services.essay_lifecycle_service.implementations.redis_batch_queries import RedisBatchQueries
from services.essay_lifecycle_service.implementations.redis_batch_state import RedisBatchState
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_pending_content_ops import (
    RedisPendingContentOperations,
)
from services.essay_lifecycle_service.implementations.redis_script_manager import RedisScriptManager
from services.essay_lifecycle_service.implementations.redis_slot_operations import (
    RedisSlotOperations,
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
from services.essay_lifecycle_service.notification_projector import ELSNotificationProjector
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    BatchEssayTracker,
    BatchPhaseCoordinator,
    ConsumerRecoveryManager,
    ContentAssignmentProtocol,
    EssayRepositoryProtocol,
    KafkaConsumerHealthMonitor,
    MetricsCollector,
    ServiceResultHandler,
    SpecializedServiceRequestDispatcher,
    StudentAssociationHandler,
    TopicNamingProtocol,
)


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
    def provide_metrics(self) -> dict[str, Any]:
        """Provide shared Prometheus metrics for route injection."""
        from services.essay_lifecycle_service.metrics import get_metrics

        return get_metrics()

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
    ) -> AsyncGenerator[KafkaPublisherProtocol, None]:
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

        try:
            # Yield for container usage; Dishka will run finalizer after container closes
            yield kafka_publisher  # type: ignore[misc]
        finally:
            try:
                await kafka_publisher.stop()
            except Exception:
                pass

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> AsyncGenerator[ClientSession, None]:
        """Provide HTTP client session with automatic cleanup."""
        session = ClientSession()
        try:
            yield session  # type: ignore[misc]
        finally:
            try:
                await session.close()
            except Exception:
                pass

    @provide(scope=Scope.APP)
    async def provide_redis_client(
        self, settings: Settings
    ) -> AsyncGenerator[AtomicRedisClientProtocol, None]:
        """Provide Redis client for idempotency and pub/sub operations with cleanup."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis", redis_url=settings.REDIS_URL
        )
        await redis_client.start()
        try:
            yield redis_client  # type: ignore[misc]
        finally:
            try:
                await redis_client.stop()
            except Exception:
                pass

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
    def provide_session_factory(self, engine: AsyncEngine) -> async_sessionmaker:
        """Provide async session factory for transaction management."""
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.APP)
    async def initialize_database_schema(self, engine: AsyncEngine, settings: Settings) -> None:
        """Initialize database schema at startup."""
        if settings.ENVIRONMENT != "testing":
            from services.essay_lifecycle_service.models_db import Base

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    @provide(scope=Scope.APP)
    async def provide_essay_repository(
        self,
        session_factory: async_sessionmaker,
        database_metrics: DatabaseMetrics,
        settings: Settings,
    ) -> EssayRepositoryProtocol:
        """
        Provide essay repository implementation with environment-based selection.

        Uses MockEssayRepository for development/testing and PostgreSQL for production,
        following the session factory injection pattern.
        """
        if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
            # Development/testing: use fast in-memory mock implementation
            return MockEssayRepository()
        else:
            # Production: use PostgreSQL implementation with injected session factory
            return PostgreSQLEssayRepository(session_factory, database_metrics)

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox configuration."""
        return settings.SERVICE_NAME


class ServiceClientsProvider(Provider):
    """Provider for external service client implementations."""

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
    def provide_topic_naming(self) -> TopicNamingProtocol:
        """Provide topic naming implementation."""
        from services.essay_lifecycle_service.implementations.topic_naming import DefaultTopicNaming

        return DefaultTopicNaming()

    @provide(scope=Scope.APP)
    def provide_batch_lifecycle_publisher(
        self,
        settings: Settings,
        outbox_manager: OutboxManager,
        topic_naming: TopicNamingProtocol,
    ) -> BatchLifecyclePublisher:
        """Provide batch lifecycle publisher using TRUE OUTBOX PATTERN for transactional safety."""
        return BatchLifecyclePublisher(settings, outbox_manager, topic_naming)

    @provide(scope=Scope.APP)
    def provide_notification_projector(
        self,
        kafka_publisher: KafkaPublisherProtocol,
    ) -> ELSNotificationProjector:
        """Provide notification projector for teacher notifications."""
        return ELSNotificationProjector(kafka_publisher)

    @provide(scope=Scope.APP)
    def provide_metrics_collector(self, registry: CollectorRegistry) -> MetricsCollector:
        """Provide metrics collector implementation."""
        return DefaultMetricsCollector(registry)

    @provide(scope=Scope.APP)
    def provide_specialized_service_request_dispatcher(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
        outbox_repository: OutboxRepositoryProtocol,
    ) -> SpecializedServiceRequestDispatcher:
        """Provide specialized service request dispatcher implementation with outbox support."""
        return DefaultSpecializedServiceRequestDispatcher(kafka_bus, settings, outbox_repository)

    @provide(scope=Scope.APP)
    def provide_kafka_consumer_health_monitor(
        self, settings: Settings
    ) -> KafkaConsumerHealthMonitor:
        """Provide Kafka consumer health monitor for self-healing mechanism."""
        return ConsumerHealthMonitorImpl(
            health_check_interval=getattr(settings, "KAFKA_HEALTH_CHECK_INTERVAL", 30),
            max_idle_seconds=getattr(settings, "KAFKA_MAX_IDLE_SECONDS", 60),
        )

    @provide(scope=Scope.APP)
    def provide_consumer_recovery_manager(
        self, health_monitor: KafkaConsumerHealthMonitor
    ) -> ConsumerRecoveryManager:
        """Provide consumer recovery manager for self-healing with circuit breaker."""
        # Create circuit breaker for recovery attempts
        recovery_circuit_breaker = CircuitBreaker(
            failure_threshold=3,  # Allow 3 recovery failures before opening
            recovery_timeout=timedelta(minutes=2),  # Wait 2 minutes before retry
            success_threshold=1,  # Single success closes circuit
            expected_exception=Exception,
            name="consumer_recovery",
        )

        return ConsumerRecoveryManagerImpl(
            health_monitor=health_monitor,
            circuit_breaker=recovery_circuit_breaker,
        )


class CommandHandlerProvider(Provider):
    """Provider for command handler implementations."""

    @provide(scope=Scope.APP)
    def provide_spellcheck_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        session_factory: async_sessionmaker,
    ) -> SpellcheckCommandHandler:
        """Provide spellcheck command handler implementation."""
        return SpellcheckCommandHandler(repository, request_dispatcher, session_factory)

    @provide(scope=Scope.APP)
    def provide_cj_assessment_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        session_factory: async_sessionmaker,
    ) -> CJAssessmentCommandHandler:
        """Provide CJ assessment command handler implementation."""
        return CJAssessmentCommandHandler(repository, request_dispatcher, session_factory)

    @provide(scope=Scope.APP)
    def provide_nlp_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        session_factory: async_sessionmaker,
    ) -> NlpCommandHandler:
        """Provide NLP command handler implementation."""
        return NlpCommandHandler(repository, request_dispatcher, session_factory)

    @provide(scope=Scope.APP)
    def provide_student_matching_command_handler(
        self,
        repository: EssayRepositoryProtocol,
        batch_tracker: BatchEssayTracker,
        outbox_manager: OutboxManager,
        session_factory: async_sessionmaker,
    ) -> Any:  # StudentMatchingCommandHandler
        """Provide student matching command handler for Phase 1 NLP integration."""
        from services.essay_lifecycle_service.implementations.student_matching_command_handler import (
            StudentMatchingCommandHandler,
        )

        return StudentMatchingCommandHandler(
            repository, batch_tracker, outbox_manager, session_factory
        )

    @provide(scope=Scope.APP)
    def provide_batch_command_handler(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        cj_assessment_handler: CJAssessmentCommandHandler,
        nlp_handler: NlpCommandHandler,
        student_matching_handler: Any,  # StudentMatchingCommandHandler
    ) -> BatchCommandHandler:
        """Provide batch command handler implementation."""

        # Need to create an extended version that includes student matching
        return DefaultBatchCommandHandler(
            spellcheck_handler, cj_assessment_handler, nlp_handler, student_matching_handler
        )


class BatchCoordinationProvider(Provider):
    """Provider for batch coordination and tracking implementations."""

    @provide(scope=Scope.APP)
    def provide_student_association_handler(
        self,
        repository: EssayRepositoryProtocol,
        batch_tracker: BatchEssayTracker,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        session_factory: async_sessionmaker,
    ) -> StudentAssociationHandler:
        """Provide student association handler for Phase 1 NLP integration."""
        from services.essay_lifecycle_service.implementations.student_association_handler import (
            StudentAssociationHandler as StudentAssociationHandlerImpl,
        )

        return StudentAssociationHandlerImpl(
            repository, batch_tracker, batch_lifecycle_publisher, session_factory
        )

    @provide(scope=Scope.APP)
    def provide_content_assignment_service(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
    ) -> ContentAssignmentProtocol:
        """Provide content assignment domain service implementation."""
        from services.essay_lifecycle_service.domain_services import ContentAssignmentService

        return ContentAssignmentService(
            batch_tracker=batch_tracker,
            repository=repository,
            batch_lifecycle_publisher=batch_lifecycle_publisher,
        )

    @provide(scope=Scope.APP)
    def provide_batch_coordination_handler(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        pending_content_ops: RedisPendingContentOperations,
        content_assignment_service: ContentAssignmentProtocol,
        session_factory: async_sessionmaker,
    ) -> BatchCoordinationHandler:
        """Provide batch coordination handler implementation with proper DI."""
        handler = DefaultBatchCoordinationHandler(
            batch_tracker,
            repository,
            batch_lifecycle_publisher,
            pending_content_ops,
            content_assignment_service,
            session_factory,
        )
        return handler

    @provide(scope=Scope.APP)
    def provide_batch_tracker_persistence(self, engine: AsyncEngine) -> BatchTrackerPersistence:
        """Provide batch tracker persistence implementation."""
        return BatchTrackerPersistence(engine)

    @provide(scope=Scope.APP)
    def provide_redis_script_manager(
        self, redis_client: AtomicRedisClientProtocol
    ) -> RedisScriptManager:
        """Provide Redis script manager for Lua script operations."""
        return RedisScriptManager(redis_client)

    @provide(scope=Scope.APP)
    def provide_redis_slot_operations(
        self, redis_client: AtomicRedisClientProtocol, script_manager: RedisScriptManager
    ) -> RedisSlotOperations:
        """Provide Redis slot operations for atomic slot assignment."""
        return RedisSlotOperations(redis_client, script_manager)

    @provide(scope=Scope.APP)
    def provide_redis_batch_state(
        self, redis_client: AtomicRedisClientProtocol, script_manager: RedisScriptManager
    ) -> RedisBatchState:
        """Provide Redis batch state management."""
        return RedisBatchState(
            redis_client,
            script_manager,
            default_timeout=86400,  # 24 hours
        )

    @provide(scope=Scope.APP)
    def provide_redis_batch_queries(
        self, redis_client: AtomicRedisClientProtocol, script_manager: RedisScriptManager
    ) -> RedisBatchQueries:
        """Provide Redis batch query operations."""
        return RedisBatchQueries(redis_client, script_manager)

    @provide(scope=Scope.APP)
    def provide_redis_failure_tracker(
        self, redis_client: AtomicRedisClientProtocol, script_manager: RedisScriptManager
    ) -> RedisFailureTracker:
        """Provide Redis validation failure tracking."""
        return RedisFailureTracker(redis_client, script_manager)

    @provide(scope=Scope.APP)
    def provide_redis_pending_content_ops(
        self, redis_client: AtomicRedisClientProtocol
    ) -> RedisPendingContentOperations:
        """Provide Redis pending content operations."""
        return RedisPendingContentOperations(redis_client)

    @provide(scope=Scope.APP)
    async def provide_batch_essay_tracker(
        self,
        persistence: BatchTrackerPersistence,
        batch_state: RedisBatchState,
        batch_queries: RedisBatchQueries,
        failure_tracker: RedisFailureTracker,
        slot_operations: RedisSlotOperations,
        pending_content_ops: RedisPendingContentOperations,
    ) -> BatchEssayTracker:
        """Provide batch essay tracker implementation with direct domain class composition."""
        tracker = DefaultBatchEssayTracker(
            persistence,
            batch_state,
            batch_queries,
            failure_tracker,
            slot_operations,
            pending_content_ops,
        )
        await tracker.initialize_from_database()
        return tracker

    @provide(scope=Scope.APP)
    def provide_batch_phase_coordinator(
        self,
        repository: EssayRepositoryProtocol,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        batch_tracker: BatchEssayTracker,
        session_factory: async_sessionmaker,
        notification_projector: ELSNotificationProjector,
    ) -> BatchPhaseCoordinator:
        """Provide batch phase coordinator implementation with notification projector."""
        return DefaultBatchPhaseCoordinator(
            repository,
            batch_lifecycle_publisher,
            batch_tracker,
            session_factory,
            notification_projector,
        )

    @provide(scope=Scope.APP)
    def provide_service_result_handler(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,
    ) -> ServiceResultHandler:
        """Provide service result handler implementation."""
        return DefaultServiceResultHandler(repository, batch_coordinator, session_factory)
