"""Dependency injection configuration for LLM Provider Service using Dishka."""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, cast

from aiohttp import ClientError, ClientSession
from aiokafka.errors import KafkaError
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry

from common_core import LLMProviderType
from services.llm_provider_service.config import Settings, settings
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.implementations.event_publisher_impl import (
    LLMEventPublisherImpl,
)
from services.llm_provider_service.implementations.google_provider_impl import (
    GoogleProviderImpl,
)
from services.llm_provider_service.implementations.llm_orchestrator_impl import (
    LLMOrchestratorImpl,
)
from services.llm_provider_service.implementations.local_cache_manager_impl import (
    LocalCacheManagerImpl,
)
from services.llm_provider_service.implementations.openai_provider_impl import (
    OpenAIProviderImpl,
)
from services.llm_provider_service.implementations.openrouter_provider_impl import (
    OpenRouterProviderImpl,
)
from services.llm_provider_service.implementations.redis_cache_repository_impl import (
    RedisCacheRepositoryImpl,
)
from services.llm_provider_service.implementations.resilient_cache_manager_impl import (
    ResilientCacheManagerImpl,
)
from services.llm_provider_service.implementations.retry_manager_impl import (
    RetryManagerImpl,
)
from services.llm_provider_service.protocols import (
    LLMCacheManagerProtocol,
    LLMEventPublisherProtocol,
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
    LLMRetryManagerProtocol,
)


class LLMProviderServiceProvider(Provider):
    """Dishka provider for LLM Provider Service dependencies."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
        """Provide Redis client for caching."""
        redis_client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await redis_client.start()
        return redis_client

    @provide(scope=Scope.APP)
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry."""
        registry = CircuitBreakerRegistry()

        if settings.CIRCUIT_BREAKER_ENABLED:
            # Register circuit breakers for each LLM provider
            for provider in ["anthropic", "openai", "google", "openrouter"]:
                registry.register(
                    f"llm_{provider}",
                    CircuitBreaker(
                        name=f"llm_provider.{provider}",
                        failure_threshold=settings.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                        recovery_timeout=timedelta(
                            seconds=settings.LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
                        ),
                        success_threshold=settings.LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                        expected_exception=ClientError,
                    ),
                )

        return registry

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaBus:
        """Provide Kafka bus for event publishing with optional circuit breaker protection."""
        # Create base KafkaBus instance
        base_kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}-producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )

        # Wrap with circuit breaker protection if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            kafka_circuit_breaker = CircuitBreaker(
                name=f"{settings.SERVICE_NAME}.kafka_producer",
                failure_threshold=settings.KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=timedelta(seconds=settings.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
                success_threshold=settings.KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                expected_exception=KafkaError,
            )
            circuit_breaker_registry.register("kafka_producer", kafka_circuit_breaker)

            # Create resilient wrapper
            resilient_kafka_bus = ResilientKafkaPublisher(
                delegate=base_kafka_bus,
                circuit_breaker=kafka_circuit_breaker,
                retry_interval=30,
            )
            await resilient_kafka_bus.start()
            # Return as KafkaBus type for compatibility
            return cast(KafkaBus, resilient_kafka_bus)
        else:
            # Use base KafkaBus without circuit breaker
            await base_kafka_bus.start()
            return base_kafka_bus

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> ClientSession:
        """Provide HTTP client session."""
        return ClientSession()

    @provide(scope=Scope.APP)
    def provide_redis_cache_repository(
        self,
        redis_client: RedisClientProtocol,
        settings: Settings,
    ) -> RedisCacheRepositoryImpl:
        """Provide Redis cache repository."""
        return RedisCacheRepositoryImpl(
            redis_client=cast(RedisClient, redis_client),
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_local_cache_manager(self, settings: Settings) -> LocalCacheManagerImpl:
        """Provide local cache manager."""
        return LocalCacheManagerImpl(settings=settings)

    @provide(scope=Scope.APP)
    def provide_cache_manager(
        self,
        redis_cache: RedisCacheRepositoryImpl,
        local_cache: LocalCacheManagerImpl,
        settings: Settings,
    ) -> LLMCacheManagerProtocol:
        """Provide resilient cache manager with Redis primary and local fallback."""
        return ResilientCacheManagerImpl(
            redis_cache=redis_cache,
            local_cache=local_cache,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self,
        kafka_bus: KafkaBus,
        settings: Settings,
    ) -> LLMEventPublisherProtocol:
        """Provide event publisher implementation."""
        return LLMEventPublisherImpl(kafka_bus=kafka_bus, settings=settings)

    @provide(scope=Scope.APP)
    def provide_retry_manager(self, settings: Settings) -> LLMRetryManagerProtocol:
        """Provide retry manager implementation."""
        return RetryManagerImpl(settings=settings)

    @provide(scope=Scope.APP)
    def provide_anthropic_provider(
        self,
        http_session: ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide Anthropic/Claude provider."""
        circuit_breaker = None
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_anthropic")

        return AnthropicProviderImpl(
            session=http_session,
            settings=settings,
            retry_manager=retry_manager,
        )

    @provide(scope=Scope.APP)
    def provide_openai_provider(
        self,
        http_session: ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide OpenAI provider."""
        circuit_breaker = None
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_openai")

        return OpenAIProviderImpl(
            session=http_session,
            settings=settings,
            retry_manager=retry_manager,
        )

    @provide(scope=Scope.APP)
    def provide_google_provider(
        self,
        http_session: ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide Google Gemini provider."""
        circuit_breaker = None
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_google")

        return GoogleProviderImpl(
            session=http_session,
            settings=settings,
            retry_manager=retry_manager,
        )

    @provide(scope=Scope.APP)
    def provide_openrouter_provider(
        self,
        http_session: ClientSession,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide OpenRouter provider."""
        circuit_breaker = None
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_openrouter")

        return OpenRouterProviderImpl(
            session=http_session,
            settings=settings,
            retry_manager=retry_manager,
        )

    @provide(scope=Scope.APP)
    def provide_llm_provider_map(
        self,
        settings: Settings,
        anthropic_provider: LLMProviderProtocol,
        openai_provider: LLMProviderProtocol,
        google_provider: LLMProviderProtocol,
        openrouter_provider: LLMProviderProtocol,
    ) -> Dict[LLMProviderType, LLMProviderProtocol]:
        """Provide dictionary of available LLM providers."""
        # Use mock provider for testing if enabled
        if settings.USE_MOCK_LLM:
            from services.llm_provider_service.implementations.mock_provider_impl import (
                MockProviderImpl,
            )

            mock_provider = MockProviderImpl(settings=settings, seed=42)
            return {
                LLMProviderType.MOCK: mock_provider,
                LLMProviderType.ANTHROPIC: mock_provider,
                LLMProviderType.OPENAI: mock_provider,
                LLMProviderType.GOOGLE: mock_provider,
                LLMProviderType.OPENROUTER: mock_provider,
            }

        return {
            LLMProviderType.ANTHROPIC: anthropic_provider,
            LLMProviderType.OPENAI: openai_provider,
            LLMProviderType.GOOGLE: google_provider,
            LLMProviderType.OPENROUTER: openrouter_provider,
        }

    @provide(scope=Scope.APP)
    def provide_llm_orchestrator(
        self,
        settings: Settings,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        cache_manager: LLMCacheManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
    ) -> LLMOrchestratorProtocol:
        """Provide LLM orchestrator implementation."""
        return LLMOrchestratorImpl(
            providers=providers,
            cache_manager=cache_manager,
            event_publisher=event_publisher,
            settings=settings,
        )
