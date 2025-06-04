"""Dependency injection configuration for Essay Lifecycle Service using Dishka."""

from __future__ import annotations

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from services.essay_lifecycle_service.batch_tracker import (
    BatchEssayTracker as ConcreteBatchEssayTracker,
)
from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.config import settings as app_settings
from services.essay_lifecycle_service.core_logic import (
    StateTransitionValidator as ConcreteStateTransitionValidator,
)
from services.essay_lifecycle_service.implementations.batch_command_handler_impl import (
    DefaultBatchCommandHandler,
)
from services.essay_lifecycle_service.implementations.batch_phase_coordinator_impl import (
    DefaultBatchPhaseCoordinator,
)
from services.essay_lifecycle_service.implementations.content_client import DefaultContentClient
from services.essay_lifecycle_service.implementations.event_publisher import DefaultEventPublisher
from services.essay_lifecycle_service.implementations.metrics_collector import (
    DefaultMetricsCollector,
)
from services.essay_lifecycle_service.implementations.service_request_dispatcher import (
    DefaultSpecializedServiceRequestDispatcher,
)
from services.essay_lifecycle_service.implementations.service_result_handler_impl import (
    DefaultServiceResultHandler,
)
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchEssayTracker,
    BatchPhaseCoordinator,
    ContentClient,
    EssayStateStore,
    EventPublisher,
    MetricsCollector,
    ServiceResultHandler,
    SpecializedServiceRequestDispatcher,
    StateTransitionValidator,
)
from services.essay_lifecycle_service.state_store import SQLiteEssayStateStore


class EssayLifecycleServiceProvider(Provider):
    """Provider for Essay Lifecycle Service dependencies."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return app_settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    async def provide_kafka_producer(self, settings: Settings) -> AIOKafkaProducer:
        """Provide Kafka producer for event publishing."""
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=settings.PRODUCER_CLIENT_ID,
        )
        await producer.start()
        return producer

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> ClientSession:
        """Provide HTTP client session."""
        return ClientSession()

    @provide(scope=Scope.APP)
    async def provide_essay_state_store(self, settings: Settings) -> EssayStateStore:
        """Provide essay state store implementation."""
        store = SQLiteEssayStateStore(
            database_path=settings.DATABASE_PATH, timeout=settings.DATABASE_TIMEOUT
        )
        await store.initialize()
        return store  # type: ignore[return-value]

    @provide(scope=Scope.APP)
    def provide_state_transition_validator(self) -> StateTransitionValidator:
        """Provide state transition validator implementation."""
        return ConcreteStateTransitionValidator()

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, producer: AIOKafkaProducer, settings: Settings
    ) -> EventPublisher:
        """Provide event publisher implementation."""
        return DefaultEventPublisher(producer, settings)

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
        self, producer: AIOKafkaProducer, settings: Settings
    ) -> SpecializedServiceRequestDispatcher:
        """Provide specialized service request dispatcher implementation."""
        return DefaultSpecializedServiceRequestDispatcher(producer, settings)

    @provide(scope=Scope.APP)
    def provide_batch_command_handler(
        self,
        state_store: EssayStateStore,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> BatchCommandHandler:
        """Provide batch command handler implementation."""
        return DefaultBatchCommandHandler(state_store, request_dispatcher, event_publisher)

    @provide(scope=Scope.APP)
    def provide_batch_essay_tracker(self) -> BatchEssayTracker:
        """Provide batch essay tracker implementation."""
        return ConcreteBatchEssayTracker()

    @provide(scope=Scope.APP)
    def provide_batch_phase_coordinator(
        self,
        state_store: EssayStateStore,
        event_publisher: EventPublisher,
    ) -> BatchPhaseCoordinator:
        """Provide batch phase coordinator implementation."""
        return DefaultBatchPhaseCoordinator(state_store, event_publisher)

    @provide(scope=Scope.APP)
    def provide_service_result_handler(
        self,
        state_store: EssayStateStore,
        batch_coordinator: BatchPhaseCoordinator,
    ) -> ServiceResultHandler:
        """Provide service result handler implementation."""
        return DefaultServiceResultHandler(state_store, batch_coordinator)
