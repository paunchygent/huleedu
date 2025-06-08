"""
Unit tests for enhanced batch coordination event models.

Tests the enhanced BatchEssaysReady event model with validation failure support
for Phase 6 of the File Service validation improvements.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)


class TestEnhancedBatchEssaysReady:
    """Test suite for enhanced BatchEssaysReady event model with validation failure support."""

    @pytest.fixture
    def sample_metadata(self) -> SystemProcessingMetadata:
        """Fixture providing sample processing metadata."""
        return SystemProcessingMetadata(
            entity=EntityReference(entity_id="test_entity", entity_type="batch"),
            timestamp=datetime.now(timezone.utc),
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

    @pytest.fixture
    def sample_validation_failures(self) -> list[EssayValidationFailedV1]:
        """Fixture providing sample validation failures."""
        return [
            EssayValidationFailedV1(
                batch_id="batch_123",
                original_file_name="empty_essay.txt",
                validation_error_code="EMPTY_CONTENT",
                validation_error_message="File content is empty",
                file_size_bytes=0,
            ),
            EssayValidationFailedV1(
                batch_id="batch_123",
                original_file_name="too_short.docx",
                validation_error_code="CONTENT_TOO_SHORT",
                validation_error_message="Content below minimum length",
                file_size_bytes=25,
            ),
        ]

    def test_basic_batch_ready_without_validation_failures(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test basic BatchEssaysReady creation without validation failures."""
        event = BatchEssaysReady(
            batch_id="batch_123",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
        )

        assert event.batch_id == "batch_123"
        assert len(event.ready_essays) == 3
        assert event.validation_failures is None
        assert event.total_files_processed is None
        assert event.event == "batch.essays.ready"

    def test_batch_ready_with_validation_failures(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
        sample_validation_failures: list[EssayValidationFailedV1],
    ) -> None:
        """Test BatchEssaysReady with validation failures included."""
        event = BatchEssaysReady(
            batch_id="batch_123",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            validation_failures=sample_validation_failures,
            total_files_processed=5,
        )

        assert event.batch_id == "batch_123"
        assert len(event.ready_essays) == 3
        assert event.validation_failures is not None
        assert len(event.validation_failures) == 2
        assert event.total_files_processed == 5

        # Verify validation failure content
        failures = event.validation_failures
        assert failures[0].validation_error_code == "EMPTY_CONTENT"
        assert failures[1].validation_error_code == "CONTENT_TOO_SHORT"

    def test_serialization_with_validation_failures(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
        sample_validation_failures: list[EssayValidationFailedV1],
    ) -> None:
        """Test serialization of enhanced BatchEssaysReady with validation failures."""
        event = BatchEssaysReady(
            batch_id="batch_serialize",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            validation_failures=sample_validation_failures,
            total_files_processed=5,
        )

        # Serialize to JSON
        json_data = event.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back and verify
        data_dict = json.loads(json_data)
        reconstructed = BatchEssaysReady.model_validate(data_dict)

        assert reconstructed.batch_id == event.batch_id
        assert len(reconstructed.ready_essays) == len(event.ready_essays)
        assert reconstructed.total_files_processed == event.total_files_processed
        assert reconstructed.validation_failures is not None
        assert event.validation_failures is not None
        assert len(reconstructed.validation_failures) == len(event.validation_failures)

    def test_real_world_24_of_25_scenario(
        self, sample_batch_entity: EntityReference, sample_metadata: SystemProcessingMetadata
    ) -> None:
        """Test the real-world scenario: 24 successful essays, 1 validation failure."""
        # Create 24 successful essays
        ready_essays = [
            EssayProcessingInputRefV1(essay_id=f"essay_{i:03d}", text_storage_id=f"content_{i:03d}")
            for i in range(1, 25)  # 24 essays
        ]

        # Create 1 validation failure
        validation_failures = [
            EssayValidationFailedV1(
                batch_id="batch_24_of_25",
                original_file_name="corrupted_essay_25.pdf",
                validation_error_code="CONTENT_TOO_SHORT",
                validation_error_message="Essay content below minimum threshold",
                file_size_bytes=15,
            )
        ]

        event = BatchEssaysReady(
            batch_id="batch_24_of_25",
            ready_essays=ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            validation_failures=validation_failures,
            total_files_processed=25,
        )

        # Verify the scenario
        assert len(event.ready_essays) == 24
        assert event.validation_failures is not None
        assert len(event.validation_failures) == 1
        assert event.total_files_processed == 25

        # This should allow BOS to proceed with 24 essays instead of failing the entire batch
        assert event.ready_essays[0].essay_id == "essay_001"
        assert event.ready_essays[-1].essay_id == "essay_024"

    def test_all_essays_failed_validation_scenario(
        self, sample_batch_entity: EntityReference, sample_metadata: SystemProcessingMetadata
    ) -> None:
        """Test scenario where all essays failed validation."""
        validation_failures = [
            EssayValidationFailedV1(
                batch_id="batch_all_failed",
                original_file_name=f"corrupted_{i}.txt",
                validation_error_code="EMPTY_CONTENT",
                validation_error_message="Empty file content",
                file_size_bytes=0,
            )
            for i in range(1, 6)  # 5 failed essays
        ]

        event = BatchEssaysReady(
            batch_id="batch_all_failed",
            ready_essays=[],  # No successful essays
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            validation_failures=validation_failures,
            total_files_processed=5,
        )

        assert len(event.ready_essays) == 0
        assert event.validation_failures is not None
        assert len(event.validation_failures) == 5
        assert event.total_files_processed == 5

    def test_batch_ready_metrics_calculation(
        self, sample_batch_entity: EntityReference, sample_metadata: SystemProcessingMetadata
    ) -> None:
        """Test that total_files_processed accurately reflects successful + failed counts."""
        ready_essays = [
            EssayProcessingInputRefV1(essay_id="essay_001", text_storage_id="content_001"),
            EssayProcessingInputRefV1(essay_id="essay_002", text_storage_id="content_002"),
            EssayProcessingInputRefV1(essay_id="essay_003", text_storage_id="content_003"),
        ]

        validation_failures = [
            EssayValidationFailedV1(
                batch_id="batch_metrics",
                original_file_name="failed_1.txt",
                validation_error_code="CONTENT_TOO_SHORT",
                validation_error_message="Too short",
                file_size_bytes=10,
            ),
            EssayValidationFailedV1(
                batch_id="batch_metrics",
                original_file_name="failed_2.txt",
                validation_error_code="EMPTY_CONTENT",
                validation_error_message="Empty",
                file_size_bytes=0,
            ),
        ]

        event = BatchEssaysReady(
            batch_id="batch_metrics",
            ready_essays=ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            validation_failures=validation_failures,
            total_files_processed=5,  # 3 successful + 2 failed
        )

        # Verify metrics
        successful_count = len(event.ready_essays)
        failed_count = len(event.validation_failures) if event.validation_failures else 0
        total_calculated = successful_count + failed_count

        assert successful_count == 3
        assert failed_count == 2
        assert total_calculated == 5
        assert event.total_files_processed == 5

    def test_backward_compatibility(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test that enhanced model is backward compatible with existing code."""
        # Create event without new fields (old behavior)
        event = BatchEssaysReady(
            batch_id="batch_compat",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
        )

        # Should work without validation_failures and total_files_processed
        assert event.validation_failures is None
        assert event.total_files_processed is None
        assert len(event.ready_essays) == 3

        # Should serialize/deserialize without issues
        json_data = event.model_dump_json()
        reconstructed = BatchEssaysReady.model_validate(json.loads(json_data))
        assert reconstructed.batch_id == event.batch_id

    def test_empty_validation_failures_list(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test handling of empty validation failures list."""
        event = BatchEssaysReady(
            batch_id="batch_empty_failures",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            validation_failures=[],  # Empty list instead of None
            total_files_processed=3,
        )

        assert event.validation_failures == []
        assert event.total_files_processed == 3
        assert len(event.ready_essays) == 3

    def test_validation_failure_correlation_ids(
        self,
        sample_ready_essays: list[EssayProcessingInputRefV1],
        sample_batch_entity: EntityReference,
        sample_metadata: SystemProcessingMetadata,
    ) -> None:
        """Test that validation failures preserve correlation IDs for tracing."""
        correlation_id_1 = uuid4()
        correlation_id_2 = uuid4()

        validation_failures = [
            EssayValidationFailedV1(
                batch_id="batch_correlation",
                original_file_name="file1.txt",
                validation_error_code="EMPTY_CONTENT",
                validation_error_message="Empty content",
                file_size_bytes=0,
                correlation_id=correlation_id_1,
            ),
            EssayValidationFailedV1(
                batch_id="batch_correlation",
                original_file_name="file2.txt",
                validation_error_code="CONTENT_TOO_SHORT",
                validation_error_message="Too short",
                file_size_bytes=10,
                correlation_id=correlation_id_2,
            ),
        ]

        event = BatchEssaysReady(
            batch_id="batch_correlation",
            ready_essays=sample_ready_essays,
            batch_entity=sample_batch_entity,
            metadata=sample_metadata,
            validation_failures=validation_failures,
            total_files_processed=5,
        )

        # Verify correlation IDs are preserved
        failures = event.validation_failures
        assert failures is not None
        assert failures[0].correlation_id == correlation_id_1
        assert failures[1].correlation_id == correlation_id_2
