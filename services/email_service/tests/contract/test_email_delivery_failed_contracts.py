"""
Email Delivery Failed Event Contract Testing for Email Service.

This module provides comprehensive contract tests for EmailDeliveryFailedV1 events
to ensure proper serialization, validation, and Swedish character handling
in the HuleEdu platform's email error reporting system.

Following ULTRATHINK methodology for failure event schema validation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.emailing_models import EmailDeliveryFailedV1


class TestEmailDeliveryFailedV1Contracts:
    """Contract tests for EmailDeliveryFailedV1 event schema and serialization."""

    def test_email_delivery_failed_required_fields_contract(self) -> None:
        """Contract test: EmailDeliveryFailedV1 must have all required fields."""
        # Arrange
        correlation_id = str(uuid4())
        failed_at = datetime.now(UTC)

        # Act - Create EmailDeliveryFailedV1 with all required fields
        event = EmailDeliveryFailedV1(
            message_id="failed-msg-001",
            provider="sendgrid",
            failed_at=failed_at,
            reason="Recipient email bounced",
            correlation_id=correlation_id,
        )

        # Assert - All required fields present and correct types
        assert event.message_id == "failed-msg-001"
        assert event.provider == "sendgrid"
        assert event.failed_at == failed_at
        assert event.reason == "Recipient email bounced"
        assert event.correlation_id == correlation_id

    @pytest.mark.parametrize(
        "reason, expected_reason",
        [
            # Common delivery failure reasons
            ("Recipient email bounced", "Recipient email bounced"),
            ("Invalid recipient address", "Invalid recipient address"),
            ("Temporary server error", "Temporary server error"),
            ("Rate limit exceeded", "Rate limit exceeded"),
            ("Authentication failed", "Authentication failed"),
            # Swedish educational context failures
            ("Elevens e-post är inaktiverad", "Elevens e-post är inaktiverad"),
            ("Skolan blockerar externa meddelanden", "Skolan blockerar externa meddelanden"),
            # Technical failure reasons with special characters
            ("DNS lookup failed: host åäötest.se", "DNS lookup failed: host åäötest.se"),
            (
                "SMTP 550: Mailbox unavailable för användarnamn@skola.se",
                "SMTP 550: Mailbox unavailable för användarnamn@skola.se",
            ),
        ],
    )
    def test_email_delivery_failed_reason_validation_contract(
        self, reason: str, expected_reason: str
    ) -> None:
        """Contract test: EmailDeliveryFailedV1 reason field with various failure scenarios."""
        correlation_id = str(uuid4())

        # Act
        event = EmailDeliveryFailedV1(
            message_id="reason-test",
            provider="test-provider",
            failed_at=datetime.now(UTC),
            reason=reason,
            correlation_id=correlation_id,
        )

        # Assert - Reason field preservation including Swedish characters
        assert event.reason == expected_reason

    def test_email_delivery_failed_timestamp_accuracy_contract(self) -> None:
        """Contract test: EmailDeliveryFailedV1 must preserve timestamp accuracy."""
        # Arrange - Create precise timestamp with microseconds
        correlation_id = str(uuid4())
        precise_timestamp = datetime.now(UTC).replace(microsecond=123456)

        event = EmailDeliveryFailedV1(
            message_id="precision-test",
            provider="timestamp-provider",
            failed_at=precise_timestamp,
            reason="Timestamp test failure",
            correlation_id=correlation_id,
        )

        # Act - Serialize and deserialize
        json_str = event.model_dump_json()
        deserialized = EmailDeliveryFailedV1.model_validate_json(json_str)

        # Assert - Microsecond precision preserved
        assert deserialized.failed_at == precise_timestamp
        assert deserialized.failed_at.microsecond == 123456

    def test_email_delivery_failed_error_context_propagation_contract(self) -> None:
        """Contract test: EmailDeliveryFailedV1 must maintain error context across boundaries."""
        # Arrange - Create failure event with complex reason
        correlation_id = str(uuid4())
        complex_reason = (
            "SMTP Error 550: User unknown in virtual mailbox table "
            "(error code: AUTH_FAILED_USER_LOOKUP)"
        )

        original_event = EmailDeliveryFailedV1(
            message_id="context-test-001",
            provider="complex-provider",
            failed_at=datetime.now(UTC),
            reason=complex_reason,
            correlation_id=correlation_id,
        )

        # Act - Simulate cross-service transmission via JSON
        transmission_json = original_event.model_dump_json()
        received_event = EmailDeliveryFailedV1.model_validate_json(transmission_json)

        # Assert - Complete error context preserved
        assert received_event.reason == complex_reason
        assert received_event.message_id == original_event.message_id
        assert received_event.correlation_id == correlation_id
        assert received_event == original_event
