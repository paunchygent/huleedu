"""Dependency injection configuration for Batch Orchestrator Service using Dishka."""

from __future__ import annotations

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from .config import Settings, settings
from .protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    EssayLifecycleClientProtocol,
)


class BatchOrchestratorServiceProvider(Provider):
    """Provider for Batch Orchestrator Service dependencies."""

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

    @provide(scope=Scope.APP)
    def provide_batch_repository(self) -> BatchRepositoryProtocol:
        """Provide batch repository implementation."""
        return MockBatchRepository()  # type: ignore[return-value]

    @provide(scope=Scope.APP)
    def provide_batch_event_publisher(
        self, producer: AIOKafkaProducer
    ) -> BatchEventPublisherProtocol:
        """Provide batch event publisher implementation."""
        return DefaultBatchEventPublisher(producer)  # type: ignore[return-value]

    @provide(scope=Scope.APP)
    def provide_essay_lifecycle_client(
        self, http_session: ClientSession, settings: Settings
    ) -> EssayLifecycleClientProtocol:
        """Provide essay lifecycle service client implementation."""
        return DefaultEssayLifecycleClient(http_session, settings)


# Concrete implementations
class MockBatchRepository:
    """Mock implementation of BatchRepositoryProtocol for Phase 1.2."""

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Mock implementation - returns placeholder data."""
        # Note: In production this would return a proper BatchUpload model
        return {"id": batch_id, "status": "pending", "processing_metadata": {}}

    async def create_batch(self, batch_data: dict) -> dict:
        """Mock implementation - returns the batch data with an ID."""
        # Note: In production batch_data would be a BatchUpload model
        return {"id": "mock-batch-id", **batch_data}

    async def update_batch_status(self, batch_id: str, new_status: str) -> bool:
        """Mock implementation - always succeeds."""
        return True

    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: dict) -> bool:
        """Mock implementation - always succeeds."""
        return True


class DefaultBatchEventPublisher:
    """Default implementation of BatchEventPublisherProtocol."""

    def __init__(self, producer: AIOKafkaProducer) -> None:
        self.producer = producer

    async def publish_batch_event(self, event_envelope: dict) -> None:
        """Publish batch event to Kafka."""
        import json

        topic = "batch.events"  # TODO: Make this configurable
        message = json.dumps(event_envelope).encode("utf-8")

        await self.producer.send_and_wait(topic, message)


class DefaultEssayLifecycleClient:
    """Default implementation of EssayLifecycleClientProtocol."""

    def __init__(self, http_session: ClientSession, settings: Settings) -> None:
        self.http_session = http_session
        self.settings = settings

    async def request_essay_phase_initiation(
        self, batch_id: str, essay_ids: list[str], phase: str
    ) -> None:
        """Mock implementation - logs the request."""
        # TODO: Implement actual HTTP call to Essay Lifecycle Service
        print(f"Mock: Requesting {phase} for batch {batch_id}, essays {essay_ids}")
