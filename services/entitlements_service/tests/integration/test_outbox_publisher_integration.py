"""
Integration test: verify real EventPublisher writes to shared outbox table.

Asserts topic, event_type, event_key and envelope correlation_id are correct.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from common_core import ProcessingEvent, topic_name
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.outbox.models import Base as OutboxBase
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.entitlements_service.api.admin_routes import admin_bp
from services.entitlements_service.api.entitlements_routes import entitlements_bp
from services.entitlements_service.config import Settings
from services.entitlements_service.implementations.credit_manager_impl import CreditManagerImpl
from services.entitlements_service.implementations.event_publisher_impl import (
    EventPublisherImpl,
)
from services.entitlements_service.implementations.repository_impl import EntitlementsRepositoryImpl
from services.entitlements_service.models_db import Base as EntitlementsBase
from services.entitlements_service.protocols import (
    CreditManagerProtocol,
    EntitlementsRepositoryProtocol,
    EventPublisherProtocol,
    PolicyLoaderProtocol,
    RateLimiterProtocol,
)


class OutboxIntegrationProvider(Provider):
    """DI provider using real EventPublisher + outbox repository."""

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
    def provide_outbox_repository(
        self, engine: AsyncEngine, settings: Settings
    ) -> PostgreSQLOutboxRepository:  # type: ignore[override]
        return PostgreSQLOutboxRepository(
            engine=engine, service_name=settings.SERVICE_NAME, enable_metrics=False
        )

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, outbox_repository: PostgreSQLOutboxRepository, settings: Settings
    ) -> EventPublisherProtocol:
        # Use real OutboxManager without Redis (not needed for persistence assertion)
        from huleedu_service_libs.outbox.manager import OutboxManager

        outbox_manager = OutboxManager(
            outbox_repository=outbox_repository,
            redis_client=None,
            service_name=settings.SERVICE_NAME,
        )
        return EventPublisherImpl(outbox_manager=outbox_manager, settings=settings)

    @provide(scope=Scope.APP)
    def provide_policy_loader(self) -> PolicyLoaderProtocol:  # type: ignore[override]
        from unittest.mock import AsyncMock

        loader = AsyncMock(spec=PolicyLoaderProtocol)
        loader.get_cost = AsyncMock(return_value=5)
        loader.reload_policies = AsyncMock()
        return loader

    @provide(scope=Scope.APP)
    def provide_rate_limiter(self) -> RateLimiterProtocol:  # type: ignore[override]
        from unittest.mock import AsyncMock

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
    def provide_settings(self) -> Settings:
        return Settings()

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

    container = make_async_container(OutboxIntegrationProvider(database_url))
    QuartDishka(app=app, container=container)
    app.register_blueprint(admin_bp, url_prefix="/v1/admin")
    app.register_blueprint(entitlements_bp, url_prefix="/v1/entitlements")

    # Ensure both service tables and shared outbox table exist
    async with container() as c:
        engine = await c.get(AsyncEngine)
        async with engine.begin() as conn:
            await conn.run_sync(EntitlementsBase.metadata.create_all)
            await conn.run_sync(OutboxBase.metadata.create_all)

    async with app.test_client() as client:
        yield client
    await container.close()


@pytest.mark.asyncio
async def test_real_publisher_writes_outbox(app_client: QuartTestClient, database_url: str) -> None:
    # Seed user balance to 60 (so we can consume 50)
    assert (
        await app_client.post(
            "/v1/admin/credits/set",
            json={"subject_type": "user", "subject_id": "pub-user-1", "balance": 60},
            headers={"X-Correlation-ID": "11111111-1111-1111-1111-111111111111"},
        )
    ).status_code == 200

    # Perform consumption: 10 units at cost 5 => 50
    corr = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    resp = await app_client.post(
        "/v1/entitlements/consume-credits",
        json={
            "user_id": "pub-user-1",
            "metric": "cj_comparisons",
            "amount": 10,
            "batch_id": "batch-outbox",
            "correlation_id": corr,
        },
    )
    assert resp.status_code == 200
    body = await resp.get_json()
    assert body["success"] is True

    # Verify outbox entry exists with correct fields
    expected_topic = topic_name(ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED)
    expected_usage_topic = topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED)

    # Read outbox row from the same test database
    engine = create_async_engine(database_url, echo=False)
    try:
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            stmt = (
                select(EventOutbox)
                .where(EventOutbox.event_type == expected_topic)
                .order_by(EventOutbox.created_at.desc())
            )
            result = await session.execute(stmt)
            row = result.scalars().first()

            assert row is not None, "No outbox row found for credit balance change"
            assert row.topic == expected_topic
            assert row.event_type == expected_topic
            # event_key should be partition key: subject_id
            assert row.event_key == "pub-user-1"

            # Envelope assertions
            envelope = row.event_data
            assert isinstance(envelope, dict)
            assert envelope.get("event_type") == expected_topic
            assert envelope.get("correlation_id") == corr
            # Payload includes subject id under data.subject.id
            data = envelope.get("data", {})
            subject = data.get("subject", {})
            assert subject.get("id") == "pub-user-1"

            # Also verify UsageRecordedV1 has been written for the same consumption
            stmt_usage = (
                select(EventOutbox)
                .where(EventOutbox.event_type == expected_usage_topic)
                .order_by(EventOutbox.created_at.desc())
            )
            result_usage = await session.execute(stmt_usage)
            usage_row = result_usage.scalars().first()

            assert usage_row is not None, "No outbox row found for usage recorded event"
            assert usage_row.topic == expected_usage_topic
            assert usage_row.event_type == expected_usage_topic
            # event_key should also be the subject_id
            assert usage_row.event_key == "pub-user-1"

            usage_envelope = usage_row.event_data
            assert isinstance(usage_envelope, dict)
            assert usage_envelope.get("event_type") == expected_usage_topic
            assert usage_envelope.get("correlation_id") == corr
            usage_data = usage_envelope.get("data", {})
            usage_subject = usage_data.get("subject", {})
            assert usage_subject.get("id") == "pub-user-1"
    finally:
        await engine.dispose()
