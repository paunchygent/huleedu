"""Dependency injection configuration for Essay Lifecycle Service using Dishka."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from common_core.batch_service_models import (
    BatchServiceAIFeedbackInitiateCommandDataV1,
    BatchServiceCJAssessmentInitiateCommandDataV1,
    BatchServiceNLPInitiateCommandDataV1,
    BatchServiceSpellcheckInitiateCommandDataV1,
)
from common_core.enums import ContentType, EssayStatus
from common_core.events.ai_feedback_events import AIFeedbackInputDataV1
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1
from dishka import Provider, Scope, provide
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CollectorRegistry

from .config import Settings, settings
from .core_logic import StateTransitionValidator
from .protocols import (
    BatchCommandHandler,
    ContentClient,
    EssayStateStore,
    EventPublisher,
    MetricsCollector,
    SpecializedServiceRequestDispatcher,
)
from .protocols import (
    StateTransitionValidator as StateTransitionValidatorProtocol,
)
from .state_store import SQLiteEssayStateStore


class EssayLifecycleServiceProvider(Provider):
    """Provider for Essay Lifecycle Service dependencies."""

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
    def provide_state_transition_validator(self) -> StateTransitionValidatorProtocol:
        """Provide state transition validator implementation."""
        return StateTransitionValidator()

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


# Concrete implementations
class DefaultEventPublisher:
    """Default implementation of EventPublisher protocol."""

    def __init__(self, producer: AIOKafkaProducer, settings: Settings) -> None:
        self.producer = producer
        self.settings = settings

    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID | None = None
    ) -> None:
        """Publish essay status update event."""
        import json
        from datetime import UTC, datetime
        from uuid import uuid4

        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import SystemProcessingMetadata

        # Create status update event data as a dict that's JSON serializable
        event_data = {
            "event_name": "essay.status.updated.v1",
            "entity_ref": essay_ref.model_dump(),
            "status": status.value,
            "system_metadata": SystemProcessingMetadata(
                entity=essay_ref,
                timestamp=datetime.now(UTC),
            ).model_dump(),
        }

        # Create event envelope (using Any type for now)
        from typing import Any

        envelope = EventEnvelope[Any](
            event_type="essay.status.updated.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Publish to Kafka
        topic = "essay.status.events"
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

    async def publish_batch_phase_progress(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
        total_essays_in_phase: int,
        correlation_id: UUID | None = None,
    ) -> None:
        """Report aggregated progress of a specific phase for a batch to BS."""
        import json
        from datetime import UTC, datetime
        from uuid import uuid4

        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import EntityReference

        # Create batch progress event data
        batch_ref = EntityReference(entity_id=batch_id, entity_type="batch")

        event_data = {
            "event_name": "batch.phase.progress.v1",
            "entity_ref": batch_ref.model_dump(),
            "phase": phase,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "total_essays_in_phase": total_essays_in_phase,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Create event envelope
        from typing import Any

        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch_phase.progress.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Publish to Batch Service topic
        topic = "batch.phase.progress.events"
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID | None = None,
    ) -> None:
        """Report the final conclusion of a phase for a batch to BS."""
        import json
        from datetime import UTC, datetime
        from uuid import uuid4

        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import EntityReference

        # Create batch conclusion event data
        batch_ref = EntityReference(entity_id=batch_id, entity_type="batch")

        event_data = {
            "event_name": "batch.phase.concluded.v1",
            "entity_ref": batch_ref.model_dump(),
            "phase": phase,
            "status": status,
            "details": details,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Create event envelope
        from typing import Any

        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch_phase.concluded.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Publish to Batch Service topic
        topic = "batch.phase.concluded.events"
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

    def _get_topic_for_event_type(self, event_type: str) -> str:
        """Map event type to appropriate Kafka topic."""
        if "spellcheck" in event_type:
            return "essay.spellcheck.requests"
        elif "nlp" in event_type:
            return "essay.nlp.requests"
        elif "ai_feedback" in event_type:
            return "essay.ai_feedback.requests"
        else:
            return "essay.processing.requests"


class DefaultContentClient:
    """Default implementation of ContentClient protocol."""

    def __init__(self, http_session: ClientSession, settings: Settings) -> None:
        self.http_session = http_session
        self.settings = settings

    async def fetch_content(self, storage_id: str) -> bytes:
        """Fetch content from storage by ID."""
        url = f"{self.settings.CONTENT_SERVICE_URL}/fetch/{storage_id}"

        async with self.http_session.get(url) as response:
            response.raise_for_status()
            return await response.read()

    async def store_content(self, content: bytes, content_type: ContentType) -> str:
        """Store content and return storage ID."""
        url = f"{self.settings.CONTENT_SERVICE_URL}/store"

        data = {
            "content": content.decode("utf-8") if isinstance(content, bytes) else content,
            "content_type": content_type.value,
        }

        async with self.http_session.post(url, json=data) as response:
            response.raise_for_status()
            result = await response.json()
            return str(result["storage_id"])


class DefaultMetricsCollector:
    """Default implementation of MetricsCollector protocol."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.registry = registry
        self._setup_metrics()

    def _setup_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        from prometheus_client import Counter, Histogram

        self.state_transitions = Counter(
            "essay_state_transitions_total",
            "Total number of essay state transitions",
            ["from_status", "to_status"],
            registry=self.registry,
        )

        self.processing_duration = Histogram(
            "essay_processing_duration_seconds",
            "Time spent processing operations",
            ["operation"],
            registry=self.registry,
        )

        self.operation_counter = Counter(
            "essay_operations_total",
            "Total number of operations performed",
            ["operation", "status"],
            registry=self.registry,
        )

    def record_state_transition(self, from_status: str, to_status: str) -> None:
        """Record a state transition metric."""
        self.state_transitions.labels(from_status=from_status, to_status=to_status).inc()

    def record_processing_time(self, operation: str, duration_ms: float) -> None:
        """Record processing time for an operation."""
        self.processing_duration.labels(operation=operation).observe(duration_ms / 1000.0)

    def increment_counter(self, metric_name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        labels = labels or {}

        if metric_name == "operations":
            self.operation_counter.labels(**labels).inc()


class DefaultBatchCommandHandler:
    """Default implementation of BatchCommandHandler protocol."""

    def __init__(
        self,
        state_store: EssayStateStore,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> None:
        self.state_store = state_store
        self.request_dispatcher = request_dispatcher
        self.event_publisher = event_publisher

    async def process_initiate_spellcheck_command(
        self,
        command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID | None = None,
    ) -> None:
        """Process spellcheck initiation command from Batch Orchestrator Service."""
        # TODO: Implement batch command processing
        # 1. Update essay states to AWAITING_SPELLCHECK
        # 2. Dispatch individual requests to Spell Checker Service
        # 3. Track batch progress and report to BS
        logger = create_service_logger("batch_command_handler")
        logger.info(
            "Received spellcheck initiation command (STUB)",
            extra={"batch_id": command_data.entity_ref.entity_id, "correlation_id": correlation_id},
        )

    async def process_initiate_nlp_command(
        self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID | None = None
    ) -> None:
        """Process NLP initiation command from Batch Orchestrator Service."""
        # TODO: Implement when NLP Service is available
        logger = create_service_logger("batch_command_handler")
        logger.info("Received NLP initiation command (STUB)")

    async def process_initiate_ai_feedback_command(
        self,
        command_data: BatchServiceAIFeedbackInitiateCommandDataV1,
        correlation_id: UUID | None = None,
    ) -> None:
        """Process AI feedback initiation command from Batch Orchestrator Service."""
        # TODO: Implement when AI Feedback Service is available
        logger = create_service_logger("batch_command_handler")
        logger.info("Received AI feedback initiation command (STUB)")

    async def process_initiate_cj_assessment_command(
        self,
        command_data: BatchServiceCJAssessmentInitiateCommandDataV1,
        correlation_id: UUID | None = None,
    ) -> None:
        """Process CJ assessment initiation command from Batch Orchestrator Service."""
        # TODO: Implement when CJ Assessment Service is available
        logger = create_service_logger("batch_command_handler")
        logger.info("Received CJ assessment initiation command (STUB)")


class DefaultSpecializedServiceRequestDispatcher:
    """Default implementation of SpecializedServiceRequestDispatcher protocol."""

    def __init__(self, producer: AIOKafkaProducer, settings: Settings) -> None:
        self.producer = producer
        self.settings = settings

    async def dispatch_spellcheck_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch individual spellcheck requests to Spell Checker Service."""
        # TODO: Implement spellcheck request dispatching
        # Create EssayLifecycleSpellcheckRequestV1 for each essay
        # Publish to spell checker service topic
        logger = create_service_logger("specialized_service_dispatcher")
        logger.info(
            "Dispatching spellcheck requests (STUB)",
            extra={"essay_count": len(essays_to_process), "language": language},
        )

    async def dispatch_nlp_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch individual NLP requests to NLP Service."""
        # TODO: Implement when NLP Service is available
        logger = create_service_logger("specialized_service_dispatcher")
        logger.info("Dispatching NLP requests (STUB)")

    async def dispatch_ai_feedback_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        context: AIFeedbackInputDataV1,
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch individual AI feedback requests to AI Feedback Service."""
        # TODO: Implement when AI Feedback Service is available
        logger = create_service_logger("specialized_service_dispatcher")
        logger.info("Dispatching AI feedback requests (STUB)")
