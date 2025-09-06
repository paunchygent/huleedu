from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from huleedu_service_libs.kafka_client import KafkaBus
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.protocols import HttpClientProtocol


class PreflightProvider(Provider):
    scope = Scope.APP

    def __init__(self, http_client: HttpClientProtocol, kafka_bus: KafkaBus | None = None):
        super().__init__()
        self._http_client = http_client
        self._kafka = kafka_bus or AsyncMock(spec=KafkaBus)

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    def provide_metrics(self, registry: CollectorRegistry) -> GatewayMetrics:
        return GatewayMetrics(registry=registry)

    @provide
    async def get_http_client(self) -> AsyncIterator[HttpClientProtocol]:
        yield self._http_client

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        yield self._kafka

    # Provide auth-bound values directly to avoid JWT in this focused test
    @provide(scope=Scope.REQUEST)
    def provide_user_id(self) -> str:  # matches FromDishka[str]
        return "test-user"

    @provide(scope=Scope.REQUEST)
    def provide_org_id(self) -> str | None:
        return None

    @provide(scope=Scope.REQUEST)
    def provide_correlation_id(self) -> UUID:
        return uuid4()


@pytest.mark.asyncio
async def test_pipeline_request_returns_402_on_preflight_denial():
    # Mock HttpClientProtocol.post to return 402
    class DenyClient(HttpClientProtocol):
        async def post(self, url: str, *, data: dict | None = None, files: list | None = None, json: dict | None = None, headers: dict[str, str] | None = None, timeout: float | httpx.Timeout | None = None) -> httpx.Response:  # type: ignore[override]
            return httpx.Response(402, json={
                "allowed": False,
                "denial_reason": "insufficient_credits",
                "required_credits": 10,
                "available_credits": 3,
                "resource_breakdown": {"cj_comparison": 7, "ai_feedback_generation": 3},
            })

        async def get(self, url: str, *, headers: dict[str, str] | None = None, timeout: float | httpx.Timeout | None = None) -> httpx.Response:  # type: ignore[override]
            return httpx.Response(200)

    deny_client = DenyClient()
    provider = PreflightProvider(deny_client)
    container = make_async_container(provider)

    app = FastAPI()
    setup_dishka(container, app)

    from services.api_gateway_service.routers import batch_routes

    app.include_router(batch_routes.router, prefix="/v1")

    with TestClient(app) as client:
        resp = client.post(
            "/v1/batches/batch123/pipelines",
            json={"requested_pipeline": "cj_assessment"},
            headers={"Authorization": "Bearer fake"},
        )
        assert resp.status_code == 402
        data = resp.json()
        assert data["denial_reason"] == "insufficient_credits"
        assert data["required_credits"] == 10
