"""Behavioral tests for EventPublisherImpl following Rule 075 standards."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core import (
    CreditBalanceChangedV1,
    EventEnvelope,
    ProcessingEvent,
    RateLimitExceededV1,
    UsageRecordedV1,
    topic_name,
)
from huleedu_service_libs.outbox.manager import OutboxManager

from services.entitlements_service.config import Settings
from services.entitlements_service.implementations.event_publisher_impl import (
    EventPublisherImpl,
)


class TestEventPublisherImpl:
    """Behavioral tests for EventPublisherImpl event publishing functionality."""

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Create spec-based mock for outbox manager."""
        mock_manager = AsyncMock(spec=OutboxManager)
        mock_manager.publish_to_outbox.return_value = None
        return mock_manager

    @pytest.fixture
    def mock_settings(self) -> AsyncMock:
        """Create mock settings with service name configuration."""
        mock_settings = AsyncMock(spec=Settings)
        mock_settings.SERVICE_NAME = "entitlements_service"
        return mock_settings

    @pytest.fixture
    def event_publisher(
        self, mock_outbox_manager: AsyncMock, mock_settings: AsyncMock
    ) -> EventPublisherImpl:
        """Create EventPublisherImpl with mocked dependencies."""
        return EventPublisherImpl(outbox_manager=mock_outbox_manager, settings=mock_settings)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "subject_type",
            "subject_id",
            "old_balance",
            "new_balance",
            "delta",
            "correlation_id",
            "expected_aggregate_type",
        ),
        [
            # Basic user credit operations
            ("user", "user-123", 100, 105, 5, str(uuid4()), "credit_balance_user"),
            ("user", "user-456", 50, 40, -10, str(uuid4()), "credit_balance_user"),
            # Basic org credit operations
            ("org", "org-789", 1000, 1050, 50, str(uuid4()), "credit_balance_org"),
            ("org", "org-101", 500, 450, -50, str(uuid4()), "credit_balance_org"),
            # Swedish character handling in IDs
            ("user", "lärare-örebro", 75, 80, 5, str(uuid4()), "credit_balance_user"),
            ("org", "skola-göteborg", 200, 190, -10, str(uuid4()), "credit_balance_org"),
            # Edge cases - zero balance changes
            ("user", "user-zero", 0, 0, 0, str(uuid4()), "credit_balance_user"),
            # Large balance changes
            ("org", "org-large", 10000, 15000, 5000, str(uuid4()), "credit_balance_org"),
            # Non-UUID correlation IDs (should be handled gracefully)
            ("user", "user-123", 100, 105, 5, "simple-correlation", "credit_balance_user"),
        ],
    )
    async def test_publish_credit_balance_changed_publishes_correctly(
        self,
        event_publisher: EventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        subject_type: str,
        subject_id: str,
        old_balance: int,
        new_balance: int,
        delta: int,
        correlation_id: str,
        expected_aggregate_type: str,
    ) -> None:
        """Test credit balance changed event publishing with various scenarios."""
        # Act
        await event_publisher.publish_credit_balance_changed(
            subject_type=subject_type,
            subject_id=subject_id,
            old_balance=old_balance,
            new_balance=new_balance,
            delta=delta,
            correlation_id=correlation_id,
        )

        # Assert - Verify outbox manager called correctly
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify aggregate information
        assert call_args is not None
        kwargs = call_args.kwargs
        assert kwargs["aggregate_type"] == expected_aggregate_type
        assert kwargs["aggregate_id"] == subject_id
        assert kwargs["event_type"] == topic_name(
            ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED
        )
        assert kwargs["topic"] == topic_name(ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED)

        # Verify event envelope structure
        event_envelope = kwargs["event_data"]
        assert isinstance(event_envelope, EventEnvelope)
        assert event_envelope.event_type == topic_name(
            ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED
        )
        assert event_envelope.source_service == "entitlements_service"
        assert isinstance(event_envelope.event_id, UUID)
        assert isinstance(event_envelope.correlation_id, UUID)

        # Verify event data payload
        event_data = event_envelope.data
        assert isinstance(event_data, CreditBalanceChangedV1)
        assert event_data.subject.type == subject_type
        assert event_data.subject.id == subject_id
        assert event_data.delta == delta
        assert event_data.new_balance == new_balance
        assert event_data.reason == "credit_operation"
        assert event_data.correlation_id == correlation_id
        # Verify metadata
        metadata = event_envelope.metadata
        assert metadata is not None
        assert metadata["partition_key"] == subject_id
        assert metadata["subject_type"] == subject_type
        assert metadata["delta"] == str(delta)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "subject_id",
            "metric",
            "limit",
            "current_count",
            "window_seconds",
            "correlation_id",
        ),
        [
            # Basic rate limit scenarios
            ("user-123", "api_calls", 100, 101, 3600, str(uuid4())),
            ("user-456", "ai_feedback", 50, 55, 1800, str(uuid4())),
            # Swedish character handling in IDs and metrics
            ("lärare-åse", "grammatik_kontroll", 25, 30, 3600, str(uuid4())),
            ("elev-örjan", "uppsats_bedömning", 10, 15, 7200, str(uuid4())),
            # Edge cases - exact limit reached
            ("user-exact", "exact_limit", 100, 100, 3600, str(uuid4())),
            # Large numbers
            ("org-bulk", "bulk_operations", 10000, 12000, 86400, str(uuid4())),
            # Short time windows
            ("user-burst", "burst_requests", 5, 8, 60, str(uuid4())),
            # Non-UUID correlation IDs
            ("user-simple", "simple_metric", 20, 25, 1800, "rate-limit-correlation"),
        ],
    )
    async def test_publish_rate_limit_exceeded_publishes_correctly(
        self,
        event_publisher: EventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        subject_id: str,
        metric: str,
        limit: int,
        current_count: int,
        window_seconds: int,
        correlation_id: str,
    ) -> None:
        """Test rate limit exceeded event publishing with various scenarios."""
        # Act
        await event_publisher.publish_rate_limit_exceeded(
            subject_id=subject_id,
            metric=metric,
            limit=limit,
            current_count=current_count,
            window_seconds=window_seconds,
            correlation_id=correlation_id,
        )

        # Assert - Verify outbox manager called correctly
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify aggregate information
        assert call_args is not None
        kwargs = call_args.kwargs
        assert kwargs["aggregate_type"] == "rate_limit_bucket"
        assert kwargs["aggregate_id"] == subject_id
        assert kwargs["event_type"] == topic_name(ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED)
        assert kwargs["topic"] == topic_name(ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED)

        # Verify event envelope structure
        event_envelope = kwargs["event_data"]
        assert isinstance(event_envelope, EventEnvelope)
        assert event_envelope.event_type == topic_name(
            ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED
        )
        assert event_envelope.source_service == "entitlements_service"
        assert isinstance(event_envelope.event_id, UUID)
        assert isinstance(event_envelope.correlation_id, UUID)

        # Verify event data payload
        event_data = event_envelope.data
        assert isinstance(event_data, RateLimitExceededV1)
        assert event_data.subject.type == "user"  # Rate limits always apply to users
        assert event_data.subject.id == subject_id
        assert event_data.metric == metric
        assert event_data.limit == limit
        assert event_data.window_seconds == window_seconds
        assert event_data.correlation_id == correlation_id
        # Verify metadata
        metadata = event_envelope.metadata
        assert metadata is not None
        assert metadata["partition_key"] == subject_id
        assert metadata["metric"] == metric
        assert metadata["limit"] == str(limit)
        assert metadata["current_count"] == str(current_count)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "subject_type",
            "subject_id",
            "metric",
            "amount",
            "correlation_id",
            "expected_aggregate_type",
        ),
        [
            # Basic user usage recording
            ("user", "user-123", "ai_feedback", 1, str(uuid4()), "usage_user"),
            ("user", "user-456", "essay_scoring", 3, str(uuid4()), "usage_user"),
            # Basic org usage recording
            ("org", "org-789", "batch_processing", 50, str(uuid4()), "usage_org"),
            ("org", "org-101", "bulk_export", 25, str(uuid4()), "usage_org"),
            # Swedish character handling in IDs and metrics
            ("user", "student-åsa", "språk_analys", 2, str(uuid4()), "usage_user"),
            ("org", "universitet-örebro", "kurs_utvärdering", 10, str(uuid4()), "usage_org"),
            # Edge cases - zero usage (unusual but valid)
            ("user", "user-zero", "zero_usage", 0, str(uuid4()), "usage_user"),
            # Large usage amounts
            ("org", "org-massive", "massive_batch", 10000, str(uuid4()), "usage_org"),
            # Non-UUID correlation IDs
            ("user", "user-simple", "simple_usage", 5, "usage-correlation", "usage_user"),
        ],
    )
    async def test_publish_usage_recorded_publishes_correctly(
        self,
        event_publisher: EventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        subject_type: str,
        subject_id: str,
        metric: str,
        amount: int,
        correlation_id: str,
        expected_aggregate_type: str,
    ) -> None:
        """Test usage recorded event publishing with various scenarios."""
        # Act
        await event_publisher.publish_usage_recorded(
            subject_type=subject_type,
            subject_id=subject_id,
            metric=metric,
            amount=amount,
            correlation_id=correlation_id,
        )

        # Assert - Verify outbox manager called correctly
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify aggregate information
        assert call_args is not None
        kwargs = call_args.kwargs
        assert kwargs["aggregate_type"] == expected_aggregate_type
        assert kwargs["aggregate_id"] == subject_id
        assert kwargs["event_type"] == topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED)
        assert kwargs["topic"] == topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED)

        # Verify event envelope structure
        event_envelope = kwargs["event_data"]
        assert isinstance(event_envelope, EventEnvelope)
        assert event_envelope.event_type == topic_name(ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED)
        assert event_envelope.source_service == "entitlements_service"
        assert isinstance(event_envelope.event_id, UUID)
        assert isinstance(event_envelope.correlation_id, UUID)

        # Verify event data payload
        event_data = event_envelope.data
        assert isinstance(event_data, UsageRecordedV1)
        assert event_data.subject.type == subject_type
        assert event_data.subject.id == subject_id
        assert event_data.metric == metric
        assert event_data.amount == amount
        assert event_data.correlation_id == correlation_id
        # Verify timestamps
        assert isinstance(event_data.period_start, datetime)
        assert isinstance(event_data.period_end, datetime)
        assert event_data.period_start == event_data.period_end
        # Verify metadata
        metadata = event_envelope.metadata
        assert metadata is not None
        assert metadata["partition_key"] == subject_id
        assert metadata["subject_type"] == subject_type
        assert metadata["metric"] == metric
        assert metadata["amount"] == str(amount)

    @pytest.mark.asyncio
    async def test_event_serialization_deterministic(
        self,
        event_publisher: EventPublisherImpl,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that event serialization is deterministic for same inputs."""
        test_params = {
            "subject_type": "user",
            "subject_id": "deterministic-test",
            "old_balance": 100,
            "new_balance": 95,
            "delta": -5,
            "correlation_id": "test-correlation",
        }
        await event_publisher.publish_credit_balance_changed(
            subject_type=cast(str, test_params["subject_type"]),
            subject_id=cast(str, test_params["subject_id"]),
            old_balance=cast(int, test_params["old_balance"]),
            new_balance=cast(int, test_params["new_balance"]),
            delta=cast(int, test_params["delta"]),
            correlation_id=cast(str, test_params["correlation_id"]),
        )
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args is not None
        first_call_envelope = call_args.kwargs["event_data"]

        mock_outbox_manager.reset_mock()
        await event_publisher.publish_credit_balance_changed(
            subject_type=cast(str, test_params["subject_type"]),
            subject_id=cast(str, test_params["subject_id"]),
            old_balance=cast(int, test_params["old_balance"]),
            new_balance=cast(int, test_params["new_balance"]),
            delta=cast(int, test_params["delta"]),
            correlation_id=cast(str, test_params["correlation_id"]),
        )
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args is not None
        second_call_envelope = call_args.kwargs["event_data"]

        # Verify deterministic event generation
        assert first_call_envelope.event_id == second_call_envelope.event_id
        assert first_call_envelope.data.model_dump() == second_call_envelope.data.model_dump()

    @pytest.mark.asyncio
    async def test_correlation_id_uuid_conversion_behavior(
        self,
        event_publisher: EventPublisherImpl,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test correlation ID is properly converted to UUID format."""
        # Test with valid UUID string
        valid_uuid = str(uuid4())
        await event_publisher.publish_credit_balance_changed(
            subject_type="user",
            subject_id="uuid-test",
            old_balance=50,
            new_balance=45,
            delta=-5,
            correlation_id=valid_uuid,
        )

        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args is not None
        envelope = call_args.kwargs["event_data"]
        assert envelope.correlation_id == UUID(valid_uuid)

        # Test with non-UUID string (should generate deterministic UUID)
        mock_outbox_manager.reset_mock()
        await event_publisher.publish_credit_balance_changed(
            subject_type="user",
            subject_id="non-uuid-test",
            old_balance=50,
            new_balance=45,
            delta=-5,
            correlation_id="non-uuid-correlation",
        )

        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args is not None
        envelope = call_args.kwargs["event_data"]
        assert isinstance(envelope.correlation_id, UUID)
        expected_uuid = envelope.correlation_id

        mock_outbox_manager.reset_mock()
        await event_publisher.publish_credit_balance_changed(
            subject_type="user",
            subject_id="non-uuid-test",
            old_balance=50,
            new_balance=45,
            delta=-5,
            correlation_id="non-uuid-correlation",
        )

        call_args2 = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args2 is not None
        envelope2 = call_args2.kwargs["event_data"]
        assert envelope2.correlation_id == expected_uuid

    @pytest.mark.asyncio
    async def test_swedish_characters_json_serialization(
        self,
        event_publisher: EventPublisherImpl,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that Swedish characters are properly handled in JSON serialization."""
        # Arrange - Data with Swedish characters
        swedish_params = {
            "subject_type": "org",
            "subject_id": "skola-högsätra-åäö",
            "metric": "grammatik_kontroll_åäö",
            "amount": 3,
            "correlation_id": "svenska-tecken-test",
        }

        # Act
        await event_publisher.publish_usage_recorded(
            subject_type=cast(str, swedish_params["subject_type"]),
            subject_id=cast(str, swedish_params["subject_id"]),
            metric=cast(str, swedish_params["metric"]),
            amount=cast(int, swedish_params["amount"]),
            correlation_id=cast(str, swedish_params["correlation_id"]),
        )

        # Assert - Event published successfully with Swedish characters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args is not None
        envelope = call_args.kwargs["event_data"]

        # Verify Swedish characters preserved in data
        assert envelope.data.subject.id == "skola-högsätra-åäö"
        assert envelope.data.metric == "grammatik_kontroll_åäö"

        # Verify event can be JSON serialized with Swedish characters
        serialized = json.dumps(envelope.data.model_dump(mode="json"), ensure_ascii=False)
        assert "högsätra" in serialized
        assert "åäö" in serialized

    @pytest.mark.asyncio
    async def test_event_timestamp_behavior(
        self,
        event_publisher: EventPublisherImpl,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that event timestamps are set correctly."""
        # Arrange
        before_publish = datetime.now(timezone.utc)

        # Act
        await event_publisher.publish_credit_balance_changed(
            subject_type="user",
            subject_id="timestamp-test",
            old_balance=100,
            new_balance=95,
            delta=-5,
            correlation_id="timestamp-correlation",
        )

        after_publish = datetime.now(timezone.utc)

        # Assert - Event timestamp is within expected range
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args is not None
        envelope = call_args.kwargs["event_data"]
        event_timestamp = envelope.event_timestamp

        assert isinstance(event_timestamp, datetime)
        assert event_timestamp.tzinfo == timezone.utc
        assert before_publish <= event_timestamp <= after_publish

    def test_implements_protocol_correctly(self) -> None:
        """Test that EventPublisherImpl correctly implements EventPublisherProtocol."""
        # This test verifies the class structure matches the protocol
        # If implementation doesn't match protocol, mypy would catch it during type checking

        # Verify all protocol methods are implemented
        protocol_methods = {
            "publish_credit_balance_changed",
            "publish_rate_limit_exceeded",
            "publish_usage_recorded",
        }

        impl_methods = set(dir(EventPublisherImpl))
        assert protocol_methods.issubset(impl_methods)
