"""
Integration tests for event publishing with transactional outbox pattern.

Tests comprehensive event publishing workflows with real PostgreSQL database:
- Transactional outbox pattern with real database transactions
- Events saved to EventOutbox table within transaction boundaries
- Transaction rollback preserves outbox consistency
- Event ordering guarantees and retry mechanisms
- Correlation ID propagation through event publishing

Uses testcontainers for isolated PostgreSQL testing and protocol-based mocking
for Kafka publisher to verify event publishing behavior from outbox.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.events.envelope import EventEnvelope
from common_core.identity_models import EmailVerifiedV1, LoginSucceededV1, UserRegisteredV1
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.outbox import EventOutbox, PostgreSQLOutboxRepository
from huleedu_service_libs.outbox.manager import OutboxManager
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.identity_service.config import Settings
from services.identity_service.models_db import Base, User


class TestEventPublishingIntegration:
    """Integration tests for event publishing with transactional outbox pattern."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL test container for outbox testing."""
        container = PostgresContainer("postgres:15-alpine")
        container.start()
        yield container
        container.stop()

    class DatabaseTestSettings(Settings):
        """Test settings with database URL override."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)

        @property
        def database_url(self) -> str:
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(self, postgres_container: PostgresContainer) -> Settings:
        """Create test settings with database URL."""
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        return self.DatabaseTestSettings(database_url=pg_connection_url)

    @pytest.fixture
    async def database_engine(self, test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
        """Create async database engine with schema including outbox tables."""
        engine = create_async_engine(test_settings.DATABASE_URL)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Also create the EventOutbox table from libs
            await conn.run_sync(EventOutbox.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    async def session_factory(
        self, database_engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Create async session factory."""
        return async_sessionmaker(database_engine, expire_on_commit=False)

    @pytest.fixture(autouse=True)
    async def clean_database(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Clean the database before each test."""
        async with session_factory() as session:
            async with session.begin():
                # Disable foreign key checks temporarily
                await session.execute(text("SET session_replication_role = replica;"))

                # Truncate all tables including EventOutbox
                await session.execute(text("TRUNCATE TABLE event_outbox CASCADE"))
                await session.execute(text("TRUNCATE TABLE users CASCADE"))

                # Re-enable foreign key checks
                await session.execute(text("SET session_replication_role = DEFAULT;"))

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock Redis client for outbox wake notifications."""
        mock = AsyncMock(spec=AtomicRedisClientProtocol)
        mock.lpush.return_value = 1
        return mock

    @pytest.fixture
    def outbox_repository(
        self, database_engine: AsyncEngine, test_settings: Settings
    ) -> OutboxRepositoryProtocol:
        """Create real PostgreSQL outbox repository."""
        return PostgreSQLOutboxRepository(
            engine=database_engine,
            service_name=test_settings.SERVICE_NAME,
            enable_metrics=False,  # Disable metrics for testing
        )

    @pytest.fixture
    def outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
    ) -> OutboxManager:
        """Create OutboxManager with real outbox repository."""
        return OutboxManager(
            outbox_repository=outbox_repository,
            redis_client=mock_redis_client,
            service_name=test_settings.SERVICE_NAME,
        )

    @pytest.mark.parametrize(
        "event_type,event_class,test_data",
        [
            (
                "UserRegisteredV1",
                UserRegisteredV1,
                {
                    "user_id": "user_123",
                    "org_id": "test-org",
                    "email": "test@example.com",
                    "registered_at": datetime.now(timezone.utc),
                    "correlation_id": str(uuid4()),
                },
            ),
            (
                "LoginSucceededV1",
                LoginSucceededV1,
                {
                    "user_id": "user_456",
                    "org_id": "login-org",
                    "timestamp": datetime.now(timezone.utc),
                    "correlation_id": str(uuid4()),
                },
            ),
            (
                "EmailVerifiedV1",
                EmailVerifiedV1,
                {
                    "user_id": "user_789",
                    "verified_at": datetime.now(timezone.utc),
                    "correlation_id": str(uuid4()),
                },
            ),
        ],
    )
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_outbox_event_storage_for_different_event_types(
        self,
        event_type: str,
        event_class: type[UserRegisteredV1 | LoginSucceededV1 | EmailVerifiedV1],
        test_data: dict[str, Any],
        outbox_manager: OutboxManager,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test outbox stores different event types correctly with proper serialization."""
        # Arrange
        correlation_id = UUID(test_data["correlation_id"])
        event_data = event_class(**test_data)
        envelope: EventEnvelope[Any] = EventEnvelope(
            event_type=f"huleedu.identity.{event_type.lower()}.v1",
            source_service="identity_service",
            correlation_id=correlation_id,
            data=event_data,
            metadata={"partition_key": test_data["user_id"]},
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=test_data["user_id"],
            event_type=f"huleedu.identity.{event_type.lower()}.v1",
            event_data=envelope,
            topic="identity_events",
        )

        # Assert - Verify event stored in outbox
        async with session_factory() as session:
            stmt = select(EventOutbox).where(EventOutbox.aggregate_id == test_data["user_id"])
            result = await session.execute(stmt)
            stored_event = result.scalar_one()

            assert stored_event.aggregate_type == "user"
            assert stored_event.event_type == f"huleedu.identity.{event_type.lower()}.v1"
            assert stored_event.topic == "identity_events"
            assert stored_event.event_key == test_data["user_id"]
            assert stored_event.published_at is None
            assert stored_event.retry_count == 0
            assert stored_event.last_error is None

            # Verify event data serialization
            event_data_dict = stored_event.event_data
            assert event_data_dict["event_type"] == f"huleedu.identity.{event_type.lower()}.v1"
            assert event_data_dict["source_service"] == "identity_service"
            assert event_data_dict["correlation_id"] == str(correlation_id)
            assert event_data_dict["data"]["user_id"] == test_data["user_id"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_transactional_outbox_with_user_creation(
        self,
        outbox_manager: OutboxManager,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test outbox events are saved within the same transaction as business data."""
        correlation_id = uuid4()
        user_id = "user_transactional_123"

        # Create user registration event
        event_data = UserRegisteredV1(
            user_id=user_id,
            org_id="trans-org",
            email="trans@example.com",
            registered_at=datetime.now(timezone.utc),
            correlation_id=str(correlation_id),
        )
        envelope: EventEnvelope[Any] = EventEnvelope(
            event_type="huleedu.identity.userregisteredv1.v1",
            source_service="identity_service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Act - Create user and publish event in same transaction
        async with session_factory() as session:
            async with session.begin():
                # Create user
                user = User(
                    id=uuid4(),  # Generate valid UUID
                    email="trans@example.com",
                    org_id="trans-org",
                    password_hash="hashed_password",
                    roles=["teacher"],
                )
                session.add(user)

                # Publish event using the same session
                await outbox_manager.publish_to_outbox(
                    aggregate_type="user",
                    aggregate_id=user_id,
                    event_type="huleedu.identity.userregisteredv1.v1",
                    event_data=envelope,
                    topic="identity_events",
                    session=session,
                )

        # Assert - Both user and outbox event exist
        async with session_factory() as session:
            # Verify user exists
            user_stmt = select(func.count(User.id)).where(User.email == "trans@example.com")
            user_count = await session.scalar(user_stmt)
            assert user_count == 1

            # Verify outbox event exists
            outbox_stmt = select(func.count(EventOutbox.id)).where(
                EventOutbox.aggregate_id == user_id
            )
            outbox_count = await session.scalar(outbox_stmt)
            assert outbox_count == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_transaction_rollback_preserves_outbox_consistency(
        self,
        outbox_manager: OutboxManager,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test transaction rollback removes both user and outbox event."""
        correlation_id = uuid4()
        user_id = "user_rollback_456"

        event_data = UserRegisteredV1(
            user_id=user_id,
            org_id="rollback-org",
            email="rollback@example.com",
            registered_at=datetime.now(timezone.utc),
            correlation_id=str(correlation_id),
        )
        envelope: EventEnvelope[Any] = EventEnvelope(
            event_type="huleedu.identity.userregisteredv1.v1",
            source_service="identity_service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Act - Create transaction that will be rolled back
        with pytest.raises(Exception):  # Force rollback with exception
            async with session_factory() as session:
                async with session.begin():
                    # Create user
                    user = User(
                        id=uuid4(),  # Generate valid UUID
                        email="rollback@example.com",
                        org_id="rollback-org",
                        password_hash="hashed_password",
                        roles=["teacher"],
                    )
                    session.add(user)

                    # Publish event using the same session
                    await outbox_manager.publish_to_outbox(
                        aggregate_type="user",
                        aggregate_id=user_id,
                        event_type="huleedu.identity.userregisteredv1.v1",
                        event_data=envelope,
                        topic="identity_events",
                        session=session,
                    )

                    # Force rollback
                    raise Exception("Simulated error to trigger rollback")

        # Assert - Neither user nor outbox event should exist
        async with session_factory() as session:
            # Verify user does not exist
            user_count = await session.scalar(
                select(func.count(User.id)).where(User.email == "rollback@example.com")
            )
            assert user_count == 0

            # Verify outbox event does not exist
            outbox_count = await session.scalar(
                select(func.count(EventOutbox.id)).where(EventOutbox.aggregate_id == user_id)
            )
            assert outbox_count == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_correlation_id_propagation_through_outbox(
        self,
        outbox_manager: OutboxManager,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test correlation ID is preserved through outbox storage and retrieval."""
        correlation_id = uuid4()
        user_id = "user_correlation_789"

        event_data = LoginSucceededV1(
            user_id=user_id,
            org_id="correlation-org",
            timestamp=datetime.now(timezone.utc),
            correlation_id=str(correlation_id),
        )
        envelope: EventEnvelope[Any] = EventEnvelope(
            event_type="huleedu.identity.loginsucceededv1.v1",
            source_service="identity_service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user_id,
            event_type="huleedu.identity.loginsucceededv1.v1",
            event_data=envelope,
            topic="identity_events",
        )

        # Assert - Correlation ID preserved in multiple places
        async with session_factory() as session:
            stmt = select(EventOutbox).where(EventOutbox.aggregate_id == user_id)
            stored_event = await session.scalar(stmt)

            assert stored_event is not None

            # Check correlation ID in envelope
            assert UUID(stored_event.event_data["correlation_id"]) == correlation_id

            # Check correlation ID in event data
            assert stored_event.event_data["data"]["correlation_id"] == str(correlation_id)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_event_ordering_guarantees(
        self,
        outbox_manager: OutboxManager,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test events are stored with correct ordering based on creation time."""
        correlation_id = uuid4()
        user_id = "user_ordering_999"

        events = []
        for i in range(3):
            event_data = LoginSucceededV1(
                user_id=f"{user_id}_{i}",
                org_id="ordering-org",
                timestamp=datetime.now(timezone.utc),
                correlation_id=str(correlation_id),
            )
            envelope: EventEnvelope[Any] = EventEnvelope(
                event_type=f"huleedu.identity.login_{i}.v1",
                source_service="identity_service",
                correlation_id=correlation_id,
                data=event_data,
            )
            events.append((f"{user_id}_{i}", envelope))

        # Act - Publish events in sequence
        for aggregate_id, envelope in events:
            await outbox_manager.publish_to_outbox(
                aggregate_type="user",
                aggregate_id=aggregate_id,
                event_type=envelope.event_type,
                event_data=envelope,
                topic="identity_events",
            )

        # Assert - Events are ordered by created_at
        async with session_factory() as session:
            stmt = (
                select(EventOutbox)
                .where(EventOutbox.aggregate_id.like(f"{user_id}_%"))
                .order_by(EventOutbox.created_at)
            )
            result = await session.execute(stmt)
            stored_events = result.scalars().all()

            assert len(stored_events) == 3

            # Verify ordering by checking event types
            for i, event in enumerate(stored_events):
                expected_event_type = f"huleedu.identity.login_{i}.v1"
                assert event.event_type == expected_event_type

                # Verify timestamps are sequential
                if i > 0:
                    assert event.created_at >= stored_events[i - 1].created_at

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_outbox_error_handling_with_huleedu_error(
        self,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test proper HuleEduError handling when outbox repository is not configured."""
        # Arrange - Create OutboxManager without repository
        # This is a valid test case for when the service is misconfigured
        outbox_manager = OutboxManager(
            outbox_repository=None,  # type: ignore[arg-type]  # Testing misconfiguration scenario
            redis_client=mock_redis_client,
            service_name=test_settings.SERVICE_NAME,
        )

        correlation_id = uuid4()
        event_data = UserRegisteredV1(
            user_id="user_error_test",
            org_id="error-org",
            email="error@example.com",
            registered_at=datetime.now(timezone.utc),
            correlation_id=str(correlation_id),
        )
        envelope: EventEnvelope[Any] = EventEnvelope(
            event_type="huleedu.identity.userregisteredv1.v1",
            source_service="identity_service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="user",
                aggregate_id="user_error_test",
                event_type="huleedu.identity.userregisteredv1.v1",
                event_data=envelope,
                topic="identity_events",
            )

        error_detail = exc_info.value.error_detail
        assert error_detail.service == "identity_service"
        assert error_detail.operation == "publish_to_outbox"
        assert error_detail.details["external_service"] == "outbox_repository"
        assert "not configured" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_redis_wake_notification_sent(
        self,
        outbox_manager: OutboxManager,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test Redis wake notification is sent after outbox event storage."""
        correlation_id = uuid4()
        event_data = EmailVerifiedV1(
            user_id="user_redis_wake",
            verified_at=datetime.now(timezone.utc),
            correlation_id=str(correlation_id),
        )
        envelope: EventEnvelope[Any] = EventEnvelope(
            event_type="huleedu.identity.emailverifiedv1.v1",
            source_service="identity_service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id="user_redis_wake",
            event_type="huleedu.identity.emailverifiedv1.v1",
            event_data=envelope,
            topic="identity_events",
        )

        # Assert - Redis wake notification was sent
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:identity_service", "wake")
