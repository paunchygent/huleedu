"""Dependency injection configuration for File Service using Dishka."""

from __future__ import annotations

import json
import uuid
from typing import Optional

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from config import Settings, settings
from dishka import Provider, Scope, provide
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CollectorRegistry
from protocols import (
    ContentServiceClientProtocol,
    EventPublisherProtocol,
    TextExtractorProtocol,
)
from text_processing import extract_text_from_file

from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentReady

logger = create_service_logger("file_service.di")


class DefaultContentServiceClient:
    """Default implementation of ContentServiceClientProtocol."""

    def __init__(self, http_session: ClientSession, settings: Settings):
        self.http_session = http_session
        self.settings = settings

    async def store_content(self, content_bytes: bytes) -> str:
        """Store content in Content Service and return storage ID."""
        try:
            async with self.http_session.post(
                self.settings.CONTENT_SERVICE_URL,
                data=content_bytes
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    storage_id = result.get("storage_id")
                    if isinstance(storage_id, str) and storage_id:
                        logger.info(f"Successfully stored content, storage_id: {storage_id}")
                        return storage_id
                    else:
                        raise ValueError("Content Service response missing storage_id")
                else:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Content Service returned status {response.status}: {error_text}"
                    )
        except Exception as e:
            logger.error(f"Error storing content in Content Service: {e}")
            raise


class DefaultEventPublisher:
    """Default implementation of EventPublisherProtocol."""

    def __init__(self, producer: AIOKafkaProducer, settings: Settings):
        self.producer = producer
        self.settings = settings

    async def publish_essay_content_ready(
        self,
        event_data: EssayContentReady,
        correlation_id: Optional[uuid.UUID]
    ) -> None:
        """Publish EssayContentReady event to Kafka."""
        try:
            # Construct EventEnvelope
            envelope = EventEnvelope[EssayContentReady](
                event_type=self.settings.ESSAY_CONTENT_READY_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data
            )

            # Serialize to JSON
            message_bytes = json.dumps(envelope.model_dump(mode="json")).encode('utf-8')

            # Publish to Kafka
            await self.producer.send(
                self.settings.ESSAY_CONTENT_READY_TOPIC,
                message_bytes
            )

            logger.info(
                f"Published EssayContentReady event for essay {event_data.essay_id} "
                f"to topic {self.settings.ESSAY_CONTENT_READY_TOPIC}"
            )

        except Exception as e:
            logger.error(f"Error publishing EssayContentReady event: {e}")
            raise


class DefaultTextExtractor:
    """Default implementation of TextExtractorProtocol."""

    async def extract_text(self, file_content: bytes, file_name: str) -> str:
        """Extract text content from file bytes."""
        result: str = await extract_text_from_file(file_content, file_name)
        return result


class FileServiceProvider(Provider):
    """Provider for File Service dependencies."""

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
    def provide_content_service_client(
        self, http_session: ClientSession, settings: Settings
    ) -> ContentServiceClientProtocol:
        """Provide Content Service client implementation."""
        return DefaultContentServiceClient(http_session, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, producer: AIOKafkaProducer, settings: Settings
    ) -> EventPublisherProtocol:
        """Provide event publisher implementation."""
        return DefaultEventPublisher(producer, settings)

    @provide(scope=Scope.APP)
    def provide_text_extractor(self) -> TextExtractorProtocol:
        """Provide text extractor implementation."""
        return DefaultTextExtractor()
