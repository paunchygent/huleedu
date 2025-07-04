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
from huleedu_service_libs.resilience.resilient_client import make_resilient

from common_core import LLMProviderType
from services.llm_provider_service.config import Settings, settings
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
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
from services.llm_provider_service.implementations.local_queue_manager_impl import (
    LocalQueueManagerImpl as LocalQueueManagerQueue,
)
from services.llm_provider_service.implementations.openai_provider_impl import (
    OpenAIProviderImpl,
)
from services.llm_provider_service.implementations.openrouter_provider_impl import (
    OpenRouterProviderImpl,
)
from services.llm_provider_service.implementations.queue_processor_impl import (
    QueueProcessorImpl,
)
from services.llm_provider_service.implementations.redis_queue_repository_impl import (
    RedisQueueRepositoryImpl,
)
from services.llm_provider_service.implementations.resilient_queue_manager_impl import (
    ResilientQueueManagerImpl,
)
from services.llm_provider_service.implementations.retry_manager_impl import (
    RetryManagerImpl,
)
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.protocols import (
    LLMEventPublisherProtocol,
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
    LLMRetryManagerProtocol,
    QueueManagerProtocol,
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
    def provide_connection_pool_manager(self, settings: Settings) -> ConnectionPoolManagerImpl:
        """Provide connection pool manager for optimized HTTP performance."""
        return ConnectionPoolManagerImpl(settings)

    @provide(scope=Scope.APP)
    def provide_trace_context_manager(self) -> TraceContextManagerImpl:
        """Provide trace context manager for distributed tracing."""
        return TraceContextManagerImpl()

    @provide(scope=Scope.APP)
    async def provide_http_session(self, pool_manager: ConnectionPoolManagerImpl) -> ClientSession:
        """Provide HTTP client session (backward compatibility)."""
        # Default to OpenAI session for backward compatibility
        return await pool_manager.get_session("openai")

    # Queue Provider Methods
    @provide(scope=Scope.APP)
    def provide_redis_queue_repository(
        self,
        redis_client: RedisClientProtocol,
        settings: Settings,
    ) -> RedisQueueRepositoryImpl:
        """Provide Redis queue repository."""
        return RedisQueueRepositoryImpl(
            redis_client=cast(RedisClient, redis_client),
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_local_queue_manager(
        self,
        settings: Settings,
    ) -> LocalQueueManagerQueue:
        """Provide local queue manager."""
        return LocalQueueManagerQueue(settings=settings)

    @provide(scope=Scope.APP)
    def provide_queue_manager(
        self,
        redis_queue: RedisQueueRepositoryImpl,
        local_queue: LocalQueueManagerQueue,
        settings: Settings,
    ) -> QueueManagerProtocol:
        """Provide resilient queue manager."""
        return ResilientQueueManagerImpl(
            redis_queue=redis_queue,
            local_queue=local_queue,
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
    async def provide_anthropic_provider(
        self,
        pool_manager: ConnectionPoolManagerImpl,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide Anthropic/Claude provider with optimized connection pool."""
        # Get provider-specific optimized session
        anthropic_session = await pool_manager.get_session("anthropic")

        # Create base implementation
        base_provider = AnthropicProviderImpl(
            session=anthropic_session,
            settings=settings,
            retry_manager=retry_manager,
        )

        # Wrap with circuit breaker if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_anthropic")
            if circuit_breaker:
                return make_resilient(base_provider, circuit_breaker)

        return base_provider

    @provide(scope=Scope.APP)
    async def provide_openai_provider(
        self,
        pool_manager: ConnectionPoolManagerImpl,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide OpenAI provider with optimized connection pool."""
        # Get provider-specific optimized session
        openai_session = await pool_manager.get_session("openai")

        # Create base implementation
        base_provider = OpenAIProviderImpl(
            session=openai_session,
            settings=settings,
            retry_manager=retry_manager,
        )

        # Wrap with circuit breaker if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_openai")
            if circuit_breaker:
                return make_resilient(base_provider, circuit_breaker)

        return base_provider

    @provide(scope=Scope.APP)
    async def provide_google_provider(
        self,
        pool_manager: ConnectionPoolManagerImpl,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide Google Gemini provider with optimized connection pool."""
        # Get provider-specific optimized session
        google_session = await pool_manager.get_session("google")

        # Create base implementation
        base_provider = GoogleProviderImpl(
            session=google_session,
            settings=settings,
            retry_manager=retry_manager,
        )

        # Wrap with circuit breaker if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_google")
            if circuit_breaker:
                return make_resilient(base_provider, circuit_breaker)

        return base_provider

    @provide(scope=Scope.APP)
    async def provide_openrouter_provider(
        self,
        pool_manager: ConnectionPoolManagerImpl,
        settings: Settings,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> LLMProviderProtocol:
        """Provide OpenRouter provider with optimized connection pool."""
        # Get provider-specific optimized session
        openrouter_session = await pool_manager.get_session("openrouter")

        # Create base implementation
        base_provider = OpenRouterProviderImpl(
            session=openrouter_session,
            settings=settings,
            retry_manager=retry_manager,
        )

        # Wrap with circuit breaker if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            circuit_breaker = circuit_breaker_registry.get("llm_openrouter")
            if circuit_breaker:
                return make_resilient(base_provider, circuit_breaker)

        return base_provider

    @provide(scope=Scope.APP)
    async def provide_llm_provider_map(
        self,
        settings: Settings,
        pool_manager: ConnectionPoolManagerImpl,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> Dict[LLMProviderType, LLMProviderProtocol]:
        """Provide dictionary of available LLM providers with optimized connection pools."""
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

        # Build providers map by calling the individual async provider methods
        # This ensures each provider gets its own optimized connection pool
        return {
            LLMProviderType.ANTHROPIC: await self.provide_anthropic_provider(
                pool_manager, settings, retry_manager, circuit_breaker_registry
            ),
            LLMProviderType.OPENAI: await self.provide_openai_provider(
                pool_manager, settings, retry_manager, circuit_breaker_registry
            ),
            LLMProviderType.GOOGLE: await self.provide_google_provider(
                pool_manager, settings, retry_manager, circuit_breaker_registry
            ),
            LLMProviderType.OPENROUTER: await self.provide_openrouter_provider(
                pool_manager, settings, retry_manager, circuit_breaker_registry
            ),
        }

    @provide(scope=Scope.APP)
    def provide_llm_orchestrator(
        self,
        settings: Settings,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        event_publisher: LLMEventPublisherProtocol,
        queue_manager: QueueManagerProtocol,
        trace_context_manager: TraceContextManagerImpl,
    ) -> LLMOrchestratorProtocol:
        """Provide LLM orchestrator implementation."""
        return LLMOrchestratorImpl(
            providers=providers,
            event_publisher=event_publisher,
            queue_manager=queue_manager,
            trace_context_manager=trace_context_manager,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_queue_processor(
        self,
        orchestrator: LLMOrchestratorProtocol,
        queue_manager: QueueManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
        trace_context_manager: TraceContextManagerImpl,
        settings: Settings,
    ) -> QueueProcessorImpl:
        """Provide queue processor for background request processing."""
        return QueueProcessorImpl(
            orchestrator=orchestrator,
            queue_manager=queue_manager,
            event_publisher=event_publisher,
            trace_context_manager=trace_context_manager,
            settings=settings,
        )
