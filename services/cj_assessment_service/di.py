"""Dependency injection providers for CJ Assessment Service."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from aiokafka.errors import KafkaError
from common_core import LLMProviderType
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox.manager import OutboxManager
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from opentelemetry.trace import Tracer
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine

# Import all business logic protocols
from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
from services.cj_assessment_service.cj_core_logic.batch_pool_manager import BatchPoolManager
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.cj_core_logic.batch_retry_processor import BatchRetryProcessor
from services.cj_assessment_service.cj_core_logic.grade_projection.context_service import (
    ProjectionContextService,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.config import settings as service_settings
from services.cj_assessment_service.implementations.anchor_repository import (
    PostgreSQLAnchorRepository,
)
from services.cj_assessment_service.implementations.assessment_instruction_repository import (
    PostgreSQLAssessmentInstructionRepository,
)
from services.cj_assessment_service.implementations.batch_repository import (
    PostgreSQLCJBatchRepository,
)
from services.cj_assessment_service.implementations.comparison_repository import (
    PostgreSQLCJComparisonRepository,
)
from services.cj_assessment_service.implementations.content_client_impl import ContentClientImpl
from services.cj_assessment_service.implementations.essay_repository import (
    PostgreSQLCJEssayRepository,
)
from services.cj_assessment_service.implementations.event_publisher_impl import CJEventPublisherImpl
from services.cj_assessment_service.implementations.grade_projection_repository import (
    PostgreSQLGradeProjectionRepository,
)
from services.cj_assessment_service.implementations.llm_interaction_impl import LLMInteractionImpl
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl
from services.cj_assessment_service.implementations.session_provider_impl import (
    CJSessionProviderImpl,
)
from services.cj_assessment_service.kafka_consumer import CJAssessmentKafkaConsumer
from services.cj_assessment_service.metrics import setup_cj_assessment_database_monitoring
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    BatchCompletionCheckerProtocol,
    BatchProcessorProtocol,
    BatchRetryProcessorProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    GradeProjectionRepositoryProtocol,
    LLMInteractionProtocol,
    LLMProviderProtocol,
    RetryManagerProtocol,
    SessionProviderProtocol,
)


class CJAssessmentServiceProvider(Provider):
    """Dishka provider for CJ Assessment Service dependencies."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize provider with guaranteed infrastructure."""
        super().__init__()
        self._engine = engine

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide application settings."""
        return service_settings

    @provide(scope=Scope.APP)
    def provide_database_engine(self) -> AsyncEngine:
        """Provide database engine from guaranteed infrastructure."""
        return self._engine

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_tracer(self) -> Tracer:
        """Provide OpenTelemetry tracer."""
        from opentelemetry import trace

        return trace.get_tracer("cj_assessment_service")

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
    async def provide_http_session(self) -> aiohttp.ClientSession:
        """Provide HTTP client session."""
        return aiohttp.ClientSession()

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaPublisherProtocol:
        """Provide Kafka bus for event publishing with optional circuit breaker protection."""
        # Create base KafkaBus instance
        base_kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID_CJ,
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
        """Provide Redis client for idempotency operations."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()
        return redis_client

    @provide(scope=Scope.APP)
    def provide_retry_manager(self, settings: Settings) -> RetryManagerProtocol:
        """Provide retry manager for LLM API calls."""
        return RetryManagerImpl(settings)

    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        """Provide correlation context for request-scoped operations."""

        from quart import g, request

        ctx = getattr(g, "correlation_context", None)
        if isinstance(ctx, CorrelationContext):
            return ctx

        context = extract_correlation_context_from_request(request)
        setattr(g, "correlation_context", context)
        return context

    # LLM Provider Service Client
    @provide(scope=Scope.APP)
    def provide_llm_provider_service_client(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> LLMProviderServiceClient:
        """Provide LLM Provider Service HTTP client."""
        return LLMProviderServiceClient(session, settings, retry_manager)

    # Map of providers - all route through the centralized service
    @provide(scope=Scope.APP)
    def provide_llm_provider_map(
        self,
        llm_service_client: LLMProviderServiceClient,
    ) -> dict[LLMProviderType, LLMProviderProtocol]:
        """Provide dictionary with LLM service client for all providers."""
        # All providers now route through the centralized service
        return {
            LLMProviderType.OPENAI: llm_service_client,
            LLMProviderType.ANTHROPIC: llm_service_client,
            LLMProviderType.GOOGLE: llm_service_client,
            LLMProviderType.OPENROUTER: llm_service_client,
        }

    @provide(scope=Scope.APP)
    def provide_llm_interaction(
        self,
        providers: dict[LLMProviderType, LLMProviderProtocol],
        settings: Settings,
    ) -> LLMInteractionProtocol:
        """Provide LLM interaction orchestrator."""
        return LLMInteractionImpl(
            providers=providers,
            settings=settings,
        )

    # Database engine provider removed - engine created in create_app() for guaranteed infra

    @provide(scope=Scope.APP)
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics monitoring for CJ Assessment service."""
        return setup_cj_assessment_database_monitoring(
            engine=engine, service_name="cj_assessment_service"
        )

    @provide(scope=Scope.APP)
    def provide_session_provider(self, engine: AsyncEngine) -> SessionProviderProtocol:
        """Provide shared session provider using the service engine."""
        return CJSessionProviderImpl(engine)

    @provide(scope=Scope.APP)
    def provide_cj_batch_repository(self) -> CJBatchRepositoryProtocol:
        """Provide batch aggregate repository."""
        return PostgreSQLCJBatchRepository()

    @provide(scope=Scope.APP)
    def provide_cj_essay_repository(self) -> CJEssayRepositoryProtocol:
        """Provide essay aggregate repository."""
        return PostgreSQLCJEssayRepository()

    @provide(scope=Scope.APP)
    def provide_cj_comparison_repository(self) -> CJComparisonRepositoryProtocol:
        """Provide comparison repository."""
        return PostgreSQLCJComparisonRepository()

    @provide(scope=Scope.APP)
    def provide_assessment_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
        """Provide assessment instruction repository."""
        return PostgreSQLAssessmentInstructionRepository()

    @provide(scope=Scope.APP)
    def provide_anchor_repository(self) -> AnchorRepositoryProtocol:
        """Provide anchor repository."""
        return PostgreSQLAnchorRepository()

    @provide(scope=Scope.APP)
    def provide_grade_projection_repository(self) -> GradeProjectionRepositoryProtocol:
        """Provide grade projection repository."""
        return PostgreSQLGradeProjectionRepository()

    @provide(scope=Scope.APP)
    def provide_content_client(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> ContentClientProtocol:
        """Provide content client."""
        return ContentClientImpl(session, settings, retry_manager)

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for OutboxProvider dependency."""
        return settings.SERVICE_NAME

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide shared outbox manager for TRUE OUTBOX PATTERN."""
        return OutboxManager(
            outbox_repository=outbox_repository,
            redis_client=redis_client,
            service_name=settings.SERVICE_NAME,
        )

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> CJEventPublisherProtocol:
        """Provide event publisher with outbox manager for transactional safety."""
        return CJEventPublisherImpl(outbox_manager, settings)

    # Batch processing modules with clean architecture
    @provide(scope=Scope.APP)
    def provide_batch_processor(
        self,
        session_provider: SessionProviderProtocol,
        llm_interaction: LLMInteractionProtocol,
        settings: Settings,
        batch_repo: CJBatchRepositoryProtocol,
    ) -> BatchProcessorProtocol:
        """Provide core batch processor for submission orchestration."""
        return BatchProcessor(
            session_provider=session_provider,
            llm_interaction=llm_interaction,
            settings=settings,
            batch_repository=batch_repo,
        )

    @provide(scope=Scope.APP)
    def provide_batch_completion_checker(
        self,
        session_provider: SessionProviderProtocol,
        batch_repo: CJBatchRepositoryProtocol,
    ) -> BatchCompletionCheckerProtocol:
        """Provide batch completion checker for threshold evaluation."""
        return BatchCompletionChecker(
            session_provider=session_provider,
            batch_repo=batch_repo,
        )

    @provide(scope=Scope.APP)
    def provide_batch_pool_manager(
        self,
        session_provider: SessionProviderProtocol,
        batch_repository: CJBatchRepositoryProtocol,
        settings: Settings,
    ) -> BatchPoolManager:
        """Provide batch pool manager for failed comparison handling."""
        return BatchPoolManager(
            session_provider=session_provider,
            batch_repository=batch_repository,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_batch_retry_processor(
        self,
        session_provider: SessionProviderProtocol,
        llm_interaction: LLMInteractionProtocol,
        settings: Settings,
        pool_manager: BatchPoolManager,
        batch_submitter: BatchProcessorProtocol,
    ) -> BatchRetryProcessorProtocol:
        """Provide batch retry processor for end-of-batch fairness logic."""
        return BatchRetryProcessor(
            session_provider=session_provider,
            llm_interaction=llm_interaction,
            settings=settings,
            pool_manager=pool_manager,
            batch_submitter=batch_submitter,
        )

    @provide(scope=Scope.APP)
    def provide_projection_context_service(
        self,
        session_provider: SessionProviderProtocol,
        instruction_repository: AssessmentInstructionRepositoryProtocol,
        anchor_repository: AnchorRepositoryProtocol,
    ) -> ProjectionContextService:
        """Provide projection context service for grade projector."""
        return ProjectionContextService(
            session_provider=session_provider,
            instruction_repository=instruction_repository,
            anchor_repository=anchor_repository,
        )

    @provide(scope=Scope.APP)
    def provide_grade_projector(
        self,
        session_provider: SessionProviderProtocol,
        context_service: ProjectionContextService,
    ) -> GradeProjector:
        """Provide grade projector with all required dependencies."""
        return GradeProjector(
            session_provider=session_provider,
            context_service=context_service,
        )

    @provide(scope=Scope.APP)
    def provide_kafka_consumer(
        self,
        settings: Settings,
        session_provider: SessionProviderProtocol,
        batch_repository: CJBatchRepositoryProtocol,
        essay_repository: CJEssayRepositoryProtocol,
        comparison_repository: CJComparisonRepositoryProtocol,
        instruction_repository: AssessmentInstructionRepositoryProtocol,
        anchor_repository: AnchorRepositoryProtocol,
        content_client: ContentClientProtocol,
        event_publisher: CJEventPublisherProtocol,
        llm_interaction: LLMInteractionProtocol,
        redis_client: AtomicRedisClientProtocol,
        grade_projector: GradeProjector,
        tracer: Tracer,
    ) -> CJAssessmentKafkaConsumer:
        """Provide Kafka consumer for CJ Assessment Service."""
        return CJAssessmentKafkaConsumer(
            settings=settings,
            session_provider=session_provider,
            batch_repository=batch_repository,
            essay_repository=essay_repository,
            comparison_repository=comparison_repository,
            instruction_repository=instruction_repository,
            anchor_repository=anchor_repository,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            redis_client=redis_client,
            grade_projector=grade_projector,
            tracer=tracer,
        )
