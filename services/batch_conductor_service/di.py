"""Dependency injection configuration for Batch Conductor Service using Dishka."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import ClientSession, ClientTimeout
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from huleedu_service_libs.protocols import AtomicRedisClientProtocol, RedisClientProtocol
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
    async def provide_http_session(self, settings: Settings) -> ClientSession:
        """Provide HTTP client session."""
        timeout = ClientTimeout(total=settings.HTTP_TIMEOUT)
        return ClientSession(timeout=timeout)

    @provide(scope=Scope.APP)
    def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client with atomic operations support."""
        from huleedu_service_libs.redis_client import RedisClient

        return RedisClient(
            client_id=f"bcs-{settings.SERVICE_NAME}",
            redis_url=settings.REDIS_URL,
        )


class EventDrivenServicesProvider(Provider):
    """Provider for event-driven service dependencies."""

    @provide(scope=Scope.APP)
    def provide_batch_state_repository(
        self, redis_client: AtomicRedisClientProtocol, settings: Settings
    ) -> BatchStateRepositoryProtocol:
        """Provide batch state repository implementation."""
        from services.batch_conductor_service.implementations.batch_state_repository_impl import (
            RedisCachedBatchStateRepositoryImpl,
        )

        return RedisCachedBatchStateRepositoryImpl(
            redis_client=redis_client,
        )

    @provide(scope=Scope.APP)
    def provide_dlq_producer(self, settings: Settings) -> DlqProducerProtocol:
        """Provide Kafka DLQ producer implementation."""
        # Use in-memory no-op producer for local/test to avoid Kafka requirement
        if settings.ENV_TYPE not in {"docker", "production"}:

            class _NoOpDlqProducer:
                async def publish_to_dlq(
                    self,
                    base_topic: str,
                    failed_event_envelope,
                    dlq_reason: str,
                    additional_metadata=None,
                ) -> bool:
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
            service_name=settings.SERVICE_NAME,
        )

    def provide_kafka_consumer(
        self,
        batch_state_repository: BatchStateRepositoryProtocol,
        redis_client: RedisClientProtocol,
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
    ) -> PipelineResolutionServiceProtocol:
        """Provide pipeline resolution service implementation."""
        from services.batch_conductor_service.implementations import (
            pipeline_resolution_service_impl as prs_impl,
        )

        return prs_impl.DefaultPipelineResolutionService(
            pipeline_rules, pipeline_generator, dlq_producer
        )
