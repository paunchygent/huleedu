"""
Test module to validate Pydantic model rebuilding.

This test ensures that all Pydantic models in common_core can be rebuilt
successfully, which is critical for forward reference resolution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from common_core.enums import ProcessingEvent
from common_core.events.base_event_models import (
    BaseEventData,
    EventTracker,
    ProcessingUpdate,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckRequestedDataV1,
    SpellcheckResultDataV1,
)
from common_core.metadata_models import (
    EntityReference,
    SystemProcessingMetadata,
)


class TestModelRebuilding:
    """Test that all Pydantic models can be rebuilt successfully."""

    def test_base_event_models_rebuild(self) -> None:
        """Test that base event models can be rebuilt without errors."""
        # These should not raise any exceptions
        BaseEventData.model_rebuild(raise_errors=True)
        ProcessingUpdate.model_rebuild(raise_errors=True)
        EventTracker.model_rebuild(raise_errors=True)

    def test_spellcheck_models_rebuild(self) -> None:
        """Test that spellcheck models can be rebuilt without errors."""
        # These should not raise any exceptions
        SpellcheckRequestedDataV1.model_rebuild(raise_errors=True)
        SpellcheckResultDataV1.model_rebuild(raise_errors=True)

    def test_envelope_model_rebuild(self) -> None:
        """Test that EventEnvelope can be rebuilt without errors."""
        # This should not raise any exceptions
        EventEnvelope.model_rebuild(raise_errors=True)

    def test_metadata_models_rebuild(self) -> None:
        """Test that metadata models can be rebuilt without errors."""
        # These should not raise any exceptions
        EntityReference.model_rebuild(raise_errors=True)
        SystemProcessingMetadata.model_rebuild(raise_errors=True)

    def test_forward_references_resolved(self) -> None:
        """Test that forward references in models are properly resolved."""
        # This test validates that Union types and enum forward references work
        from common_core.enums import EssayStatus, ProcessingStage

        # Create an instance to ensure forward references are resolved
        entity_ref = EntityReference(
            entity_id="test-id", entity_type="essay", parent_id="parent-id"
        )

        system_meta = SystemProcessingMetadata(
            entity=entity_ref,
            event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            processing_stage=ProcessingStage.PENDING,
        )

        # Create a ProcessingUpdate with Union status
        update = ProcessingUpdate(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            entity_ref=entity_ref,
            status=EssayStatus.AWAITING_SPELLCHECK,  # This uses the Union type
            system_metadata=system_meta,
        )

        # Validate that the model was created successfully
        assert update.status == EssayStatus.AWAITING_SPELLCHECK
        assert update.entity_ref.entity_id == "test-id"


class TestEventEnvelopeSchemaVersion:
    """Tests for the schema_version field in EventEnvelope."""

    def test_schema_version_roundtrip(self) -> None:
        """Test default value, serialization, and deserialization of schema_version."""
        import json

        from common_core.events.envelope import EventEnvelope

        # Dummy data for the envelope
        dummy_data = BaseEventData(
            event_name=ProcessingEvent.PROCESSING_STARTED,
            entity_ref=EntityReference(entity_id="test_entity", entity_type="test"),
        )

        # 1. Test default value upon creation
        envelope_new = EventEnvelope[BaseEventData](
            event_type="test.event.v1", source_service="test_service", data=dummy_data
        )
        assert envelope_new.schema_version == 1

        # 2. Test serialization to JSON
        envelope_json = envelope_new.model_dump_json()
        envelope_dict_from_json = json.loads(envelope_json)
        assert "schema_version" in envelope_dict_from_json
        assert envelope_dict_from_json["schema_version"] == 1

        # 3. Test deserialization from JSON (with schema_version present)
        envelope_from_json = EventEnvelope[BaseEventData].model_validate_json(envelope_json)
        assert envelope_from_json.schema_version == 1

        # 4. Test deserialization from an old payload (dict) without schema_version
        old_payload_dict = {
            "event_id": str(uuid4()),
            "event_type": "test.oldevent.v1",
            "event_timestamp": datetime.now(timezone.utc).isoformat(),
            "source_service": "old_service",
            "data": dummy_data.model_dump(),  # Pydantic will handle parsing this to BaseEventData
        }
        envelope_from_old_payload = EventEnvelope[BaseEventData].model_validate(old_payload_dict)
        assert envelope_from_old_payload.schema_version == 1, (
            "Schema version should default to 1 when parsing an old payload without it."
        )
