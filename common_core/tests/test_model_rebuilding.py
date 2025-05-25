"""
Test module to validate Pydantic model rebuilding.

This test ensures that all Pydantic models in common_core can be rebuilt
successfully, which is critical for forward reference resolution.
"""

from __future__ import annotations

from common_core.events.base_event_models import (
    BaseEventData,
    EnhancedProcessingUpdate,
    EventTracker,
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
        EnhancedProcessingUpdate.model_rebuild(raise_errors=True)
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
        from common_core.enums import EssayStatus, ProcessingEvent, ProcessingStage

        # Create an instance to ensure forward references are resolved
        entity_ref = EntityReference(
            entity_id="test-id", entity_type="essay", parent_id="parent-id"
        )

        system_meta = SystemProcessingMetadata(
            entity=entity_ref,
            event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            processing_stage=ProcessingStage.PENDING,
        )

        # Create an EnhancedProcessingUpdate with Union status
        update = EnhancedProcessingUpdate(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            entity_ref=entity_ref,
            status=EssayStatus.AWAITING_SPELLCHECK,  # This uses the Union type
            system_metadata=system_meta,
        )

        # Validate that the model was created successfully
        assert update.status == EssayStatus.AWAITING_SPELLCHECK
        assert update.entity_ref.entity_id == "test-id"
