"""Dependency injection configuration for Batch Conductor Service using Dishka."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import ClientSession, ClientTimeout

# DlqProducerProtocol must be importable at runtime for Dishka type analysis
from services.batch_conductor_service.protocols import DlqProducerProtocol
_DLP_RT: type[DlqProducerProtocol] = DlqProducerProtocol

if TYPE_CHECKING:
    from services.batch_conductor_service.protocols import DlqProducerProtocol
from dishka import Provider, Scope, provide
from prometheus_client import CollectorRegistry

from huleedu_service_libs.protocols import RedisClientProtocol
from services.batch_conductor_service.config import Settings, settings
from services.batch_conductor_service.protocols import (
    BatchStateRepositoryProtocol,
    KafkaEventConsumerProtocol,
    PipelineGeneratorProtocol,
    PipelineResolutionServiceProtocol,
    PipelineRulesProtocol,
)


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
    async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
        """Provide Redis client implementation."""
        from huleedu_service_libs.redis_client import RedisClient

        return RedisClient(
            client_id="batch-conductor-service",
            redis_url=settings.REDIS_URL
        )


class EventDrivenServicesProvider(Provider):
    """Provider for event-driven service dependencies."""

    @provide(scope=Scope.APP)
    def provide_batch_state_repository(
        self, redis_client: RedisClientProtocol, settings: Settings
    ) -> BatchStateRepositoryProtocol:
        """Provide batch state repository implementation."""
        from services.batch_conductor_service.implementations.batch_state_repository_impl import (
            RedisCachedBatchStateRepositoryImpl,
        )

        # For now, use Redis-only. PostgreSQL integration would be added later
        return RedisCachedBatchStateRepositoryImpl(redis_client=redis_client)

    @provide(scope=Scope.APP)
    def provide_dlq_producer(self, settings: Settings) -> "DlqProducerProtocol":
        """Provide Kafka DLQ producer implementation."""
                # Use in-memory no-op producer for local/test to avoid Kafka requirement
        if settings.ENV_TYPE not in {"docker", "production"}:
            class _NoOpDlqProducer:
                async def publish(self, envelope: dict, reason: str) -> None:
                    pass
            return _NoOpDlqProducer()

        from services.batch_conductor_service.implementations.kafka_dlq_producer_impl import (
            KafkaDlqProducerImpl,
        )

        return KafkaDlqProducerImpl(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            base_topic="huleedu.pipelines.resolution",
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
    def provide_pipeline_generator(self, settings: Settings) -> PipelineGeneratorProtocol:
        """Provide pipeline generator implementation."""
        from services.batch_conductor_service.implementations.pipeline_generator_impl import (
            DefaultPipelineGenerator,
        )

        return DefaultPipelineGenerator(settings)

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
        dlq_producer: "DlqProducerProtocol",
    ) -> PipelineResolutionServiceProtocol:
        """Provide pipeline resolution service implementation."""
        from services.batch_conductor_service.implementations.pipeline_resolution_service_impl import (
            DefaultPipelineResolutionService,
        )

        return DefaultPipelineResolutionService(pipeline_rules, pipeline_generator, dlq_producer)
