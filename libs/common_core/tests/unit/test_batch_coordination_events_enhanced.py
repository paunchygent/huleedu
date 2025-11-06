"""Enhanced unit tests for batch coordination events with comprehensive validation."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.events.batch_coordination_events import (
    BatchEssaysReady,
)
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)


class TestEnhancedBatchEssaysReadyLean:
    """Test suite for enhanced BatchEssaysReady with lean registration fields."""

    @pytest.fixture
    def sample_metadata(self) -> SystemProcessingMetadata:
        """Fixture providing sample processing metadata."""
        return SystemProcessingMetadata(
            entity_id="test_entity",
            entity_type="batch",
            timestamp=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_ready_essays(self) -> list[EssayProcessingInputRefV1]:
        """Fixture providing sample ready essays."""
        return [
            EssayProcessingInputRefV1(essay_id="essay_001", text_storage_id="content_123"),
            EssayProcessingInputRefV1(essay_id="essay_002", text_storage_id="content_456"),
            EssayProcessingInputRefV1(essay_id="essay_003", text_storage_id="content_789"),
        ]

    def test_lean_batch_ready_regular_class(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test BatchEssaysReady with REGULAR class type."""
        prompt_ref = StorageReferenceMetadata()
        prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, "prompt_123")

        event = BatchEssaysReady(
            batch_id="batch_regular",
            ready_essays=sample_ready_essays,
            metadata=sample_metadata,
            # Lean registration fields from BOS
            course_code=CourseCode.ENG5,
            course_language="en",
            student_prompt_ref=prompt_ref,
            # Educational context from Class Management Service
            class_type="REGULAR",
        )

        assert event.batch_id == "batch_regular"
        assert event.course_code == CourseCode.ENG5
        assert event.course_language == "en"
        assert event.class_type == "REGULAR"
        assert len(event.ready_essays) == 3

    def test_lean_batch_ready_guest_class(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test BatchEssaysReady with GUEST class type."""
        prompt_ref = StorageReferenceMetadata()
        prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, "prompt_sv")

        event = BatchEssaysReady(
            batch_id="batch_guest",
            ready_essays=sample_ready_essays,
            metadata=sample_metadata,
            # Lean registration fields from BOS
            course_code=CourseCode.SV1,
            course_language="sv",
            student_prompt_ref=prompt_ref,
            # Educational context
            class_type="GUEST",
        )

        assert event.batch_id == "batch_guest"
        assert event.course_code == CourseCode.SV1
        assert event.course_language == "sv"
        assert event.class_type == "GUEST"

    def test_lean_batch_ready_serialization_roundtrip(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test BatchEssaysReady serialization and deserialization with lean registration fields."""
        prompt_ref = StorageReferenceMetadata()
        prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, "prompt_serialized")

        event = BatchEssaysReady(
            batch_id="batch_serialization",
            ready_essays=sample_ready_essays,
            metadata=sample_metadata,
            # Lean registration fields from BOS
            course_code=CourseCode.ENG6,
            course_language="en",
            student_prompt_ref=prompt_ref,
            # Educational context from Class Management Service
            class_type="REGULAR",
        )

        # Test serialization
        json_data = event.model_dump_json()
        assert isinstance(json_data, str)

        # Test deserialization
        data_dict = json.loads(json_data)
        reconstructed_event = BatchEssaysReady.model_validate(data_dict)

        # Verify lean registration fields
        assert data_dict["course_code"] == CourseCode.ENG6.value
        assert data_dict["course_language"] == "en"
        assert data_dict["class_type"] == "REGULAR"

        # Verify all fields match after reconstruction
        assert reconstructed_event.batch_id == event.batch_id
        assert reconstructed_event.course_code == event.course_code
        assert reconstructed_event.course_language == event.course_language
        assert reconstructed_event.class_type == event.class_type
