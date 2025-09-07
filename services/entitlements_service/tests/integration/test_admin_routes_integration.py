"""
Integration tests for Entitlements admin endpoints with real PostgreSQL via testcontainers.

Validates end-to-end persistence for credit set operations and operations audit.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.quart import register_error_handlers
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.entitlements_service.api.admin_routes import admin_bp
from services.entitlements_service.implementations.credit_manager_impl import CreditManagerImpl
from services.entitlements_service.implementations.repository_impl import EntitlementsRepositoryImpl
from services.entitlements_service.models_db import Base as EntitlementsBase
from services.entitlements_service.protocols import (
    CreditManagerProtocol,
    EntitlementsRepositoryProtocol,
    EventPublisherProtocol,
    PolicyLoaderProtocol,
    RateLimiterProtocol,
)


class AdminIntegrationProvider(Provider):
    """Integration DI provider that creates engine within the app loop.

    This avoids event loop mismatches by ensuring the AsyncEngine and sessions
    are created in the same loop that serves the Quart requests.
    """

    def __init__(self, database_url: str) -> None:
        super().__init__()
        self._database_url = database_url

    @provide(scope=Scope.APP)
    def provide_engine(self) -> AsyncEngine:
        # Create engine inside app's loop; disable pooling to avoid cross-loop issues
        # in tests. Production uses pooling via service DI.
        engine = create_async_engine(self._database_url, echo=False, pool_pre_ping=True)
        return engine

    @provide(scope=Scope.APP)
    def provide_session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.APP)
    def provide_repository(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> EntitlementsRepositoryProtocol:
        return EntitlementsRepositoryImpl(session_factory)

    @provide(scope=Scope.APP)
    def provide_event_publisher(self) -> EventPublisherProtocol:  # type: ignore[override]
        # Minimal stub; admin balance changes publish events but tests don't require Kafka
        stub = AsyncMock(spec=EventPublisherProtocol)
        stub.publish_credit_balance_changed = AsyncMock()
        stub.publish_rate_limit_exceeded = AsyncMock()
        return stub

    @provide(scope=Scope.APP)
    def provide_policy_loader(self) -> PolicyLoaderProtocol:  # type: ignore[override]
        # Not used in admin operations; provide trivial stub
        stub = AsyncMock(spec=PolicyLoaderProtocol)
        stub.get_cost = AsyncMock(return_value=1)
        stub.reload_policies = AsyncMock()
        return stub

    @provide(scope=Scope.APP)
    def provide_rate_limiter(self) -> RateLimiterProtocol:  # type: ignore[override]
        stub = AsyncMock(spec=RateLimiterProtocol)
        stub.check_rate_limit = AsyncMock(return_value=AsyncMock(allowed=True))
        return stub

    @provide(scope=Scope.APP)
    def provide_credit_manager(
        self,
        repository: EntitlementsRepositoryProtocol,
        policy_loader: PolicyLoaderProtocol,
        rate_limiter: RateLimiterProtocol,
        event_publisher: EventPublisherProtocol,
    ) -> CreditManagerProtocol:
        return CreditManagerImpl(repository, policy_loader, rate_limiter, event_publisher)


@pytest.fixture(scope="module")
def postgres_container() -> PostgresContainer:
    container = PostgresContainer("postgres:15")
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="module")
def database_url(postgres_container: PostgresContainer) -> str:
    url = str(postgres_container.get_connection_url())
    url = url.replace("+psycopg2://", "+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


@pytest.fixture
async def app_client(database_url: str) -> AsyncGenerator[QuartTestClient, None]:
    from quart import Quart

    app = Quart(__name__)
    app.config.update({"TESTING": True})
    register_error_handlers(app)

    # Create container with provider that creates engine & session in app loop
    container = make_async_container(AdminIntegrationProvider(database_url))
    QuartDishka(app=app, container=container)
    app.register_blueprint(admin_bp, url_prefix="/v1/admin")

    # Ensure DB schema exists using the engine from the container
    async with container() as c:
        engine = await c.get(AsyncEngine)
        async with engine.begin() as conn:
            await conn.run_sync(EntitlementsBase.metadata.create_all)

    async with app.test_client() as client:
        yield client
    await container.close()


@pytest.mark.asyncio
async def test_set_credits_persists_and_audits(app_client: QuartTestClient) -> None:
    # Seed user balance to 0 → set to 250
    payload = {"subject_type": "user", "subject_id": "integration-user-1", "balance": 250}
    resp = await app_client.post(
        "/v1/admin/credits/set",
        json=payload,
        headers={"X-Correlation-ID": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
    )
    assert resp.status_code == 200
    data: dict[str, Any] = await resp.get_json()
    assert data["success"] is True
    assert data["balance"] == 250
    assert data["correlation_id"]

    # Verify via operations audit API
    # Reuse same app_client (admin blueprint also exposes operations)
    # Note: The operations endpoint is on /v1/admin/credits/operations
    resp_ops = await app_client.get(
        f"/v1/admin/credits/operations?subject_type=user&subject_id=integration-user-1&limit=10"
    )
    assert resp_ops.status_code == 200
    ops = await resp_ops.get_json()
    assert ops["count"] >= 1
    first = ops["operations"][0]
    assert first["subject_type"] == "user"
    assert first["subject_id"] == "integration-user-1"
    assert first["metric"] == "manual_adjustment"
    assert first["amount"] == 250
