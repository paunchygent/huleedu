"""Dependency injection configuration for Spell Checker Service using Dishka."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from common_core.enums import ContentType
from common_core.events.spellcheck_models import SpellcheckResultDataV1

from .config import Settings, settings
from .core_logic import (
    default_fetch_content_impl,
    default_perform_spell_check_algorithm,
    default_store_content_impl,
)
from .protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)


class SpellCheckerServiceProvider(Provider):
    """Provider for Spell Checker Service dependencies."""

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
    def provide_content_client(self) -> ContentClientProtocol:
        """Provide content client implementation."""
        return DefaultContentClient()

    @provide(scope=Scope.APP)
    def provide_spell_logic(self) -> SpellLogicProtocol:
        """Provide spell check logic implementation."""
        return DefaultSpellLogic()

    @provide(scope=Scope.APP)
    def provide_result_store(self) -> ResultStoreProtocol:
        """Provide result store implementation."""
        return DefaultResultStore()

    @provide(scope=Scope.APP)
    def provide_spellcheck_event_publisher(self) -> SpellcheckEventPublisherProtocol:
        """Provide spellcheck event publisher implementation."""
        return DefaultSpellcheckEventPublisher()


class DefaultContentClient:
    """Default implementation of ContentClientProtocol."""

    async def fetch_content(self, storage_id: str, http_session: ClientSession) -> str:
        """Fetch content using the core logic implementation."""
        from .config import settings

        return await default_fetch_content_impl(
            http_session, storage_id, settings.CONTENT_SERVICE_URL
        )


class DefaultSpellLogic:
    """Default implementation of SpellLogicProtocol."""

    async def perform_spell_check(self, text: str) -> SpellcheckResultDataV1:
        """Perform spell check using the core logic implementation."""
        # Use core logic and create the SpellcheckResultDataV1 object
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(text)

        # Create a mock SpellcheckResultDataV1 for now
        # In production, this would be created properly with all required fields
        from datetime import datetime, timezone

        from common_core.enums import EssayStatus, ProcessingEvent, ProcessingStage
        from common_core.metadata_models import EntityReference, SystemProcessingMetadata

        # Mock data for Phase 1.2
        entity_ref = EntityReference(entity_id="mock-essay-id", entity_type="essay")
        system_meta = SystemProcessingMetadata(
            entity=entity_ref,
            event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
        )

        return SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
            entity_ref=entity_ref,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_meta,
            original_text_storage_id="mock-storage-id",  # Will be set properly when integrated
            corrections_made=corrections_count,
        )


class DefaultResultStore:
    """Default implementation of ResultStoreProtocol."""

    async def store_content(
        self,
        original_storage_id: str,
        content_type: ContentType,
        content: str,
        http_session: ClientSession,
    ) -> str:
        """Store content using the core logic implementation."""
        from .config import settings

        return await default_store_content_impl(http_session, content, settings.CONTENT_SERVICE_URL)


class DefaultSpellcheckEventPublisher:
    """Default implementation of SpellcheckEventPublisherProtocol."""

    async def publish_spellcheck_result(
        self,
        producer: AIOKafkaProducer,
        event_data: SpellcheckResultDataV1,
        correlation_id: Optional[UUID],
    ) -> None:
        """Publish spellcheck result event to Kafka."""
        # Import here to avoid circular imports
        import json

        from common_core.enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED)

        envelope = EventEnvelope[SpellcheckResultDataV1](
            event_type=topic,
            source_service="spell-checker-service",
            correlation_id=correlation_id,
            data=event_data,
        )

        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await producer.send_and_wait(topic, message)
