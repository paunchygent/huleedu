"""Dependency injection configuration for CJ Assessment Service."""

from __future__ import annotations

from typing import Dict

import aiohttp
from aiokafka import AIOKafkaProducer
from config import Settings
from config import settings as service_settings
from dishka import Provider, Scope, provide
from implementations.anthropic_provider_impl import AnthropicProviderImpl
from implementations.cache_manager_impl import CacheManagerImpl
from implementations.content_client_impl import ContentClientImpl
from implementations.db_access_impl import CJDatabaseImpl
from implementations.event_publisher_impl import CJEventPublisherImpl
from implementations.google_provider_impl import GoogleProviderImpl
from implementations.llm_interaction_impl import LLMInteractionImpl
from implementations.openai_provider_impl import OpenAIProviderImpl
from implementations.openrouter_provider_impl import OpenRouterProviderImpl
from implementations.retry_manager_impl import RetryManagerImpl
from prometheus_client import CollectorRegistry
from protocols import (
    CacheProtocol,
    CJDatabaseProtocol,
    CJEventPublisherProtocol,
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
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> aiohttp.ClientSession:
        """Provide HTTP client session."""
        return aiohttp.ClientSession()

    @provide(scope=Scope.APP)
    async def provide_kafka_producer(self, settings: Settings) -> AIOKafkaProducer:
        """Provide Kafka producer."""
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id=settings.PRODUCER_CLIENT_ID_CJ,
        )
        await producer.start()
        return producer

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
    ) -> Dict[str, LLMProviderProtocol]:
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
        providers: Dict[str, LLMProviderProtocol],
        settings: Settings,
    ) -> LLMInteractionProtocol:
        """Provide LLM interaction orchestrator."""
        return LLMInteractionImpl(
            cache_manager=cache_manager, providers=providers, settings=settings
        )

    @provide(scope=Scope.APP)
    def provide_database_handler(self, settings: Settings) -> CJDatabaseProtocol:
        """Provide database handler."""
        return CJDatabaseImpl(settings)

    @provide(scope=Scope.APP)
    def provide_content_client(
        self, session: aiohttp.ClientSession, settings: Settings
    ) -> ContentClientProtocol:
        """Provide content client."""
        return ContentClientImpl(session, settings)

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, producer: AIOKafkaProducer, settings: Settings
    ) -> CJEventPublisherProtocol:
        """Provide event publisher."""
        return CJEventPublisherImpl(producer, settings)
