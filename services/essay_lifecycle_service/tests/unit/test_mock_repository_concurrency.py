"""
Concurrency and atomicity tests for MockEssayRepository.

Validates atomic operations, double-checked locking patterns, and concurrent
access safety for the mock repository implementation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.implementations.mock_essay_repository import (
    MockEssayRepository,
)


class TestMockRepositoryConcurrency:
    """Test suite for MockEssayRepository concurrency and atomicity."""
    
    # Test configuration constants
    SMALL_CONCURRENCY = 10
    MEDIUM_CONCURRENCY = 50 
    HIGH_CONCURRENCY = 100
    STRESS_CONCURRENCY = 200

    @pytest.fixture
    def mock_repository(self) -> MockEssayRepository:
        """Create mock repository instance."""
        return MockEssayRepository()
        
    @pytest.fixture(autouse=True) 
    def cleanup_repository(self, mock_repository: MockEssayRepository) -> Generator[None, None, None]:
        """Cleanup repository state after each test."""
        yield
        # Clear all state for clean test isolation
        mock_repository.essays.clear()
        mock_repository._unique_constraints.clear()
        mock_repository._locks.clear()

    @pytest.mark.parametrize("concurrency_level", [10, 25, 50])
    @pytest.mark.asyncio
    async def test_concurrent_essay_creation_race_condition(
        self, mock_repository: MockEssayRepository, concurrency_level: int
    ) -> None:
        """Test that concurrent essay creation with same ID results in single creation."""
        correlation_id = uuid4()
        essay_id = "concurrent-essay"
        batch_id = "concurrent-batch"

        # Create multiple concurrent creation tasks with same essay ID
        async def create_essay() -> bool:
            try:
                await mock_repository.create_essay_record(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    correlation_id=correlation_id,
                )
                return True
            except Exception:
                # Should raise exception for duplicate essay_id
                return False

        # Execute concurrent creation attempts
        tasks = [create_essay() for _ in range(concurrency_level)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful creations
        successful_creations = sum(1 for result in results if result is True)
        failed_creations = sum(1 for result in results if result is False or isinstance(result, Exception))

        # Should have exactly 1 success and (concurrency_level - 1) failures due to unique constraint
        expected_failures = concurrency_level - 1
        assert successful_creations == 1, f"Expected 1 successful creation, got {successful_creations}"
        assert failed_creations == expected_failures, f"Expected {expected_failures} failed creations, got {failed_creations}"

        # Verify only one essay exists
        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None
        assert essay.essay_id == essay_id

    @pytest.mark.parametrize("concurrency_level", [50, 100, 150])
    @pytest.mark.asyncio
    async def test_concurrent_content_idempotency_atomicity(
        self, mock_repository: MockEssayRepository, concurrency_level: int
    ) -> None:
        """Test atomic idempotency check for content provisioning under concurrency."""
        correlation_id = uuid4()
        batch_id = "idempotency-batch"
        text_storage_id = "shared-text-storage"

        essay_data = {
            "internal_essay_id": "idempotent-essay",
            "original_file_name": "test.txt",
            "file_size": 1024,
        }

        # Create multiple concurrent idempotency operations
        async def create_with_idempotency() -> tuple[bool, str | None]:
            return await mock_repository.create_essay_state_with_content_idempotency(
                batch_id=batch_id,
                text_storage_id=text_storage_id,
                essay_data=essay_data,
                correlation_id=correlation_id,
            )

        # Execute concurrent calls to stress-test atomic behavior
        tasks = [create_with_idempotency() for _ in range(concurrency_level)]
        results = await asyncio.gather(*tasks)

        # Count creation vs idempotent responses
        creations = sum(1 for was_created, _ in results if was_created)
        idempotent_responses = sum(1 for was_created, _ in results if not was_created)

        # Should have exactly 1 creation and (concurrency_level - 1) idempotent responses
        expected_idempotent = concurrency_level - 1
        assert creations == 1, f"Expected exactly 1 creation, got {creations}"
        assert idempotent_responses == expected_idempotent, f"Expected {expected_idempotent} idempotent responses, got {idempotent_responses}"

        # All responses should return the same essay_id
        essay_ids = [essay_id for _, essay_id in results]
        unique_essay_ids = set(essay_ids)
        assert len(unique_essay_ids) == 1, f"Expected single essay_id, got {unique_essay_ids}"
        assert "idempotent-essay" in unique_essay_ids

        # Verify essay was created correctly
        essay = await mock_repository.get_essay_state("idempotent-essay")
        assert essay is not None
        assert essay.text_storage_id == text_storage_id

    @pytest.mark.asyncio
    async def test_concurrent_essay_state_updates(self, mock_repository: MockEssayRepository) -> None:
        """Test concurrent state updates maintain consistency."""
        correlation_id = uuid4()
        essay_id = "concurrent-update-essay"

        # Create base essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="update-batch",
            correlation_id=correlation_id,
        )

        # Define concurrent update operations
        update_operations = [
            (EssayStatus.AWAITING_SPELLCHECK, {"phase": "spellcheck", "step": 1}),
            (EssayStatus.SPELLCHECKING_IN_PROGRESS, {"phase": "spellcheck", "step": 2}),
            (EssayStatus.SPELLCHECKED_SUCCESS, {"phase": "spellcheck", "step": 3}),
            (EssayStatus.AWAITING_CJ_ASSESSMENT, {"phase": "cj", "step": 1}),
            (EssayStatus.CJ_ASSESSMENT_IN_PROGRESS, {"phase": "cj", "step": 2}),
        ]

        async def update_essay_state(status: EssayStatus, metadata: dict) -> bool:
            try:
                await mock_repository.update_essay_state(
                    essay_id=essay_id,
                    new_status=status,
                    metadata=metadata,
                    correlation_id=correlation_id,
                )
                return True
            except Exception:
                return False

        # Execute concurrent updates
        tasks = [update_essay_state(status, metadata) for status, metadata in update_operations]
        results = await asyncio.gather(*tasks)

        # All updates should succeed (no lost updates)
        successful_updates = sum(results)
        assert successful_updates == len(update_operations), f"Expected all {len(update_operations)} updates to succeed"

        # Verify final state is consistent
        final_essay = await mock_repository.get_essay_state(essay_id)
        assert final_essay is not None
        assert final_essay.current_status in [status for status, _ in update_operations]

        # Verify timeline contains all status transitions
        timeline_statuses = set(final_essay.timeline.keys())
        expected_statuses = {status.value for status, _ in update_operations}
        expected_statuses.add(EssayStatus.UPLOADED.value)  # Initial status
        assert expected_statuses.issubset(timeline_statuses), "Timeline missing expected status transitions"

    @pytest.mark.asyncio
    async def test_concurrent_batch_operations(self, mock_repository: MockEssayRepository) -> None:
        """Test concurrent batch operations maintain consistency."""
        correlation_id = uuid4()
        batch_id = "concurrent-batch"

        # Create multiple concurrent batch creation operations
        async def create_batch_essays(batch_index: int) -> int:
            essay_data: list[dict[str, str | None]] = [
                {
                    "essay_id": f"batch-{batch_index}-essay-{i}",
                    "batch_id": batch_id,
                    "entity_type": "essay",
                }
                for i in range(5)
            ]

            created_essays = await mock_repository.create_essay_records_batch(
                essay_data=essay_data,
                correlation_id=correlation_id,
            )
            return len(created_essays)

        # Execute 10 concurrent batch creation operations (50 essays total)
        tasks = [create_batch_essays(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All batch operations should succeed
        total_created = sum(results)
        assert total_created == 50, f"Expected 50 essays created, got {total_created}"

        # Verify all essays exist in batch
        batch_essays = await mock_repository.list_essays_by_batch(batch_id)
        assert len(batch_essays) == 50, f"Expected 50 essays in batch, got {len(batch_essays)}"

        # Verify all essays have correct batch_id
        for essay in batch_essays:
            assert essay.batch_id == batch_id

        # Verify batch status summary is correct
        status_summary = await mock_repository.get_batch_status_summary(batch_id)
        assert status_summary[EssayStatus.UPLOADED] == 50

    @pytest.mark.asyncio
    async def test_concurrent_metadata_updates(self, mock_repository: MockEssayRepository) -> None:
        """Test concurrent metadata updates don't cause data loss."""
        correlation_id = uuid4()
        essay_id = "metadata-concurrent-essay"

        # Create base essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="metadata-batch",
            correlation_id=correlation_id,
        )

        # Define concurrent metadata update operations
        metadata_updates = [
            {"spellcheck_request_id": f"req-{i}", f"metadata_key_{i}": f"value_{i}"}
            for i in range(20)
        ]

        async def update_metadata(updates: dict) -> bool:
            try:
                await mock_repository.update_essay_processing_metadata(
                    essay_id=essay_id,
                    metadata_updates=updates,
                    correlation_id=correlation_id,
                )
                return True
            except Exception:
                return False

        # Execute concurrent metadata updates
        tasks = [update_metadata(updates) for updates in metadata_updates]
        results = await asyncio.gather(*tasks)

        # All updates should succeed
        successful_updates = sum(results)
        assert successful_updates == 20, f"Expected 20 successful metadata updates, got {successful_updates}"

        # Verify all metadata was preserved (no lost updates)
        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None

        # Check that all metadata keys exist
        for i in range(20):
            assert f"metadata_key_{i}" in essay.processing_metadata
            assert essay.processing_metadata[f"metadata_key_{i}"] == f"value_{i}"

        # Check spellcheck_request_id (should be one of the concurrent values)
        assert "spellcheck_request_id" in essay.processing_metadata
        spellcheck_id = essay.processing_metadata["spellcheck_request_id"]
        assert spellcheck_id in [f"req-{i}" for i in range(20)]

    @pytest.mark.asyncio
    async def test_concurrent_student_association_updates(self, mock_repository: MockEssayRepository) -> None:
        """Test concurrent student association updates maintain consistency."""
        correlation_id = uuid4()
        essay_id = "student-concurrent-essay"

        # Create base essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="student-batch",
            correlation_id=correlation_id,
        )

        # Define concurrent student association updates
        association_updates = [
            (f"student-{i}", "human" if i % 2 == 0 else "auto")
            for i in range(10)
        ]

        async def update_student_association(student_id: str, method: str) -> bool:
            try:
                await mock_repository.update_student_association(
                    essay_id=essay_id,
                    student_id=student_id,
                    association_confirmed_at=datetime.now(UTC),
                    association_method=method,
                    correlation_id=correlation_id,
                )
                return True
            except Exception:
                return False

        # Execute concurrent association updates
        tasks = [
            update_student_association(student_id, method)
            for student_id, method in association_updates
        ]
        results = await asyncio.gather(*tasks)

        # All updates should succeed
        successful_updates = sum(results)
        assert successful_updates == 10, f"Expected 10 successful association updates, got {successful_updates}"

        # Verify final state is consistent (one of the concurrent updates won)
        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None
        assert essay.student_id is not None
        assert essay.student_id in [f"student-{i}" for i in range(10)]
        assert essay.association_method in ["human", "auto"]
        assert essay.association_confirmed_at is not None

    @pytest.mark.asyncio
    async def test_concurrent_storage_reference_updates(self, mock_repository: MockEssayRepository) -> None:
        """Test concurrent storage reference updates preserve all references."""
        correlation_id = uuid4()
        essay_id = "storage-concurrent-essay"

        # Create base essay
        await mock_repository.create_essay_record(
            essay_id=essay_id,
            batch_id="storage-batch",
            correlation_id=correlation_id,
        )

        # Define concurrent storage reference updates
        storage_references = [
            (ContentType.CORRECTED_TEXT, "corrected-storage-1"),
            (ContentType.CJ_RESULTS_JSON, "cj-storage-1"),
            (ContentType.NLP_METRICS_JSON, "nlp-storage-1"),
            (ContentType.AI_DETAILED_ANALYSIS_JSON, "ai-storage-1"),
            # Mix some duplicates to test overwriting
            (ContentType.CORRECTED_TEXT, "corrected-storage-updated-1"),
        ]

        async def update_with_storage_reference(content_type: ContentType, storage_id: str) -> bool:
            try:
                await mock_repository.update_essay_state(
                    essay_id=essay_id,
                    new_status=EssayStatus.SPELLCHECKED_SUCCESS,  # Status needed for update
                    metadata={"storage_update": f"ref-{storage_id}"},
                    storage_reference=(content_type, storage_id),
                    correlation_id=correlation_id,
                )
                return True
            except Exception:
                return False

        # Execute concurrent storage reference updates
        tasks = [
            update_with_storage_reference(content_type, storage_id)
            for content_type, storage_id in storage_references
        ]
        results = await asyncio.gather(*tasks)

        # All updates should succeed
        successful_updates = sum(results)
        assert successful_updates == len(storage_references), f"Expected all storage updates to succeed"

        # Verify storage references were preserved
        essay = await mock_repository.get_essay_state(essay_id)
        assert essay is not None

        # Should have references for all content types
        expected_content_types = {ContentType.CORRECTED_TEXT, ContentType.CJ_RESULTS_JSON, 
                                ContentType.NLP_METRICS_JSON, ContentType.AI_DETAILED_ANALYSIS_JSON}
        actual_content_types = set(essay.storage_references.keys())
        assert expected_content_types.issubset(actual_content_types)

        # CORRECTED_TEXT should have the latest update (due to race condition)
        corrected_text_ref = essay.storage_references[ContentType.CORRECTED_TEXT]
        assert corrected_text_ref.startswith("corrected-storage-")

    @pytest.mark.asyncio
    async def test_global_lock_prevents_repository_corruption(self, mock_repository: MockEssayRepository) -> None:
        """Test that global lock prevents repository state corruption."""
        correlation_id = uuid4()

        # Define mixed concurrent operations that could cause corruption
        async def mixed_operations(operation_id: int) -> str:
            batch_id = f"batch-{operation_id}"
            essay_id = f"essay-{operation_id}"

            # Create essay
            await mock_repository.create_essay_record(
                essay_id=essay_id,
                batch_id=batch_id,
                correlation_id=correlation_id,
            )

            # Update essay
            await mock_repository.update_essay_state(
                essay_id=essay_id,
                new_status=EssayStatus.AWAITING_SPELLCHECK,
                metadata={"operation": f"op-{operation_id}"},
                correlation_id=correlation_id,
            )

            # Create batch essay data for additional essays
            additional_essays: list[dict[str, str | None]] = [
                {
                    "essay_id": f"batch-{operation_id}-essay-{i}",
                    "batch_id": batch_id,
                    "entity_type": "essay",
                }
                for i in range(3)
            ]

            await mock_repository.create_essay_records_batch(
                essay_data=additional_essays,
                correlation_id=correlation_id,
            )

            return batch_id

        # Execute many concurrent mixed operations
        operation_count = 20
        tasks = [mixed_operations(i) for i in range(operation_count)]
        batch_ids = await asyncio.gather(*tasks)

        # Verify repository integrity
        assert len(batch_ids) == operation_count

        # Each batch should contain exactly 4 essays (1 individual + 3 batch)
        for batch_id in batch_ids:
            batch_essays = await mock_repository.list_essays_by_batch(batch_id)
            assert len(batch_essays) == 4, f"Batch {batch_id} should have 4 essays, got {len(batch_essays)}"

            # Verify all essays in batch have correct batch_id
            for essay in batch_essays:
                assert essay.batch_id == batch_id

        # Verify total essay count
        total_essays = 0
        for batch_id in batch_ids:
            batch_essays = await mock_repository.list_essays_by_batch(batch_id)
            total_essays += len(batch_essays)

        expected_total = operation_count * 4  # 20 operations * 4 essays each
        assert total_essays == expected_total, f"Expected {expected_total} total essays, got {total_essays}"

    @pytest.mark.asyncio
    async def test_concurrent_phase_queries_consistency(self, mock_repository: MockEssayRepository) -> None:
        """Test that concurrent phase queries return consistent results."""
        correlation_id = uuid4()
        batch_id = "phase-query-batch"

        # Create essays and update them to various phases concurrently
        async def create_and_update_essay(essay_index: int) -> None:
            essay_id = f"phase-essay-{essay_index}"
            
            await mock_repository.create_essay_record(
                essay_id=essay_id,
                batch_id=batch_id,
                correlation_id=correlation_id,
            )

            # Update to a phase status based on index
            phase_statuses = [
                EssayStatus.AWAITING_SPELLCHECK,
                EssayStatus.SPELLCHECKING_IN_PROGRESS,
                EssayStatus.SPELLCHECKED_SUCCESS,
                EssayStatus.AWAITING_CJ_ASSESSMENT,
                EssayStatus.CJ_ASSESSMENT_SUCCESS,
            ]
            status = phase_statuses[essay_index % len(phase_statuses)]

            await mock_repository.update_essay_state(
                essay_id=essay_id,
                new_status=status,
                metadata={"phase_test": True},
                correlation_id=correlation_id,
            )

        # Create 25 essays concurrently (5 of each phase status)
        creation_tasks = [create_and_update_essay(i) for i in range(25)]
        await asyncio.gather(*creation_tasks)

        # Perform concurrent phase queries
        async def query_phase(phase_name: str) -> int:
            essays = await mock_repository.list_essays_by_batch_and_phase(
                batch_id=batch_id,
                phase_name=phase_name,
            )
            return len(essays)

        # Query all phases concurrently multiple times
        query_tasks = []
        for _ in range(10):  # 10 concurrent query rounds
            query_tasks.extend([
                query_phase("spellcheck"),
                query_phase("cj_assessment"),
            ])

        results = await asyncio.gather(*query_tasks)

        # Results should be consistent (each query returns same count)
        spellcheck_results = results[::2]  # Every other result starting from 0
        cj_results = results[1::2]  # Every other result starting from 1

        # All spellcheck queries should return same count
        assert len(set(spellcheck_results)) == 1, f"Inconsistent spellcheck query results: {set(spellcheck_results)}"
        
        # All CJ queries should return same count
        assert len(set(cj_results)) == 1, f"Inconsistent CJ query results: {set(cj_results)}"

        # Verify expected counts (3 spellcheck statuses * 5 essays each = 15)
        assert spellcheck_results[0] == 15, f"Expected 15 spellcheck essays, got {spellcheck_results[0]}"
        # CJ has 2 statuses in our test (AWAITING + SUCCESS) * 5 each = 10, but we only created 5 essays with those statuses
        assert cj_results[0] == 10, f"Expected 10 CJ essays, got {cj_results[0]}"