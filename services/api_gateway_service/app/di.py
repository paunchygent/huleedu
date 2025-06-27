from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.redis_client import RedisClient

from services.api_gateway_service.config import Settings, settings


class ApiGatewayProvider(Provider):
    scope = Scope.APP

    @provide
    def get_config(self) -> Settings:
        return settings

    @provide
    async def get_http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.HTTP_CLIENT_TIMEOUT_SECONDS,
                connect=settings.HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS,
            )
        ) as client:
            yield client

    @provide
    async def get_redis_client(self) -> AsyncIterator[RedisClient]:
        client = RedisClient(client_id=settings.SERVICE_NAME, redis_url="redis://redis:6379")
        await client.start()
        yield client
        await client.stop()

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        kafka_bus = KafkaBus(
            client_id=settings.SERVICE_NAME, bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
        )
        await kafka_bus.start()
        yield kafka_bus
        await kafka_bus.stop()
