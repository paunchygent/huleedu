"""
Behavioral parity tests for MockEssayRepository.

Ensures MockEssayRepository behaves identically to PostgreSQLEssayRepository
for all CRUD operations, state transitions, and error handling patterns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import HuleEduError

from services.essay_lifecycle_service.constants import (
    MetadataKey,
)
from services.essay_lifecycle_service.implementations.mock_essay_repository import (
    MockEssayRepository,
)


class TestRepositoryBehavioralParity:
    """Test suite ensuring behavioral parity between repository implementations."""

    @pytest.fixture
    def mock_repository(self) -> MockEssayRepository:
        """Create mock repository instance."""
        return MockEssayRepository()

    @pytest.mark.asyncio
    async def test_create_and_retrieve_essay_lifecycle(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test complete essay creation and retrieval lifecycle."""
        correlation_id = uuid4()
        essay_id = "lifecycle-test-essay"
        batch_id = "lifecycle-test-batch"

        # 1. Initial state - essay should not exist
        initial_state = await mock_repository.get_essay_state(essay_id)
        assert initial_state is None

        # 2. Create essay record
        created_essay = await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Verify creation
        assert created_essay.essay_id == essay_id
        assert created_essay.batch_id == batch_id
        assert created_essay.current_status == EssayStatus.UPLOADED
        assert isinstance(created_essay.created_at, datetime)
        assert isinstance(created_essay.updated_at, datetime)
        assert created_essay.processing_metadata is not None
        assert created_essay.timeline is not None

        # 3. Retrieve created essay
        retrieved_essay = await mock_repository.get_essay_state(essay_id)
        assert retrieved_essay is not None
        assert retrieved_essay.essay_id == essay_id
        assert retrieved_essay.batch_id == batch_id
        assert retrieved_essay.current_status == EssayStatus.UPLOADED

        # 4. Update essay state using constants
        await mock_repository.update_essay_state(
            essay_id=essay_id,
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={
                MetadataKey.CURRENT_PHASE: "spellcheck",
                MetadataKey.PHASE_INITIATED_AT: datetime.now(UTC).isoformat(),
                "test_scenario": "lifecycle_test",
            },
            correlation_id=correlation_id,
        )

        # 5. Verify state update using constants
        updated_essay = await mock_repository.get_essay_state(essay_id)
        assert updated_essay is not None
        assert updated_essay.current_status == EssayStatus.AWAITING_SPELLCHECK
        assert MetadataKey.CURRENT_PHASE in updated_essay.processing_metadata
        assert updated_essay.processing_metadata[MetadataKey.CURRENT_PHASE] == "spellcheck"

    @pytest.mark.asyncio
    async def test_essay_status_transitions(self, mock_repository: MockEssayRepository) -> None:
        """Test essay status transitions follow valid patterns."""
        correlation_id = uuid4()
        essay_id = "transition-test-essay"

        # Create base essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="transition-batch",
            correlation_id=correlation_id,
        )

        # Test complete spellcheck workflow
        spellcheck_statuses = [
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
        ]

        for status in spellcheck_statuses:
            await mock_repository.update_essay_state(
                essay_id=essay_id,
                new_status=status,
                metadata={
                    "status_reason": f"Transitioning to {status.value}",
                    MetadataKey.CURRENT_PHASE: "spellcheck",
                    MetadataKey.PHASE_INITIATED_AT: datetime.now(UTC).isoformat(),
                },
                correlation_id=correlation_id,
            )

            essay = await mock_repository.get_essay_state(essay_id)
            assert essay is not None
            assert essay.current_status == status
            assert status.value in essay.timeline

        # Test CJ Assessment workflow
        cj_statuses = [
            EssayStatus.AWAITING_CJ_ASSESSMENT,
            EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
            EssayStatus.CJ_ASSESSMENT_SUCCESS,
        ]

        for status in cj_statuses:
            await mock_repository.update_essay_state(
                essay_id=essay_id,
                new_status=status,
                metadata={
                    "status_reason": f"Transitioning to {status.value}",
                    MetadataKey.CURRENT_PHASE: "cj_assessment",
                    MetadataKey.PHASE_INITIATED_AT: datetime.now(UTC).isoformat(),
                },
                correlation_id=correlation_id,
            )

            essay = await mock_repository.get_essay_state(essay_id)
            assert essay is not None
            assert essay.current_status == status

    @pytest.mark.asyncio
    async def test_batch_operations_consistency(self, mock_repository: MockEssayRepository) -> None:
        """Test batch operations maintain consistency across essays."""
        correlation_id = uuid4()
        batch_id = "consistency-batch"
        essay_ids = [f"consistency-essay-{i}" for i in range(5)]

        # Create batch of essays
        essay_data: list[dict[str, str | None]] = [
            {"entity_id": essay_id, "parent_id": batch_id, "entity_type": "essay"}
            for essay_id in essay_ids
        ]

        created_essays = await mock_repository.create_essay_records_batch(
            essay_data=essay_data,
            correlation_id=correlation_id,
        )

        assert len(created_essays) == 5
        for essay in created_essays:
            assert essay.batch_id == batch_id
            assert essay.current_status == EssayStatus.UPLOADED

        # Test list_essays_by_batch
        batch_essays = await mock_repository.list_essays_by_batch(batch_id)
        assert len(batch_essays) == 5
        retrieved_ids = {essay.essay_id for essay in batch_essays}
        expected_ids = set(essay_ids)
        assert retrieved_ids == expected_ids

        # Test batch status summary
        status_summary = await mock_repository.get_batch_status_summary(batch_id)
        assert EssayStatus.UPLOADED in status_summary
        assert status_summary[EssayStatus.UPLOADED] == 5

        # Update some essays to different statuses
        await mock_repository.update_essay_state(
            essay_id=essay_ids[0],
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={},
            correlation_id=correlation_id,
        )
        await mock_repository.update_essay_state(
            essay_id=essay_ids[1],
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={},
            correlation_id=correlation_id,
        )
        await mock_repository.update_essay_state(
            essay_id=essay_ids[2],
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={},
            correlation_id=correlation_id,
        )

        # Verify updated status summary
        updated_summary = await mock_repository.get_batch_status_summary(batch_id)
        assert updated_summary[EssayStatus.UPLOADED] == 2
        assert updated_summary[EssayStatus.AWAITING_SPELLCHECK] == 2
        assert updated_summary[EssayStatus.SPELLCHECKED_SUCCESS] == 1

    @pytest.mark.asyncio
    async def test_phase_query_accuracy(self, mock_repository: MockEssayRepository) -> None:
        """Test phase queries return accurate results."""
        correlation_id = uuid4()
        batch_id = "phase-query-batch"

        # Create essays in different phases
        essay_statuses = [
            ("essay-1", EssayStatus.AWAITING_SPELLCHECK),
            ("essay-2", EssayStatus.SPELLCHECKING_IN_PROGRESS),
            ("essay-3", EssayStatus.SPELLCHECKED_SUCCESS),
            ("essay-4", EssayStatus.AWAITING_CJ_ASSESSMENT),
            ("essay-5", EssayStatus.CJ_ASSESSMENT_SUCCESS),
            ("essay-6", EssayStatus.AWAITING_NLP),
            ("essay-7", EssayStatus.NLP_SUCCESS),
        ]

        for essay_id, status in essay_statuses:
            await mock_repository.create_essay_record(
                essay_id=essay_id,
                batch_id=batch_id,
                correlation_id=correlation_id,
            )
            await mock_repository.update_essay_state(
                essay_id=essay_id,
                new_status=status,
                metadata={"phase_assigned": "test"},
                correlation_id=correlation_id,
            )

        # Test spellcheck phase query
        spellcheck_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id,
            phase_name="spellcheck",
        )
        spellcheck_ids = {essay.essay_id for essay in spellcheck_essays}
        expected_spellcheck = {"essay-1", "essay-2", "essay-3"}
        assert spellcheck_ids == expected_spellcheck

        # Test CJ assessment phase query
        cj_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id,
            phase_name="cj_assessment",
        )
        cj_ids = {essay.essay_id for essay in cj_essays}
        expected_cj = {"essay-4", "essay-5"}
        assert cj_ids == expected_cj

        # Test NLP phase query
        nlp_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id,
            phase_name="nlp",
        )
        nlp_ids = {essay.essay_id for essay in nlp_essays}
        expected_nlp = {"essay-6", "essay-7"}
        assert nlp_ids == expected_nlp

        # Test unknown phase returns empty list
        unknown_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id=batch_id,
            phase_name="unknown_phase",
        )
        assert len(unknown_essays) == 0

    @pytest.mark.asyncio
    async def test_content_idempotency_behavior(self, mock_repository: MockEssayRepository) -> None:
        """Test content idempotency follows PostgreSQL constraint behavior."""
        correlation_id = uuid4()
        batch_id = "idempotency-batch"
        text_storage_id = "unique-text-123"

        essay_data = {
            "internal_essay_id": "idempotent-essay",
            "original_file_name": "test.txt",
            "file_size": 1024,
        }

        # First creation should succeed
        (
            was_created_1,
            essay_id_1,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data=essay_data,
            correlation_id=correlation_id,
        )

        assert was_created_1 is True
        assert essay_id_1 == "idempotent-essay"

        # Verify essay was created
        created_essay = await mock_repository.get_essay_state(essay_id_1)
        assert created_essay is not None
        assert created_essay.text_storage_id == text_storage_id

        # Second creation with same (batch_id, text_storage_id) should be idempotent
        (
            was_created_2,
            essay_id_2,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data={"internal_essay_id": "different-essay-id"},  # Different data
            correlation_id=correlation_id,
        )

        assert was_created_2 is False  # Not created
        assert essay_id_2 == "idempotent-essay"  # Returns original essay_id

        # Third creation with different text_storage_id should succeed
        (
            was_created_3,
            essay_id_3,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id="different-text-456",
            essay_data={"internal_essay_id": "different-essay"},
            correlation_id=correlation_id,
        )

        assert was_created_3 is True
        assert essay_id_3 == "different-essay"

        # Fourth creation with different batch_id but same text_storage_id should succeed
        (
            was_created_4,
            essay_id_4,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id="different-batch",
            text_storage_id=text_storage_id,
            essay_data={"internal_essay_id": "cross-batch-essay"},
            correlation_id=correlation_id,
        )

        assert was_created_4 is True
        assert essay_id_4 == "cross-batch-essay"

    @pytest.mark.asyncio
    async def test_storage_reference_handling(self, mock_repository: MockEssayRepository) -> None:
        """Test storage reference handling matches expected behavior."""
        correlation_id = uuid4()
        essay_id = "storage-ref-essay"

        # Create essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="storage-batch",
            correlation_id=correlation_id,
        )

        # Update with storage reference
        await mock_repository.update_essay_state(
            essay_id=essay_id,
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={"spellcheck_completed": True},
            storage_reference=(ContentType.CORRECTED_TEXT, "corrected-text-storage-123"),
            correlation_id=correlation_id,
        )

        # Verify storage reference was saved
        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None
        assert ContentType.CORRECTED_TEXT in essay.storage_references
        assert essay.storage_references[ContentType.CORRECTED_TEXT] == "corrected-text-storage-123"

        # Update with different storage reference
        await mock_repository.update_essay_state(
            essay_id=essay_id,
            new_status=EssayStatus.CJ_ASSESSMENT_SUCCESS,
            metadata={"cj_assessment_completed": True},
            storage_reference=(ContentType.CJ_RESULTS_JSON, "cj-results-789"),
            correlation_id=correlation_id,
        )

        # Verify both storage references exist
        updated_essay = await mock_repository.get_essay_state(essay_id)
        assert updated_essay is not None
        assert ContentType.CORRECTED_TEXT in updated_essay.storage_references
        assert ContentType.CJ_RESULTS_JSON in updated_essay.storage_references
        assert updated_essay.storage_references[ContentType.CJ_RESULTS_JSON] == "cj-results-789"

    @pytest.mark.asyncio
    async def test_student_association_handling(self, mock_repository: MockEssayRepository) -> None:
        """Test student association updates work correctly."""
        correlation_id = uuid4()
        essay_id = "student-assoc-essay"

        # Create essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="student-batch",
            correlation_id=correlation_id,
        )

        # Update student association
        association_time = datetime.now(UTC)
        await mock_repository.update_student_association(
            essay_id=essay_id,
            student_id="student-123",
            association_confirmed_at=association_time,
            association_method="human",
            correlation_id=correlation_id,
        )

        # Verify association was saved
        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None
        assert essay.student_id == "student-123"
        assert essay.association_confirmed_at == association_time
        assert essay.association_method == "human"

        # Update to different student
        new_association_time = datetime.now(UTC)
        await mock_repository.update_student_association(
            essay_id=essay_id,
            student_id="student-456",
            association_confirmed_at=new_association_time,
            association_method="auto",
            correlation_id=correlation_id,
        )

        # Verify association was updated
        updated_essay = await mock_repository.get_essay_state(essay_id)
        assert updated_essay is not None
        assert updated_essay.student_id == "student-456"
        assert updated_essay.association_confirmed_at == new_association_time
        assert updated_essay.association_method == "auto"

    @pytest.mark.asyncio
    async def test_processing_metadata_updates(self, mock_repository: MockEssayRepository) -> None:
        """Test processing metadata updates work correctly."""
        correlation_id = uuid4()
        essay_id = "metadata-essay"

        # Create essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="metadata-batch",
            correlation_id=correlation_id,
        )

        # Update processing metadata
        metadata_updates = {
            "spellcheck_service_request_id": "req-123",
            "processing_attempt_count": 2,
            "last_error_message": "Temporary service unavailable",
        }

        await mock_repository.update_essay_processing_metadata(
            essay_id=essay_id,
            metadata_updates=metadata_updates,
            correlation_id=correlation_id,
        )

        # Verify metadata was updated
        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None
        for key, value in metadata_updates.items():
            assert key in essay.processing_metadata
            assert essay.processing_metadata[key] == value

        # Additional metadata update should merge
        additional_updates = {
            "cj_assessment_service_request_id": "cj-req-456",
            "processing_attempt_count": 3,  # Should overwrite
        }

        await mock_repository.update_essay_processing_metadata(
            essay_id=essay_id,
            metadata_updates=additional_updates,
            correlation_id=correlation_id,
        )

        # Verify merged metadata
        updated_essay = await mock_repository.get_essay_state(essay_id)
        assert updated_essay is not None
        assert (
            updated_essay.processing_metadata["spellcheck_service_request_id"] == "req-123"
        )  # Preserved
        assert (
            updated_essay.processing_metadata["cj_assessment_service_request_id"] == "cj-req-456"
        )  # Added
        assert updated_essay.processing_metadata["processing_attempt_count"] == 3  # Updated
        assert (
            updated_essay.processing_metadata["last_error_message"]
            == "Temporary service unavailable"
        )  # Preserved

    @pytest.mark.asyncio
    async def test_error_handling_consistency(self, mock_repository: MockEssayRepository) -> None:
        """Test error handling matches expected patterns."""
        correlation_id = uuid4()

        # Test update non-existent essay
        with pytest.raises(HuleEduError, match="Essay with ID .* not found"):
            await mock_repository.update_essay_state(
                essay_id="non-existent-essay",
                new_status=EssayStatus.SPELLCHECKED_SUCCESS,
                metadata={},
                correlation_id=correlation_id,
            )

        # Test update student association for non-existent essay
        with pytest.raises(HuleEduError, match="Essay with ID .* not found"):
            await mock_repository.update_student_association(
                essay_id="non-existent-essay",
                student_id="student-123",
                association_confirmed_at=datetime.now(UTC),
                association_method="human",
                correlation_id=correlation_id,
            )

        # Test update metadata for non-existent essay
        with pytest.raises(HuleEduError, match="Essay with ID .* not found"):
            await mock_repository.update_essay_processing_metadata(
                essay_id="non-existent-essay",
                metadata_updates={"test": "value"},
                correlation_id=correlation_id,
            )

    @pytest.mark.asyncio
    async def test_timeline_management(self, mock_repository: MockEssayRepository) -> None:
        """Test that timeline is properly maintained across state transitions."""
        correlation_id = uuid4()
        essay_id = "timeline-essay"

        # Create essay
        created_essay = await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="timeline-batch",
            correlation_id=correlation_id,
        )

        # Should have UPLOADED in timeline
        assert EssayStatus.UPLOADED.value in created_essay.timeline

        # Update to spellcheck status
        await mock_repository.update_essay_state(
            essay_id=essay_id,
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={},
            correlation_id=correlation_id,
        )

        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None
        assert EssayStatus.UPLOADED.value in essay.timeline
        assert EssayStatus.AWAITING_SPELLCHECK.value in essay.timeline

        # Update to completed status
        await mock_repository.update_essay_state(
            essay_id=essay_id,
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={},
            correlation_id=correlation_id,
        )

        final_essay = await mock_repository.get_essay_state(essay_id)
        assert final_essay is not None
        assert EssayStatus.UPLOADED.value in final_essay.timeline
        assert EssayStatus.AWAITING_SPELLCHECK.value in final_essay.timeline
        assert EssayStatus.SPELLCHECKED_SUCCESS.value in final_essay.timeline

        # Verify timeline timestamps are datetime objects
        for _, timestamp in final_essay.timeline.items():
            assert isinstance(timestamp, datetime)
            assert timestamp.tzinfo is not None  # Should be timezone-aware
