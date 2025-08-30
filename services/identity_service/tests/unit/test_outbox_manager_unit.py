"""
Unit tests for OutboxManager transactional outbox pattern behavior.

Tests focus on the transactional outbox pattern implementation, protocol-based
dependency injection, error handling, and infrastructure integration patterns.
Validates reliable event publishing through outbox and relay worker coordination.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from pydantic import BaseModel

from services.identity_service.config import Settings
from huleedu_service_libs.outbox.manager import OutboxManager


class MockEventData(BaseModel):
    """Mock event data for testing EventEnvelope serialization."""

    user_id: str
    action: str
    message: str = "Test event with Swedish characters: åäö"


class TestOutboxManager:
    """Tests for OutboxManager transactional outbox pattern."""

    @pytest.fixture
    def mock_outbox_repository(self) -> AsyncMock:
        """Create mock outbox repository following protocol."""
        return AsyncMock(spec=OutboxRepositoryProtocol)

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client following protocol."""
        return AsyncMock(spec=AtomicRedisClientProtocol)

    @pytest.fixture
    def mock_settings(self) -> AsyncMock:
        """Create mock settings configuration."""
        return AsyncMock(spec=Settings)

    @pytest.fixture
    def outbox_manager(
        self,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> OutboxManager:
        """Create OutboxManager instance with mocked dependencies."""
        return OutboxManager(
            outbox_repository=mock_outbox_repository,
            redis_client=mock_redis_client,
            service_name="identity_service",
        )

    @pytest.fixture
    def sample_event_envelope(self) -> EventEnvelope[MockEventData]:
        """Create sample EventEnvelope for testing."""
        correlation_id = uuid4()
        event_data = MockEventData(
            user_id="user_123",
            action="password_reset",
            message="Lösenord återställning för användare: åäö",
        )
        return EventEnvelope[MockEventData](
            event_type="huleedu.identity.password_reset.v1",
            source_service="identity_service",
            correlation_id=correlation_id,
            data=event_data,
            metadata={"partition_key": "user_123", "trace_id": str(correlation_id)},
        )

    @pytest.fixture
    def outbox_event_id(self) -> UUID:
        """Generate UUID for outbox event ID."""
        return uuid4()

    async def test_publish_to_outbox_success_with_session(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope[MockEventData],
        outbox_event_id: UUID,
    ) -> None:
        """Test successful event publishing to outbox with database session."""
        # Arrange
        mock_session = AsyncMock()
        mock_outbox_repository.add_event.return_value = outbox_event_id
        mock_redis_client.lpush.return_value = 1

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id="user_123",
            event_type="huleedu.identity.password_reset.v1",
            event_data=sample_event_envelope,
            topic="identity_events",
            session=mock_session,
        )

        # Assert - Repository called with correct parameters
        mock_outbox_repository.add_event.assert_called_once()
        call_args = mock_outbox_repository.add_event.call_args

        assert call_args.kwargs["aggregate_id"] == "user_123"
        assert call_args.kwargs["aggregate_type"] == "user"
        assert call_args.kwargs["event_type"] == "huleedu.identity.password_reset.v1"
        assert call_args.kwargs["topic"] == "identity_events"
        assert call_args.kwargs["event_key"] == "user_123"  # From metadata partition_key
        assert call_args.kwargs["session"] is mock_session

        # Verify event data serialization
        event_data = call_args.kwargs["event_data"]
        assert isinstance(event_data, dict)
        assert event_data["event_type"] == "huleedu.identity.password_reset.v1"
        assert event_data["source_service"] == "identity_service"
        assert event_data["correlation_id"] == str(sample_event_envelope.correlation_id)
        assert event_data["data"]["user_id"] == "user_123"
        assert event_data["data"]["action"] == "password_reset"
        assert "åäö" in event_data["data"]["message"]

        # Assert - Redis notification sent
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:identity_service", "wake")

    async def test_publish_to_outbox_success_without_session(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope[MockEventData],
        outbox_event_id: UUID,
    ) -> None:
        """Test successful event publishing to outbox without database session."""
        # Arrange
        mock_outbox_repository.add_event.return_value = outbox_event_id
        mock_redis_client.lpush.return_value = 1

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id="user_123",
            event_type="huleedu.identity.password_reset.v1",
            event_data=sample_event_envelope,
            topic="identity_events",
        )

        # Assert - Repository called with None session
        mock_outbox_repository.add_event.assert_called_once()
        call_args = mock_outbox_repository.add_event.call_args
        assert call_args.kwargs["session"] is None

    async def test_publish_to_outbox_uses_aggregate_id_when_no_partition_key(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        outbox_event_id: UUID,
    ) -> None:
        """Test event key defaults to aggregate_id when no partition_key in metadata."""
        # Arrange
        event_data = MockEventData(user_id="user_456", action="login")
        envelope = EventEnvelope[MockEventData](
            event_type="huleedu.identity.login.v1",
            source_service="identity_service",
            correlation_id=uuid4(),
            data=event_data,
            metadata={"trace_id": "trace_789"},  # No partition_key
        )
        mock_outbox_repository.add_event.return_value = outbox_event_id
        mock_redis_client.lpush.return_value = 1

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id="user_456",
            event_type="huleedu.identity.login.v1",
            event_data=envelope,
            topic="identity_events",
        )

        # Assert - Event key uses aggregate_id
        call_args = mock_outbox_repository.add_event.call_args
        assert call_args.kwargs["event_key"] == "user_456"

    async def test_publish_to_outbox_uses_aggregate_id_when_no_metadata(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        outbox_event_id: UUID,
    ) -> None:
        """Test event key defaults to aggregate_id when no metadata present."""
        # Arrange
        event_data = MockEventData(user_id="user_789", action="logout")
        envelope = EventEnvelope[MockEventData](
            event_type="huleedu.identity.logout.v1",
            source_service="identity_service",
            correlation_id=uuid4(),
            data=event_data,
            metadata=None,  # No metadata
        )
        mock_outbox_repository.add_event.return_value = outbox_event_id
        mock_redis_client.lpush.return_value = 1

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id="user_789",
            event_type="huleedu.identity.logout.v1",
            event_data=envelope,
            topic="identity_events",
        )

        # Assert - Event key uses aggregate_id
        call_args = mock_outbox_repository.add_event.call_args
        assert call_args.kwargs["event_key"] == "user_789"

    async def test_publish_to_outbox_repository_not_configured(
        self,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope[MockEventData],
    ) -> None:
        """Test HuleEduError raised when outbox repository is not configured."""
        # Arrange
        outbox_manager = OutboxManager(
            outbox_repository=None,  # type: ignore[arg-type]  # Testing None scenario
            redis_client=mock_redis_client,
            service_name="identity_service",
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="user",
                aggregate_id="user_123",
                event_type="huleedu.identity.password_reset.v1",
                event_data=sample_event_envelope,
                topic="identity_events",
            )

        error_detail = exc_info.value.error_detail
        assert error_detail.service == "identity_service"
        assert error_detail.operation == "publish_to_outbox"
        assert error_detail.details["external_service"] == "outbox_repository"
        assert "not configured" in error_detail.message
        assert error_detail.correlation_id == sample_event_envelope.correlation_id
        assert error_detail.details["aggregate_id"] == "user_123"
        assert error_detail.details["event_type"] == "huleedu.identity.password_reset.v1"

    async def test_publish_to_outbox_invalid_event_data_without_model_dump(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test HuleEduError raised when event_data lacks model_dump method."""
        # Arrange - Plain dict without model_dump method
        invalid_event_data = {"user_id": "user_123", "action": "test"}

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="user",
                aggregate_id="user_123",
                event_type="huleedu.identity.test.v1",
                event_data=invalid_event_data,  # type: ignore[arg-type]  # Testing invalid event data
                topic="identity_events",
            )

        error_detail = exc_info.value.error_detail
        assert error_detail.service == "identity_service"
        assert error_detail.operation == "publish_to_outbox"
        assert error_detail.details["external_service"] == "outbox_repository"
        assert "Failed to store event in outbox: ValueError" in error_detail.message
        assert error_detail.details["error_type"] == "ValueError"
        assert (
            "OutboxManager expects Pydantic EventEnvelope" in error_detail.details["error_details"]
        )

    async def test_publish_to_outbox_repository_storage_failure(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope[MockEventData],
    ) -> None:
        """Test HuleEduError raised when repository storage fails."""
        # Arrange
        mock_outbox_repository.add_event.side_effect = Exception("Database connection lost")

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="user",
                aggregate_id="user_123",
                event_type="huleedu.identity.password_reset.v1",
                event_data=sample_event_envelope,
                topic="identity_events",
            )

        error_detail = exc_info.value.error_detail
        assert error_detail.service == "identity_service"
        assert error_detail.operation == "publish_to_outbox"
        assert error_detail.details["external_service"] == "outbox_repository"
        assert "Failed to store event in outbox: Exception" in error_detail.message
        assert error_detail.details["error_type"] == "Exception"
        assert error_detail.details["error_details"] == "Database connection lost"

    async def test_publish_to_outbox_preserves_huleedu_error(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope[MockEventData],
    ) -> None:
        """Test HuleEduError from repository is re-raised as-is."""
        # Arrange
        from huleedu_service_libs.error_handling import raise_external_service_error

        try:
            raise_external_service_error(
                service="identity_service",
                operation="add_event",
                external_service="database",
                message="Connection timeout",
                correlation_id=sample_event_envelope.correlation_id,
            )
        except HuleEduError as e:
            original_error = e
        mock_outbox_repository.add_event.side_effect = original_error

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="user",
                aggregate_id="user_123",
                event_type="huleedu.identity.password_reset.v1",
                event_data=sample_event_envelope,
                topic="identity_events",
            )

        # Assert same error instance is re-raised
        assert exc_info.value is original_error

    async def test_publish_to_outbox_correlation_id_extraction_from_dict(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test correlation ID extraction when event_data has no correlation_id."""

        # Arrange - Object without correlation_id and without model_dump
        class MockEventWithoutCorrelationId:
            def __init__(self) -> None:
                self.user_id = "user_123"

        invalid_event_data = MockEventWithoutCorrelationId()
        mock_outbox_repository.add_event.side_effect = Exception("Storage failed")

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="user",
                aggregate_id="user_123",
                event_type="huleedu.identity.test.v1",
                event_data=invalid_event_data,  # type: ignore[arg-type]  # Testing invalid object
                topic="identity_events",
            )

        # Should use default UUID when correlation_id not extractable from invalid object
        error_detail = exc_info.value.error_detail
        # The correlation_id should be the default UUID since extraction failed
        assert error_detail.correlation_id == UUID("00000000-0000-0000-0000-000000000000")

    async def test_publish_to_outbox_redis_notification_failure_does_not_fail_operation(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope[MockEventData],
        outbox_event_id: UUID,
    ) -> None:
        """Test Redis notification failure does not fail the outbox operation."""
        # Arrange
        mock_outbox_repository.add_event.return_value = outbox_event_id
        mock_redis_client.lpush.side_effect = Exception("Redis connection failed")

        # Act - Should not raise exception
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id="user_123",
            event_type="huleedu.identity.password_reset.v1",
            event_data=sample_event_envelope,
            topic="identity_events",
        )

        # Assert - Repository operation completed successfully
        mock_outbox_repository.add_event.assert_called_once()


    async def test_publish_to_outbox_serialization_preserves_swedish_characters(
        self,
        outbox_manager: OutboxManager,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        outbox_event_id: UUID,
    ) -> None:
        """Test EventEnvelope serialization preserves Swedish characters correctly."""
        # Arrange
        event_data = MockEventData(
            user_id="user_åäö",
            action="lösenord_återställning",
            message="Användare med svenska tecken: åäöÅÄÖ",
        )
        envelope = EventEnvelope[MockEventData](
            event_type="huleedu.identity.swedish_test.v1",
            source_service="identity_service",
            correlation_id=uuid4(),
            data=event_data,
            metadata={"locale": "sv_SE"},
        )
        mock_outbox_repository.add_event.return_value = outbox_event_id
        mock_redis_client.lpush.return_value = 1

        # Act
        await outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id="user_åäö",
            event_type="huleedu.identity.swedish_test.v1",
            event_data=envelope,
            topic="identity_events",
        )

        # Assert - Swedish characters preserved in serialized data
        call_args = mock_outbox_repository.add_event.call_args
        event_data_dict = call_args.kwargs["event_data"]
        assert event_data_dict["data"]["user_id"] == "user_åäö"
        assert event_data_dict["data"]["action"] == "lösenord_återställning"
        assert "åäöÅÄÖ" in event_data_dict["data"]["message"]
        assert event_data_dict["metadata"]["locale"] == "sv_SE"
