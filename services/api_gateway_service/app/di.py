from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
from dishka import Provider, Scope, provide
from prometheus_client import REGISTRY, CollectorRegistry

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.config import Settings, settings
from services.api_gateway_service.implementations.circuit_breaker_http_client import (
    ApiGatewayCircuitBreakerHttpClient,
)
from services.api_gateway_service.implementations.http_client import ApiGatewayHttpClient
from services.api_gateway_service.protocols import HttpClientProtocol, MetricsProtocol


class ApiGatewayProvider(Provider):
    scope = Scope.APP

    @provide
    def get_config(self) -> Settings:
        return settings

    @provide(scope=Scope.APP)
    def provide_circuit_breaker_registry(self) -> CircuitBreakerRegistry:
        return CircuitBreakerRegistry()

    @provide(scope=Scope.APP)
    async def get_http_client(
        self, config: Settings, registry: CircuitBreakerRegistry
    ) -> AsyncIterator[HttpClientProtocol]:
        # Create httpx AsyncClient with proper timeouts
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.HTTP_CLIENT_TIMEOUT_SECONDS,
                connect=config.HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS,
            )
        ) as httpx_client:
            # Create API Gateway's HTTP client implementation
            base_client = ApiGatewayHttpClient(httpx_client)

            if config.CIRCUIT_BREAKER_ENABLED:
                # Create circuit breaker for HTTP client
                circuit_breaker = CircuitBreaker(
                    name=f"{config.SERVICE_NAME}.http_client",
                    failure_threshold=config.HTTP_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                    recovery_timeout=timedelta(
                        seconds=config.HTTP_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
                    ),
                    success_threshold=config.HTTP_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                    expected_exception=httpx.HTTPError,
                )
                registry.register("http_client", circuit_breaker)
                yield ApiGatewayCircuitBreakerHttpClient(base_client, circuit_breaker)
            else:
                yield base_client

    @provide
    async def get_redis_client(self, config: Settings) -> AsyncIterator[AtomicRedisClientProtocol]:
        client = RedisClient(client_id=config.SERVICE_NAME, redis_url=config.REDIS_URL)
        await client.start()
        yield client
        await client.stop()

    @provide
    async def get_kafka_bus(self, config: Settings) -> AsyncIterator[KafkaBus]:
        kafka_bus = KafkaBus(
            client_id=config.SERVICE_NAME, bootstrap_servers=config.KAFKA_BOOTSTRAP_SERVERS
        )
        await kafka_bus.start()
        yield kafka_bus
        await kafka_bus.stop()

    @provide(scope=Scope.APP)
    def provide_metrics(self) -> MetricsProtocol:
        return GatewayMetrics()

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        return REGISTRY
