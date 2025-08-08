"""Dependency injection configuration for Spell Checker Service using Dishka."""

from __future__ import annotations

from datetime import timedelta

from aiohttp import ClientSession
from aiokafka.errors import KafkaError
from common_core.event_enums import ProcessingEvent, topic_name
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import (
    EventRelayWorker,
    OutboxRepositoryProtocol,
    OutboxSettings,
    PostgreSQLOutboxRepository,
)
from huleedu_service_libs.protocols import (
    AtomicRedisClientProtocol,
    KafkaPublisherProtocol,
    RedisClientProtocol,
)
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from opentelemetry.trace import Tracer
from prometheus_client import CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine

from services.spellchecker_service.config import Settings, settings
from services.spellchecker_service.implementations.content_client_impl import (
    DefaultContentClient,
)
from services.spellchecker_service.implementations.event_publisher_impl import (
    DefaultSpellcheckEventPublisher,
)
from services.spellchecker_service.implementations.outbox_manager import OutboxManager
from services.spellchecker_service.implementations.parallel_processor_impl import (
    DefaultParallelProcessor,
)
from services.spellchecker_service.implementations.result_store_impl import (
    DefaultResultStore,
)
from services.spellchecker_service.implementations.spell_logic_impl import (
    DefaultSpellLogic,
)
from services.spellchecker_service.implementations.spell_repository_postgres_impl import (
    PostgreSQLSpellcheckRepository,
)
from services.spellchecker_service.implementations.whitelist_impl import (
    DefaultWhitelist,
)
from services.spellchecker_service.kafka_consumer import SpellCheckerKafkaConsumer
from services.spellchecker_service.metrics import setup_spell_checker_database_monitoring
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ParallelProcessorProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
    WhitelistProtocol,
)
from services.spellchecker_service.repository_protocol import SpellcheckRepositoryProtocol


class SpellCheckerServiceProvider(Provider):
    """Provider for Spell Checker Service dependencies."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize provider with pre-configured database engine."""
        super().__init__()
        self._engine = engine

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
    def provide_tracer(self) -> Tracer:
        """Provide OpenTelemetry tracer."""
        from opentelemetry import trace

        return trace.get_tracer("spellchecker_service")

    @provide(scope=Scope.APP)
    def provide_whitelist(self, settings: Settings) -> WhitelistProtocol:
        """Provide whitelist for spell checking (loaded once at startup)."""
        return DefaultWhitelist(settings)

    @provide(scope=Scope.APP)
    def provide_parallel_processor(self) -> ParallelProcessorProtocol:
        """Provide parallel processor for word corrections."""
        return DefaultParallelProcessor()

    @provide(scope=Scope.APP)
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry."""
        registry = CircuitBreakerRegistry()

        # Only register circuit breakers if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            # Future: Add more circuit breakers here as needed
            pass

        return registry

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaPublisherProtocol:
        """Provide Kafka bus for event publishing with optional circuit breaker protection."""
        # Create base KafkaBus instance
        base_kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )

        # Wrap with circuit breaker protection if enabled
        kafka_publisher: KafkaPublisherProtocol
        if settings.CIRCUIT_BREAKER_ENABLED:
            kafka_circuit_breaker = CircuitBreaker(
                name=f"{settings.SERVICE_NAME}.kafka_producer",
                failure_threshold=settings.KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=timedelta(seconds=settings.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
                success_threshold=settings.KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                expected_exception=KafkaError,
            )
            circuit_breaker_registry.register("kafka_producer", kafka_circuit_breaker)

            # Create resilient wrapper using composition
            kafka_publisher = ResilientKafkaPublisher(
                delegate=base_kafka_bus,
                circuit_breaker=kafka_circuit_breaker,
                retry_interval=30,
            )
        else:
            # Use base KafkaBus without circuit breaker
            kafka_publisher = base_kafka_bus

        await kafka_publisher.start()
        return kafka_publisher

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client for idempotency operations."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()
        return redis_client

    @provide(scope=Scope.APP)
    async def provide_base_redis_client(
        self, atomic_redis_client: AtomicRedisClientProtocol
    ) -> RedisClientProtocol:
        """Provide Redis client as RedisClientProtocol for basic operations."""
        return atomic_redis_client

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> ClientSession:
        """Provide HTTP client session."""
        return ClientSession()

    @provide(scope=Scope.APP)
    def provide_content_client(self, settings: Settings) -> ContentClientProtocol:
        """Provide content client implementation."""
        return DefaultContentClient(content_service_url=settings.CONTENT_SERVICE_URL)

    @provide(scope=Scope.APP)
    def provide_result_store(self, settings: Settings) -> ResultStoreProtocol:
        """Provide result store implementation."""
        return DefaultResultStore(content_service_url=settings.CONTENT_SERVICE_URL)

    @provide(scope=Scope.APP)
    def provide_database_engine(self) -> AsyncEngine:
        """Provide the pre-configured database engine."""
        return self._engine

    @provide(scope=Scope.APP)
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics monitoring for spell checker service."""
        return setup_spell_checker_database_monitoring(
            engine=engine, service_name=settings.SERVICE_NAME
        )

    @provide(scope=Scope.APP)
    async def provide_spellcheck_repository(
        self, settings: Settings, database_metrics: DatabaseMetrics, engine: AsyncEngine
    ) -> SpellcheckRepositoryProtocol:
        """Provide PostgreSQL-backed spell-check repository with metrics."""
        repo = PostgreSQLSpellcheckRepository(settings, database_metrics, engine)
        # ensure schema exists (idempotent)
        await repo.initialize_db_schema()
        return repo

    @provide(scope=Scope.APP)
    def provide_spell_logic(
        self,
        result_store: ResultStoreProtocol,
        http_session: ClientSession,
        whitelist: WhitelistProtocol,
        parallel_processor: ParallelProcessorProtocol,
    ) -> SpellLogicProtocol:
        """Provide spell logic implementation."""
        return DefaultSpellLogic(
            result_store=result_store,
            http_session=http_session,
            whitelist=whitelist,
            parallel_processor=parallel_processor,
        )

    @provide(scope=Scope.APP)
    async def provide_outbox_repository(
        self,
        engine: AsyncEngine,
    ) -> OutboxRepositoryProtocol:
        """Provide outbox repository for transactional event storage."""
        return PostgreSQLOutboxRepository(engine)

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repo: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager for transactional event publishing."""
        return OutboxManager(outbox_repo, redis_client, settings)

    @provide(scope=Scope.APP)
    def provide_spellcheck_event_publisher(
        self,
        outbox_manager: OutboxManager,
    ) -> SpellcheckEventPublisherProtocol:
        """Provide spellcheck event publisher using TRUE OUTBOX PATTERN."""
        return DefaultSpellcheckEventPublisher(
            kafka_event_type=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            source_service_name="spell-checker-service",
            kafka_output_topic=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            outbox_manager=outbox_manager,
        )

    @provide(scope=Scope.APP)
    async def provide_event_relay_worker(
        self,
        outbox_repo: OutboxRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> EventRelayWorker:
        """Provide event relay worker for publishing outbox events to Kafka."""
        # Create outbox settings
        outbox_settings = OutboxSettings(
            poll_interval_seconds=1.0,
            batch_size=100,
            max_retries=5,
        )

        return EventRelayWorker(
            outbox_repository=outbox_repo,
            kafka_bus=kafka_bus,
            settings=outbox_settings,
            service_name=settings.SERVICE_NAME,
            redis_client=redis_client,
        )

    @provide(scope=Scope.APP)
    def provide_spell_checker_kafka_consumer(
        self,
        settings: Settings,
        content_client: ContentClientProtocol,
        result_store: ResultStoreProtocol,
        spell_logic: SpellLogicProtocol,
        event_publisher: SpellcheckEventPublisherProtocol,
        kafka_bus: KafkaPublisherProtocol,
        http_session: ClientSession,
        redis_client: AtomicRedisClientProtocol,
        tracer: Tracer,
    ) -> SpellCheckerKafkaConsumer:
        """Provide Kafka consumer with injected dependencies."""
        return SpellCheckerKafkaConsumer(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=settings.CONSUMER_GROUP,
            consumer_client_id=settings.CONSUMER_CLIENT_ID,
            content_client=content_client,
            result_store=result_store,
            spell_logic=spell_logic,
            event_publisher=event_publisher,
            kafka_bus=kafka_bus,
            http_session=http_session,
            redis_client=redis_client,
            tracer=tracer,
        )
