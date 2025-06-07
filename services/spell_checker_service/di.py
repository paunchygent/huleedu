"""Dependency injection configuration for Spell Checker Service using Dishka."""

from __future__ import annotations

from aiohttp import ClientSession
from aiokafka import AIOKafkaProducer
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from common_core.enums import ProcessingEvent, topic_name
from services.spell_checker_service.config import Settings, settings
from services.spell_checker_service.protocol_implementations.content_client_impl import (
    DefaultContentClient,
)
from services.spell_checker_service.protocol_implementations.event_publisher_impl import (
    DefaultSpellcheckEventPublisher,
)
from services.spell_checker_service.protocol_implementations.result_store_impl import (
    DefaultResultStore,
)
from services.spell_checker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
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
    def provide_content_client(self, app_settings: Settings) -> ContentClientProtocol:
        """Provide content client implementation."""
        return DefaultContentClient(content_service_url=app_settings.CONTENT_SERVICE_URL)

    @provide(scope=Scope.APP)
    def provide_result_store(self, app_settings: Settings) -> ResultStoreProtocol:
        """Provide result store implementation."""
        return DefaultResultStore(content_service_url=app_settings.CONTENT_SERVICE_URL)

    @provide(scope=Scope.APP)
    def provide_spellcheck_event_publisher(
        self, app_settings: Settings
    ) -> SpellcheckEventPublisherProtocol:
        """Provide spellcheck event publisher implementation."""
        return DefaultSpellcheckEventPublisher(
            kafka_event_type=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            source_service_name="spell-checker-service",
            kafka_output_topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        )

    # Note: SpellLogicProtocol will be provided per-message since it needs message-specific data
    # This will be handled in the event processor or worker_main
