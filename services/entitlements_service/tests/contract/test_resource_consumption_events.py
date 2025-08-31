"""
Contract compliance tests for ResourceConsumptionV1 event serialization/deserialization.

These tests verify that the ResourceConsumptionV1 event model properly validates,
serializes, and deserializes event contracts for inter-service communication.
Tests cover field validation, JSON roundtrip behavior, EventEnvelope integration,
and Swedish character preservation for the educational domain.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from pydantic import ValidationError


class TestResourceConsumptionV1Contract:
    """Test the ResourceConsumptionV1 Pydantic model contract."""

    def test_resource_consumption_v1_full_model(self) -> None:
        """Test ResourceConsumptionV1 with all fields populated."""
        # Arrange
        test_timestamp = datetime.now(UTC)

        # Act
        event = ResourceConsumptionV1(
            entity_id="batch-123",
            entity_type="batch",
            user_id="user-456",
            org_id="org-789",
            resource_type="cj_comparison",
            quantity=5,
            service_name="cj-assessment-service",
            processing_id="proc-abc-123",
            consumed_at=test_timestamp,
        )

        # Assert
        assert event.entity_id == "batch-123"
        assert event.entity_type == "batch"
        assert event.user_id == "user-456"
        assert event.org_id == "org-789"
        assert event.resource_type == "cj_comparison"
        assert event.quantity == 5
        assert event.service_name == "cj-assessment-service"
        assert event.processing_id == "proc-abc-123"
        assert event.consumed_at == test_timestamp
        assert event.event_name == ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED

    def test_resource_consumption_v1_minimal_model(self) -> None:
        """Test ResourceConsumptionV1 with only required fields."""
        # Act
        event = ResourceConsumptionV1(
            user_id="user-123",
            resource_type="ai_feedback_generation",
            quantity=1,
            service_name="nlp-service",
            processing_id="proc-def-456",
        )

        # Assert required fields
        assert event.user_id == "user-123"
        assert event.resource_type == "ai_feedback_generation"
        assert event.quantity == 1
        assert event.service_name == "nlp-service"
        assert event.processing_id == "proc-def-456"

        # Assert optional fields
        assert event.org_id is None
        assert event.entity_id is None
        assert event.entity_type is None

        # Assert defaults
        assert event.event_name == ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED
        assert isinstance(event.consumed_at, datetime)
        assert isinstance(event.timestamp, datetime)

    @pytest.mark.parametrize(
        "user_id, org_id, resource_type, quantity, service_name, processing_id, expected_valid",
        [
            # Valid cases - all string fields allow empty values
            ("user-123", None, "metric", 1, "service", "proc-1", True),
            ("user-456", "org-789", "metric", 0, "service", "proc-2", True),
            ("user-åäö", "org-ÅÄÖ", "metric", 999, "service", "proc-3", True),
            # Empty strings are allowed by the current contract
            ("", None, "metric", 1, "service", "proc-4", True),
            ("user-123", None, "", 1, "service", "proc-5", True),
            ("user-123", None, "metric", 1, "", "proc-7", True),
            ("user-123", None, "metric", 1, "service", "", True),
            # Invalid cases - only quantity constraints are enforced
            ("user-123", None, "metric", -1, "service", "proc-6", False),  # negative quantity
        ],
    )
    def test_resource_consumption_v1_field_validation(
        self,
        user_id: str,
        org_id: str | None,
        resource_type: str,
        quantity: int,
        service_name: str,
        processing_id: str,
        expected_valid: bool,
    ) -> None:
        """Test field validation constraints for ResourceConsumptionV1."""
        if expected_valid:
            # Should not raise ValidationError
            event = ResourceConsumptionV1(
                user_id=user_id,
                org_id=org_id,
                resource_type=resource_type,
                quantity=quantity,
                service_name=service_name,
                processing_id=processing_id,
            )
            assert event.user_id == user_id
            assert event.org_id == org_id
            assert event.resource_type == resource_type
            assert event.quantity == quantity
            assert event.service_name == service_name
            assert event.processing_id == processing_id
        else:
            # Should raise ValidationError
            with pytest.raises(ValidationError):
                ResourceConsumptionV1(
                    user_id=user_id,
                    org_id=org_id,
                    resource_type=resource_type,
                    quantity=quantity,
                    service_name=service_name,
                    processing_id=processing_id,
                )

    def test_resource_consumption_v1_quantity_constraints(self) -> None:
        """Test quantity field constraints (non-negative integer)."""
        # Valid quantities
        valid_quantities = [0, 1, 10, 100, 9999]
        for quantity in valid_quantities:
            event = ResourceConsumptionV1(
                user_id="user-123",
                resource_type="test_metric",
                quantity=quantity,
                service_name="test-service",
                processing_id="proc-123",
            )
            assert event.quantity == quantity

        # Invalid quantities
        invalid_quantities = [-1, -10, -999]
        for quantity in invalid_quantities:
            with pytest.raises(ValidationError):
                ResourceConsumptionV1(
                    user_id="user-123",
                    resource_type="test_metric",
                    quantity=quantity,
                    service_name="test-service",
                    processing_id="proc-123",
                )

    def test_resource_consumption_v1_serialization_roundtrip(self) -> None:
        """Test serialization and deserialization roundtrip."""
        # Arrange
        original_timestamp = datetime.now(UTC)
        original = ResourceConsumptionV1(
            entity_id="batch-roundtrip",
            entity_type="batch",
            user_id="user-roundtrip-123",
            org_id="org-roundtrip-456",
            resource_type="roundtrip_metric",
            quantity=42,
            service_name="roundtrip-service",
            processing_id="proc-roundtrip-789",
            consumed_at=original_timestamp,
        )

        # Act - Serialize and deserialize
        serialized = original.model_dump(mode="json")
        json_str = json.dumps(serialized)
        parsed = json.loads(json_str)
        reconstructed = ResourceConsumptionV1.model_validate(parsed)

        # Assert
        assert reconstructed.entity_id == original.entity_id
        assert reconstructed.entity_type == original.entity_type
        assert reconstructed.user_id == original.user_id
        assert reconstructed.org_id == original.org_id
        assert reconstructed.resource_type == original.resource_type
        assert reconstructed.quantity == original.quantity
        assert reconstructed.service_name == original.service_name
        assert reconstructed.processing_id == original.processing_id
        assert reconstructed.consumed_at == original.consumed_at
        assert reconstructed.event_name == original.event_name

    @pytest.mark.parametrize(
        "user_id, org_id, expected_user, expected_org",
        [
            # Standard ASCII characters
            ("user_standard", "org_standard", "user_standard", "org_standard"),
            # Swedish characters - should survive serialization
            ("användare_åäö", "organisation_ÅÄÖ", "användare_åäö", "organisation_ÅÄÖ"),
            ("lärare_öberg", "skola_åström", "lärare_öberg", "skola_åström"),
            ("elev_ängström", None, "elev_ängström", None),
            # Mixed characters
            ("user_åäö_123", "org_ÅÄÖ_456", "user_åäö_123", "org_ÅÄÖ_456"),
            # Special educational terms in Swedish
            (
                "lärare_språkvetenskap",
                "högskola_göteborg",
                "lärare_språkvetenskap",
                "högskola_göteborg",
            ),
        ],
    )
    def test_resource_consumption_v1_swedish_characters(
        self,
        user_id: str,
        org_id: str | None,
        expected_user: str,
        expected_org: str | None,
    ) -> None:
        """Test Swedish characters survive JSON serialization for educational domain."""
        # Arrange & Act
        original = ResourceConsumptionV1(
            user_id=user_id,
            org_id=org_id,
            resource_type="språkanalys",
            quantity=1,
            service_name="språkprocessor-tjänst",
            processing_id="bearbetning-åäö-123",
        )

        # Serialize through JSON (simulating Kafka transport)
        json_data = json.dumps(original.model_dump(mode="json"), ensure_ascii=False)
        parsed_data = json.loads(json_data)
        reconstructed = ResourceConsumptionV1.model_validate(parsed_data)

        # Assert Swedish characters preserved
        assert reconstructed.user_id == expected_user
        assert reconstructed.org_id == expected_org
        assert reconstructed.resource_type == "språkanalys"
        assert reconstructed.service_name == "språkprocessor-tjänst"
        assert reconstructed.processing_id == "bearbetning-åäö-123"


class TestResourceConsumptionV1EventEnvelopeIntegration:
    """Test ResourceConsumptionV1 integration with EventEnvelope."""

    def test_event_envelope_with_resource_consumption_v1(self) -> None:
        """Test EventEnvelope containing ResourceConsumptionV1."""
        # Arrange
        resource_event = ResourceConsumptionV1(
            entity_id="batch-envelope-123",
            entity_type="batch",
            user_id="user-envelope-456",
            org_id="org-envelope-789",
            resource_type="envelope_test_metric",
            quantity=7,
            service_name="envelope-test-service",
            processing_id="proc-envelope-abc",
        )

        correlation_id = uuid4()

        # Act
        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.reported.v1",
            source_service="test-service",
            correlation_id=correlation_id,
            data=resource_event,
        )

        # Assert
        assert envelope.event_type == "huleedu.resource.consumption.reported.v1"
        assert envelope.source_service == "test-service"
        assert envelope.correlation_id == correlation_id
        assert isinstance(envelope.data, ResourceConsumptionV1)
        assert envelope.data.user_id == "user-envelope-456"
        assert envelope.data.quantity == 7

    def test_event_envelope_serialization_roundtrip(self) -> None:
        """Test EventEnvelope[ResourceConsumptionV1] serialization roundtrip."""
        # Arrange
        resource_event = ResourceConsumptionV1(
            entity_id="batch-serial-123",
            entity_type="batch",
            user_id="användare_serialtest",
            org_id="skola_serialtest",
            resource_type="serialisering_test",
            quantity=13,
            service_name="serialisering-tjänst",
            processing_id="proc-serial-xyz",
        )

        original_envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.reported.v1",
            source_service="serialization-test-service",
            correlation_id=uuid4(),
            data=resource_event,
        )

        # Act - Simulate Kafka serialization
        serialized = json.dumps(
            original_envelope.model_dump(mode="json"), ensure_ascii=False
        ).encode("utf-8")
        parsed = json.loads(serialized.decode("utf-8"))
        reconstructed = EventEnvelope[ResourceConsumptionV1].model_validate(parsed)

        # Assert envelope structure
        assert reconstructed.event_type == original_envelope.event_type
        assert reconstructed.source_service == original_envelope.source_service
        assert reconstructed.correlation_id == original_envelope.correlation_id
        assert reconstructed.event_id == original_envelope.event_id

        # Assert data structure with Swedish characters preserved
        typed_data = ResourceConsumptionV1.model_validate(reconstructed.data)
        assert typed_data.user_id == "användare_serialtest"
        assert typed_data.org_id == "skola_serialtest"
        assert typed_data.resource_type == "serialisering_test"
        assert typed_data.quantity == 13
        assert typed_data.service_name == "serialisering-tjänst"
        assert typed_data.processing_id == "proc-serial-xyz"

    def test_event_envelope_with_minimal_resource_consumption(self) -> None:
        """Test EventEnvelope with minimal ResourceConsumptionV1 (no org_id)."""
        # Arrange
        minimal_event = ResourceConsumptionV1(
            user_id="minimal-user-123",
            resource_type="minimal_metric",
            quantity=1,
            service_name="minimal-service",
            processing_id="proc-minimal-123",
        )

        # Act
        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.reported.v1",
            source_service="minimal-test-service",
            data=minimal_event,
        )

        # Serialize and deserialize
        json_data = json.dumps(envelope.model_dump(mode="json"))
        parsed = json.loads(json_data)
        reconstructed = EventEnvelope[ResourceConsumptionV1].model_validate(parsed)

        # Assert
        typed_data = ResourceConsumptionV1.model_validate(reconstructed.data)
        assert typed_data.user_id == "minimal-user-123"
        assert typed_data.org_id is None
        assert typed_data.resource_type == "minimal_metric"
        assert typed_data.quantity == 1

    @pytest.mark.parametrize(
        "resource_type, service_name, expected_resource, expected_service",
        [
            # Standard metrics
            ("cj_comparison", "cj-assessment-service", "cj_comparison", "cj-assessment-service"),
            ("ai_feedback_generation", "nlp-service", "ai_feedback_generation", "nlp-service"),
            ("spell_check", "spell-checker-service", "spell_check", "spell-checker-service"),
            # Swedish educational metrics
            ("språkgranskning", "språk-tjänst", "språkgranskning", "språk-tjänst"),
            (
                "bedömning_komparativ",
                "bedömning-tjänst",
                "bedömning_komparativ",
                "bedömning-tjänst",
            ),
            ("textanalys_djup", "analys-motor", "textanalys_djup", "analys-motor"),
        ],
    )
    def test_event_envelope_metric_types_serialization(
        self,
        resource_type: str,
        service_name: str,
        expected_resource: str,
        expected_service: str,
    ) -> None:
        """Test various metric types in EventEnvelope serialization."""
        # Arrange
        event = ResourceConsumptionV1(
            user_id="test-metrics-user",
            resource_type=resource_type,
            quantity=5,
            service_name=service_name,
            processing_id="proc-metrics-test",
        )

        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.reported.v1",
            source_service=service_name,
            data=event,
        )

        # Act - JSON roundtrip
        json_str = json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False)
        parsed = json.loads(json_str)
        reconstructed = EventEnvelope[ResourceConsumptionV1].model_validate(parsed)

        # Assert
        typed_data = ResourceConsumptionV1.model_validate(reconstructed.data)
        assert typed_data.resource_type == expected_resource
        assert typed_data.service_name == expected_service
        assert envelope.source_service == expected_service
