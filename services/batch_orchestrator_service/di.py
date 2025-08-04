"""Dependency injection configuration for Batch Orchestrator Service using Dishka."""

from __future__ import annotations

from datetime import timedelta

from aiohttp import ClientError, ClientSession
from aiokafka.errors import KafkaError
from common_core.pipeline_models import PhaseName
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from huleedu_service_libs.resilience.metrics_bridge import create_metrics_bridge
from huleedu_service_libs.resilience.resilient_client import make_resilient
from prometheus_client import CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.batch_orchestrator_service.config import Settings, settings
from services.batch_orchestrator_service.implementations.ai_feedback_initiator_impl import (
    AIFeedbackInitiatorImpl,
)
from services.batch_orchestrator_service.implementations.batch_conductor_client_impl import (
    BatchConductorClientImpl,
)
from services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler import (  # noqa: E501
    BatchContentProvisioningCompletedHandler,
)
from services.batch_orchestrator_service.implementations.batch_database_infrastructure import (
    BatchDatabaseInfrastructure,
)
from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
)
from services.batch_orchestrator_service.implementations.batch_pipeline_state_manager import (
    BatchPipelineStateManager,
)
from services.batch_orchestrator_service.implementations.batch_processing_service_impl import (
    BatchProcessingServiceImpl,
)
from services.batch_orchestrator_service.implementations.batch_repository_impl import (
    MockBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.batch_repository_postgres_impl import (
    PostgreSQLBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.batch_validation_errors_handler import (
    BatchValidationErrorsHandler,
)
from services.batch_orchestrator_service.implementations.cj_assessment_initiator_impl import (
    DefaultCJAssessmentInitiator,
)
from services.batch_orchestrator_service.implementations.client_pipeline_request_handler import (
    ClientPipelineRequestHandler,
)
from services.batch_orchestrator_service.implementations.els_batch_phase_outcome_handler import (
    ELSBatchPhaseOutcomeHandler,
)
from services.batch_orchestrator_service.implementations.essay_lifecycle_client_impl import (
    DefaultEssayLifecycleClientImpl,
)
from services.batch_orchestrator_service.implementations.event_publisher_impl import (
    DefaultBatchEventPublisherImpl,
)
from services.batch_orchestrator_service.implementations.nlp_initiator_impl import NLPInitiatorImpl
from services.batch_orchestrator_service.implementations.notification_service import (
    NotificationService,
)
from services.batch_orchestrator_service.implementations.outbox_manager import (
    OutboxManager,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)
from services.batch_orchestrator_service.implementations.spellcheck_initiator_impl import (
    SpellcheckInitiatorImpl,
)
from services.batch_orchestrator_service.implementations.student_associations_confirmed_handler import (  # noqa: E501
    StudentAssociationsConfirmedHandler,
)
from services.batch_orchestrator_service.implementations.student_matching_initiator_impl import (
    StudentMatchingInitiatorImpl,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer
from services.batch_orchestrator_service.metrics import (
    get_circuit_breaker_metrics,
    get_database_metrics,
)
from services.batch_orchestrator_service.protocols import (
    AIFeedbackInitiatorProtocol,
    BatchConductorClientProtocol,
    BatchEventPublisherProtocol,
    BatchProcessingServiceProtocol,
    BatchRepositoryProtocol,
    CJAssessmentInitiatorProtocol,
    EssayLifecycleClientProtocol,
    NLPInitiatorProtocol,
    PipelinePhaseCoordinatorProtocol,
    PipelinePhaseInitiatorProtocol,
    SpellcheckInitiatorProtocol,
    StudentMatchingInitiatorProtocol,
)


class CoreInfrastructureProvider(Provider):
    """Provider for core infrastructure dependencies (settings, metrics, Kafka, HTTP)."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return CollectorRegistry()

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
            # Create metrics bridge for kafka circuit breaker
            circuit_breaker_metrics = get_circuit_breaker_metrics()
            metrics_bridge = create_metrics_bridge(circuit_breaker_metrics, settings.SERVICE_NAME)

            kafka_circuit_breaker = CircuitBreaker(
                name="kafka_producer",
                failure_threshold=settings.KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=timedelta(seconds=settings.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
                success_threshold=settings.KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                expected_exception=KafkaError,
                metrics=metrics_bridge,
                service_name=settings.SERVICE_NAME,
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
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry with metrics integration."""
        registry = CircuitBreakerRegistry()

        # Only register circuit breakers if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            # Create metrics bridge for circuit breaker metrics
            circuit_breaker_metrics = get_circuit_breaker_metrics()
            metrics_bridge = create_metrics_bridge(circuit_breaker_metrics, settings.SERVICE_NAME)

            # Circuit breaker for Batch Conductor Service
            registry.register(
                "batch_conductor",
                CircuitBreaker(
                    name="batch_conductor",
                    failure_threshold=settings.BCS_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                    recovery_timeout=timedelta(
                        seconds=settings.BCS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
                    ),
                    success_threshold=settings.BCS_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                    expected_exception=ClientError,
                    metrics=metrics_bridge,
                    service_name=settings.SERVICE_NAME,
                ),
            )

            # Future: Add more circuit breakers here as needed
            # e.g., for Essay Lifecycle Service, external APIs, etc.

        return registry

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client for idempotency and pub/sub operations."""
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
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox configuration."""
        return settings.SERVICE_NAME


class RepositoryAndPublishingProvider(Provider):
    """Provider for data repository and event publishing dependencies."""

    @provide(scope=Scope.APP)
    async def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        """Provide async database engine for outbox pattern."""
        engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_pre_ping=True,  # Validate connections before use
        )
        return engine

    @provide(scope=Scope.APP)
    def provide_database_metrics(self, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics instance integrated with existing BOS metrics."""
        # Get existing BOS metrics dictionary to integrate database metrics
        database_metrics_dict = get_database_metrics()

        # Create database metrics instance with BOS service prefix and existing metrics
        return DatabaseMetrics(
            service_name="batch_orchestrator_service", metrics_dict=database_metrics_dict
        )

    @provide(scope=Scope.APP)
    def provide_batch_repository(
        self, settings: Settings, database_metrics: DatabaseMetrics
    ) -> BatchRepositoryProtocol:
        """Provide batch repository implementation based on environment configuration."""
        if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
            return MockBatchRepositoryImpl()
        else:
            return PostgreSQLBatchRepositoryImpl(settings, database_metrics)

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager for TRUE OUTBOX PATTERN."""
        return OutboxManager(outbox_repository, redis_client, settings)

    @provide(scope=Scope.APP)
    def provide_batch_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> BatchEventPublisherProtocol:
        """Provide batch event publisher implementation using TRUE OUTBOX PATTERN."""
        return DefaultBatchEventPublisherImpl(outbox_manager, settings)


class ExternalClientsProvider(Provider):
    """Provider for external service client dependencies."""

    @provide(scope=Scope.APP)
    def provide_essay_lifecycle_client(
        self,
        http_session: ClientSession,
        settings: Settings,
    ) -> EssayLifecycleClientProtocol:
        """Provide essay lifecycle service client implementation."""
        return DefaultEssayLifecycleClientImpl(http_session, settings)

    @provide(scope=Scope.APP)
    def provide_batch_conductor_client(
        self,
        http_session: ClientSession,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> BatchConductorClientProtocol:
        """Provide Batch Conductor Service HTTP client with optional circuit breaker."""
        # Create the base implementation
        base_client = BatchConductorClientImpl(http_session, settings)

        # Wrap with circuit breaker if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("batch_conductor")
            if circuit_breaker:
                return make_resilient(base_client, circuit_breaker)

        return base_client


class PhaseInitiatorsProvider(Provider):
    """Provider for pipeline phase initiator implementations."""

    @provide(scope=Scope.APP)
    def provide_cj_assessment_initiator(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> CJAssessmentInitiatorProtocol:
        """Provide CJ assessment initiator implementation."""
        return DefaultCJAssessmentInitiator(event_publisher, batch_repo)

    @provide(scope=Scope.APP)
    def provide_spellcheck_initiator(
        self,
        event_publisher: BatchEventPublisherProtocol,
    ) -> SpellcheckInitiatorProtocol:
        """Provide spellcheck initiator implementation."""
        return SpellcheckInitiatorImpl(event_publisher)

    @provide(scope=Scope.APP)
    def provide_student_matching_initiator(
        self,
        event_publisher: BatchEventPublisherProtocol,
    ) -> StudentMatchingInitiatorProtocol:
        """Provide student matching initiator implementation for Phase 1."""
        return StudentMatchingInitiatorImpl(event_publisher)

    @provide(scope=Scope.APP)
    def provide_ai_feedback_initiator(
        self,
        event_publisher: BatchEventPublisherProtocol,
    ) -> AIFeedbackInitiatorProtocol:
        """
        Provide AI feedback initiator implementation.

        TODO: AI Feedback Service is not yet implemented - commands will be queued.
        """
        return AIFeedbackInitiatorImpl(event_publisher)

    @provide(scope=Scope.APP)
    def provide_nlp_initiator(
        self,
        event_publisher: BatchEventPublisherProtocol,
    ) -> NLPInitiatorProtocol:
        """
        Provide NLP initiator implementation.

        Publishes commands to Kafka topics consumed by the NLP Service.
        """
        return NLPInitiatorImpl(event_publisher)


class NotificationServiceProvider(Provider):
    """Provider for notification service dependencies."""

    @provide(scope=Scope.APP)
    def provide_notification_service(
        self,
        redis_client: AtomicRedisClientProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> NotificationService:
        """Provide notification service for real-time updates."""
        return NotificationService(redis_client, batch_repo)


class StateManagementProvider(Provider):
    """Provider for pipeline state management dependencies."""

    @provide(scope=Scope.APP)
    def provide_database_infrastructure(
        self,
        settings: Settings,
        database_metrics: DatabaseMetrics,
    ) -> BatchDatabaseInfrastructure:
        """Provide database infrastructure for batch operations."""
        return BatchDatabaseInfrastructure(settings, database_metrics)

    @provide(scope=Scope.APP)
    def provide_pipeline_state_manager(
        self,
        db_infrastructure: BatchDatabaseInfrastructure,
    ) -> BatchPipelineStateManager:
        """Provide pipeline state manager for state persistence."""
        return BatchPipelineStateManager(db_infrastructure)


class PipelineCoordinationProvider(Provider):
    """Provider for high-level pipeline coordination and processing services."""

    @provide(scope=Scope.APP)
    def provide_pipeline_phase_coordinator(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
        redis_client: AtomicRedisClientProtocol,
        notification_service: NotificationService,
        state_manager: BatchPipelineStateManager,
    ) -> PipelinePhaseCoordinatorProtocol:
        """Provide pipeline phase coordinator implementation with extracted services."""
        return DefaultPipelinePhaseCoordinator(
            batch_repo, phase_initiators_map, redis_client, notification_service, state_manager
        )

    @provide(scope=Scope.APP)
    def provide_batch_processing_service(
        self,
        batch_repo: BatchRepositoryProtocol,
        event_publisher: BatchEventPublisherProtocol,
        settings: Settings,
    ) -> BatchProcessingServiceProtocol:
        """Provide batch processing service implementation."""
        return BatchProcessingServiceImpl(batch_repo, event_publisher, settings)


class EventHandlingProvider(Provider):
    """Provider for event handling and Kafka consumer dependencies."""

    @provide(scope=Scope.APP)
    def provide_batch_essays_ready_handler(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> BatchEssaysReadyHandler:
        """Provide BatchEssaysReady message handler."""
        return BatchEssaysReadyHandler(event_publisher, batch_repo)

    @provide(scope=Scope.APP)
    def provide_els_batch_phase_outcome_handler(
        self,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
    ) -> ELSBatchPhaseOutcomeHandler:
        """Provide ELSBatchPhaseOutcome message handler."""
        return ELSBatchPhaseOutcomeHandler(phase_coordinator)

    @provide(scope=Scope.APP)
    def provide_client_pipeline_request_handler(
        self,
        bcs_client: BatchConductorClientProtocol,
        batch_repo: BatchRepositoryProtocol,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
    ) -> ClientPipelineRequestHandler:
        """Provide ClientBatchPipelineRequest message handler."""
        return ClientPipelineRequestHandler(bcs_client, batch_repo, phase_coordinator)

    @provide(scope=Scope.APP)
    def provide_student_associations_confirmed_handler(
        self,
        batch_repo: BatchRepositoryProtocol,
    ) -> StudentAssociationsConfirmedHandler:
        """Provide StudentAssociationsConfirmed message handler."""
        return StudentAssociationsConfirmedHandler(batch_repo)

    @provide(scope=Scope.APP)
    def provide_batch_content_provisioning_completed_handler(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
    ) -> BatchContentProvisioningCompletedHandler:
        """Provide BatchContentProvisioningCompleted message handler for Phase 1."""
        return BatchContentProvisioningCompletedHandler(batch_repo, phase_initiators_map)

    @provide(scope=Scope.APP)
    def provide_batch_validation_errors_handler(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> BatchValidationErrorsHandler:
        """Provide BatchValidationErrors message handler for dual-event architecture."""
        return BatchValidationErrorsHandler(event_publisher, batch_repo)

    @provide(scope=Scope.APP)
    def provide_batch_kafka_consumer(
        self,
        settings: Settings,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
        batch_content_provisioning_completed_handler: BatchContentProvisioningCompletedHandler,
        batch_validation_errors_handler: BatchValidationErrorsHandler,
        els_batch_phase_outcome_handler: ELSBatchPhaseOutcomeHandler,
        client_pipeline_request_handler: ClientPipelineRequestHandler,
        student_associations_confirmed_handler: StudentAssociationsConfirmedHandler,
        redis_client: AtomicRedisClientProtocol,
    ) -> BatchKafkaConsumer:
        """Provide Kafka consumer with idempotency support."""
        return BatchKafkaConsumer(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=settings.KAFKA_CONSUMER_GROUP_ID,
            batch_essays_ready_handler=batch_essays_ready_handler,
            batch_content_provisioning_completed_handler=batch_content_provisioning_completed_handler,
            batch_validation_errors_handler=batch_validation_errors_handler,
            els_batch_phase_outcome_handler=els_batch_phase_outcome_handler,
            client_pipeline_request_handler=client_pipeline_request_handler,
            student_associations_confirmed_handler=student_associations_confirmed_handler,
            redis_client=redis_client,
        )


class InitiatorMapProvider(Provider):
    """Provider for phase initiators map for dynamic dispatch."""

    @provide(scope=Scope.APP)
    def provide_phase_initiators_map(
        self,
        spellcheck_initiator: SpellcheckInitiatorProtocol,
        cj_assessment_initiator: CJAssessmentInitiatorProtocol,
        ai_feedback_initiator: AIFeedbackInitiatorProtocol,
        nlp_initiator: NLPInitiatorProtocol,
        student_matching_initiator: StudentMatchingInitiatorProtocol,
    ) -> dict[PhaseName, PipelinePhaseInitiatorProtocol]:
        """
        Provide complete phase initiators map for dynamic dispatch.

        This map is central to the generic orchestration system,
        enabling type-safe dynamic dispatch based on PhaseName enum.

        TODO: AI Feedback service is not yet implemented - commands will be queued.
        NLP Service is implemented and consuming commands.
        """
        return {
            PhaseName.SPELLCHECK: spellcheck_initiator,
            PhaseName.CJ_ASSESSMENT: cj_assessment_initiator,
            PhaseName.AI_FEEDBACK: ai_feedback_initiator,  # TODO: Service not implemented
            PhaseName.NLP: nlp_initiator,  # Phase 2 text analysis
            PhaseName.STUDENT_MATCHING: student_matching_initiator,  # Phase 1 student matching
        }
