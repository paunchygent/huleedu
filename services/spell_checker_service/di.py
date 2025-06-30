"""Dependency injection configuration for Spell Checker Service using Dishka."""

from __future__ import annotations

from aiohttp import ClientSession
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from prometheus_client import CollectorRegistry

from common_core.event_enums import ProcessingEvent, topic_name
from services.spell_checker_service.config import Settings, settings
from services.spell_checker_service.kafka_consumer import SpellCheckerKafkaConsumer
from services.spell_checker_service.protocol_implementations.content_client_impl import (
    DefaultContentClient,
)
from services.spell_checker_service.protocol_implementations.event_publisher_impl import (
    DefaultSpellcheckEventPublisher,
)
from services.spell_checker_service.protocol_implementations.result_store_impl import (
    DefaultResultStore,
)
from services.spell_checker_service.protocol_implementations.spell_logic_impl import (
    DefaultSpellLogic,
)
from services.spell_checker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)
from services.spell_checker_service.repository_protocol import SpellcheckRepositoryProtocol
from services.spell_checker_service.implementations.spell_repository_postgres_impl import (
    PostgreSQLSpellcheckRepository,
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
        from prometheus_client import REGISTRY

        return REGISTRY

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        """Provide Kafka bus for event publishing."""
        kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}-producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
        """Provide Redis client for idempotency operations."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()
        return redis_client

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
    async def provide_spellcheck_repository(self, settings: Settings) -> SpellcheckRepositoryProtocol:
        """Provide PostgreSQL-backed spell-check repository."""
        repo = PostgreSQLSpellcheckRepository(settings)
        # ensure schema exists (idempotent)
        await repo.initialize_db_schema()
        return repo

    @provide(scope=Scope.APP)
    def provide_spell_logic(
        self,
        result_store: ResultStoreProtocol,
        http_session: ClientSession,
    ) -> SpellLogicProtocol:
        """Provide spell logic implementation."""
        return DefaultSpellLogic(result_store=result_store, http_session=http_session)

    @provide(scope=Scope.APP)
    def provide_spellcheck_event_publisher(
        self,
        app_settings: Settings,
    ) -> SpellcheckEventPublisherProtocol:
        """Provide spellcheck event publisher implementation."""
        return DefaultSpellcheckEventPublisher(
            kafka_event_type=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            source_service_name="spell-checker-service",
            kafka_output_topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        )

    @provide(scope=Scope.APP)
    def provide_spell_checker_kafka_consumer(
        self,
        app_settings: Settings,
        content_client: ContentClientProtocol,
        result_store: ResultStoreProtocol,
        spell_logic: SpellLogicProtocol,
        event_publisher: SpellcheckEventPublisherProtocol,
        kafka_bus: KafkaBus,
        http_session: ClientSession,
        redis_client: RedisClientProtocol,
    ) -> SpellCheckerKafkaConsumer:
        """Provide Kafka consumer with injected dependencies."""
        return SpellCheckerKafkaConsumer(
            kafka_bootstrap_servers=app_settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=app_settings.CONSUMER_GROUP,
            consumer_client_id=app_settings.CONSUMER_CLIENT_ID,
            content_client=content_client,
            result_store=result_store,
            spell_logic=spell_logic,
            event_publisher=event_publisher,
            kafka_bus=kafka_bus,
            http_session=http_session,
            redis_client=redis_client,
        )
