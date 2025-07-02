"""Dependency injection configuration for Batch Orchestrator Service using Dishka."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from aiohttp import ClientError, ClientSession
from aiokafka.errors import KafkaError
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from huleedu_service_libs.resilience.resilient_client import make_resilient
from prometheus_client import CollectorRegistry

from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.config import Settings, settings
from services.batch_orchestrator_service.implementations.ai_feedback_initiator_impl import (
    AIFeedbackInitiatorImpl,
)
from services.batch_orchestrator_service.implementations.batch_conductor_client_impl import (
    BatchConductorClientImpl,
)
from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
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
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)
from services.batch_orchestrator_service.implementations.pipeline_state_manager import (
    PipelineStateManager,
)
from services.batch_orchestrator_service.implementations.spellcheck_initiator_impl import (
    SpellcheckInitiatorImpl,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer
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
    async def provide_http_session(self) -> ClientSession:
        """Provide HTTP client session."""
        return ClientSession()

    @provide(scope=Scope.APP)
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry."""
        registry = CircuitBreakerRegistry()

        # Only register circuit breakers if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            # Circuit breaker for Batch Conductor Service
            registry.register(
                "batch_conductor",
                CircuitBreaker(
                    name="batch_orchestrator.batch_conductor_client",
                    failure_threshold=settings.BCS_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                    recovery_timeout=timedelta(
                        seconds=settings.BCS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
                    ),
                    success_threshold=settings.BCS_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                    expected_exception=ClientError,
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

        # RedisClient implements all AtomicRedisClientProtocol methods
        return cast(AtomicRedisClientProtocol, redis_client)


class RepositoryAndPublishingProvider(Provider):
    """Provider for data repository and event publishing dependencies."""

    @provide(scope=Scope.APP)
    def provide_batch_repository(self, settings: Settings) -> BatchRepositoryProtocol:
        """Provide batch repository implementation based on environment configuration."""
        if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
            return MockBatchRepositoryImpl()
        else:
            return PostgreSQLBatchRepositoryImpl(settings)

    @provide(scope=Scope.APP)
    def provide_batch_event_publisher(self, kafka_bus: KafkaPublisherProtocol) -> BatchEventPublisherProtocol:
        """Provide batch event publisher implementation."""
        return DefaultBatchEventPublisherImpl(kafka_bus)


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

        TODO: NLP Service is not yet implemented - commands will be queued.
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
    def provide_pipeline_state_manager(
        self,
        batch_repo: BatchRepositoryProtocol,
    ) -> PipelineStateManager:
        """Provide pipeline state manager for state persistence."""
        return PipelineStateManager(batch_repo)


class PipelineCoordinationProvider(Provider):
    """Provider for high-level pipeline coordination and processing services."""

    @provide(scope=Scope.APP)
    def provide_pipeline_phase_coordinator(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
        redis_client: AtomicRedisClientProtocol,
        notification_service: NotificationService,
        state_manager: PipelineStateManager,
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
    def provide_batch_kafka_consumer(
        self,
        settings: Settings,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
        els_batch_phase_outcome_handler: ELSBatchPhaseOutcomeHandler,
        client_pipeline_request_handler: ClientPipelineRequestHandler,
        redis_client: AtomicRedisClientProtocol,
    ) -> BatchKafkaConsumer:
        """Provide Kafka consumer with idempotency support."""
        return BatchKafkaConsumer(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=settings.KAFKA_CONSUMER_GROUP_ID,
            batch_essays_ready_handler=batch_essays_ready_handler,
            els_batch_phase_outcome_handler=els_batch_phase_outcome_handler,
            client_pipeline_request_handler=client_pipeline_request_handler,
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
    ) -> dict[PhaseName, PipelinePhaseInitiatorProtocol]:
        """
        Provide complete phase initiators map for dynamic dispatch.

        This map is central to the generic orchestration system,
        enabling type-safe dynamic dispatch based on PhaseName enum.

        TODO: AI Feedback and NLP services are not yet implemented - their
        commands will be queued until the services are built.
        """
        return {
            PhaseName.SPELLCHECK: spellcheck_initiator,
            PhaseName.CJ_ASSESSMENT: cj_assessment_initiator,
            PhaseName.AI_FEEDBACK: ai_feedback_initiator,  # TODO: Service not implemented
            PhaseName.NLP: nlp_initiator,  # TODO: Service not implemented
        }
