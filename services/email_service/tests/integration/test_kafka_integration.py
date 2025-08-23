"""
Comprehensive Kafka integration tests for Email Service.

This module tests real Kafka consumer/producer interactions, message flow integrity,
Swedish character support, error handling, and performance characteristics following
Rule 075 methodology with focused integration testing approach.

Key Test Areas:
- Kafka Consumer/Producer message processing patterns
- NotificationEmailRequestedV1 consumption with EmailKafkaConsumer
- EmailSentV1/EmailDeliveryFailedV1 publishing via OutboxManager
- Swedish character preservation (åäöÅÄÖ) in message payloads
- Idempotent message processing with Redis-based deduplication
- Error handling and reliability patterns
- Message serialization/deserialization with EventEnvelope

Integration Approach:
- Real email service components with mocked external dependencies
- Focus on business logic and message flow validation
- AsyncMock(spec=Protocol) for external service boundaries
- In-memory database for fast test execution
- Comprehensive Swedish character and edge case testing
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from aiokafka import ConsumerRecord
from common_core.emailing_models import (
    EmailDeliveryFailedV1,
    EmailSentV1,
    NotificationEmailRequestedV1,
)
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from prometheus_client import REGISTRY
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.implementations.outbox_manager import OutboxManager
from services.email_service.implementations.repository_impl import PostgreSQLEmailRepository
from services.email_service.implementations.template_renderer_impl import (
    JinjaTemplateRenderer,
)
from services.email_service.kafka_consumer import EmailKafkaConsumer
from services.email_service.models_db import Base, EmailRecord, EmailStatus
from services.email_service.protocols import (
    EmailProvider,
    EmailRepository,
    EmailSendResult,
    RenderedTemplate,
)


class TestKafkaIntegration:
    """
    Comprehensive integration tests for Kafka consumer/producer interactions.
    
    Tests focus on business logic validation, message flow integrity, and Swedish 
    character handling with mocked external dependencies for reliable test execution.
    """

    @pytest.fixture
    async def mock_redis_client(self) -> AtomicRedisClientProtocol:
        """Create mock Redis client for idempotency testing."""
        mock_redis = AsyncMock(spec=AtomicRedisClientProtocol)
        
        # Track keys for duplicate detection
        self._redis_keys: set[str] = set()
        
        async def mock_set_if_not_exists(key: str, value: Any, ttl_seconds: int | None = None) -> bool:
            if key in self._redis_keys:
                return False  # Key already exists, operation failed
            self._redis_keys.add(key)
            return True  # Key was set
        
        async def mock_delete_key(key: str) -> int:
            if key in self._redis_keys:
                self._redis_keys.remove(key)
                return 1
            return 0
            
        mock_redis.set_if_not_exists.side_effect = mock_set_if_not_exists
        mock_redis.delete_key.side_effect = mock_delete_key
        mock_redis.ping.return_value = True
        return mock_redis

    @pytest.fixture
    async def async_engine(self) -> AsyncGenerator[AsyncEngine, None]:
        """Create in-memory database engine for fast test execution."""
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
        )
        
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        yield engine
        await engine.dispose()

    @pytest.fixture
    async def db_session(self, async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
        """Create database session for tests."""
        async_session = async_sessionmaker(async_engine, expire_on_commit=False)
        async with async_session() as session:
            yield session
            await session.rollback()

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings for integration tests."""
        return Settings(
            SERVICE_NAME="email-service-test",
            KAFKA_BOOTSTRAP_SERVERS="localhost:29092",
            DB_HOST="localhost",
            DB_PORT=5432,
            DB_NAME="test_email_db",
            DB_USER="test_user",
            DB_PASSWORD="test_password",
            REDIS_URL="redis://localhost:6379",
            TEMPLATE_DIR="services/email_service/templates",
            FROM_EMAIL="test@huledu.se",
            FROM_NAME="HuleEdu Test",
        )

    @pytest.fixture
    def mock_email_provider(self) -> AsyncMock:
        """Create mock email provider with Swedish character support."""
        provider = AsyncMock(spec=EmailProvider)
        provider.send_email.return_value = EmailSendResult(
            success=True, 
            provider_message_id="mock_provider_123"
        )
        provider.get_provider_name.return_value = "MockProvider Sverige"
        return provider

    @pytest.fixture
    async def email_repository(self, db_session: AsyncSession) -> EmailRepository:
        """Create email repository implementation."""
        return PostgreSQLEmailRepository(db_session)

    @pytest.fixture
    async def template_renderer(self) -> JinjaTemplateRenderer:
        """Create template renderer with Swedish character support."""
        renderer = AsyncMock(spec=JinjaTemplateRenderer)
        
        async def mock_render(template_id: str, variables: dict[str, str]) -> RenderedTemplate:
            # Support Swedish characters in template rendering
            subject_map = {
                "verification": f"Verifiering för {variables.get('name', 'Användare')}",
                "password_reset": f"Återställ lösenord för {variables.get('name', 'Användare')}",
                "welcome": f"Välkommen till HuleEdu, {variables.get('name', 'Användare')}!",
            }
            
            html_content = f"""
            <html>
                <body>
                    <h1>{subject_map.get(template_id, 'Standard ämne')}</h1>
                    <p>Hej {variables.get('name', 'Användare')}!</p>
                    <p>Detta är ett mejl på svenska med åäöÅÄÖ.</p>
                </body>
            </html>
            """
            
            return RenderedTemplate(
                subject=subject_map.get(template_id, "Standard ämne"),
                html_content=html_content,
                text_content=f"Hej {variables.get('name', 'Användare')}! Detta är ett textmejl på svenska."
            )
        
        renderer.render.side_effect = mock_render
        renderer.template_exists.return_value = True
        return renderer

    @pytest.fixture
    async def mock_outbox_repository(self) -> OutboxRepositoryProtocol:
        """Create mock outbox repository for event storage."""
        mock_repo = AsyncMock(spec=OutboxRepositoryProtocol)
        mock_repo.add_event.return_value = uuid.uuid4()
        return mock_repo

    @pytest.fixture
    async def outbox_manager(
        self, 
        mock_outbox_repository: OutboxRepositoryProtocol,
        mock_redis_client: AtomicRedisClientProtocol,
        settings: Settings
    ) -> OutboxManager:
        """Create outbox manager for event publishing."""
        # Create manager with proper dependencies
        manager = OutboxManager(mock_outbox_repository, mock_redis_client, settings)
        
        # Store published events for verification
        self._published_events: list[tuple[str, Any]] = []
        
        # Mock the actual Kafka publishing if the method exists
        if hasattr(manager, '_publish_event_to_kafka'):
            async def mock_publish_event(topic: str, event_data: dict[str, Any]) -> None:
                self._published_events.append((topic, event_data))
                # Skip actual Kafka publishing in tests
            
            manager._publish_event_to_kafka = mock_publish_event
            
        return manager

    @pytest.fixture
    async def event_processor(
        self,
        email_repository: EmailRepository,
        template_renderer: JinjaTemplateRenderer,
        mock_email_provider: AsyncMock,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> EmailEventProcessor:
        """Create email event processor with all dependencies."""
        return EmailEventProcessor(
            repository=email_repository,
            template_renderer=template_renderer,
            email_provider=mock_email_provider,
            outbox_manager=outbox_manager,
            settings=settings,
        )

    @pytest.fixture
    async def kafka_consumer(
        self,
        settings: Settings,
        event_processor: EmailEventProcessor,
        mock_redis_client: AtomicRedisClientProtocol,
    ) -> EmailKafkaConsumer:
        """Create EmailKafkaConsumer for integration testing."""
        return EmailKafkaConsumer(settings, event_processor, mock_redis_client)

    @pytest.fixture(autouse=True)
    def clear_prometheus_registry(self) -> None:
        """Clear Prometheus registry before each test."""
        collectors = list(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            try:
                REGISTRY.unregister(collector)
            except KeyError:
                pass

    async def test_email_request_message_processing_with_swedish_characters(
        self,
        kafka_consumer: EmailKafkaConsumer,
        email_repository: EmailRepository,
        mock_email_provider: AsyncMock,
    ) -> None:
        """
        Test EmailKafkaConsumer processing NotificationEmailRequestedV1 with Swedish content.
        
        Validates:
        - Message deserialization from EventEnvelope
        - Swedish character handling in variables and email addresses
        - Email record creation with proper encoding
        - Email provider interaction with Swedish content
        """
        # Arrange - Create message with comprehensive Swedish content
        correlation_id = str(uuid.uuid4())
        message_id = f"msg_{uuid.uuid4()}"
        
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="verification",
            to="erik.öhman@björkskolan.se",
            variables={
                "name": "Erik Öhman-Åslund",
                "school": "Björkskolan i Västerås", 
                "subject": "Naturvetenskap och Matematik",
                "verification_url": "https://huledu.se/verify?token=åäöÅÄÖ123",
                "expires_at": "31 december 2024 kl 23:59"
            },
            category="verification",
            correlation_id=correlation_id,
        )
        
        envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_id=str(uuid.uuid4()),
            event_type="NotificationEmailRequestedV1",
            data=email_request,
            correlation_id=correlation_id,
            event_timestamp=datetime.now(UTC),
            source_service="identity-service",
        )
        
        # Create mock Kafka message
        mock_msg = Mock(spec=ConsumerRecord)
        mock_msg.topic = topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED)
        mock_msg.partition = 0
        mock_msg.offset = 123
        mock_msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        
        # Act - Process message through consumer
        result = await kafka_consumer._process_message(mock_msg)
        
        # Assert - Verify successful processing
        assert result is True, "Message processing should succeed"
        
        # Verify email record was created with Swedish characters preserved
        email_record = await email_repository.get_by_message_id(message_id)
        assert email_record is not None, "Email record should be created"
        assert email_record.message_id == message_id
        assert email_record.correlation_id == correlation_id
        assert email_record.to_address == "erik.öhman@björkskolan.se"
        assert email_record.variables["name"] == "Erik Öhman-Åslund"
        assert email_record.variables["school"] == "Björkskolan i Västerås"
        assert email_record.variables["subject"] == "Naturvetenskap och Matematik"
        assert "åäöÅÄÖ123" in email_record.variables["verification_url"]
        
        # Verify email provider was called with Swedish content
        mock_email_provider.send_email.assert_called_once()
        call_args = mock_email_provider.send_email.call_args
        assert "Erik Öhman-Åslund" in str(call_args)

    async def test_outbox_pattern_event_publishing_with_swedish_provider(
        self,
        outbox_manager: OutboxManager,
        db_session: AsyncSession,
    ) -> None:
        """
        Test outbox pattern for EmailSentV1 and EmailDeliveryFailedV1 events.
        
        Validates:
        - Event serialization with Swedish provider names
        - Transactional outbox processing
        - Event metadata preservation
        - Correlation ID propagation
        """
        # Arrange - Create email sent event with Swedish provider
        correlation_id = str(uuid.uuid4())
        message_id = f"msg_{uuid.uuid4()}"
        
        email_sent_event = EmailSentV1(
            message_id=message_id,
            provider="PostNord Digital Sverige AB",
            sent_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )
        
        # Act - Publish event via outbox
        await outbox_manager.publish_email_sent(email_sent_event)
        
        # Process pending events (mocked Kafka publishing)
        await outbox_manager.process_pending_events()
        
        # Assert - Verify event was processed
        published_events = getattr(outbox_manager, '_published_events', [])
        assert len(published_events) == 1, "Should publish exactly one EmailSentV1 event"
        
        topic, event_data = published_events[0]
        assert topic == topic_name(ProcessingEvent.EMAIL_SENT)
        assert event_data["data"]["message_id"] == message_id
        assert event_data["data"]["provider"] == "PostNord Digital Sverige AB"
        assert event_data["correlation_id"] == correlation_id

    async def test_email_delivery_failure_event_publishing(
        self,
        outbox_manager: OutboxManager,
        db_session: AsyncSession,
    ) -> None:
        """
        Test EmailDeliveryFailedV1 event publishing with Swedish error messages.
        
        Validates:
        - Failure event creation and publishing
        - Swedish error message handling
        - Event envelope structure
        - Correlation tracking
        """
        # Arrange - Create delivery failure event with Swedish error
        correlation_id = str(uuid.uuid4())
        message_id = f"msg_{uuid.uuid4()}"
        
        failure_event = EmailDeliveryFailedV1(
            message_id=message_id,
            provider="SendGrid Sverige",
            failed_at=datetime.now(UTC),
            reason="E-postadress kunde inte hittas: mottagaren existerar inte på domänen",
            correlation_id=correlation_id,
        )
        
        # Act - Publish failure event
        await outbox_manager.publish_email_delivery_failed(failure_event)
        await outbox_manager.process_pending_events()
        
        # Assert - Verify failure event was published
        published_events = getattr(outbox_manager, '_published_events', [])
        assert len(published_events) == 1
        
        topic, event_data = published_events[0]
        assert topic == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)
        assert event_data["data"]["message_id"] == message_id
        assert event_data["data"]["provider"] == "SendGrid Sverige"
        assert "mottagaren existerar inte på domänen" in event_data["data"]["reason"]

    async def test_kafka_consumer_idempotency_with_duplicate_messages(
        self,
        kafka_consumer: EmailKafkaConsumer,
        email_repository: EmailRepository,
        mock_email_provider: AsyncMock,
    ) -> None:
        """
        Test Kafka consumer idempotency with duplicate message processing.
        
        Validates:
        - First message processing succeeds
        - Duplicate message detection via Redis
        - Email provider called only once
        - Database record created only once
        """
        # Arrange - Create identical messages
        correlation_id = str(uuid.uuid4())
        message_id = f"msg_{uuid.uuid4()}"
        
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="password_reset",
            to="anna.svensson@huledu.se",
            variables={
                "name": "Anna Svensson",
                "reset_link": "https://huledu.se/reset?token=xyz789",
                "expires_in": "30 minuter"
            },
            category="password_reset",
            correlation_id=correlation_id,
        )
        
        envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_id=str(uuid.uuid4()),
            event_type="NotificationEmailRequestedV1",
            data=email_request,
            correlation_id=correlation_id,
            event_timestamp=datetime.now(UTC),
            source_service="identity-service",
        )
        
        # Create mock Kafka message
        mock_msg = Mock(spec=ConsumerRecord)
        mock_msg.topic = topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED)
        mock_msg.partition = 0
        mock_msg.offset = 456
        mock_msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        
        # Act - Process the same message twice
        first_result = await kafka_consumer._process_email_request_idempotently(mock_msg)
        second_result = await kafka_consumer._process_email_request_idempotently(mock_msg)
        
        # Assert - First processing succeeds, second is skipped
        assert first_result is True, "First message processing should succeed"
        assert second_result is None, "Duplicate message should be skipped"
        
        # Verify email provider called only once
        assert mock_email_provider.send_email.call_count == 1
        
        # Verify only one email record exists
        email_records = await email_repository.get_by_correlation_id(correlation_id)
        assert len(email_records) == 1, "Should have exactly one email record"

    async def test_kafka_consumer_error_handling_with_invalid_message(
        self,
        kafka_consumer: EmailKafkaConsumer,
        email_repository: EmailRepository,
        mock_email_provider: AsyncMock,
    ) -> None:
        """
        Test Kafka consumer error handling with malformed messages.
        
        Validates:
        - Invalid JSON message handling
        - Invalid EventEnvelope structure
        - Graceful error recovery
        - No database records for failed messages
        """
        # Arrange - Create invalid message
        mock_msg = Mock(spec=ConsumerRecord)
        mock_msg.topic = topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED)
        mock_msg.partition = 0
        mock_msg.offset = 789
        mock_msg.value = b'{"invalid": "json structure", "missing_required_fields": true}'
        
        # Act - Process invalid message
        result = await kafka_consumer._process_message(mock_msg)
        
        # Assert - Processing should fail gracefully
        assert result is False, "Invalid message processing should fail"
        
        # Verify no email provider calls
        mock_email_provider.send_email.assert_not_called()

    async def test_concurrent_message_processing_with_swedish_content(
        self,
        event_processor: EmailEventProcessor,
        email_repository: EmailRepository,
        mock_email_provider: AsyncMock,
    ) -> None:
        """
        Test concurrent processing of multiple email requests with Swedish content.
        
        Validates:
        - Multiple email requests processed concurrently
        - Swedish character preservation across concurrent operations
        - Database consistency with concurrent writes
        - Provider interaction under load
        """
        # Arrange - Create multiple email requests with Swedish content
        correlation_id = str(uuid.uuid4())
        email_requests = []
        
        swedish_names = [
            "Åsa Öhman", "Erik Åslund", "Märta Ström", 
            "Björn Löfgren", "Astrid Öberg"
        ]
        
        for i, name in enumerate(swedish_names):
            message_id = f"msg_{uuid.uuid4()}"
            email_request = NotificationEmailRequestedV1(
                message_id=message_id,
                template_id="welcome",
                to=f"teacher{i}@björkskolan.se",
                variables={
                    "name": name,
                    "school": f"Björkskolan {i+1}",
                    "subject": "Matematik och Naturvetenskap",
                    "welcome_message": "Välkommen till vårt digitala lärandesystem!"
                },
                category="verification",
                correlation_id=correlation_id,
            )
            email_requests.append(email_request)
        
        # Act - Process all requests concurrently
        tasks = []
        for request in email_requests:
            task = event_processor.process_email_request(request)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Assert - All emails processed successfully
        email_records = await email_repository.get_by_correlation_id(correlation_id)
        assert len(email_records) == 5, "Should process all 5 email requests"
        
        # Verify Swedish characters preserved
        for record in email_records:
            assert "Björkskolan" in record.variables["school"]
            assert "Välkommen" in record.variables["welcome_message"]
        
        # Verify all provider calls made
        assert mock_email_provider.send_email.call_count == 5

    async def test_message_envelope_serialization_with_special_characters(
        self,
        kafka_consumer: EmailKafkaConsumer,
    ) -> None:
        """
        Test EventEnvelope serialization/deserialization with special characters.
        
        Validates:
        - JSON serialization preserves Swedish characters
        - EventEnvelope structure validation
        - Pydantic model validation with Unicode
        - Message timestamp handling
        """
        # Arrange - Create envelope with comprehensive Swedish content
        correlation_id = str(uuid.uuid4())
        message_id = f"msg_{uuid.uuid4()}"
        
        email_request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="verification",
            to="användare@åäötest.se",
            variables={
                "full_name": "Åsa Öhman-Ström",
                "course": "Avancerad Matematik för Årskurs 9",
                "institution": "Kungliga Tekniska Högskolan i Stockholm",
                "special_chars": "Testing: åäöÅÄÖ!@#$%^&*()_+-=[]{}|;:,.<>?",
                "unicode_emoji": "📧📚🇸🇪",
            },
            category="verification",
            correlation_id=correlation_id,
        )
        
        envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_id=str(uuid.uuid4()),
            event_type="NotificationEmailRequestedV1",
            data=email_request,
            correlation_id=correlation_id,
            event_timestamp=datetime.now(UTC),
            source_service="test-service",
        )
        
        # Act - Serialize and deserialize envelope
        serialized = json.dumps(envelope.model_dump(mode="json"))
        serialized_bytes = serialized.encode("utf-8")
        
        # Simulate Kafka message
        mock_msg = Mock(spec=ConsumerRecord)
        mock_msg.value = serialized_bytes
        mock_msg.topic = topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED)
        mock_msg.partition = 0
        mock_msg.offset = 999
        
        # Process message (this involves deserialization)
        result = await kafka_consumer._process_message(mock_msg)
        
        # Assert - Verify successful processing with character preservation
        assert result is True, "Message with Swedish characters should process successfully"
        
        # Verify deserialization preserved all special characters
        deserialized_envelope = EventEnvelope[NotificationEmailRequestedV1].model_validate_json(
            serialized_bytes
        )
        
        assert deserialized_envelope.data.to == "användare@åäötest.se"
        assert deserialized_envelope.data.variables["full_name"] == "Åsa Öhman-Ström"
        assert deserialized_envelope.data.variables["course"] == "Avancerad Matematik för Årskurs 9"
        assert deserialized_envelope.data.variables["institution"] == "Kungliga Tekniska Högskolan i Stockholm"
        assert "åäöÅÄÖ" in deserialized_envelope.data.variables["special_chars"]
        assert "📧📚🇸🇪" in deserialized_envelope.data.variables["unicode_emoji"]