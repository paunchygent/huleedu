"""
Email Event Contract Testing for Email Service.

This module provides comprehensive contract tests for all email-related events
to ensure proper serialization, validation, and integration with EventEnvelope
across service boundaries in the HuleEdu platform.

Following ULTRATHINK methodology for event-driven architecture validation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from common_core.emailing_models import (
    EmailDeliveryFailedV1,
    EmailSentV1,
    NotificationEmailRequestedV1,
)
from common_core.events.envelope import EventEnvelope
from pydantic import ValidationError


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
        complex_reason = "SMTP Error 550: User unknown in virtual mailbox table (error code: AUTH_FAILED_USER_LOOKUP)"

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


class TestNotificationEmailRequestedV1Contracts:
    """Contract tests for NotificationEmailRequestedV1 event schema and validation."""

    def test_notification_email_requested_required_fields_contract(self) -> None:
        """Contract test: NotificationEmailRequestedV1 must have all required fields."""
        # Arrange
        correlation_id = str(uuid4())

        # Act - Create NotificationEmailRequestedV1 with all required fields
        event = NotificationEmailRequestedV1(
            message_id="notification-001",
            template_id="welcome_teacher",
            to="teacher@school.se",
            variables={"teacher_name": "Anna Lindström", "school": "Björkskolan"},
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Assert - All required fields present and correct types
        assert event.message_id == "notification-001"
        assert event.template_id == "welcome_teacher"
        assert event.to == "teacher@school.se"
        assert event.variables == {"teacher_name": "Anna Lindström", "school": "Björkskolan"}
        assert event.category == "teacher_notification"
        assert event.correlation_id == correlation_id

    @pytest.mark.parametrize(
        "template_variables, expected_variables",
        [
            # Empty variables (default)
            ({}, {}),
            # Swedish educational context variables with special characters
            (
                {"student_name": "Åsa Öhman", "class": "7A", "subject": "Matematik"},
                {"student_name": "Åsa Öhman", "class": "7A", "subject": "Matematik"},
            ),
            (
                {"teacher_name": "Erik Ångström", "school_name": "Älvsjö Grundskola"},
                {"teacher_name": "Erik Ångström", "school_name": "Älvsjö Grundskola"},
            ),
            # Complex template variables
            (
                {
                    "assignment_title": "Språkanalys: Årstider på svenska",
                    "due_date": "2024-09-15",
                    "instructions": "Skriv en uppsats om höstens färger i naturen",
                    "teacher_email": "svenska.lärare@skola.se",
                },
                {
                    "assignment_title": "Språkanalys: Årstider på svenska",
                    "due_date": "2024-09-15",
                    "instructions": "Skriv en uppsats om höstens färger i naturen",
                    "teacher_email": "svenska.lärare@skola.se",
                },
            ),
            # Password reset context
            (
                {
                    "reset_token": "abc123xyz789",
                    "user_name": "Märta Öberg",
                    "expires_in": "24 timmar",
                },
                {
                    "reset_token": "abc123xyz789",
                    "user_name": "Märta Öberg",
                    "expires_in": "24 timmar",
                },
            ),
        ],
    )
    def test_notification_email_template_variables_swedish_contract(
        self, template_variables: dict[str, str], expected_variables: dict[str, str]
    ) -> None:
        """Contract test: NotificationEmailRequestedV1 template variables with Swedish characters."""
        correlation_id = str(uuid4())

        # Act
        event = NotificationEmailRequestedV1(
            message_id="swedish-vars-test",
            template_id="test_template",
            to="test@example.se",
            variables=template_variables,
            category="system",
            correlation_id=correlation_id,
        )

        # Assert - Template variables preserved including Swedish characters
        assert event.variables == expected_variables

    @pytest.mark.parametrize(
        "category",
        [
            "verification",
            "password_reset",
            "receipt",
            "teacher_notification",
            "system",
        ],
    )
    def test_notification_email_category_enum_contract(self, category: str) -> None:
        """Contract test: NotificationEmailRequestedV1 category enum constraint validation."""
        correlation_id = str(uuid4())

        # Act
        event = NotificationEmailRequestedV1(
            message_id="category-test",
            template_id="test_template",
            to="test@example.com",
            variables={},
            category=category,  # type: ignore[arg-type] # testing literal constraint
            correlation_id=correlation_id,
        )

        # Assert - Category accepted and preserved
        assert event.category == category

    def test_notification_email_category_invalid_contract(self) -> None:
        """Contract test: NotificationEmailRequestedV1 must reject invalid categories."""
        correlation_id = str(uuid4())

        # Act & Assert - Invalid category should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            NotificationEmailRequestedV1(
                message_id="invalid-category-test",
                template_id="test_template",
                to="test@example.com",
                variables={},
                category="invalid_category",  # type: ignore[arg-type] # intentionally invalid
                correlation_id=correlation_id,
            )

        # Assert - Validation error contains category constraint information
        error_details = str(exc_info.value)
        assert "category" in error_details.lower()

    @pytest.mark.parametrize(
        "email_address",
        [
            # Valid Swedish educational email addresses
            "student@skola.se",
            "lärare.matematik@grundskola.se",
            "anna.öhman@högstadiet.se",
            "erik.ångström@gymnasium.se",
            "test+tag@universitetet.se",
            # International formats
            "teacher@international-school.edu",
            "admin@school.org",
        ],
    )
    def test_notification_email_emailstr_validation_contract(self, email_address: str) -> None:
        """Contract test: NotificationEmailRequestedV1 EmailStr field validation."""
        correlation_id = str(uuid4())

        # Act
        event = NotificationEmailRequestedV1(
            message_id="email-validation-test",
            template_id="test_template",
            to=email_address,
            variables={},
            category="system",
            correlation_id=correlation_id,
        )

        # Assert - Email address validated and preserved
        assert event.to == email_address

    def test_notification_email_variable_dict_serialization_contract(self) -> None:
        """Contract test: NotificationEmailRequestedV1 variables dict JSON serialization."""
        # Arrange - Complex variables with Swedish characters
        correlation_id = str(uuid4())
        complex_variables = {
            "student_name": "Åse Öhrn",
            "assignment_title": "Naturvetenskap - Årstidernas påverkan",
            "teacher_comment": "Bra arbete! Fortsätt så här.",
            "grade": "VG",
            "submission_date": "2024-08-23",
            "school_year": "2024/2025",
        }

        event = NotificationEmailRequestedV1(
            message_id="dict-serialization-test",
            template_id="assignment_feedback",
            to="student@school.se",
            variables=complex_variables,
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Act - JSON round-trip serialization
        json_str = event.model_dump_json()
        json_dict = json.loads(json_str)
        deserialized = NotificationEmailRequestedV1.model_validate(json_dict)

        # Assert - Variables dictionary perfectly preserved
        assert deserialized.variables == complex_variables
        assert deserialized.variables["student_name"] == "Åse Öhrn"
        assert deserialized.variables["assignment_title"] == "Naturvetenskap - Årstidernas påverkan"
        assert deserialized == event


class TestEventEnvelopeIntegrationContracts:
    """Contract tests for EventEnvelope integration with email events."""

    def test_event_envelope_email_sent_wrapping_contract(self) -> None:
        """Contract test: EventEnvelope must properly wrap EmailSentV1 events."""
        # Arrange
        correlation_id = uuid4()
        email_event = EmailSentV1(
            message_id="envelope-test-001",
            provider="envelope-provider",
            sent_at=datetime.now(UTC),
            correlation_id=str(correlation_id),
        )

        # Act - Wrap in EventEnvelope
        envelope = EventEnvelope[EmailSentV1](
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=email_event,
        )

        # Assert - Proper wrapping contract
        assert envelope.event_type == "huleedu.email.sent.v1"
        assert envelope.source_service == "email_service"
        assert envelope.correlation_id == correlation_id
        assert envelope.data == email_event
        assert isinstance(envelope.event_id, UUID)
        assert isinstance(envelope.event_timestamp, datetime)
        assert envelope.schema_version == 1

    def test_event_envelope_email_delivery_failed_wrapping_contract(self) -> None:
        """Contract test: EventEnvelope must properly wrap EmailDeliveryFailedV1 events."""
        # Arrange
        correlation_id = uuid4()
        failure_event = EmailDeliveryFailedV1(
            message_id="envelope-failure-001",
            provider="test-provider",
            failed_at=datetime.now(UTC),
            reason="Test delivery failure for envelope",
            correlation_id=str(correlation_id),
        )

        # Act - Wrap in EventEnvelope
        envelope = EventEnvelope[EmailDeliveryFailedV1](
            event_type="huleedu.email.delivery_failed.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=failure_event,
        )

        # Assert - Proper wrapping with failure event
        assert envelope.data == failure_event
        assert envelope.data.reason == "Test delivery failure for envelope"
        assert envelope.correlation_id == correlation_id

    def test_event_envelope_notification_email_requested_wrapping_contract(self) -> None:
        """Contract test: EventEnvelope must properly wrap NotificationEmailRequestedV1 events."""
        # Arrange
        correlation_id = uuid4()
        notification_event = NotificationEmailRequestedV1(
            message_id="envelope-notification-001",
            template_id="envelope_test_template",
            to="envelope.test@school.se",
            variables={"test_variable": "Envelope integration test"},
            category="system",
            correlation_id=str(correlation_id),
        )

        # Act - Wrap in EventEnvelope
        envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_type="huleedu.email.notification_requested.v1",
            source_service="user_service",  # Typically originates from user service
            correlation_id=correlation_id,
            data=notification_event,
        )

        # Assert - Proper wrapping with notification event
        assert envelope.data == notification_event
        assert envelope.source_service == "user_service"
        assert envelope.event_type == "huleedu.email.notification_requested.v1"

    def test_event_envelope_generic_type_handling_contract(self) -> None:
        """Contract test: EventEnvelope must handle generic type information properly."""
        # Arrange
        correlation_id = uuid4()
        email_event = EmailSentV1(
            message_id="generic-test-001",
            provider="generic-provider",
            sent_at=datetime.now(UTC),
            correlation_id=str(correlation_id),
        )

        envelope = EventEnvelope[EmailSentV1](
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=email_event,
        )

        # Act - Serialize and deserialize (simulating cross-service transmission)
        json_str = envelope.model_dump_json()
        json_dict = json.loads(json_str)

        # Deserialize envelope (data will be dict due to generic type limitations)
        deserialized_envelope: EventEnvelope[Any] = EventEnvelope.model_validate(json_dict)

        # Validate the data field manually (standard pattern for generic deserialization)
        validated_data = EmailSentV1.model_validate(deserialized_envelope.data)

        # Assert - Data field correctly deserializes to original event
        assert validated_data == email_event
        assert validated_data.message_id == "generic-test-001"
        assert validated_data.provider == "generic-provider"
        assert deserialized_envelope.event_type == envelope.event_type
        assert deserialized_envelope.correlation_id == envelope.correlation_id

    def test_event_envelope_metadata_preservation_contract(self) -> None:
        """Contract test: EventEnvelope must preserve metadata across boundaries."""
        # Arrange
        correlation_id = uuid4()
        email_event = EmailSentV1(
            message_id="metadata-test-001",
            provider="metadata-provider",
            sent_at=datetime.now(UTC),
            correlation_id=str(correlation_id),
        )

        metadata = {
            "trace_id": "trace-abc123",
            "span_id": "span-def456",
            "user_id": "user-789",
            "operation": "bulk_email_send",
        }

        envelope = EventEnvelope[EmailSentV1](
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=email_event,
            metadata=metadata,
        )

        # Act - JSON round-trip
        json_str = envelope.model_dump_json()
        deserialized_envelope: EventEnvelope[Any] = EventEnvelope.model_validate_json(json_str)

        # Assert - Metadata perfectly preserved
        assert deserialized_envelope.metadata == metadata
        assert deserialized_envelope.metadata["trace_id"] == "trace-abc123"
        assert deserialized_envelope.metadata["operation"] == "bulk_email_send"

    def test_event_envelope_event_type_format_validation_contract(self) -> None:
        """Contract test: EventEnvelope must validate event type string format."""
        # Arrange - Test various event type formats
        correlation_id = uuid4()
        email_event = EmailSentV1(
            message_id="format-test-001",
            provider="format-provider",
            sent_at=datetime.now(UTC),
            correlation_id=str(correlation_id),
        )

        # Act & Assert - Valid event type formats should work
        valid_formats = [
            "huleedu.email.sent.v1",
            "huleedu.email.delivery_failed.v1",
            "huleedu.email.notification_requested.v1",
            "huleedu.user.notification_email_requested.v1",
        ]

        for event_type in valid_formats:
            envelope = EventEnvelope[EmailSentV1](
                event_type=event_type,
                source_service="email_service",
                correlation_id=correlation_id,
                data=email_event,
            )
            assert envelope.event_type == event_type

    def test_event_envelope_source_service_specification_contract(self) -> None:
        """Contract test: EventEnvelope must specify source service for event routing."""
        # Arrange
        correlation_id = uuid4()
        email_event = EmailSentV1(
            message_id="source-test-001",
            provider="source-provider",
            sent_at=datetime.now(UTC),
            correlation_id=str(correlation_id),
        )

        # Act - Create envelopes with different source services
        services = [
            "email_service",
            "user_service",
            "notification_service",
            "class_management_service",
        ]

        for service in services:
            envelope = EventEnvelope[EmailSentV1](
                event_type="huleedu.email.sent.v1",
                source_service=service,
                correlation_id=correlation_id,
                data=email_event,
            )

            # Assert - Source service correctly specified
            assert envelope.source_service == service

            # Assert - Service specification survives serialization
            json_str = envelope.model_dump_json()
            deserialized: EventEnvelope[Any] = EventEnvelope.model_validate_json(json_str)
            assert deserialized.source_service == service


class TestEmailEventsCrossServiceContracts:
    """Contract tests for email events across service boundaries."""

    def test_email_events_service_boundary_transmission_contract(self) -> None:
        """Contract test: Email events must transmit correctly across service boundaries."""
        # Arrange - Create events that would be transmitted between services
        correlation_id = uuid4()

        # Email request from user service to email service
        request_event = NotificationEmailRequestedV1(
            message_id="boundary-test-001",
            template_id="password_reset",
            to="user@school.se",
            variables={
                "reset_link": "https://huleedu.se/reset?token=abc123",
                "expires_in": "1 timme",
            },
            category="password_reset",
            correlation_id=str(correlation_id),
        )

        # Email sent response from email service
        sent_event = EmailSentV1(
            message_id="boundary-test-001",
            provider="sendgrid",
            sent_at=datetime.now(UTC),
            correlation_id=str(correlation_id),
        )

        # Act - Simulate cross-service transmission via JSON
        request_json = request_event.model_dump_json()
        sent_json = sent_event.model_dump_json()

        # Simulate receiving service deserializing
        received_request = NotificationEmailRequestedV1.model_validate_json(request_json)
        received_sent = EmailSentV1.model_validate_json(sent_json)

        # Assert - Perfect transmission fidelity
        assert received_request == request_event
        assert received_sent == sent_event
        assert received_request.correlation_id == received_sent.correlation_id
        assert received_request.message_id == received_sent.message_id

    def test_email_events_correlation_id_consistency_contract(self) -> None:
        """Contract test: Correlation IDs must remain consistent across related email events."""
        # Arrange - Simulate email flow: request -> sent -> potential failure
        correlation_id = uuid4()
        correlation_str = str(correlation_id)
        message_id = "correlation-flow-test-001"

        # Request event
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="teacher_notification",
            to="teacher@school.se",
            variables={"student_name": "Anna Åberg", "assignment": "Matematik kapitel 5"},
            category="teacher_notification",
            correlation_id=correlation_str,
        )

        # Sent event (successful)
        sent = EmailSentV1(
            message_id=message_id,
            provider="sendgrid",
            sent_at=datetime.now(UTC),
            correlation_id=correlation_str,
        )

        # Failure event (alternative outcome)
        failed = EmailDeliveryFailedV1(
            message_id=message_id,
            provider="sendgrid",
            failed_at=datetime.now(UTC) + timedelta(minutes=5),
            reason="Recipient mailbox full",
            correlation_id=correlation_str,
        )

        # Act - Verify correlation ID consistency across events
        events = [request, sent, failed]

        # Assert - All events share the same correlation ID
        for event in events:
            assert event.correlation_id == correlation_str  # type: ignore[attr-defined] # All events have this attr
            assert event.message_id == message_id  # type: ignore[attr-defined] # All events have this attr

        # Assert - Correlation ID survives JSON serialization for all events
        for event in events:
            json_str = event.model_dump_json()
            event_type = type(event)
            deserialized = event_type.model_validate_json(json_str)
            assert deserialized.correlation_id == correlation_str  # type: ignore[attr-defined] # All events have this attr

    def test_email_events_envelope_integration_full_flow_contract(self) -> None:
        """Contract test: Full email event flow integration with EventEnvelope."""
        # Arrange - Complete email notification flow
        correlation_id = uuid4()
        message_id = "full-flow-test-001"

        # Step 1: Notification request wrapped in envelope
        request_event = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="assignment_reminder",
            to="student@school.se",
            variables={
                "student_name": "Erik Öberg",
                "assignment_title": "Svenska uppsats om årstider",
                "due_date": "2024-09-01",
                "teacher_name": "Maria Lindström",
            },
            category="system",
            correlation_id=str(correlation_id),
        )

        request_envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_type="huleedu.email.notification_requested.v1",
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=request_event,
            metadata={"operation": "assignment_reminder_batch", "batch_id": "batch-2024-08-23"},
        )

        # Step 2: Email sent response wrapped in envelope
        sent_event = EmailSentV1(
            message_id=message_id,
            provider="sendgrid",
            sent_at=datetime.now(UTC),
            correlation_id=str(correlation_id),
        )

        sent_envelope = EventEnvelope[EmailSentV1](
            event_type="huleedu.email.sent.v1",
            source_service="email_service",
            correlation_id=correlation_id,
            data=sent_event,
            metadata={"provider_message_id": "sg-msg-abc123", "send_duration_ms": 245},
        )

        # Act - Simulate full cross-service flow via JSON
        request_json = request_envelope.model_dump_json()
        sent_json = sent_envelope.model_dump_json()

        # Deserialize as receiving services would
        received_request_envelope: EventEnvelope[Any] = EventEnvelope.model_validate_json(
            request_json
        )
        received_sent_envelope: EventEnvelope[Any] = EventEnvelope.model_validate_json(sent_json)

        # Validate data fields manually (standard generic deserialization pattern)
        received_request_data = NotificationEmailRequestedV1.model_validate(
            received_request_envelope.data
        )
        received_sent_data = EmailSentV1.model_validate(received_sent_envelope.data)

        # Assert - Complete flow integrity
        assert received_request_envelope.correlation_id == correlation_id
        assert received_sent_envelope.correlation_id == correlation_id
        assert received_request_data.message_id == message_id
        assert received_sent_data.message_id == message_id
        assert received_request_data.variables["student_name"] == "Erik Öberg"
        assert received_request_envelope.metadata is not None
        assert received_request_envelope.metadata["batch_id"] == "batch-2024-08-23"
        assert received_sent_envelope.metadata is not None
        assert received_sent_envelope.metadata["provider_message_id"] == "sg-msg-abc123"
