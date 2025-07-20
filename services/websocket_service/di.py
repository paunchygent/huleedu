from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from prometheus_client import REGISTRY, CollectorRegistry

from services.websocket_service.config import Settings, settings
from services.websocket_service.implementations.jwt_validator import JWTValidator
from services.websocket_service.implementations.message_listener import RedisMessageListener
from services.websocket_service.implementations.websocket_manager import WebSocketManager
from services.websocket_service.metrics import WebSocketMetrics
from services.websocket_service.protocols import (
    JWTValidatorProtocol,
    MessageListenerProtocol,
    WebSocketManagerProtocol,
)


class WebSocketServiceProvider(Provider):
    """Dependency injection provider for WebSocket service."""

    scope = Scope.APP

    @provide
    def get_config(self) -> Settings:
        """Provide service configuration."""
        return settings

    @provide
    async def get_redis_client(self, config: Settings) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide Redis client for pub/sub operations."""
        client = RedisClient(
            client_id=config.SERVICE_NAME,
            redis_url=config.REDIS_URL,
        )
        await client.start()
        yield client
        await client.stop()

    @provide(scope=Scope.APP)
    def provide_websocket_manager(self, config: Settings) -> WebSocketManagerProtocol:
        """Provide WebSocket connection manager."""
        return WebSocketManager(max_connections_per_user=config.WEBSOCKET_MAX_CONNECTIONS_PER_USER)

    @provide(scope=Scope.APP)
    def provide_jwt_validator(self, config: Settings) -> JWTValidatorProtocol:
        """Provide JWT token validator."""
        return JWTValidator(
            secret_key=config.JWT_SECRET_KEY,
            algorithm=config.JWT_ALGORITHM,
        )

    @provide(scope=Scope.SESSION)
    def provide_message_listener(
        self,
        redis_client: AtomicRedisClientProtocol,
        websocket_manager: WebSocketManagerProtocol,
    ) -> MessageListenerProtocol:
        """Provide Redis message listener for WebSocket forwarding."""
        return RedisMessageListener(
            redis_client=redis_client,
            websocket_manager=websocket_manager,
        )

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide Prometheus registry."""
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_metrics(self, registry: CollectorRegistry) -> WebSocketMetrics:
        """Provide Prometheus metrics collector."""
        return WebSocketMetrics(registry=registry)
