"""Dependency injection configuration for Batch Conductor Service using Dishka."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp import ClientSession, ClientTimeout
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from services.batch_conductor_service.config import Settings, settings
from services.batch_conductor_service.protocols import (
    BatchStateRepositoryProtocol,
    DlqProducerProtocol,
    KafkaEventConsumerProtocol,
    PipelineGeneratorProtocol,
    PipelineResolutionServiceProtocol,
    PipelineRulesProtocol,
)

if TYPE_CHECKING:
    pass


class CoreInfrastructureProvider(Provider):
    """Provider for core infrastructure dependencies (settings, metrics, HTTP)."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    def provide_metrics(self) -> dict[str, Any]:
        """Provide metrics for pipeline service integration."""
        from services.batch_conductor_service.metrics import get_pipeline_service_metrics

        return get_pipeline_service_metrics()

    @provide(scope=Scope.APP)
    async def provide_http_session(self, settings: Settings) -> ClientSession:
        """Provide HTTP client session."""
        timeout = ClientTimeout(total=settings.HTTP_TIMEOUT)
        return ClientSession(timeout=timeout)

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client with atomic operations and pub/sub support."""
        from huleedu_service_libs.redis_client import RedisClient

        redis_client = RedisClient(
            client_id=f"bcs-{settings.SERVICE_NAME}",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()
        return redis_client


class EventDrivenServicesProvider(Provider):
    """Provider for event-driven service dependencies."""

    @provide(scope=Scope.APP)
    def provide_batch_state_repository(
        self, redis_client: AtomicRedisClientProtocol, settings: Settings
    ) -> BatchStateRepositoryProtocol:
        """
        Provide batch state repository with cache-aside pattern.

        Uses Redis for fast lookups (7-day TTL) and PostgreSQL for permanent storage.
        This enables dependency resolution even weeks/months after phases complete.
        """
        if settings.ENVIRONMENT == "testing" or getattr(settings, "USE_MOCK_REPOSITORY", False):
            from services.batch_conductor_service.implementations import (
                mock_batch_state_repository,
            )

            return mock_batch_state_repository.MockBatchStateRepositoryImpl()
        else:
            from services.batch_conductor_service.implementations import (
                postgres_batch_state_repository,
                redis_batch_state_repository,
            )

            # Create PostgreSQL repository for permanent storage
            postgres_repo = postgres_batch_state_repository.PostgreSQLBatchStateRepositoryImpl(
                database_url=settings.database_url
            )

            # Create Redis repository with PostgreSQL fallback
            return redis_batch_state_repository.RedisCachedBatchStateRepositoryImpl(
                redis_client=redis_client,
                postgres_repository=postgres_repo,  # Wire both repositories together!
            )

    @provide(scope=Scope.APP)
    def provide_dlq_producer(self, settings: Settings) -> DlqProducerProtocol:
        """Provide Kafka DLQ producer implementation."""
        # Use in-memory no-op producer for development/testing to avoid Kafka requirement
        if settings.is_development() or settings.is_testing():

            class _NoOpDlqProducer:
                async def publish_to_dlq(
                    self,
                    base_topic: str,
                    failed_event_envelope,
                    dlq_reason: str,
                    additional_metadata=None,
                ) -> bool:
                    _ = (base_topic, failed_event_envelope, dlq_reason, additional_metadata)
                    return True

            return _NoOpDlqProducer()

        from huleedu_service_libs.kafka_client import KafkaBus
        from services.batch_conductor_service.implementations.kafka_dlq_producer_impl import (
            KafkaDlqProducerImpl,
        )

        # Create KafkaBus for DLQ publishing
        kafka_bus = KafkaBus(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=f"bcs-dlq-{settings.SERVICE_NAME}",
        )

        return KafkaDlqProducerImpl(
            kafka_bus=kafka_bus,
        )

    @provide(scope=Scope.APP)
    def provide_kafka_consumer(
        self,
        batch_state_repository: BatchStateRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> KafkaEventConsumerProtocol:
        """Provide Kafka event consumer implementation."""
        from services.batch_conductor_service.kafka_consumer import BCSKafkaConsumer

        return BCSKafkaConsumer(
            kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=settings.KAFKA_CONSUMER_GROUP_ID,
            batch_state_repo=batch_state_repository,
            redis_client=redis_client,
        )

    @provide(scope=Scope.APP)
    async def provide_event_publisher(self, settings: Settings) -> KafkaPublisherProtocol:
        """Provide Kafka event publisher for BCS phase events."""
        # Use no-op publisher for development/testing to avoid Kafka requirement
        if settings.is_development() or settings.is_testing():
            from huleedu_service_libs.logging_utils import create_service_logger

            logger = create_service_logger("bcs.di.event_publisher")
            logger.info(f"Using NoOpEventPublisher for {settings.ENVIRONMENT.value} environment")

            class _NoOpEventPublisher:
                async def start(self) -> None:
                    pass

                async def stop(self) -> None:
                    pass

                async def publish(
                    self,
                    topic: str,
                    envelope,
                    key: str | None = None,
                    headers: dict[str, str] | None = None,
                ) -> None:
                    logger.debug(
                        f"NoOp: Would publish to {topic} with key {key}, headers: {headers}"
                    )

            return _NoOpEventPublisher()

        from huleedu_service_libs.kafka_client import KafkaBus
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("bcs.di.event_publisher")
        logger.info(
            "Creating real KafkaBus for event publishing in "
            f"{settings.ENVIRONMENT.value} environment"
        )

        # Create KafkaBus for event publishing
        kafka_bus = KafkaBus(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=f"bcs-events-{settings.SERVICE_NAME}",
        )

        # Start the publisher immediately since it's APP-scoped
        await kafka_bus.start()
        logger.info("KafkaBus event publisher started successfully")

        return kafka_bus


class PipelineServicesProvider(Provider):
    """Provider for pipeline-related service dependencies."""

    @provide(scope=Scope.APP)
    async def provide_pipeline_generator(self, settings: Settings) -> PipelineGeneratorProtocol:
        """Provide pipeline generator implementation."""
        from services.batch_conductor_service.implementations.pipeline_generator_impl import (
            DefaultPipelineGenerator,
        )

        generator = DefaultPipelineGenerator(settings)
        # Ensure configuration is loaded during initialization
        await generator._ensure_loaded()
        return generator

    @provide(scope=Scope.APP)
    def provide_pipeline_rules(
        self,
        pipeline_generator: PipelineGeneratorProtocol,
        batch_state_repository: BatchStateRepositoryProtocol,
    ) -> PipelineRulesProtocol:
        """Provide pipeline rules implementation."""
        from services.batch_conductor_service.implementations.pipeline_rules_impl import (
            DefaultPipelineRules,
        )

        return DefaultPipelineRules(pipeline_generator, batch_state_repository)

    @provide(scope=Scope.APP)
    def provide_pipeline_resolution_service(
        self,
        pipeline_rules: PipelineRulesProtocol,
        pipeline_generator: PipelineGeneratorProtocol,
        dlq_producer: DlqProducerProtocol,
        event_publisher: KafkaPublisherProtocol,
        metrics: dict[str, Any],
    ) -> PipelineResolutionServiceProtocol:
        """Provide pipeline resolution service implementation with proper DI metrics injection."""
        from services.batch_conductor_service.implementations import (
            pipeline_resolution_service_impl as prs_impl,
        )

        # Create service instance with metrics injected via constructor
        service = prs_impl.DefaultPipelineResolutionService(
            pipeline_rules, pipeline_generator, dlq_producer, event_publisher, metrics
        )

        return service
