"""Integration tests for retry mechanisms and failed comparison pool management.

This module tests the real retry mechanism functionality without mocks, validating:
- Failed comparison pool management and persistence
- Threshold-based retry batch formation
- End-of-batch fairness processing (force_retry_all)
- Retry count tracking and permanent failure designation
- Pool statistics tracking and metrics
- Integration with batch submission flow

IMPORTANT: This test file uses the repository pattern exclusively for all database
operations to match production patterns and avoid session management issues.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from common_core import EssayComparisonWinner, LLMProviderType
from common_core.error_enums import ErrorCode
from common_core.events.llm_provider_events import (
    LLMComparisonResultV1,
    TokenUsage,
)
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy import select

from services.cj_assessment_service.cj_core_logic.batch_pool_manager import (
    BatchPoolManager,
)
from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
    BatchRetryProcessor,
)
from services.cj_assessment_service.cj_core_logic.batch_submission import (
    BatchSubmissionResult,
    get_batch_state,
    update_batch_processing_metadata,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
    FailedComparisonEntry,
    FailedComparisonPool,
    FailedComparisonPoolStatistics,
)
from services.cj_assessment_service.models_db import (
    CJBatchState,
    CJBatchUpload,
    ComparisonPair,
    ProcessedEssay,
)
from services.cj_assessment_service.protocols import (
    BatchProcessorProtocol,
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)

if TYPE_CHECKING:
    pass


@pytest.mark.integration
class TestRetryMechanisms:
    """Test retry mechanisms and failed comparison pool management.
    
    All tests use the repository pattern exclusively for database operations,
    matching production patterns and ensuring proper transaction boundaries.
    """

    async def _create_test_batch(
        self,
        repository: CJRepositoryProtocol,
        essay_count: int = 5,
        batch_id: str = "retry-test-batch",
    ) -> tuple[int, list[ProcessedEssay]]:
        """Create a test batch with essays ready for comparisons.
        
        Args:
            repository: Repository for database operations
            essay_count: Number of essays to create
            batch_id: Batch identifier
            
        Returns:
            Tuple of (cj_batch_id, list of processed essays)
        """
        async with repository.session() as session:
            # Create batch
            cj_batch = await repository.create_new_cj_batch(
                session=session,
                bos_batch_id=batch_id,
                event_correlation_id=str(uuid4()),
                language="en",
                course_code="ENG5",
                essay_instructions="Retry test instructions",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=essay_count,
            )
            
            # Create essays
            essays = []
            for i in range(essay_count):
                essay = await repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch.id,
                    els_essay_id=f"retry_essay_{i:03d}",
                    text_storage_id=f"retry_storage_{i:03d}",
                    assessment_input_text=f"Essay content for retry test {i}",
                )
                essays.append(essay)
            
            # Initialize batch state
            batch_state = await session.get(CJBatchState, cj_batch.id)
            if batch_state:
                batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
                batch_state.processing_metadata = {}  # Initialize empty metadata
            
            await session.commit()
            return cj_batch.id, essays

    def _create_comparison_task(
        self,
        essay_a_id: str,
        essay_b_id: str,
        essay_a_content: str = "Content A",
        essay_b_content: str = "Content B",
    ) -> ComparisonTask:
        """Create a comparison task for testing."""
        return ComparisonTask(
            essay_a=EssayForComparison(
                id=essay_a_id,
                text_content=essay_a_content,
                current_bt_score=0.0,
            ),
            essay_b=EssayForComparison(
                id=essay_b_id,
                text_content=essay_b_content,
                current_bt_score=0.0,
            ),
            prompt="Compare these essays for retry testing",
        )

    async def test_add_failed_comparison_to_pool(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test that failed comparisons are correctly added to the pool."""
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository)
        
        # Create pool manager
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        # Create a failed comparison task
        comparison_task = self._create_comparison_task(
            essay_a_id=essays[0].els_essay_id,
            essay_b_id=essays[1].els_essay_id,
            essay_a_content=essays[0].assessment_input_text,
            essay_b_content=essays[1].assessment_input_text,
        )
        
        correlation_id = uuid4()
        
        # Add to failed pool
        await pool_manager.add_to_failed_pool(
            cj_batch_id=batch_id,
            comparison_task=comparison_task,
            failure_reason="LLM timeout during comparison",
            correlation_id=correlation_id,
        )
        
        # Verify pool was updated
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=correlation_id,
            )
            
            assert batch_state.processing_metadata is not None
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            # Check pool contents
            assert len(failed_pool.failed_comparison_pool) == 1
            failed_entry = failed_pool.failed_comparison_pool[0]
            
            assert failed_entry.essay_a_id == essays[0].els_essay_id
            assert failed_entry.essay_b_id == essays[1].els_essay_id
            assert failed_entry.failure_reason == "LLM timeout during comparison"
            assert failed_entry.retry_count == 0
            assert failed_entry.original_batch_id == str(batch_id)
            assert failed_entry.correlation_id == correlation_id
            
            # Check statistics
            assert failed_pool.pool_statistics.total_failed == 1
            assert failed_pool.pool_statistics.permanently_failed == 0

    async def test_threshold_based_retry_batch_formation(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test that retry batches are formed when threshold is reached."""
        # Configure test settings
        test_settings.ENABLE_FAILED_COMPARISON_RETRY = True
        test_settings.FAILED_COMPARISON_RETRY_THRESHOLD = 3
        test_settings.RETRY_BATCH_SIZE = 5
        test_settings.MAX_RETRY_ATTEMPTS = 2
        
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository, essay_count=6)
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        # Add failures below threshold
        for i in range(2):
            comparison_task = self._create_comparison_task(
                essay_a_id=essays[i].els_essay_id,
                essay_b_id=essays[i + 1].els_essay_id,
            )
            await pool_manager.add_to_failed_pool(
                cj_batch_id=batch_id,
                comparison_task=comparison_task,
                failure_reason=f"Failure {i}",
                correlation_id=uuid4(),
            )
        
        # Check retry not needed (below threshold)
        retry_needed = await pool_manager.check_retry_batch_needed(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=False,
        )
        assert not retry_needed, "Should not trigger retry below threshold"
        
        # Add one more to reach threshold
        comparison_task = self._create_comparison_task(
            essay_a_id=essays[2].els_essay_id,
            essay_b_id=essays[3].els_essay_id,
        )
        await pool_manager.add_to_failed_pool(
            cj_batch_id=batch_id,
            comparison_task=comparison_task,
            failure_reason="Failure 3",
            correlation_id=uuid4(),
        )
        
        # Check retry needed (at threshold)
        retry_needed = await pool_manager.check_retry_batch_needed(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=False,
        )
        assert retry_needed, "Should trigger retry at threshold"
        
        # Form retry batch
        retry_tasks = await pool_manager.form_retry_batch(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=False,
        )
        
        assert retry_tasks is not None
        assert len(retry_tasks) == 3, "Should form batch with all 3 failed comparisons"
        
        # Verify retry counts were incremented
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            # All entries should have retry_count = 1
            for entry in failed_pool.failed_comparison_pool:
                assert entry.retry_count == 1
            
            # Statistics should be updated
            assert failed_pool.pool_statistics.retry_attempts == 1

    async def test_end_of_batch_fairness_retry(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test that force_retry_all processes any remaining failures for fairness."""
        # Configure settings
        test_settings.ENABLE_FAILED_COMPARISON_RETRY = True
        test_settings.FAILED_COMPARISON_RETRY_THRESHOLD = 5  # High threshold
        test_settings.MAX_RETRY_ATTEMPTS = 3
        
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository)
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        # Add 2 failures (below threshold)
        for i in range(2):
            comparison_task = self._create_comparison_task(
                essay_a_id=essays[i].els_essay_id,
                essay_b_id=essays[i + 1].els_essay_id,
            )
            await pool_manager.add_to_failed_pool(
                cj_batch_id=batch_id,
                comparison_task=comparison_task,
                failure_reason=f"End-of-batch failure {i}",
                correlation_id=uuid4(),
            )
        
        # Check normal retry (should not trigger due to high threshold)
        retry_needed = await pool_manager.check_retry_batch_needed(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=False,
        )
        assert not retry_needed, "Should not trigger normal retry below threshold"
        
        # Check force retry (should trigger for fairness)
        retry_needed = await pool_manager.check_retry_batch_needed(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=True,
        )
        assert retry_needed, "Should trigger retry with force_retry_all"
        
        # Form retry batch with force_retry_all
        retry_tasks = await pool_manager.form_retry_batch(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=True,
        )
        
        assert retry_tasks is not None
        assert len(retry_tasks) == 2, "Should process all remaining failures"
        
        # Verify pool statistics reflect fairness processing
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            assert failed_pool.pool_statistics.retry_attempts == 1
            assert all(entry.retry_count == 1 for entry in failed_pool.failed_comparison_pool)

    async def test_retry_count_and_permanent_failure(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test that comparisons are marked permanently failed after max retries."""
        # Configure settings
        test_settings.ENABLE_FAILED_COMPARISON_RETRY = True
        test_settings.FAILED_COMPARISON_RETRY_THRESHOLD = 1
        test_settings.MAX_RETRY_ATTEMPTS = 2  # Allow only 2 retry attempts
        test_settings.RETRY_BATCH_SIZE = 10
        
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository)
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        # Add a failed comparison
        comparison_task = self._create_comparison_task(
            essay_a_id=essays[0].els_essay_id,
            essay_b_id=essays[1].els_essay_id,
        )
        await pool_manager.add_to_failed_pool(
            cj_batch_id=batch_id,
            comparison_task=comparison_task,
            failure_reason="Persistent failure",
            correlation_id=uuid4(),
        )
        
        # First retry
        retry_tasks_1 = await pool_manager.form_retry_batch(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=False,
        )
        assert retry_tasks_1 is not None
        assert len(retry_tasks_1) == 1
        
        # Verify retry count = 1
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            assert failed_pool.failed_comparison_pool[0].retry_count == 1
        
        # Second retry
        retry_tasks_2 = await pool_manager.form_retry_batch(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=False,
        )
        assert retry_tasks_2 is not None
        assert len(retry_tasks_2) == 1
        
        # After second retry, entry should be removed (permanently failed)
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            # Pool should be empty (entry removed as permanently failed)
            assert len(failed_pool.failed_comparison_pool) == 0
            
            # Statistics should reflect permanent failure
            assert failed_pool.pool_statistics.permanently_failed == 1
            assert failed_pool.pool_statistics.retry_attempts == 2

    async def test_pool_statistics_tracking(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test that pool statistics are accurately tracked."""
        # Configure settings
        test_settings.ENABLE_FAILED_COMPARISON_RETRY = True
        test_settings.FAILED_COMPARISON_RETRY_THRESHOLD = 2
        test_settings.MAX_RETRY_ATTEMPTS = 3
        
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository, essay_count=6)
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        # Add multiple failures
        for i in range(4):
            comparison_task = self._create_comparison_task(
                essay_a_id=essays[i].els_essay_id,
                essay_b_id=essays[(i + 1) % 6].els_essay_id,
            )
            await pool_manager.add_to_failed_pool(
                cj_batch_id=batch_id,
                comparison_task=comparison_task,
                failure_reason=f"Stats test failure {i}",
                correlation_id=uuid4(),
            )
        
        # Check initial statistics
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            assert failed_pool.pool_statistics.total_failed == 4
            assert failed_pool.pool_statistics.retry_attempts == 0
            assert failed_pool.pool_statistics.permanently_failed == 0
            assert failed_pool.pool_statistics.successful_retries == 0
        
        # Form retry batch
        correlation_id = uuid4()
        retry_tasks = await pool_manager.form_retry_batch(
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
            force_retry_all=False,
        )
        
        assert retry_tasks is not None
        assert len(retry_tasks) == 4  # All 4 failures should be retried
        
        # Check updated statistics
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            assert failed_pool.pool_statistics.retry_attempts == 1
            assert failed_pool.pool_statistics.last_retry_batch == f"retry_batch_{correlation_id}"
            # All entries still in pool with retry_count = 1
            assert len(failed_pool.failed_comparison_pool) == 4
            assert all(entry.retry_count == 1 for entry in failed_pool.failed_comparison_pool)

    async def test_failed_pool_persistence(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test that failed pool data persists correctly in processing_metadata."""
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository)
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        # Add failed comparisons with various metadata
        correlation_ids = []
        for i in range(3):
            comparison_task = self._create_comparison_task(
                essay_a_id=essays[i].els_essay_id,
                essay_b_id=essays[i + 1].els_essay_id,
            )
            corr_id = uuid4()
            correlation_ids.append(corr_id)
            
            await pool_manager.add_to_failed_pool(
                cj_batch_id=batch_id,
                comparison_task=comparison_task,
                failure_reason=f"Persistence test failure {i}",
                correlation_id=corr_id,
            )
        
        # Read pool data back
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            
            assert batch_state.processing_metadata is not None
            
            # Validate pool can be reconstructed from metadata
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            assert len(failed_pool.failed_comparison_pool) == 3
            
            # Verify all data is preserved
            for i, entry in enumerate(failed_pool.failed_comparison_pool):
                assert entry.essay_a_id == essays[i].els_essay_id
                assert entry.essay_b_id == essays[i + 1].els_essay_id
                assert entry.failure_reason == f"Persistence test failure {i}"
                assert entry.retry_count == 0
                assert entry.original_batch_id == str(batch_id)
                assert entry.correlation_id == correlation_ids[i]
                assert entry.comparison_task is not None
                assert entry.comparison_task.prompt == "Compare these essays for retry testing"
        
        # Modify pool and verify persistence
        await pool_manager.form_retry_batch(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=True,
        )
        
        # Read modified pool
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            # All entries should have incremented retry count
            assert all(entry.retry_count == 1 for entry in failed_pool.failed_comparison_pool)
            assert failed_pool.pool_statistics.retry_attempts == 1

    async def test_retry_batch_submission_flow(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test the full retry batch submission flow."""
        # Configure settings
        test_settings.ENABLE_FAILED_COMPARISON_RETRY = True
        test_settings.FAILED_COMPARISON_RETRY_THRESHOLD = 2
        test_settings.MAX_RETRY_ATTEMPTS = 2
        
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository)
        
        # Mock dependencies
        mock_llm_interaction = AsyncMock(spec=LLMInteractionProtocol)
        mock_batch_submitter = AsyncMock(spec=BatchProcessorProtocol)
        
        # Configure mock batch submitter
        mock_batch_submitter.submit_comparison_batch.return_value = BatchSubmissionResult(
            batch_id=batch_id,
            total_submitted=2,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=uuid4(),
        )
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        retry_processor = BatchRetryProcessor(
            database=postgres_repository,
            llm_interaction=mock_llm_interaction,
            settings=test_settings,
            pool_manager=pool_manager,
            batch_submitter=mock_batch_submitter,
        )
        
        # Add failures to trigger retry
        for i in range(2):
            comparison_task = self._create_comparison_task(
                essay_a_id=essays[i].els_essay_id,
                essay_b_id=essays[i + 1].els_essay_id,
            )
            await pool_manager.add_to_failed_pool(
                cj_batch_id=batch_id,
                comparison_task=comparison_task,
                failure_reason=f"Submission test failure {i}",
                correlation_id=uuid4(),
            )
        
        # Submit retry batch
        result = await retry_processor.submit_retry_batch(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
            force_retry_all=False,
        )
        
        assert result is not None
        assert result.total_submitted == 2
        
        # Verify batch submitter was called correctly
        mock_batch_submitter.submit_comparison_batch.assert_called_once()
        call_args = mock_batch_submitter.submit_comparison_batch.call_args
        
        assert call_args.kwargs["cj_batch_id"] == batch_id
        assert len(call_args.kwargs["comparison_tasks"]) == 2
        assert call_args.kwargs["config_overrides"] is None
        
        # Verify pool was updated
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            assert failed_pool.pool_statistics.retry_attempts == 1
            assert all(entry.retry_count == 1 for entry in failed_pool.failed_comparison_pool)

    async def test_concurrent_failure_handling(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test that concurrent additions to failed pool are handled correctly.
        
        With SELECT FOR UPDATE locking, all concurrent updates should be preserved.
        """
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository, essay_count=10)
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        # Create concurrent add tasks
        async def add_failure(index: int) -> None:
            comparison_task = self._create_comparison_task(
                essay_a_id=essays[index].els_essay_id,
                essay_b_id=essays[(index + 1) % 10].els_essay_id,
            )
            await pool_manager.add_to_failed_pool(
                cj_batch_id=batch_id,
                comparison_task=comparison_task,
                failure_reason=f"Concurrent failure {index}",
                correlation_id=uuid4(),
            )
        
        # Add failures concurrently
        tasks = [add_failure(i) for i in range(8)]
        await asyncio.gather(*tasks)
        
        # Verify all failures were recorded correctly
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            # With proper locking, all 8 failures should be recorded
            assert len(failed_pool.failed_comparison_pool) == 8, "All concurrent failures should be recorded"
            assert failed_pool.pool_statistics.total_failed == 8
            
            # Verify no duplicates
            seen_pairs = set()
            for entry in failed_pool.failed_comparison_pool:
                pair_key = (entry.essay_a_id, entry.essay_b_id)
                assert pair_key not in seen_pairs, f"Duplicate pair found: {pair_key}"
                seen_pairs.add(pair_key)
            
            # Verify all have correct initial state
            for entry in failed_pool.failed_comparison_pool:
                assert entry.retry_count == 0
                assert entry.original_batch_id == str(batch_id)
                assert "Concurrent failure" in entry.failure_reason

    async def test_process_remaining_failed_comparisons(
        self,
        postgres_repository: CJRepositoryProtocol,
        test_settings: Settings,
    ) -> None:
        """Test the end-of-batch processing of remaining failed comparisons."""
        # Configure settings
        test_settings.ENABLE_FAILED_COMPARISON_RETRY = True
        test_settings.FAILED_COMPARISON_RETRY_THRESHOLD = 10  # Very high threshold
        test_settings.MAX_RETRY_ATTEMPTS = 3
        
        # Create test batch
        batch_id, essays = await self._create_test_batch(postgres_repository)
        
        # Mock dependencies
        mock_llm_interaction = AsyncMock(spec=LLMInteractionProtocol)
        mock_batch_submitter = AsyncMock(spec=BatchProcessorProtocol)
        
        # Configure mock batch submitter
        mock_batch_submitter.submit_comparison_batch.return_value = BatchSubmissionResult(
            batch_id=batch_id,
            total_submitted=3,
            submitted_at=datetime.now(UTC),
            all_submitted=True,
            correlation_id=uuid4(),
        )
        
        pool_manager = BatchPoolManager(
            database=postgres_repository,
            settings=test_settings,
        )
        
        retry_processor = BatchRetryProcessor(
            database=postgres_repository,
            llm_interaction=mock_llm_interaction,
            settings=test_settings,
            pool_manager=pool_manager,
            batch_submitter=mock_batch_submitter,
        )
        
        # Add 3 failures (well below threshold)
        for i in range(3):
            comparison_task = self._create_comparison_task(
                essay_a_id=essays[i].els_essay_id,
                essay_b_id=essays[(i + 1) % 5].els_essay_id,
            )
            await pool_manager.add_to_failed_pool(
                cj_batch_id=batch_id,
                comparison_task=comparison_task,
                failure_reason=f"End-of-batch test failure {i}",
                correlation_id=uuid4(),
            )
        
        # Process remaining failed comparisons (simulating end of batch)
        result = await retry_processor.process_remaining_failed_comparisons(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )
        
        assert result is not None
        assert result.total_submitted == 3
        
        # Verify force_retry_all was used
        mock_batch_submitter.submit_comparison_batch.assert_called_once()
        
        # Verify pool was updated
        async with postgres_repository.session() as session:
            batch_state = await get_batch_state(
                session=session,
                cj_batch_id=batch_id,
                correlation_id=uuid4(),
            )
            
            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            
            # All entries should have been retried
            assert failed_pool.pool_statistics.retry_attempts == 1
            assert all(entry.retry_count == 1 for entry in failed_pool.failed_comparison_pool)
            
            # Should still have 3 entries (not removed yet)
            assert len(failed_pool.failed_comparison_pool) == 3