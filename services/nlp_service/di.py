"""Dependency injection configuration for NLP Service."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from common_core.event_enums import ProcessingEvent, topic_name
from huleedu_service_libs.error_handling import HuleEduError
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.outbox.manager import OutboxManager
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from opentelemetry.trace import Tracer
from prometheus_client import CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine

from services.nlp_service.command_handlers.batch_nlp_analysis_handler import BatchNlpAnalysisHandler
from services.nlp_service.command_handlers.essay_student_matching_handler import (
    EssayStudentMatchingHandler,
)
from services.nlp_service.config import Settings, settings
from services.nlp_service.features.student_matching.extraction.base_extractor import BaseExtractor
from services.nlp_service.features.student_matching.extraction.email_anchor_extractor import (
    EmailAnchorExtractor,
)
from services.nlp_service.features.student_matching.extraction.examnet_extractor import (
    ExamnetExtractor,
)
from services.nlp_service.features.student_matching.extraction.extraction_pipeline import (
    ExtractionPipeline,
)
from services.nlp_service.features.student_matching.extraction.header_extractor import (
    HeaderExtractor,
)
from services.nlp_service.features.student_matching.matching.confidence_calculator import (
    ConfidenceCalculator,
)
from services.nlp_service.features.student_matching.matching.email_matcher import EmailMatcher
from services.nlp_service.features.student_matching.matching.name_matcher import NameMatcher
from services.nlp_service.features.student_matching.matching.roster_matcher import RosterMatcher
from services.nlp_service.features.student_matching.matching.simple_name_parser import (
    SimpleNameParser,
)
from services.nlp_service.implementations.content_client_impl import DefaultContentClient
from services.nlp_service.implementations.event_publisher_impl import DefaultNlpEventPublisher
from services.nlp_service.implementations.language_tool_client_impl import LanguageToolServiceClient
from services.nlp_service.implementations.roster_cache_impl import RedisRosterCache
from services.nlp_service.implementations.roster_client_impl import DefaultClassManagementClient
from services.nlp_service.implementations.student_matcher_impl import DefaultStudentMatcher
from services.nlp_service.kafka_consumer import NlpKafkaConsumer
from services.nlp_service.metrics import get_business_metrics
from services.nlp_service.protocols import (
    ClassManagementClientProtocol,
    CommandHandlerProtocol,
    ContentClientProtocol,
    LanguageToolClientProtocol,
    NlpAnalyzerProtocol,
    NlpEventPublisherProtocol,
    RosterCacheProtocol,
    StudentMatcherProtocol,
)
from services.nlp_service.repositories.nlp_repository import NlpRepository


class NlpServiceProvider(Provider):
    """Provider for NLP Service dependencies."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize provider with database engine."""
        super().__init__()
        self._engine = engine

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox configuration."""
        return settings.SERVICE_NAME

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        from prometheus_client import REGISTRY

        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_tracer(self) -> Tracer:
        """Provide OpenTelemetry tracer."""
        from opentelemetry import trace

        return trace.get_tracer("nlp_service")

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaPublisherProtocol:
        """Provide Kafka bus for event publishing."""
        kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client for caching and idempotency."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()
        return redis_client

    @provide(scope=Scope.REQUEST)
    def provide_kafka_consumer(
        self,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
        command_handlers: dict[str, CommandHandlerProtocol],
        tracer: Tracer,
    ) -> NlpKafkaConsumer:
        """Provide Kafka consumer instance."""
        return NlpKafkaConsumer(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=settings.CONSUMER_GROUP,
            consumer_client_id=settings.CONSUMER_CLIENT_ID,
            redis_client=redis_client,
            command_handlers=command_handlers,
            tracer=tracer,
        )

    @provide(scope=Scope.APP)
    def provide_business_metrics(self) -> dict[str, Any]:
        """Provide business metrics."""
        return get_business_metrics()

    @provide(scope=Scope.APP)
    def provide_engine(self) -> AsyncEngine:
        """Provide database engine."""
        return self._engine

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
    ) -> OutboxManager:
        """Provide shared outbox manager for reliable event publishing."""
        return OutboxManager(
            outbox_repository=outbox_repository,
            redis_client=redis_client,
            service_name="nlp_service",
        )

    @provide(scope=Scope.REQUEST)
    def provide_nlp_repository(self, engine: AsyncEngine) -> NlpRepository:
        """Provide NLP repository for database access."""
        return NlpRepository(engine)

    # Content and Class Management clients
    @provide(scope=Scope.APP)
    def provide_content_client(self, settings: Settings) -> ContentClientProtocol:
        """Provide content client for fetching essay text."""
        return DefaultContentClient(content_service_url=settings.CONTENT_SERVICE_URL)

    @provide(scope=Scope.APP)
    def provide_class_management_client(self, settings: Settings) -> ClassManagementClientProtocol:
        """Provide class management client for fetching rosters."""
        return DefaultClassManagementClient(
            class_management_url=settings.CLASS_MANAGEMENT_SERVICE_URL
        )

    @provide(scope=Scope.APP)
    def provide_roster_cache(self, redis_client: AtomicRedisClientProtocol) -> RosterCacheProtocol:
        """Provide roster cache for caching class rosters."""
        return RedisRosterCache(redis_client=redis_client, default_ttl_seconds=3600)

    # Extraction components
    @provide(scope=Scope.APP)
    def provide_examnet_extractor(self) -> ExamnetExtractor:
        """Provide exam.net format extractor."""
        return ExamnetExtractor()

    @provide(scope=Scope.APP)
    def provide_header_extractor(self) -> HeaderExtractor:
        """Provide header pattern extractor."""
        return HeaderExtractor()

    @provide(scope=Scope.APP)
    def provide_email_anchor_extractor(self) -> EmailAnchorExtractor:
        """Provide email anchor extractor."""
        return EmailAnchorExtractor()

    @provide(scope=Scope.APP)
    def provide_extraction_strategies(
        self,
        examnet_extractor: ExamnetExtractor,
        header_extractor: HeaderExtractor,
        email_anchor_extractor: EmailAnchorExtractor,
    ) -> list[BaseExtractor]:
        """Provide extraction strategies in priority order."""
        return [examnet_extractor, header_extractor, email_anchor_extractor]

    @provide(scope=Scope.APP)
    def provide_extraction_pipeline(self, strategies: list[BaseExtractor]) -> ExtractionPipeline:
        """Provide extraction pipeline with configured strategies."""
        return ExtractionPipeline(strategies=strategies)

    # Matching components
    @provide(scope=Scope.APP)
    def provide_simple_name_parser(self) -> SimpleNameParser:
        """Provide simple name parser."""
        return SimpleNameParser()

    @provide(scope=Scope.APP)
    def provide_name_matcher(self, name_parser: SimpleNameParser) -> NameMatcher:
        """Provide name matcher with simple, predictable parsing."""
        return NameMatcher(name_parser=name_parser)

    @provide(scope=Scope.APP)
    def provide_email_matcher(self) -> EmailMatcher:
        """Provide email matcher."""
        return EmailMatcher()

    @provide(scope=Scope.APP)
    def provide_confidence_calculator(self) -> ConfidenceCalculator:
        """Provide confidence calculator."""
        return ConfidenceCalculator()

    @provide(scope=Scope.APP)
    def provide_roster_matcher(
        self,
        name_matcher: NameMatcher,
        email_matcher: EmailMatcher,
        confidence_calculator: ConfidenceCalculator,
    ) -> RosterMatcher:
        """Provide roster matcher orchestrator."""
        return RosterMatcher(
            name_matcher=name_matcher,
            email_matcher=email_matcher,
            confidence_calculator=confidence_calculator,
        )

    # Main student matcher
    @provide(scope=Scope.APP)
    def provide_student_matcher(
        self, extraction_pipeline: ExtractionPipeline, roster_matcher: RosterMatcher
    ) -> StudentMatcherProtocol:
        """Provide student matcher orchestrating extraction and matching."""
        return DefaultStudentMatcher(
            extraction_pipeline=extraction_pipeline, roster_matcher=roster_matcher
        )

    # Event publisher
    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, outbox_manager: OutboxManager, settings: Settings
    ) -> NlpEventPublisherProtocol:
        """Provide event publisher using outbox pattern."""
        return DefaultNlpEventPublisher(
            outbox_manager=outbox_manager,
            source_service_name=settings.SERVICE_NAME,
            output_topic=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
        )

    # Command handlers
    @provide(scope=Scope.APP)
    def provide_essay_student_matching_handler(
        self,
        content_client: ContentClientProtocol,
        class_management_client: ClassManagementClientProtocol,
        roster_cache: RosterCacheProtocol,
        student_matcher: StudentMatcherProtocol,
        event_publisher: NlpEventPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        tracer: Tracer,
    ) -> EssayStudentMatchingHandler:
        """Provide Phase 1 essay student matching command handler."""
        return EssayStudentMatchingHandler(
            content_client=content_client,
            class_management_client=class_management_client,
            roster_cache=roster_cache,
            student_matcher=student_matcher,
            event_publisher=event_publisher,
            outbox_repository=outbox_repository,
            kafka_bus=kafka_bus,
            tracer=tracer,
        )

    @provide(scope=Scope.APP)
    def provide_language_tool_client(
        self,
        settings: Settings,
        tracer: Tracer,
    ) -> LanguageToolClientProtocol:
        """Provide Language Tool Service client with optional circuit breaker protection."""
        # Create base client with settings
        client = LanguageToolServiceClient(settings)

        # Add circuit breaker if enabled
        if settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = CircuitBreaker(
                name="language_tool_service",
                failure_threshold=settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=timedelta(
                    seconds=settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
                ),
                success_threshold=settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                expected_exception=HuleEduError,
                tracer=tracer,
                service_name=settings.SERVICE_NAME,
            )
            # Attach circuit breaker to client for conditional use
            client._circuit_breaker = circuit_breaker  # type: ignore[attr-defined]

        return client

    @provide(scope=Scope.APP)
    def provide_batch_nlp_handler(
        self,
        content_client: ContentClientProtocol,
        event_publisher: NlpEventPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        nlp_analyzer: NlpAnalyzerProtocol,
        language_tool_client: LanguageToolClientProtocol,
        tracer: Tracer,
    ) -> BatchNlpAnalysisHandler:
        """Provide Phase 2 batch NLP command handler."""
        return BatchNlpAnalysisHandler(
            content_client=content_client,
            event_publisher=event_publisher,
            outbox_repository=outbox_repository,
            nlp_analyzer=nlp_analyzer,
            language_tool_client=language_tool_client,
            tracer=tracer,
        )

    @provide(scope=Scope.APP)
    def provide_command_handlers(
        self,
        essay_student_matching_handler: EssayStudentMatchingHandler,
        batch_nlp_handler: BatchNlpAnalysisHandler,
    ) -> dict[str, CommandHandlerProtocol]:
        """Provide dictionary of command handlers."""
        return {
            "phase1_student_matching": essay_student_matching_handler,
            "phase2_batch_nlp": batch_nlp_handler,
        }
