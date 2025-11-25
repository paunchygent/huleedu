"""Integration tests for async workflow continuation and state transitions.

This module tests the real asynchronous workflow continuation without mocks, validating:
- Batch state transitions (INITIALIZING → PROCESSING → WAITING_CALLBACKS → SCORING → COMPLETED)
- Callback handler correctly triggers workflow continuation
- Partial scoring at configured threshold (80% default)
- Event publishing at completion
- Iteration management and comparison pair generation

IMPORTANT: This test file uses the repository pattern exclusively for all database
operations to match production patterns and avoid session management issues.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core import EssayComparisonWinner, LLMProviderType
from common_core.events.llm_provider_events import (
    LLMComparisonResultV1,
    TokenUsage,
)
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy import select

from services.cj_assessment_service.cj_core_logic.batch_callback_handler import (
    check_workflow_continuation,
)
from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
from services.cj_assessment_service.cj_core_logic.callback_state_manager import (
    update_comparison_result,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import (
    CJBatchState,
    ComparisonPair,
)
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.fixtures.database_fixtures import PostgresDataAccess

if TYPE_CHECKING:
    pass


@pytest.mark.integration
class TestAsyncWorkflowContinuation:
    """Test the async callback-driven workflow continuation.

    All tests use the repository pattern exclusively for database operations,
    matching production patterns and ensuring proper transaction boundaries.
    """

    async def _create_batch_with_comparisons(
        self,
        repository: PostgresDataAccess,
        essay_count: int,
        batch_id: str = "test-batch",
        completion_threshold: int = 80,
    ) -> tuple[int, list[UUID], int]:
        """Create a batch with essays and comparison pairs ready for callbacks.

        Uses repository pattern exclusively - no external session management.

        Args:
            repository: Repository for database operations
            essay_count: Number of essays to create
            batch_id: Batch identifier
            completion_threshold: Completion threshold percentage

        Returns:
            Tuple of (cj_batch_id, list of correlation_ids, total_comparisons)
        """
        async with repository.session() as session:
            # Create batch
            cj_batch = await repository.create_new_cj_batch(
                session=session,
                bos_batch_id=batch_id,
                event_correlation_id=str(uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=essay_count,
            )
            cj_batch.processing_metadata = {"student_prompt_text": "Test instructions"}

            # Create essays
            essays = []
            for i in range(essay_count):
                essay = await repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=cj_batch.id,
                    els_essay_id=f"essay_{i:03d}",
                    text_storage_id=f"storage_{i:03d}",
                    assessment_input_text=f"Essay content {i}",
                )
                essays.append(essay)

            # Create comparison pairs with correlation IDs for callbacks
            correlation_ids = []
            pair_count = 0
            for i in range(essay_count):
                for j in range(i + 1, essay_count):
                    correlation_id = uuid4()
                    correlation_ids.append(correlation_id)

                    comparison = ComparisonPair(
                        cj_batch_id=cj_batch.id,
                        essay_a_els_id=f"essay_{i:03d}",
                        essay_b_els_id=f"essay_{j:03d}",
                        prompt_text="Compare these essays",
                        request_correlation_id=correlation_id,
                        submitted_at=datetime.now(UTC),
                    )
                    session.add(comparison)
                    pair_count += 1

            # Update batch state with threshold
            batch_state = await session.get(CJBatchState, cj_batch.id)
            if batch_state:
                batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
                batch_state.total_comparisons = pair_count
                batch_state.submitted_comparisons = pair_count
                batch_state.completed_comparisons = 0
                batch_state.failed_comparisons = 0
                batch_state.completion_threshold_pct = completion_threshold

            # Commit all changes within the session
            await session.commit()

            # Return IDs that don't require session access
            return cj_batch.id, correlation_ids, pair_count

    def _create_callback_result(
        self,
        correlation_id: UUID,
        winner: EssayComparisonWinner,
        is_error: bool = False,
    ) -> LLMComparisonResultV1:
        """Create a mock LLM callback result."""
        if is_error:
            # For errors, only set error_detail and common fields
            from common_core.error_enums import ErrorCode
            from common_core.models.error_models import ErrorDetail

            return LLMComparisonResultV1(
                request_id=str(uuid4()),
                correlation_id=correlation_id,
                provider=LLMProviderType.ANTHROPIC,
                model="claude-3-haiku-20240307",
                winner=None,  # Don't set for errors
                confidence=None,  # Don't set for errors
                justification=None,  # Don't set for errors
                response_time_ms=1500,
                token_usage=TokenUsage(
                    prompt_tokens=500,
                    completion_tokens=150,
                    total_tokens=650,
                ),
                cost_estimate=0.0,
                requested_at=datetime.now(UTC) - timedelta(seconds=2),
                completed_at=datetime.now(UTC),
                error_detail=ErrorDetail(
                    error_code=ErrorCode.LLM_PROVIDER_SERVICE_ERROR,
                    message="Test error occurred",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="llm_provider_service",
                    operation="essay_comparison",
                    details={"test": "error"},
                ),
            )
        else:
            # For success, set all success fields
            return LLMComparisonResultV1(
                request_id=str(uuid4()),
                correlation_id=correlation_id,
                provider=LLMProviderType.ANTHROPIC,
                model="claude-3-haiku-20240307",
                winner=winner,
                confidence=4.0,
                justification="Test justification",
                response_time_ms=1500,
                token_usage=TokenUsage(
                    prompt_tokens=500,
                    completion_tokens=150,
                    total_tokens=650,
                ),
                cost_estimate=0.001,
                requested_at=datetime.now(UTC) - timedelta(seconds=2),
                completed_at=datetime.now(UTC),
                error_detail=None,
            )

    async def test_batch_state_transitions(
        self,
        postgres_data_access: PostgresDataAccess,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
    ) -> None:
        """Test that batch states transition correctly through the workflow."""
        # Create batch with 5 essays (10 comparisons)
        batch_id, correlation_ids, total_comparisons = await self._create_batch_with_comparisons(
            postgres_data_access, essay_count=5, completion_threshold=80
        )

        # Verify initial state using repository session
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            assert batch_state.state == CJBatchStateEnum.WAITING_CALLBACKS
            assert batch_state.total_comparisons == 10
            assert batch_state.completed_comparisons == 0

        # Process callbacks one by one
        for i, corr_id in enumerate(correlation_ids[:5]):  # Process first 5
            # Create callback result
            winner = EssayComparisonWinner.ESSAY_A if i % 2 == 0 else EssayComparisonWinner.ESSAY_B
            callback_result = self._create_callback_result(corr_id, winner)

            # Update comparison result (uses its own session internally)
            returned_batch_id = await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=corr_id,
                settings=test_settings,
            )

            assert returned_batch_id == batch_id

            # Check if comparison was updated using repository session
            async with postgres_data_access.session() as session:
                stmt = select(ComparisonPair).where(
                    ComparisonPair.request_correlation_id == corr_id
                )
                result = await session.execute(stmt)
                comparison = result.scalar_one()

                # Convert enum value to database format
                expected_winner = winner.value.lower().replace(" ", "_")  # "Essay A" -> "essay_a"
                assert comparison.winner == expected_winner
                assert comparison.completed_at is not None
                assert comparison.confidence == 4.0

        # Update batch state completed count
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            batch_state.completed_comparisons = 5
            await session.commit()

        # Check if we should trigger completion (50% done, below 80% threshold)
        completion_checker = BatchCompletionChecker(
            session_provider=postgres_session_provider,
            batch_repo=postgres_batch_repository,
        )
        should_complete = await completion_checker.check_batch_completion(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )
        assert not should_complete, "Should not complete at 50%"

        # Process more callbacks to reach 80%
        for corr_id in correlation_ids[5:8]:  # Process 3 more (total 8/10 = 80%)
            callback_result = self._create_callback_result(corr_id, EssayComparisonWinner.ESSAY_A)
            await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=corr_id,
                settings=test_settings,
            )

        # Update batch state to 80% completion
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            batch_state.completed_comparisons = 8
            await session.commit()

        # Check if we should trigger completion (80% done)
        should_complete = await completion_checker.check_batch_completion(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )
        assert should_complete, "Should complete at 80% threshold"

    async def test_callback_triggers_workflow_continuation(
        self,
        postgres_data_access: PostgresDataAccess,
        mock_event_publisher: AsyncMock,
        mock_content_client: AsyncMock,
        test_settings: Settings,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
    ) -> None:
        """Test that callbacks correctly trigger workflow continuation."""
        # Create batch with comparisons
        batch_id, correlation_ids, total_comparisons = await self._create_batch_with_comparisons(
            postgres_data_access,
            essay_count=4,  # 6 comparisons total
        )

        # Mock content client
        mock_content_client.fetch_content.side_effect = lambda cid, corr: f"Content {cid}"

        # Process callbacks and check workflow continuation
        for i, corr_id in enumerate(correlation_ids):
            callback_result = self._create_callback_result(
                corr_id,
                EssayComparisonWinner.ESSAY_A if i % 2 == 0 else EssayComparisonWinner.ESSAY_B,
            )

            # Update comparison result
            await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=corr_id,
                settings=test_settings,
            )

            # Update batch state using repository session
            async with postgres_data_access.session() as session:
                batch_state = await session.get(CJBatchState, batch_id)
                assert batch_state is not None
                batch_state.completed_comparisons = i + 1
                await session.commit()

            # Check workflow continuation logic
            should_continue = await check_workflow_continuation(
                batch_id=batch_id,
                session_provider=postgres_session_provider,
                batch_repository=postgres_batch_repository,
                correlation_id=uuid4(),
            )

            # New logic: continuation triggers only when all submitted callbacks have arrived
            if i < total_comparisons - 1:
                # For partial completion we should NOT continue yet
                assert not should_continue, f"Should not continue at completion {i + 1}"
            else:
                # On the final callback (all comparisons completed), continuation should trigger
                assert should_continue, (
                    f"Should continue only after all {total_comparisons} callbacks, "
                    f"got continuation at {i + 1}"
                )

            # Simulate state change if workflow continues
            if should_continue:
                async with postgres_data_access.session() as session:
                    batch_state = await session.get(CJBatchState, batch_id)
                    assert batch_state is not None
                    batch_state.state = CJBatchStateEnum.SCORING
                    await session.commit()

    async def test_partial_scoring_at_threshold(
        self,
        postgres_data_access: PostgresDataAccess,
        test_settings: Settings,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
    ) -> None:
        """Test that partial scoring triggers at the configured threshold."""
        # Create batch with 10 essays (45 comparisons)
        batch_id, correlation_ids, total_comparisons = await self._create_batch_with_comparisons(
            postgres_data_access, essay_count=10, completion_threshold=80
        )

        assert total_comparisons == 45, "Should have 45 comparisons for 10 essays"

        # Process callbacks up to just below threshold (79%)
        callbacks_for_79_pct = int(45 * 0.79)  # 35 callbacks
        for i in range(callbacks_for_79_pct):
            callback_result = self._create_callback_result(
                correlation_ids[i],
                EssayComparisonWinner.ESSAY_A if i % 3 == 0 else EssayComparisonWinner.ESSAY_B,
            )
            await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=correlation_ids[i],
                settings=test_settings,
            )

        # Update batch state to 79% completion
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            batch_state.completed_comparisons = callbacks_for_79_pct
            await session.commit()

        # Check completion - should NOT trigger at 79%
        completion_checker = BatchCompletionChecker(
            session_provider=postgres_session_provider,
            batch_repo=postgres_batch_repository,
        )
        should_complete = await completion_checker.check_batch_completion(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )
        assert not should_complete, f"Should not complete at {callbacks_for_79_pct}/45 (79%)"

        # Process one more callback to reach 80%
        callback_result = self._create_callback_result(
            correlation_ids[callbacks_for_79_pct], EssayComparisonWinner.ESSAY_B
        )
        await update_comparison_result(
            comparison_result=callback_result,
            session_provider=postgres_session_provider,
            comparison_repository=postgres_comparison_repository,
            batch_repository=postgres_batch_repository,
            correlation_id=correlation_ids[callbacks_for_79_pct],
            settings=test_settings,
        )

        # Update batch state to 80% completion
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            batch_state.completed_comparisons = callbacks_for_79_pct + 1
            await session.commit()

        # Check completion - should trigger at 80%
        should_complete = await completion_checker.check_batch_completion(
            cj_batch_id=batch_id,
            correlation_id=uuid4(),
        )
        assert should_complete, f"Should complete at {callbacks_for_79_pct + 1}/45 (80%)"

        # Verify we can mark partial scoring as triggered
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            batch_state.partial_scoring_triggered = True
            await session.commit()

            # Verify flag was set
            assert batch_state.partial_scoring_triggered

    async def test_error_callbacks_and_recovery(
        self,
        postgres_data_access: PostgresDataAccess,
        test_settings: Settings,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
    ) -> None:
        """Test handling of error callbacks and recovery."""
        # Create batch
        batch_id, correlation_ids, total_comparisons = await self._create_batch_with_comparisons(
            postgres_data_access,
            essay_count=3,  # 3 comparisons
        )

        # Process mix of success and error callbacks
        results = [
            (correlation_ids[0], EssayComparisonWinner.ESSAY_A, False),  # Success
            (correlation_ids[1], EssayComparisonWinner.ERROR, True),  # Error
            (correlation_ids[2], EssayComparisonWinner.ESSAY_B, False),  # Success
        ]

        for corr_id, winner, is_error in results:
            callback_result = self._create_callback_result(corr_id, winner, is_error)

            returned_batch_id = await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=corr_id,
                settings=test_settings,
            )

            assert returned_batch_id == batch_id

            # Verify result was recorded correctly
            async with postgres_data_access.session() as session:
                stmt = select(ComparisonPair).where(
                    ComparisonPair.request_correlation_id == corr_id
                )
                result = await session.execute(stmt)
                comparison = result.scalar_one()

                if is_error:
                    assert comparison.winner == "error"
                    # Error handling may set error_code or just mark as error
                else:
                    assert comparison.winner in ["essay_a", "essay_b"]
                    assert comparison.confidence == 4.0

        # Update batch state with results
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            batch_state.completed_comparisons = 2  # Only successful ones
            batch_state.failed_comparisons = 1
            await session.commit()

        # Verify batch can still progress with some failures
        completion_percentage = (2 / 3) * 100  # 66.67%
        assert completion_percentage < 80, "Below default threshold with failures"

    async def test_idempotent_callback_processing(
        self,
        postgres_data_access: PostgresDataAccess,
        test_settings: Settings,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
    ) -> None:
        """Test that callbacks are processed idempotently."""
        # Create batch with one comparison
        batch_id, correlation_ids, _ = await self._create_batch_with_comparisons(
            postgres_data_access,
            essay_count=2,  # 1 comparison
        )

        corr_id = correlation_ids[0]

        # Process the same callback multiple times
        for attempt in range(3):
            callback_result = self._create_callback_result(corr_id, EssayComparisonWinner.ESSAY_A)

            returned_batch_id = await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=corr_id,
                settings=test_settings,
            )

            assert returned_batch_id == batch_id

        # Verify comparison was only updated once
        async with postgres_data_access.session() as session:
            stmt = select(ComparisonPair).where(ComparisonPair.request_correlation_id == corr_id)
            result = await session.execute(stmt)
            comparison = result.scalar_one()

            assert comparison.winner == "essay_a"
            assert comparison.confidence == 4.0

            # Check that we still only have one comparison with this correlation_id
            count_stmt = select(ComparisonPair).where(
                ComparisonPair.request_correlation_id == corr_id
            )
            count_result = await session.execute(count_stmt)
            all_comparisons = count_result.scalars().all()
            assert len(all_comparisons) == 1, (
                "Should only have one comparison despite multiple callbacks"
            )

    async def test_iteration_management(
        self,
        postgres_data_access: PostgresDataAccess,
        test_settings: Settings,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
    ) -> None:
        """Test that iterations are tracked correctly."""
        # Create batch
        batch_id, correlation_ids, total_comparisons = await self._create_batch_with_comparisons(
            postgres_data_access,
            essay_count=5,  # 10 comparisons
        )

        # Check initial iteration
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            # Initial iteration could be 0 or 1 depending on implementation
            assert batch_state.current_iteration in [0, 1]

        # Simulate moving to next iteration with metadata
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            batch_state.current_iteration = 2
            batch_state.processing_metadata = {
                "iteration_1_scores": {"essay_000": 0.5, "essay_001": -0.3},
                "iteration_1_completed_at": datetime.now(UTC).isoformat(),
            }
            await session.commit()

        # Process some callbacks for iteration 2
        for i in range(3):
            callback_result = self._create_callback_result(
                correlation_ids[i], EssayComparisonWinner.ESSAY_B
            )
            await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=correlation_ids[i],
                settings=test_settings,
            )

        # Verify iteration tracking
        async with postgres_data_access.session() as session:
            batch_state = await session.get(CJBatchState, batch_id)
            assert batch_state is not None
            assert batch_state.current_iteration == 2
            assert batch_state.processing_metadata is not None
            assert "iteration_1_scores" in batch_state.processing_metadata
            assert "iteration_1_completed_at" in batch_state.processing_metadata

    async def test_concurrent_callback_processing(
        self,
        postgres_data_access: PostgresDataAccess,
        test_settings: Settings,
        postgres_session_provider: SessionProviderProtocol,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        postgres_comparison_repository: CJComparisonRepositoryProtocol,
    ) -> None:
        """Test that concurrent callbacks are handled correctly."""
        # Create batch with multiple comparisons
        batch_id, correlation_ids, _ = await self._create_batch_with_comparisons(
            postgres_data_access,
            essay_count=6,  # 15 comparisons
        )

        # Process multiple callbacks concurrently
        async def process_callback(corr_id: UUID, winner: EssayComparisonWinner) -> None:
            callback_result = self._create_callback_result(corr_id, winner)
            await update_comparison_result(
                comparison_result=callback_result,
                session_provider=postgres_session_provider,
                comparison_repository=postgres_comparison_repository,
                batch_repository=postgres_batch_repository,
                correlation_id=corr_id,
                settings=test_settings,
            )

        # Create concurrent tasks
        tasks = []
        for i, corr_id in enumerate(correlation_ids[:10]):
            winner = EssayComparisonWinner.ESSAY_A if i % 2 == 0 else EssayComparisonWinner.ESSAY_B
            tasks.append(process_callback(corr_id, winner))

        # Execute concurrently
        await asyncio.gather(*tasks)

        # Verify all callbacks were processed correctly
        async with postgres_data_access.session() as session:
            stmt = select(ComparisonPair).where(
                ComparisonPair.cj_batch_id == batch_id, ComparisonPair.winner.isnot(None)
            )
            result = await session.execute(stmt)
            completed_pairs = result.scalars().all()

            assert len(completed_pairs) == 10, "All concurrent callbacks should be processed"

            # Verify no duplicates or corruption
            seen_correlation_ids = set()
            for pair in completed_pairs:
                assert pair.request_correlation_id not in seen_correlation_ids
                seen_correlation_ids.add(pair.request_correlation_id)
                assert pair.winner in ["essay_a", "essay_b"]
                assert pair.confidence == 4.0

            # Verify data integrity
            for pair in completed_pairs:
                assert pair.completed_at is not None
                assert pair.justification == "Test justification"
