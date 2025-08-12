"""
Constraint simulation tests for MockEssayRepository.

Validates PostgreSQL constraint simulation accuracy, particularly the
partial unique constraint on (batch_id, text_storage_id) and other
constraint behaviors that match production database behavior.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.essay_lifecycle_service.implementations.mock_essay_repository import (
    MockEssayRepository,
)


class TestMockRepositoryConstraints:
    """Test suite for MockEssayRepository constraint simulation."""

    @pytest.fixture
    def mock_repository(self) -> MockEssayRepository:
        """Create mock repository instance."""
        return MockEssayRepository()

    @pytest.mark.asyncio
    async def test_essay_id_uniqueness_constraint_enforced(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that essay_id uniqueness constraint is properly enforced across all essays."""
        correlation_id = uuid4()
        essay_id = "unique-essay-test"

        # Create first essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="batch-1",
            correlation_id=correlation_id,
        )

        # Attempt to create second essay with same ID in different batch should fail
        with pytest.raises(HuleEduError) as exc_info:
            await mock_repository.create_essay_record(
                essay_id=essay_id,
                batch_id="batch-2",  # Different batch
                correlation_id=correlation_id,
            )
        assert "already exists" in str(exc_info.value)

        # Attempt to create essay with same ID in same batch should also fail
        with pytest.raises(HuleEduError) as exc_info:
            await mock_repository.create_essay_record(
                essay_id=essay_id,
                batch_id="batch-1",  # Same batch
                correlation_id=correlation_id,
            )
        assert "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_content_idempotency_constraint_with_non_null_storage_id(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that content idempotency constraint works correctly when
        text_storage_id is not null."""
        correlation_id = uuid4()
        batch_id = "constraint-batch"
        text_storage_id = "unique-text-storage"

        # Create first essay with content idempotency (sets text_storage_id)
        (
            was_created_1,
            essay_id_1,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data={"internal_essay_id": "essay-1"},
            correlation_id=correlation_id,
        )

        assert was_created_1 is True
        assert essay_id_1 == "essay-1"

        # Attempt to create second essay with same (batch_id, text_storage_id) should be idempotent
        (
            was_created_2,
            essay_id_2,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,  # Same text_storage_id
            essay_data={"internal_essay_id": "essay-2"},  # Different essay data
            correlation_id=correlation_id,
        )

        # Should be idempotent (not created) and return original essay_id
        assert was_created_2 is False
        assert essay_id_2 == "essay-1"  # Returns original essay_id

        # Verify only one essay exists with this text_storage_id
        found_essay = await mock_repository.get_essay_by_text_storage_id_and_batch_id(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
        )
        assert found_essay is not None
        assert found_essay.essay_id == "essay-1"

    @pytest.mark.asyncio
    async def test_content_idempotency_allows_same_storage_id_across_batches(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that same text_storage_id is correctly allowed in different batches."""
        correlation_id = uuid4()
        text_storage_id = "shared-text-storage"

        # Create essay in first batch
        (
            was_created_1,
            essay_id_1,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id="batch-1",
            text_storage_id=text_storage_id,
            essay_data={"internal_essay_id": "essay-batch-1"},
            correlation_id=correlation_id,
        )

        assert was_created_1 is True
        assert essay_id_1 == "essay-batch-1"

        # Create essay in second batch with same text_storage_id should succeed
        (
            was_created_2,
            essay_id_2,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id="batch-2",  # Different batch
            text_storage_id=text_storage_id,  # Same text_storage_id
            essay_data={"internal_essay_id": "essay-batch-2"},
            correlation_id=correlation_id,
        )

        assert was_created_2 is True  # Should be created (different batch)
        assert essay_id_2 == "essay-batch-2"

        # Verify both essays exist
        essay_1 = await mock_repository.get_essay_by_text_storage_id_and_batch_id(
            batch_id="batch-1",
            text_storage_id=text_storage_id,
        )
        essay_2 = await mock_repository.get_essay_by_text_storage_id_and_batch_id(
            batch_id="batch-2",
            text_storage_id=text_storage_id,
        )

        assert essay_1 is not None
        assert essay_2 is not None
        assert essay_1.essay_id == "essay-batch-1"
        assert essay_2.essay_id == "essay-batch-2"

    @pytest.mark.asyncio
    async def test_partial_constraint_allows_multiple_null_storage_ids(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that partial constraint correctly allows multiple essays with
        null text_storage_id in same batch."""
        correlation_id = uuid4()
        batch_id = "null-text-batch"

        # Create multiple essays in same batch without text_storage_id (NULL values)
        essay_ids = []
        for i in range(5):
            essay = await mock_repository.create_essay_record(
                essay_id=f"null-text-essay-{i}",
                batch_id=batch_id,
                correlation_id=correlation_id,
            )
            essay_ids.append(essay.essay_id)

            # Verify text_storage_id is None/NULL
            assert essay.text_storage_id is None

        # All essays should be created successfully
        assert len(essay_ids) == 5

        # Verify all essays exist in the batch
        batch_essays = await mock_repository.list_essays_by_batch(batch_id)
        assert len(batch_essays) == 5

        # All should have NULL text_storage_id
        for essay_item in batch_essays:
            assert essay_item.text_storage_id is None

    @pytest.mark.asyncio
    async def test_partial_constraint_handles_mixed_null_and_non_null_values(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that partial constraint correctly handles mixed NULL and
        non-NULL text_storage_id values in same batch."""
        correlation_id = uuid4()
        batch_id = "mixed-text-batch"

        # Create essays with NULL text_storage_id
        null_essays = []
        for i in range(3):
            essay = await mock_repository.create_essay_record(
                essay_id=f"null-essay-{i}",
                batch_id=batch_id,
                correlation_id=correlation_id,
            )
            null_essays.append(essay)

        # Create essays with non-NULL text_storage_id
        non_null_essays = []
        for i in range(3):
            (
                was_created,
                returned_essay_id,
            ) = await mock_repository.create_essay_state_with_content_idempotency(
                batch_id=batch_id,
                text_storage_id=f"text-storage-{i}",
                essay_data={"internal_essay_id": f"non-null-essay-{i}"},
                correlation_id=correlation_id,
            )
            assert was_created is True
            assert returned_essay_id is not None

            retrieved_essay = await mock_repository.get_essay_state(returned_essay_id)
            assert retrieved_essay is not None  # Should exist since we just created it
            non_null_essays.append(retrieved_essay)

        # Verify constraint behavior
        # 1. Multiple NULL values are allowed
        assert len(null_essays) == 3
        for essay_item in null_essays:
            assert essay_item.text_storage_id is None

        # 2. Non-NULL values are unique within batch
        assert len(non_null_essays) == 3
        text_storage_ids = set()
        for essay_item in non_null_essays:
            assert essay_item.text_storage_id is not None
            assert essay_item.text_storage_id not in text_storage_ids  # No duplicates
            text_storage_ids.add(essay_item.text_storage_id)

        # 3. Total essays in batch
        batch_essays = await mock_repository.list_essays_by_batch(batch_id)
        assert len(batch_essays) == 6

    @pytest.mark.asyncio
    async def test_constraint_edge_cases_and_boundary_conditions(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test constraint behavior in edge cases and boundary conditions."""
        correlation_id = uuid4()
        batch_id = "edge-case-batch"
        text_storage_id = "edge-case-text"

        # Create initial essay
        was_created_1, _ = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data={"internal_essay_id": "original-essay"},
            correlation_id=correlation_id,
        )

        assert was_created_1 is True

        # Test 1: Empty string text_storage_id should be treated as non-NULL
        (
            was_created_2,
            essay_id_2,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id="",  # Empty string
            essay_data={"internal_essay_id": "empty-string-essay"},
            correlation_id=correlation_id,
        )

        assert was_created_2 is True  # Different from non-empty string
        assert essay_id_2 == "empty-string-essay"

        # Test 2: Whitespace-only text_storage_id should be treated as distinct
        (
            was_created_3,
            essay_id_3,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id="   ",  # Whitespace
            essay_data={"internal_essay_id": "whitespace-essay"},
            correlation_id=correlation_id,
        )

        assert was_created_3 is True  # Different from empty and regular strings
        assert essay_id_3 == "whitespace-essay"

        # Test 3: Attempt duplicate of original should be idempotent
        (
            was_created_4,
            essay_id_4,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,  # Same as original
            essay_data={"internal_essay_id": "duplicate-attempt"},
            correlation_id=correlation_id,
        )

        assert was_created_4 is False  # Idempotent
        assert essay_id_4 == "original-essay"  # Returns original

    @pytest.mark.asyncio
    async def test_batch_creation_operations_enforce_constraints_properly(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that constraint validation works correctly in batch creation operations."""
        correlation_id = uuid4()

        # Test 1: Batch creation with duplicate essay_ids should fail
        duplicate_essay_data: list[dict[str, str | None]] = [
            {"essay_id": "duplicate-essay", "batch_id": "batch-1", "entity_type": "essay"},
            {
                "essay_id": "duplicate-essay",
                "batch_id": "batch-1",
                "entity_type": "essay",
            },  # Duplicate
            {"essay_id": "unique-essay", "batch_id": "batch-1", "entity_type": "essay"},
        ]

        from huleedu_service_libs.error_handling import HuleEduError
        from common_core.error_enums import ErrorCode
        
        with pytest.raises(HuleEduError) as exc_info:  # Should raise constraint violation
            await mock_repository.create_essay_records_batch(
                essay_data=duplicate_essay_data,
                correlation_id=correlation_id,
            )
        
        # Verify error details
        assert exc_info.value.error_detail.error_code == ErrorCode.VALIDATION_ERROR
        assert "Duplicate essay_ids" in str(exc_info.value)

        # Test 2: Batch creation with unique essay_ids should succeed
        unique_essay_data: list[dict[str, str | None]] = [
            {"essay_id": "batch-essay-1", "batch_id": "batch-1", "entity_type": "essay"},
            {"essay_id": "batch-essay-2", "batch_id": "batch-1", "entity_type": "essay"},
            {"essay_id": "batch-essay-3", "batch_id": "batch-1", "entity_type": "essay"},
        ]

        created_essays = await mock_repository.create_essay_records_batch(
            essay_data=unique_essay_data,
            correlation_id=correlation_id,
        )

        assert len(created_essays) == 3
        essay_ids = {essay.essay_id for essay in created_essays}
        expected_ids = {"batch-essay-1", "batch-essay-2", "batch-essay-3"}
        assert essay_ids == expected_ids

    @pytest.mark.asyncio
    async def test_constraint_isolation_ensures_cross_batch_independence(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that content idempotency constraints maintain proper isolation
        across different batches."""
        correlation_id = uuid4()

        # Create essays with same text_storage_id in different batches
        batch_configs = [
            ("batch-A", "shared-text", "essay-A"),
            ("batch-B", "shared-text", "essay-B"),
            ("batch-C", "shared-text", "essay-C"),
        ]

        created_essays = []
        for batch_id, text_storage_id, essay_id in batch_configs:
            (
                was_created,
                returned_essay_id,
            ) = await mock_repository.create_essay_state_with_content_idempotency(
                batch_id=batch_id,
                text_storage_id=text_storage_id,
                essay_data={"internal_essay_id": essay_id},
                correlation_id=correlation_id,
            )

            assert was_created is True  # Each should be created (different batches)
            assert returned_essay_id == essay_id

            essay = await mock_repository.get_essay_state(essay_id)
            assert essay is not None  # Should exist since we just created it
            created_essays.append(essay)

        # Verify all essays were created
        assert len(created_essays) == 3

        # Verify each has the expected text_storage_id
        for essay_item in created_essays:
            assert essay_item.text_storage_id == "shared-text"

        # Verify they're in different batches
        batch_ids = {
            essay_item.batch_id for essay_item in created_essays if essay_item.batch_id is not None
        }
        assert batch_ids == {"batch-A", "batch-B", "batch-C"}

        # Test idempotency within each batch
        for batch_id, text_storage_id, original_essay_id in batch_configs:
            (
                was_created,
                returned_essay_id,
            ) = await mock_repository.create_essay_state_with_content_idempotency(
                batch_id=batch_id,
                text_storage_id=text_storage_id,  # Same as before
                essay_data={"internal_essay_id": "different-id"},  # Different data
                correlation_id=correlation_id,
            )

            # Should be idempotent within each batch
            assert was_created is False
            assert returned_essay_id == original_essay_id

    @pytest.mark.asyncio
    async def test_constraint_consistency_maintained_during_essay_updates(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that constraints remain properly consistent during essay state updates."""
        correlation_id = uuid4()
        batch_id = "update-constraint-batch"
        text_storage_id = "update-text-storage"

        # Create essay with content idempotency
        was_created, essay_id = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data={"internal_essay_id": "constraint-essay"},
            correlation_id=correlation_id,
        )

        assert was_created is True
        assert essay_id == "constraint-essay"

        # Update essay multiple times
        from common_core.status_enums import EssayStatus

        statuses = [
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
        ]

        for status in statuses:
            await mock_repository.update_essay_state(
                essay_id=essay_id,
                new_status=status,
                metadata={"constraint_test": "update"},
                correlation_id=correlation_id,
            )

        # Test that constraint still prevents duplicate creation
        (
            was_created_2,
            essay_id_2,
        ) = await mock_repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,  # Same as original
            essay_data={"internal_essay_id": "duplicate-attempt"},
            correlation_id=correlation_id,
        )

        # Should still be idempotent after updates
        assert was_created_2 is False
        assert essay_id_2 == "constraint-essay"

        # Verify essay state is correct
        final_essay = await mock_repository.get_essay_state("constraint-essay")
        assert final_essay is not None
        assert final_essay.current_status == EssayStatus.SPELLCHECKED_SUCCESS
        assert final_essay.text_storage_id == text_storage_id

    @pytest.mark.asyncio
    async def test_constraint_violation_error_messages_are_descriptive(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that constraint violations produce appropriate and descriptive error messages."""
        correlation_id = uuid4()

        # Create first essay
        await mock_repository.create_essay_record(
            essay_id="error-test-essay",
            batch_id="error-batch",
            correlation_id=correlation_id,
        )

        # Attempt to create duplicate should produce meaningful error
        try:
            await mock_repository.create_essay_record(
                essay_id="error-test-essay",  # Duplicate
                batch_id="error-batch",
                correlation_id=correlation_id,
            )
            raise AssertionError("Expected constraint violation error")
        except Exception as e:
            # Error message should be informative
            error_str = str(e)
            assert (
                "error-test-essay" in error_str
                or "duplicate" in error_str.lower()
                or "exists" in error_str.lower()
            )

    @pytest.mark.asyncio
    async def test_repository_state_consistency_after_constraint_failures(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that repository state remains consistent after constraint violation failures."""
        correlation_id = uuid4()
        batch_id = "recovery-batch"

        # Create successful essay
        await mock_repository.create_essay_record(
            essay_id="recovery-essay-1",
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Attempt constraint violation
        try:
            await mock_repository.create_essay_record(
                essay_id="recovery-essay-1",  # Duplicate
                batch_id=batch_id,
                correlation_id=correlation_id,
            )
        except Exception:
            pass  # Expected

        # Repository should still work correctly after failure
        await mock_repository.create_essay_record(
            essay_id="recovery-essay-2",  # Different ID
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Verify batch contains expected essays
        batch_essays = await mock_repository.list_essays_by_batch(batch_id)
        assert len(batch_essays) == 2

        essay_ids = {essay.essay_id for essay in batch_essays}
        assert essay_ids == {"recovery-essay-1", "recovery-essay-2"}
