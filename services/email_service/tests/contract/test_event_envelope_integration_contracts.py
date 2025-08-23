"""
Event Envelope Integration Contract Testing for Email Service.

This module provides comprehensive contract tests for EventEnvelope integration
with email events and cross-service contract validation to ensure proper
event-driven architecture compliance in the HuleEdu platform.

Following ULTRATHINK methodology for event envelope and service boundary validation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from common_core.emailing_models import (
    EmailDeliveryFailedV1,
    EmailSentV1,
    NotificationEmailRequestedV1,
)
from common_core.events.envelope import EventEnvelope


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
