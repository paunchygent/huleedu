"""Dependency injection providers for CJ Assessment Service."""

from __future__ import annotations

import aiohttp
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from opentelemetry.trace import Tracer
from prometheus_client import REGISTRY, CollectorRegistry

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.config import settings as service_settings
from services.cj_assessment_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.cj_assessment_service.implementations.cache_manager_impl import CacheManagerImpl
from services.cj_assessment_service.implementations.content_client_impl import ContentClientImpl
from services.cj_assessment_service.implementations.db_access_impl import PostgreSQLCJRepositoryImpl
from services.cj_assessment_service.implementations.event_publisher_impl import CJEventPublisherImpl
from services.cj_assessment_service.implementations.google_provider_impl import GoogleProviderImpl
from services.cj_assessment_service.implementations.llm_interaction_impl import LLMInteractionImpl
from services.cj_assessment_service.implementations.openai_provider_impl import OpenAIProviderImpl
from services.cj_assessment_service.implementations.openrouter_provider_impl import (
    OpenRouterProviderImpl,
)
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl

# Import all business logic protocols
from services.cj_assessment_service.kafka_consumer import CJAssessmentKafkaConsumer
from services.cj_assessment_service.protocols import (
    CacheProtocol,
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    LLMProviderProtocol,
    RetryManagerProtocol,
)


class CJAssessmentServiceProvider(Provider):
    """Dishka provider for CJ Assessment Service dependencies."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide application settings."""
        return service_settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_tracer(self) -> Tracer:
        """Provide OpenTelemetry tracer."""
        from opentelemetry import trace
        return trace.get_tracer("cj_assessment_service")

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> aiohttp.ClientSession:
        """Provide HTTP client session."""
        return aiohttp.ClientSession()

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        """Provide Kafka bus for event publishing."""
        kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID_CJ,
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
    def provide_cache_manager(self, settings: Settings) -> CacheProtocol:
        """Provide cache manager for LLM response caching."""
        return CacheManagerImpl(settings)

    @provide(scope=Scope.APP)
    def provide_retry_manager(self, settings: Settings) -> RetryManagerProtocol:
        """Provide retry manager for LLM API calls."""
        return RetryManagerImpl(settings)

    # Individual LLM Providers
    @provide(scope=Scope.APP)
    def provide_openai_llm_provider(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> OpenAIProviderImpl:
        """Provide OpenAI LLM provider."""
        return OpenAIProviderImpl(session, settings, retry_manager)

    @provide(scope=Scope.APP)
    def provide_anthropic_llm_provider(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> AnthropicProviderImpl:
        """Provide Anthropic LLM provider."""
        return AnthropicProviderImpl(session, settings, retry_manager)

    @provide(scope=Scope.APP)
    def provide_google_llm_provider(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> GoogleProviderImpl:
        """Provide Google LLM provider."""
        return GoogleProviderImpl(session, settings, retry_manager)

    @provide(scope=Scope.APP)
    def provide_openrouter_llm_provider(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
        retry_manager: RetryManagerProtocol,
    ) -> OpenRouterProviderImpl:
        """Provide OpenRouter LLM provider."""
        return OpenRouterProviderImpl(session, settings, retry_manager)

    # Map of providers
    @provide(scope=Scope.APP)
    def provide_llm_provider_map(
        self,
        openai: OpenAIProviderImpl,
        anthropic: AnthropicProviderImpl,
        google: GoogleProviderImpl,
        openrouter: OpenRouterProviderImpl,
    ) -> dict[str, LLMProviderProtocol]:
        """Provide dictionary of available LLM providers."""
        return {
            "openai": openai,
            "anthropic": anthropic,
            "google": google,
            "openrouter": openrouter,
        }

    @provide(scope=Scope.APP)
    def provide_llm_interaction(
        self,
        cache_manager: CacheProtocol,
        providers: dict[str, LLMProviderProtocol],
        settings: Settings,
    ) -> LLMInteractionProtocol:
        """Provide LLM interaction orchestrator."""
        # Use mock LLM for testing if enabled
        if settings.USE_MOCK_LLM:
            from services.cj_assessment_service.implementations.mock_llm_interaction_impl import (
                MockLLMInteractionImpl,
            )

            return MockLLMInteractionImpl(seed=42)  # Fixed seed for reproducible tests

        return LLMInteractionImpl(
            cache_manager=cache_manager,
            providers=providers,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_database_handler(self, settings: Settings) -> CJRepositoryProtocol:
        """Provide database handler."""
        return PostgreSQLCJRepositoryImpl(settings)

    @provide(scope=Scope.APP)
    def provide_content_client(
        self,
        session: aiohttp.ClientSession,
        settings: Settings,
    ) -> ContentClientProtocol:
        """Provide content client."""
        return ContentClientImpl(session, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        kafka_bus: KafkaBus,
        settings: Settings,
    ) -> CJEventPublisherProtocol:
        """Provide event publisher."""
        return CJEventPublisherImpl(kafka_bus, settings)

    @provide(scope=Scope.APP)
    def provide_kafka_consumer(
        self,
        settings: Settings,
        database: CJRepositoryProtocol,
        content_client: ContentClientProtocol,
        event_publisher: CJEventPublisherProtocol,
        llm_interaction: LLMInteractionProtocol,
        redis_client: RedisClientProtocol,
        tracer: Tracer,
    ) -> CJAssessmentKafkaConsumer:
        """Provide Kafka consumer for CJ Assessment Service."""
        return CJAssessmentKafkaConsumer(
            settings=settings,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            redis_client=redis_client,
            tracer=tracer,
        )
