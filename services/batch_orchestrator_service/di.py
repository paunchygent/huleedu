"""Dependency injection configuration for Batch Orchestrator Service using Dishka."""

from __future__ import annotations

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from config import Settings, settings
from dishka import Provider, Scope, provide
from implementations.ai_feedback_initiator_impl import AIFeedbackInitiatorImpl
from implementations.batch_essays_ready_handler import BatchEssaysReadyHandler
from implementations.batch_processing_service_impl import BatchProcessingServiceImpl
from implementations.batch_repository_impl import MockBatchRepositoryImpl
from implementations.batch_repository_postgres_impl import PostgreSQLBatchRepositoryImpl
from implementations.cj_assessment_initiator_impl import DefaultCJAssessmentInitiator
from implementations.els_batch_phase_outcome_handler import ELSBatchPhaseOutcomeHandler
from implementations.essay_lifecycle_client_impl import DefaultEssayLifecycleClientImpl
from implementations.event_publisher_impl import DefaultBatchEventPublisherImpl
from implementations.nlp_initiator_impl import NLPInitiatorImpl
from implementations.pipeline_phase_coordinator_impl import DefaultPipelinePhaseCoordinator
from implementations.spellcheck_initiator_impl import SpellcheckInitiatorImpl
from kafka_consumer import BatchKafkaConsumer
from prometheus_client import CollectorRegistry
from protocols import (
    AIFeedbackInitiatorProtocol,
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

from common_core.pipeline_models import PhaseName


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
    async def provide_kafka_producer(self, settings: Settings) -> AIOKafkaProducer:
        """Provide Kafka producer for event publishing."""
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=f"{settings.SERVICE_NAME}-producer",
        )
        await producer.start()
        return producer

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> ClientSession:
        """Provide HTTP client session."""
        return ClientSession()


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
    def provide_batch_event_publisher(
        self, producer: AIOKafkaProducer
    ) -> BatchEventPublisherProtocol:
        """Provide batch event publisher implementation."""
        return DefaultBatchEventPublisherImpl(producer)


class ExternalClientsProvider(Provider):
    """Provider for external service client dependencies."""

    @provide(scope=Scope.APP)
    def provide_essay_lifecycle_client(
        self, http_session: ClientSession, settings: Settings
    ) -> EssayLifecycleClientProtocol:
        """Provide essay lifecycle service client implementation."""
        return DefaultEssayLifecycleClientImpl(http_session, settings)


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


class PipelineCoordinationProvider(Provider):
    """Provider for high-level pipeline coordination and processing services."""

    @provide(scope=Scope.APP)
    def provide_pipeline_phase_coordinator(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
    ) -> PipelinePhaseCoordinatorProtocol:
        """Provide pipeline phase coordinator implementation."""
        return DefaultPipelinePhaseCoordinator(batch_repo, phase_initiators_map)

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
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
    ) -> BatchEssaysReadyHandler:
        """Provide BatchEssaysReady message handler."""
        return BatchEssaysReadyHandler(event_publisher, batch_repo, phase_initiators_map)

    @provide(scope=Scope.APP)
    def provide_els_batch_phase_outcome_handler(
        self,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
    ) -> ELSBatchPhaseOutcomeHandler:
        """Provide ELSBatchPhaseOutcome message handler."""
        return ELSBatchPhaseOutcomeHandler(phase_coordinator)

    @provide(scope=Scope.APP)
    def provide_batch_kafka_consumer(
        self,
        settings: Settings,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
        els_batch_phase_outcome_handler: ELSBatchPhaseOutcomeHandler,
    ) -> BatchKafkaConsumer:
        """Provide Kafka consumer for batch events."""
        return BatchKafkaConsumer(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group="batch-orchestrator-group",
            batch_essays_ready_handler=batch_essays_ready_handler,
            els_batch_phase_outcome_handler=els_batch_phase_outcome_handler,
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
