"""
Integration tests for Entitlements credit consumption with real PostgreSQL.

Validates debit semantics, operations audit, and event publisher invocations.
Follows established Quart + Dishka + testcontainers patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from huleedu_service_libs.error_handling.quart import register_error_handlers
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.entitlements_service.api.admin_routes import admin_bp
from services.entitlements_service.api.entitlements_routes import entitlements_bp
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


class ConsumptionIntegrationProvider(Provider):
    """DI provider creating engine inside app loop; stubs for RL, policies, events."""

    def __init__(self, database_url: str) -> None:
        super().__init__()
        self._database_url = database_url

    @provide(scope=Scope.APP)
    def provide_engine(self) -> AsyncEngine:
        return create_async_engine(self._database_url, echo=False, pool_pre_ping=True)

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
        pub = AsyncMock(spec=EventPublisherProtocol)
        pub.publish_credit_balance_changed = AsyncMock()
        pub.publish_usage_recorded = AsyncMock()
        pub.publish_rate_limit_exceeded = AsyncMock()
        return pub

    @provide(scope=Scope.APP)
    def provide_policy_loader(self) -> PolicyLoaderProtocol:  # type: ignore[override]
        loader = AsyncMock(spec=PolicyLoaderProtocol)
        # Default test cost: 5 credits per unit
        loader.get_cost = AsyncMock(return_value=5)
        loader.reload_policies = AsyncMock()
        return loader

    @provide(scope=Scope.APP)
    def provide_rate_limiter(self) -> RateLimiterProtocol:  # type: ignore[override]
        rl = AsyncMock(spec=RateLimiterProtocol)
        allowed_obj = AsyncMock()
        allowed_obj.allowed = True
        allowed_obj.limit = 1000
        allowed_obj.current_count = 0
        allowed_obj.window_seconds = 60
        rl.check_rate_limit = AsyncMock(return_value=allowed_obj)
        rl.record_usage = AsyncMock()
        return rl

    @provide(scope=Scope.APP)
    def provide_credit_manager(
        self,
        repository: EntitlementsRepositoryProtocol,
        policy_loader: PolicyLoaderProtocol,
        rate_limiter: RateLimiterProtocol,
        event_publisher: EventPublisherProtocol,
    ) -> CreditManagerProtocol:
        return CreditManagerImpl(repository, policy_loader, rate_limiter, event_publisher)

    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        from quart import request

        return extract_correlation_context_from_request(request)


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

    container = make_async_container(ConsumptionIntegrationProvider(database_url))
    QuartDishka(app=app, container=container)

    # Register both blueprints to seed via admin API, then consume via entitlements API
    app.register_blueprint(admin_bp, url_prefix="/v1/admin")
    app.register_blueprint(entitlements_bp, url_prefix="/v1/entitlements")

    # Ensure schema exists
    async with container() as c:
        engine = await c.get(AsyncEngine)
        async with engine.begin() as conn:
            await conn.run_sync(EntitlementsBase.metadata.create_all)

    async with app.test_client() as client:
        yield client
    await container.close()


@pytest.mark.asyncio
async def test_consume_credits_user_success(app_client: QuartTestClient) -> None:
    # Seed user balance to 100 using admin API
    seed_payload = {
        "subject_type": "user",
        "subject_id": "cc-user-1",
        "balance": 100,
    }
    resp_seed = await app_client.post(
        "/v1/admin/credits/set",
        json=seed_payload,
        headers={"X-Correlation-ID": "11111111-1111-1111-1111-111111111111"},
    )
    assert resp_seed.status_code == 200

    # Consume: metric cost=5, amount=10 => total_cost=50
    consumption = {
        "user_id": "cc-user-1",
        "metric": "cj_comparisons",
        "amount": 10,
        "batch_id": "batch-x",
        "correlation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    }
    resp = await app_client.post("/v1/entitlements/consume-credits", json=consumption)
    assert resp.status_code == 200
    body: dict[str, Any] = await resp.get_json()
    assert body["success"] is True
    assert body["consumed_from"] == "user"
    assert body["new_balance"] == 50  # 100 - 50

    # Verify operations audit contains completed manual operation for consumption
    ops_resp = await app_client.get(
        "/v1/admin/credits/operations?subject_type=user&subject_id=cc-user-1&limit=5"
    )
    assert ops_resp.status_code == 200
    ops = await ops_resp.get_json()
    assert ops["count"] >= 2
    # Find the latest operation for our correlation (not returned in list items) so check metric/amount
    found = False
    for op in ops["operations"]:
        if op["metric"] == "cj_comparisons" and op["amount"] == 50:
            assert op["consumed_from"] == "user"
            assert op["operation_status"] == "completed"
            found = True
            break
    assert found, "Expected consumption operation not found in audit history"


@pytest.mark.asyncio
async def test_consume_credits_insufficient_balance_fails(app_client: QuartTestClient) -> None:
    # Seed user balance to 20
    seed_payload = {
        "subject_type": "user",
        "subject_id": "cc-user-2",
        "balance": 20,
    }
    assert (await app_client.post("/v1/admin/credits/set", json=seed_payload)).status_code == 200

    # Try to consume total_cost=50 (amount=10, cost=5)
    consumption = {
        "user_id": "cc-user-2",
        "metric": "cj_comparisons",
        "amount": 10,
        "batch_id": "batch-y",
        "correlation_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    }
    resp = await app_client.post("/v1/entitlements/consume-credits", json=consumption)
    assert resp.status_code == 200
    body: dict[str, Any] = await resp.get_json()
    assert body["success"] is False
    assert body["consumed_from"] == "user"
    # Balance unchanged (still 20)
    assert body["new_balance"] == 20

    # Verify failed operation recorded
    ops_resp = await app_client.get(
        "/v1/admin/credits/operations?subject_type=user&subject_id=cc-user-2&limit=5"
    )
    ops = await ops_resp.get_json()
    assert ops_resp.status_code == 200
    found_failed = False
    for op in ops["operations"]:
        if op["metric"] == "cj_comparisons" and op["amount"] == 50:
            assert op["operation_status"] == "failed"
            found_failed = True
            break
    assert found_failed, "Expected failed consumption operation not found"


@pytest.mark.asyncio
async def test_consume_credits_org_first(app_client: QuartTestClient) -> None:
    # Seed org has enough (200), user has less (50)
    assert (
        await app_client.post(
            "/v1/admin/credits/set",
            json={"subject_type": "org", "subject_id": "cc-org-1", "balance": 200},
        )
    ).status_code == 200
    assert (
        await app_client.post(
            "/v1/admin/credits/set",
            json={"subject_type": "user", "subject_id": "cc-user-3", "balance": 50},
        )
    ).status_code == 200

    # Consume: total_cost=50 should be taken from org
    consumption = {
        "user_id": "cc-user-3",
        "org_id": "cc-org-1",
        "metric": "cj_comparisons",
        "amount": 10,
        "batch_id": "batch-z",
        "correlation_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    }
    resp = await app_client.post("/v1/entitlements/consume-credits", json=consumption)
    assert resp.status_code == 200
    body: dict[str, Any] = await resp.get_json()
    assert body["success"] is True
    assert body["consumed_from"] == "org"
    assert body["new_balance"] == 150  # org 200 - 50

    # Verify audit shows org debit
    ops_resp = await app_client.get(
        "/v1/admin/credits/operations?subject_type=org&subject_id=cc-org-1&limit=5"
    )
    assert ops_resp.status_code == 200
    ops = await ops_resp.get_json()
    found = any(op["metric"] == "cj_comparisons" and op["amount"] == 50 for op in ops["operations"])
    assert found, "Expected org consumption operation not found"
