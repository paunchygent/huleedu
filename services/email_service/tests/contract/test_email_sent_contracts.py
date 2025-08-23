"""
Email Sent Event Contract Testing for Email Service.

This module provides comprehensive contract tests for EmailSentV1 events
to ensure proper serialization, validation, and integration with the
HuleEdu event-driven architecture.

Following ULTRATHINK methodology for event schema validation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from common_core.emailing_models import EmailSentV1


class TestEmailSentV1Contracts:
    """Contract tests for EmailSentV1 event schema and serialization."""

    def test_email_sent_required_fields_contract(self) -> None:
        """Contract test: EmailSentV1 must have all required fields with correct types."""
        # Arrange
        correlation_id = str(uuid4())
        sent_at = datetime.now(UTC)

        # Act - Create EmailSentV1 with all required fields
        event = EmailSentV1(
            message_id="msg-12345",
            provider="sendgrid",
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

        # Assert - All required fields present and correct types
        assert event.message_id == "msg-12345"
        assert event.provider == "sendgrid"
        assert event.sent_at == sent_at
        assert event.correlation_id == correlation_id

    @pytest.mark.parametrize(
        "message_id, provider, expected_message_id, expected_provider",
        [
            # Standard provider cases
            ("email-001", "sendgrid", "email-001", "sendgrid"),
            ("notification-abc123", "mailgun", "notification-abc123", "mailgun"),
            ("bulk-email-456", "ses", "bulk-email-456", "ses"),
            # Edge case: minimal valid strings
            ("1", "x", "1", "x"),
            # Special characters in message_id
            ("msg_2024-08-23_batch-1", "smtp", "msg_2024-08-23_batch-1", "smtp"),
        ],
    )
    def test_email_sent_field_validation_contract(
        self,
        message_id: str,
        provider: str,
        expected_message_id: str,
        expected_provider: str,
    ) -> None:
        """Contract test: EmailSentV1 field validation with various inputs."""
        correlation_id = str(uuid4())
        sent_at = datetime.now(UTC)

        # Act
        event = EmailSentV1(
            message_id=message_id,
            provider=provider,
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

        # Assert
        assert event.message_id == expected_message_id
        assert event.provider == expected_provider

    def test_email_sent_datetime_serialization_contract(self) -> None:
        """Contract test: EmailSentV1 datetime fields must serialize with timezone info."""
        # Arrange - Create event with timezone-aware datetime
        correlation_id = str(uuid4())
        sent_at = datetime.now(UTC)
        event = EmailSentV1(
            message_id="time-test",
            provider="test-provider",
            sent_at=sent_at,
            correlation_id=correlation_id,
        )

        # Act - Serialize to dict and JSON
        event_dict = event.model_dump(mode="json")
        json_str = event.model_dump_json()
        parsed_json = json.loads(json_str)

        # Assert - Timezone preservation in serialization
        assert "sent_at" in event_dict
        assert "sent_at" in parsed_json
        # ISO format should include timezone info
        assert parsed_json["sent_at"].endswith("Z") or "+" in parsed_json["sent_at"]

        # Assert - Round-trip preservation
        deserialized = EmailSentV1.model_validate(parsed_json)
        assert deserialized.sent_at == sent_at
        assert deserialized.message_id == "time-test"

    def test_email_sent_json_roundtrip_contract(self) -> None:
        """Contract test: EmailSentV1 must serialize/deserialize perfectly via JSON."""
        # Arrange
        correlation_id = str(uuid4())
        original_event = EmailSentV1(
            message_id="roundtrip-test",
            provider="json-provider",
            sent_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )

        # Act - Full JSON round-trip
        json_str = original_event.model_dump_json()
        json_dict = json.loads(json_str)
        deserialized_event = EmailSentV1.model_validate(json_dict)

        # Assert - Perfect round-trip preservation
        assert deserialized_event == original_event
        assert deserialized_event.message_id == original_event.message_id
        assert deserialized_event.provider == original_event.provider
        assert deserialized_event.sent_at == original_event.sent_at
        assert deserialized_event.correlation_id == original_event.correlation_id

    def test_email_sent_uuid_correlation_conversion_contract(self) -> None:
        """Contract test: EmailSentV1 must handle UUID to string conversion for correlation_id."""
        # Arrange
        correlation_uuid = uuid4()
        correlation_str = str(correlation_uuid)

        # Act - Create with string correlation_id (standard usage)
        event = EmailSentV1(
            message_id="uuid-test",
            provider="uuid-provider",
            sent_at=datetime.now(UTC),
            correlation_id=correlation_str,
        )

        # Assert - String storage and consistency
        assert isinstance(event.correlation_id, str)
        assert event.correlation_id == correlation_str
        assert UUID(event.correlation_id) == correlation_uuid  # Can convert back to UUID
