"""Dependency injection configuration for NLP Service."""

from __future__ import annotations

from typing import Any

from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from opentelemetry.trace import Tracer
from prometheus_client import CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine

from services.nlp_service.config import Settings, settings
from services.nlp_service.implementations.outbox_manager import OutboxManager
from services.nlp_service.kafka_consumer import NlpKafkaConsumer
from services.nlp_service.metrics import get_business_metrics
from services.nlp_service.repositories.nlp_repository import NlpRepository


class NlpServiceProvider(Provider):
    """Provider for NLP Service dependencies."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize provider with database engine."""
        super().__init__()
        self._engine = engine

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox configuration."""
        return settings.SERVICE_NAME

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        from prometheus_client import REGISTRY
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_tracer(self) -> Tracer:
        """Provide OpenTelemetry tracer."""
        from opentelemetry import trace
        return trace.get_tracer("nlp_service")

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaPublisherProtocol:
        """Provide Kafka bus for event publishing."""
        kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client for caching and idempotency."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()
        return redis_client


    @provide(scope=Scope.REQUEST)
    def provide_kafka_consumer(
        self,
        settings: Settings,
        kafka_bus: KafkaPublisherProtocol,
        redis_client: AtomicRedisClientProtocol,
        tracer: Tracer,
    ) -> NlpKafkaConsumer:
        """Provide Kafka consumer instance."""
        return NlpKafkaConsumer(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=settings.CONSUMER_GROUP,
            consumer_client_id=settings.CONSUMER_CLIENT_ID,
            kafka_bus=kafka_bus,
            redis_client=redis_client,
            tracer=tracer,
        )

    @provide(scope=Scope.APP)
    def provide_business_metrics(self) -> dict[str, Any]:
        """Provide business metrics."""
        return get_business_metrics()

    @provide(scope=Scope.APP)
    def provide_engine(self) -> AsyncEngine:
        """Provide database engine."""
        return self._engine

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager for reliable event publishing."""
        return OutboxManager(outbox_repository, redis_client, settings)

    @provide(scope=Scope.REQUEST)
    def provide_nlp_repository(self, engine: AsyncEngine) -> NlpRepository:
        """Provide NLP repository for database access."""
        return NlpRepository(engine)
