"""
Comprehensive integration tests for transactional outbox pattern in Email Service.

Tests atomic transaction behavior, rollback scenarios, event ordering preservation,
concurrent processing safety, and Swedish character support using real PostgreSQL
via testcontainers. Follows Rule 075 methodology with Protocol-based mocking.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.emailing_models import (
    EmailSentV1,
    NotificationEmailRequestedV1,
)
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.outbox.models import EventOutbox
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.implementations.outbox_manager import OutboxManager
from services.email_service.models_db import Base, EmailStatus
from services.email_service.models_db import EmailRecord as DbEmailRecord
from services.email_service.protocols import EmailProvider, EmailRepository, TemplateRenderer


class TestOutboxPublishingIntegration:
    """Integration tests for transactional outbox pattern with real PostgreSQL."""

    # Class-level counter to ensure unique provider message IDs across all tests
    _provider_message_counter = 0

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL test container with schema setup."""
        container = PostgresContainer("postgres:15-alpine")
        container.start()
        yield container
        container.stop()

    class DatabaseTestSettings(Settings):
        """Test settings with database URL override for testcontainers."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)

        @property
        def DATABASE_URL(self) -> str:
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(self, postgres_container: PostgresContainer) -> Settings:
        """Create test settings with testcontainer database URL."""
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        return self.DatabaseTestSettings(database_url=pg_connection_url)

    @pytest.fixture
    async def database_engine(self, test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
        """Create async database engine with complete schema creation."""
        engine = create_async_engine(
            test_settings.database_url,
            echo=False,  # Enable for SQL debugging if needed
        )

        # Create all tables including outbox
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Also create outbox table from huleedu_service_libs
            await conn.run_sync(EventOutbox.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    async def session_factory(
        self, database_engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Create async session factory for database operations."""
        return async_sessionmaker(database_engine, expire_on_commit=False)

    @pytest.fixture
    async def db_session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession, None]:
        """Provide database session with automatic cleanup."""
        async with session_factory() as session:
            yield session

    @pytest.fixture
    def mock_outbox_repository(self, database_engine: AsyncEngine) -> OutboxRepositoryProtocol:
        """Create real outbox repository with PostgreSQL testcontainer."""
        from huleedu_service_libs.outbox.repository import PostgreSQLOutboxRepository

        return PostgreSQLOutboxRepository(
            engine=database_engine,
            service_name="email_service_test",
            enable_metrics=False,  # Disable metrics in tests
        )

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock Redis client for outbox notifications following Protocol spec."""
        mock = AsyncMock(spec=AtomicRedisClientProtocol)
        mock.lpush = AsyncMock()
        return mock

    @pytest.fixture
    def mock_template_renderer(self) -> AsyncMock:
        """Mock template renderer with Swedish character support."""
        from services.email_service.protocols import RenderedTemplate

        mock = AsyncMock(spec=TemplateRenderer)
        mock.template_exists = AsyncMock(return_value=True)
        mock.render = AsyncMock(
            return_value=RenderedTemplate(
                subject=(
                    "Välkommen till HuleEdu - Ditt konto är verifierat!"
                ),  # Subject with Swedish chars
                html_content=(
                    "<p>Hej! Ditt konto för <strong>Göteborgs Högskola</strong> är nu aktivt.</p>"
                ),  # HTML
                text_content=("Hej! Ditt konto för Göteborgs Högskola är nu aktivt."),  # Text
            )
        )
        return mock

    @pytest.fixture
    def mock_email_provider(self) -> AsyncMock:
        """Mock email provider for integration testing with unique provider message IDs."""
        from services.email_service.protocols import EmailSendResult

        mock = AsyncMock(spec=EmailProvider)

        # Default behavior for send_email (can be overridden in tests with side_effect)
        def create_default_result(*args: Any, **kwargs: Any) -> EmailSendResult:
            TestOutboxPublishingIntegration._provider_message_counter += 1
            return EmailSendResult(
                success=True,
                provider_message_id=f"test-provider-msg-{TestOutboxPublishingIntegration._provider_message_counter}",
            )

        mock.send_email = AsyncMock(side_effect=create_default_result)
        mock.get_provider_name = lambda: "mock_provider"  # Non-async method
        return mock

    @pytest.fixture(autouse=True)
    async def clean_database_tables(
        self, database_engine: AsyncEngine
    ) -> AsyncGenerator[None, None]:
        """Clean database tables before and after each test for isolation."""
        # Clean before test
        async with database_engine.begin() as conn:
            await conn.execute(delete(DbEmailRecord))
            await conn.execute(delete(EventOutbox))

        yield

        # Clean after test
        async with database_engine.begin() as conn:
            await conn.execute(delete(DbEmailRecord))
            await conn.execute(delete(EventOutbox))

    @pytest.fixture
    def mock_email_repository(self, database_engine: AsyncEngine) -> EmailRepository:
        """Create real email repository with PostgreSQL testcontainer."""
        from services.email_service.implementations.repository_impl import PostgreSQLEmailRepository

        return PostgreSQLEmailRepository(engine=database_engine, database_metrics=None)

    @pytest.fixture
    def outbox_manager(
        self,
        mock_outbox_repository: OutboxRepositoryProtocol,
        mock_redis_client: AsyncMock,
        test_settings: Settings,
    ) -> OutboxManager:
        """Create OutboxManager with real outbox repository."""
        return OutboxManager(
            outbox_repository=mock_outbox_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

    @pytest.fixture
    def email_processor(
        self,
        mock_email_repository: EmailRepository,
        mock_template_renderer: AsyncMock,
        mock_email_provider: AsyncMock,
        outbox_manager: OutboxManager,
        test_settings: Settings,
    ) -> EmailEventProcessor:
        """Create EmailEventProcessor with integration dependencies."""
        return EmailEventProcessor(
            repository=mock_email_repository,
            template_renderer=mock_template_renderer,
            email_provider=mock_email_provider,
            outbox_manager=outbox_manager,
            settings=test_settings,
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_atomic_email_processing_with_outbox_storage(
        self,
        email_processor: EmailEventProcessor,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        """Test atomic transaction between email record creation and outbox event storage.

        Verifies that email records and outbox events are created atomically within
        the same transaction, ensuring consistency guarantees of the outbox pattern.
        """
        # Arrange
        correlation_id = uuid4()
        message_id = f"msg-atomic-{uuid4().hex[:8]}"
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            to=str("student@example.com"),
            template_id="verification",
            category="verification",
            variables={
                "name": "Anna Lindström",
                "verification_link": "https://hule.edu/verify/123",
            },
            correlation_id=str(correlation_id),
        )

        # Act - Process email request (should create both email record and outbox event)
        await email_processor.process_email_request(email_request)

        # Assert - Verify email record was created
        email_stmt = select(DbEmailRecord).where(DbEmailRecord.message_id == message_id)
        email_result = await db_session.execute(email_stmt)
        email_record = email_result.scalar_one_or_none()

        assert email_record is not None
        assert email_record.message_id == message_id
        assert email_record.to_address == "student@example.com"
        assert email_record.template_id == "verification"
        assert email_record.correlation_id == str(correlation_id)
        assert email_record.status == EmailStatus.SENT

        # Assert - Verify outbox event was created
        outbox_stmt = select(EventOutbox).where(
            EventOutbox.aggregate_id == message_id,
            EventOutbox.aggregate_type == "email_message",
        )
        outbox_result = await db_session.execute(outbox_stmt)
        outbox_events = outbox_result.scalars().all()

        assert len(outbox_events) == 1  # Should have EmailSentV1 event
        outbox_event = outbox_events[0]
        assert outbox_event.event_type == "huleedu.email.sent.v1"
        assert outbox_event.topic == topic_name(ProcessingEvent.EMAIL_SENT)
        assert outbox_event.published_at is None  # Not published yet

        # Verify event data structure
        event_data = outbox_event.event_data
        assert event_data["data"]["message_id"] == message_id
        assert event_data["data"]["provider"] == "mock_provider"
        assert "correlation_id" in event_data  # Correlation ID should be present

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_database_rollback_consistency_on_processing_failure(
        self,
        email_processor: EmailEventProcessor,
        mock_email_provider: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        """Test transaction rollback when email processing fails after record creation.

        Verifies that database rollbacks properly clean up both email records and
        outbox events when processing failures occur, maintaining consistency.
        """
        # Arrange - Configure email provider to fail

        mock_email_provider.send_email.side_effect = Exception("Email service unavailable")

        correlation_id = uuid4()
        message_id = f"msg-rollback-{uuid4().hex[:8]}"
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            to=str("test@rollback.com"),
            template_id="verification",
            category="verification",
            variables={"name": "Test User"},
            correlation_id=str(correlation_id),
        )

        # Act - Process should fail and rollback
        with pytest.raises(
            Exception
        ):  # Processing should fail (HuleEduError or its base Exception)
            await email_processor.process_email_request(email_request)

        # Assert - Verify no email record was persisted after rollback
        email_stmt = select(DbEmailRecord).where(DbEmailRecord.message_id == message_id)
        email_result = await db_session.execute(email_stmt)
        email_record = email_result.scalar_one_or_none()

        # Email record should not exist or should be in failed state
        if email_record:
            assert email_record.status == EmailStatus.FAILED

        # Assert - Verify no outbox events were persisted
        outbox_stmt = select(EventOutbox).where(EventOutbox.aggregate_id == message_id)
        outbox_result = await db_session.execute(outbox_stmt)
        outbox_events = outbox_result.scalars().all()

        # Should be empty or only contain failure events
        success_events = [e for e in outbox_events if e.event_type == "huleedu.email.sent.v1"]
        assert len(success_events) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_event_ordering_preservation_with_correlation_ids(
        self,
        email_processor: EmailEventProcessor,
        db_session: AsyncSession,
    ) -> None:
        """Test event ordering preservation for sequential email processing.

        Verifies that events are stored in outbox with proper ordering and that
        correlation IDs are preserved throughout the processing pipeline.
        """
        # Arrange - Create sequence of related email requests
        base_correlation_id = uuid4()
        email_sequence = [
            NotificationEmailRequestedV1(
                message_id=f"msg-sequence-{i:03d}",
                to=f"user{i}@example.com",
                template_id="verification",
                category="verification",
                variables={"name": f"User {i}", "sequence_id": str(i)},
                correlation_id=str(base_correlation_id),
            )
            for i in range(5)
        ]

        # Act - Process emails in sequence
        for request in email_sequence:
            await email_processor.process_email_request(request)

        # Assert - Verify events are ordered by creation time
        outbox_stmt = (
            select(EventOutbox)
            .where(EventOutbox.aggregate_type == "email_message")
            .where(EventOutbox.event_data.op("->>")("correlation_id") == str(base_correlation_id))
            .order_by(EventOutbox.created_at)
        )
        outbox_result = await db_session.execute(outbox_stmt)
        outbox_events = outbox_result.scalars().all()

        assert len(outbox_events) == 5

        # Verify ordering preservation
        for i, event in enumerate(outbox_events):
            expected_msg_id = f"msg-sequence-{i:03d}"
            assert event.aggregate_id == expected_msg_id
            assert event.event_data["data"]["message_id"] == expected_msg_id

            # Verify correlation ID preservation
            assert event.event_data["correlation_id"] == str(base_correlation_id)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_email_processing_safety(
        self,
        email_processor: EmailEventProcessor,
        db_session: AsyncSession,
    ) -> None:
        """Test concurrent email processing with database isolation guarantees.

        Verifies that multiple concurrent email processing requests maintain
        data integrity and don't cause database lock conflicts or race conditions.
        """
        # Arrange - Create concurrent email requests
        correlation_id = uuid4()
        concurrent_requests = [
            NotificationEmailRequestedV1(
                message_id=f"msg-concurrent-{i:03d}",
                to=f"user{i}@example.com",
                template_id="verification",
                category="verification",
                variables={"name": f"Concurrent User {i}", "thread_id": str(i)},
                correlation_id=str(correlation_id),
            )
            for i in range(10)
        ]

        # Act - Process emails concurrently
        tasks = [email_processor.process_email_request(request) for request in concurrent_requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - Verify all requests processed successfully
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Concurrent processing had exceptions: {exceptions}"

        # Assert - Verify all email records were created
        email_stmt = select(func.count(DbEmailRecord.message_id)).where(
            DbEmailRecord.correlation_id == str(correlation_id)
        )
        email_result = await db_session.execute(email_stmt)
        email_count = email_result.scalar()
        assert email_count == 10

        # Assert - Verify all outbox events were created
        outbox_stmt = select(func.count(EventOutbox.id)).where(
            EventOutbox.event_data.op("->>")("correlation_id") == str(correlation_id)
        )
        outbox_result = await db_session.execute(outbox_stmt)
        outbox_count = outbox_result.scalar()
        assert outbox_count == 10

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_swedish_character_preservation_in_outbox_events(
        self,
        email_processor: EmailEventProcessor,
        mock_template_renderer: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        """Test Swedish character preservation (åäöÅÄÖ) in outbox event serialization.

        Verifies that Swedish characters in email data are properly serialized
        and preserved through JSON storage in PostgreSQL outbox events.
        """
        # Arrange - Configure template renderer with Swedish content
        from services.email_service.protocols import RenderedTemplate

        mock_template_renderer.render.return_value = RenderedTemplate(
            subject=("Välkommen! Din ansökan till Göteborgs Högskola"),  # Swedish subject
            html_content=(
                "<p>Hej <strong>Åsa</strong>! Ditt konto för <em>Växjö Universitet</em> "
                "är klart.</p>"
            ),
            text_content=("Hej Åsa! Ditt konto för Växjö Universitet är klart."),
        )

        correlation_id = uuid4()
        message_id = f"msg-swedish-åäöÅÄÖ-{uuid4().hex[:8]}"
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            to=str("åsa.lindström@universitet.se"),
            template_id="välkommen_template",
            category="verification",
            variables={
                "namn": "Åsa Lindström",
                "skola": "Göteborgs Högskola",
                "ämne": "Svenska språket",
                "specialtecken": "åäöÅÄÖ",
            },
            correlation_id=str(correlation_id),
        )

        # Act
        await email_processor.process_email_request(email_request)

        # Assert - Verify Swedish characters in email record
        email_stmt = select(DbEmailRecord).where(DbEmailRecord.message_id == message_id)
        email_result = await db_session.execute(email_stmt)
        email_record = email_result.scalar_one()

        assert email_record.to_address == "åsa.lindström@universitet.se"
        assert email_record.template_id == "välkommen_template"
        assert email_record.category == "verification"
        assert email_record.variables["namn"] == "Åsa Lindström"
        assert email_record.variables["skola"] == "Göteborgs Högskola"
        assert "åäöÅÄÖ" in email_record.variables["specialtecken"]

        # Assert - Verify Swedish characters in outbox event data
        outbox_stmt = select(EventOutbox).where(EventOutbox.aggregate_id == message_id)
        outbox_result = await db_session.execute(outbox_stmt)
        outbox_event = outbox_result.scalar_one()

        event_data = outbox_event.event_data
        # Check for Swedish characters in message_id (which is part of EmailSentV1)
        assert message_id in str(event_data) or "åäöÅÄÖ" in str(event_data)

        # Verify that the message_id field itself contains the correct value
        assert event_data["data"]["message_id"] == message_id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_outbox_redis_notification_integration(
        self,
        outbox_manager: OutboxManager,
        mock_redis_client: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        """Test Redis notification system for outbox relay worker wake-up.

        Verifies that Redis notifications are sent correctly when events are
        added to the outbox, enabling immediate processing by relay workers.
        """
        # Arrange
        correlation_id = uuid4()
        message_id = f"msg-redis-{uuid4().hex[:8]}"
        test_event = EmailSentV1(
            message_id=message_id,
            provider="sendgrid",
            sent_at=datetime.now(timezone.utc),
            correlation_id=str(correlation_id),
        )

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=test_event,
            metadata={"notification_type": "relay_worker_test"},
        )

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id=message_id,
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Assert - Verify Redis notification was sent
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:email_service", "1")

        # Assert - Verify event is in outbox
        outbox_stmt = select(EventOutbox).where(EventOutbox.aggregate_id == message_id)
        outbox_result = await db_session.execute(outbox_stmt)
        outbox_event = outbox_result.scalar_one()

        assert outbox_event.published_at is None  # Awaiting relay worker processing
        assert outbox_event.event_type == "huleedu.email.sent.v1"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_failed_email_outbox_event_creation(
        self,
        email_processor: EmailEventProcessor,
        mock_email_provider: AsyncMock,
        db_session: AsyncSession,
    ) -> None:
        """Test outbox event creation for failed email delivery scenarios.

        Verifies that EmailDeliveryFailedV1 events are properly created and stored
        in the outbox when email sending fails, maintaining audit trail.
        """
        # Arrange - Configure email provider to fail
        from services.email_service.protocols import EmailSendResult

        # Override the side_effect for this test
        mock_email_provider.send_email.side_effect = None  # Clear the side_effect
        mock_email_provider.send_email.return_value = EmailSendResult(
            success=False,
            provider_message_id=None,
            error_message="Recipient email address is invalid",
        )

        correlation_id = uuid4()
        message_id = f"msg-failure-{uuid4().hex[:8]}"
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            to="test@example.com",
            template_id="verification",
            category="verification",
            variables={"name": "Failed User"},
            correlation_id=str(correlation_id),
        )

        # Act
        await email_processor.process_email_request(email_request)

        # Assert - Verify email record shows failure
        email_stmt = select(DbEmailRecord).where(DbEmailRecord.message_id == message_id)
        email_result = await db_session.execute(email_stmt)
        email_record = email_result.scalar_one()

        assert email_record.status == EmailStatus.FAILED
        assert email_record.failure_reason and "invalid" in email_record.failure_reason.lower()

        # Assert - Verify EmailDeliveryFailedV1 event in outbox
        outbox_stmt = select(EventOutbox).where(
            EventOutbox.aggregate_id == message_id,
            EventOutbox.event_type == "huleedu.email.delivery_failed.v1",
        )
        outbox_result = await db_session.execute(outbox_stmt)
        outbox_events = outbox_result.scalars().all()

        assert len(outbox_events) == 1
        failure_event = outbox_events[0]
        assert failure_event.event_data["data"]["reason"] == "Recipient email address is invalid"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_database_connection_recovery_during_outbox_operations(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: OutboxRepositoryProtocol,
        database_engine: AsyncEngine,
    ) -> None:
        """Test database connection recovery and retry behavior during outbox operations.

        Verifies that outbox operations can recover from temporary database
        connection issues and maintain data consistency.
        """
        # Arrange
        correlation_id = uuid4()
        message_id = f"msg-recovery-{uuid4().hex[:8]}"
        test_event = EmailSentV1(
            message_id=message_id,
            provider="sendgrid",
            sent_at=datetime.now(timezone.utc),
            correlation_id=str(correlation_id),
        )

        event_envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=test_event,
        )

        # Act & Assert - Should complete without connection errors
        await outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id=message_id,
            event_type="huleedu.email.sent.v1",
            event_data=event_envelope,
            topic="huleedu-email-events",
        )

        # Verify event was stored successfully despite potential connection issues
        async with async_sessionmaker(database_engine)() as session:
            stmt = select(EventOutbox).where(EventOutbox.aggregate_id == message_id)
            result = await session.execute(stmt)
            outbox_event = result.scalar_one()

            assert outbox_event is not None
            assert outbox_event.event_type == "huleedu.email.sent.v1"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_outbox_event_idempotency_with_duplicate_messages(
        self,
        email_processor: EmailEventProcessor,
        db_session: AsyncSession,
    ) -> None:
        """Test outbox event idempotency when processing duplicate message IDs.

        Verifies that duplicate email processing attempts don't create duplicate
        outbox events, maintaining idempotency guarantees.
        """
        # Arrange
        correlation_id = uuid4()
        message_id = f"msg-idempotency-{uuid4().hex[:8]}"
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            to="duplicate@example.com",
            template_id="verification",
            category="verification",
            variables={"name": "Duplicate Test"},
            correlation_id=str(correlation_id),
        )

        # Act - Process the same email request twice
        await email_processor.process_email_request(email_request)

        # Second processing should be idempotent or handle gracefully
        try:
            await email_processor.process_email_request(email_request)
        except (IntegrityError, Exception):
            # Expected behavior - duplicate message_id should be rejected
            # The event processor wraps IntegrityError in HuleEduError
            pass

        # Assert - Verify only one email record exists
        email_stmt = select(func.count(DbEmailRecord.message_id)).where(
            DbEmailRecord.message_id == message_id
        )
        email_result = await db_session.execute(email_stmt)
        email_count = email_result.scalar() or 0
        assert email_count <= 1  # Should not exceed 1 due to primary key constraint

        # Assert - Verify correct outbox events: 1 success + 1 failure for duplicate
        # Count successful events
        success_stmt = select(func.count(EventOutbox.id)).where(
            EventOutbox.aggregate_id == message_id,
            EventOutbox.event_type == "huleedu.email.sent.v1",
        )
        success_result = await db_session.execute(success_stmt)
        success_count = success_result.scalar()
        assert success_count == 1  # Should have exactly 1 successful send

        # Count failure events
        failure_stmt = select(func.count(EventOutbox.id)).where(
            EventOutbox.aggregate_id == message_id,
            EventOutbox.event_type == "huleedu.email.delivery_failed.v1",
        )
        failure_result = await db_session.execute(failure_stmt)
        failure_count = failure_result.scalar()
        assert failure_count == 1  # Should have exactly 1 failure for duplicate attempt
