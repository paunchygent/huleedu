"""Dependency injection configuration for Essay Lifecycle Service using Dishka."""

from __future__ import annotations

from aiohttp import ClientSession
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.redis_client import RedisClient
from prometheus_client import CollectorRegistry

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.config import settings as app_settings
from services.essay_lifecycle_service.core_logic import (
    StateTransitionValidator as ConcreteStateTransitionValidator,
)
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
from services.essay_lifecycle_service.implementations.content_client import DefaultContentClient
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
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    BatchEssayTracker,
    BatchPhaseCoordinator,
    ContentClient,
    EssayRepositoryProtocol,
    EventPublisher,
    MetricsCollector,
    RedisClientProtocol,
    ServiceResultHandler,
    SpecializedServiceRequestDispatcher,
    StateTransitionValidator,
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
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        """Provide Kafka bus for event publishing."""
        kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
        )
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> ClientSession:
        """Provide HTTP client session."""
        return ClientSession()

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
        """Provide Redis client for idempotency operations."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL
        )
        await redis_client.start()
        return redis_client

    @provide(scope=Scope.APP)
    async def provide_essay_repository(self, settings: Settings) -> EssayRepositoryProtocol:
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
            # Production: use PostgreSQL implementation
            postgres_repo = PostgreSQLEssayRepository(settings)
            await postgres_repo.initialize_db_schema()
            return postgres_repo

    @provide(scope=Scope.APP)
    def provide_state_transition_validator(self) -> StateTransitionValidator:
        """Provide state transition validator implementation."""
        return ConcreteStateTransitionValidator()


class ServiceClientsProvider(Provider):
    """Provider for external service client implementations."""

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, kafka_bus: KafkaBus, settings: Settings
    ) -> EventPublisher:
        """Provide event publisher implementation."""
        return DefaultEventPublisher(kafka_bus, settings)

    @provide(scope=Scope.APP)
    def provide_content_client(
        self, http_session: ClientSession, settings: Settings
    ) -> ContentClient:
        """Provide content client implementation."""
        return DefaultContentClient(http_session, settings)

    @provide(scope=Scope.APP)
    def provide_metrics_collector(self, registry: CollectorRegistry) -> MetricsCollector:
        """Provide metrics collector implementation."""
        return DefaultMetricsCollector(registry)

    @provide(scope=Scope.APP)
    def provide_specialized_service_request_dispatcher(
        self, kafka_bus: KafkaBus, settings: Settings
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
        future_services_handler: FutureServicesCommandHandler,
    ) -> BatchCommandHandler:
        """Provide batch command handler implementation with injected service handlers."""
        return DefaultBatchCommandHandler(
            spellcheck_handler, cj_assessment_handler, future_services_handler
        )


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
