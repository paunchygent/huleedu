from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide
from prometheus_client import REGISTRY, CollectorRegistry

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.config import Settings, settings
from services.api_gateway_service.protocols import HttpClientProtocol, MetricsProtocol


class ApiGatewayProvider(Provider):
    scope = Scope.APP

    @provide
    def get_config(self) -> Settings:
        return settings

    @provide
    async def get_http_client(self, config: Settings) -> AsyncIterator[HttpClientProtocol]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.HTTP_CLIENT_TIMEOUT_SECONDS,
                connect=config.HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS,
            )
        ) as client:
            yield client

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
