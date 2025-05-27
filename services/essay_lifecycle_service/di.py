"""Dependency injection configuration for Essay Lifecycle Service using Dishka."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from common_core.enums import ContentType, EssayStatus
from common_core.metadata_models import EntityReference
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from config import Settings, settings
from core_logic import StateTransitionValidator
from protocols import (
    ContentClient,
    EssayStateStore,
    EventPublisher,
    MetricsCollector,
)
from protocols import (
    StateTransitionValidator as StateTransitionValidatorProtocol,
)
from state_store import SQLiteEssayStateStore


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

    async def publish_processing_request(
        self,
        event_type: str,
        essay_ref: EntityReference,
        payload: dict[str, Any],
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish processing request to specialized services."""
        import json
        from datetime import UTC, datetime

        # Create event envelope with processing request
        from typing import Any
        from uuid import uuid4

        from common_core.events.envelope import EventEnvelope

        envelope = EventEnvelope[Any](
            event_type=event_type,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data={
                "entity_ref": essay_ref.model_dump(),
                "timestamp": datetime.now(UTC).isoformat(),
                **payload,
            },
        )

        # Determine topic based on event type
        topic = self._get_topic_for_event_type(event_type)
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
