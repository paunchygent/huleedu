"""
Unit tests for enhanced batch coordination event models with lean registration support.

Tests the enhanced BatchEssaysReady event model with new required fields
for the lean registration refactoring.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from common_core.enums import CourseCode
from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)


class TestEnhancedBatchEssaysReadyLean:
    """Test suite for enhanced BatchEssaysReady with lean registration fields."""

    @pytest.fixture
    def sample_metadata(self) -> SystemProcessingMetadata:
        """Fixture providing sample processing metadata."""
        return SystemProcessingMetadata(
            entity=EntityReference(entity_id="test_entity", entity_type="batch"),
            timestamp=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_batch_entity(self) -> EntityReference:
        """Fixture providing sample batch entity reference."""
        return EntityReference(entity_id="batch_123", entity_type="batch")

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
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test BatchEssaysReady with REGULAR class type and teacher names."""
        event = BatchEssaysReady(
            batch_id="batch_regular",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            # Lean registration fields from BOS
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Write about your role model",
            # Educational context from Class Management Service
            class_type="REGULAR",
            teacher_first_name="Emma",
            teacher_last_name="Johnson",
        )

        assert event.batch_id == "batch_regular"
        assert event.course_code == CourseCode.ENG5
        assert event.course_language == "en"
        assert event.class_type == "REGULAR"
        assert event.teacher_first_name == "Emma"
        assert event.teacher_last_name == "Johnson"
        assert len(event.ready_essays) == 3

    def test_lean_batch_ready_guest_class(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test BatchEssaysReady with GUEST class type (no teacher names)."""
        event = BatchEssaysReady(
            batch_id="batch_guest",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            # Lean registration fields from BOS
            course_code=CourseCode.SV1,
            course_language="sv",
            essay_instructions="Skriv om din förebild",
            # Educational context - GUEST class has no teacher names
            class_type="GUEST",
            teacher_first_name=None,
            teacher_last_name=None,
        )

        assert event.batch_id == "batch_guest"
        assert event.course_code == CourseCode.SV1
        assert event.course_language == "sv"
        assert event.class_type == "GUEST"
        assert event.teacher_first_name is None
        assert event.teacher_last_name is None

    def test_lean_batch_ready_serialization_roundtrip(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test BatchEssaysReady serialization and deserialization with lean registration fields."""
        event = BatchEssaysReady(
            batch_id="batch_serialization",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            # Lean registration fields from BOS
            course_code=CourseCode.ENG6,
            course_language="en",
            essay_instructions="Analyze the character development in your chosen novel",
            # Educational context from Class Management Service
            class_type="REGULAR",
            teacher_first_name="Michael",
            teacher_last_name="Thompson",
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
        assert data_dict["teacher_first_name"] == "Michael"
        assert data_dict["teacher_last_name"] == "Thompson"

        # Verify all fields match after reconstruction
        assert reconstructed_event.batch_id == event.batch_id
        assert reconstructed_event.course_code == event.course_code
        assert reconstructed_event.course_language == event.course_language
        assert reconstructed_event.class_type == event.class_type
        assert reconstructed_event.teacher_first_name == event.teacher_first_name
        assert reconstructed_event.teacher_last_name == event.teacher_last_name
