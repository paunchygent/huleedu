"""Integration test for multi-round batch state accumulation.

This test validates that CJ batch state correctly accumulates totals across multiple
iterations (simulating a 100-comparison batch processed in 10 chunks of 10),
ensuring that total_budget remains locked and counters increment monotonically.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum

from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.implementations.session_provider_impl import (
    CJSessionProviderImpl,
)
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import LLMInteractionProtocol
from services.cj_assessment_service.tests.fixtures.database_fixtures import PostgresDataAccess


@pytest.mark.integration
class TestBatchStateMultiRoundIntegration:
    """Integration test for multi-round batch state accumulation."""

    async def test_multi_round_batch_accumulation(
        self,
        postgres_data_access: PostgresDataAccess,
        postgres_session_provider: CJSessionProviderImpl,
    ) -> None:
        """Simulate 100-comparison batch with 10 submissions of 10 comparisons each.

        Verify:
        - total_budget = 100 (set once, never changes)
        - total_comparisons accumulates: 10 -> 20 -> 30 -> ... -> 100
        - submitted_comparisons accumulates: 10 -> 20 -> 30 -> ... -> 100
        - current_iteration increments: 1 -> 2 -> 3 -> ... -> 10
        - Final state matches database reality
        """
        # 1. Setup: Create a batch in the database
        async with postgres_session_provider.session() as session:
            cj_batch = await postgres_data_access.create_new_cj_batch(
                session=session,
                bos_batch_id="multi-round-test-batch",
                event_correlation_id=str(uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=10,
            )
            # Seed metadata with the budget we expect
            cj_batch.processing_metadata = {"comparison_budget": {"max_pairs_requested": 100}}

            # Initialize state record (created by trigger/service method)
            batch_state = await session.get(CJBatchState, cj_batch.id)
            if not batch_state:
                # Fallback if not created automatically (though it should be)
                batch_state = CJBatchState(
                    batch_id=cj_batch.id,
                    state=CJBatchStateEnum.GENERATING_PAIRS,
                    total_budget=None,
                    total_comparisons=0,
                    submitted_comparisons=0,
                    completed_comparisons=0,
                    failed_comparisons=0,
                    current_iteration=0,
                )
                session.add(batch_state)
            else:
                # Reset/Ensure state for test
                batch_state.state = CJBatchStateEnum.GENERATING_PAIRS
                batch_state.total_budget = None
                batch_state.total_comparisons = 0
                batch_state.submitted_comparisons = 0
                batch_state.completed_comparisons = 0
                batch_state.failed_comparisons = 0
                batch_state.current_iteration = 0

            # Ensure batch_state has the metadata for budget resolution
            batch_state.processing_metadata = {"comparison_budget": {"max_pairs_requested": 100}}

            await session.commit()
            batch_id = cj_batch.id

        # 2. Setup BatchProcessor with real repository but mock LLM
        batch_processor = BatchProcessor(
            session_provider=postgres_session_provider,
            llm_interaction=AsyncMock(spec=LLMInteractionProtocol),
            settings=Settings(),
            batch_repository=postgres_data_access.batch_repo,
        )

        # 3. Simulate 10 iterations
        total_iterations = 10
        comparisons_per_iteration = 10

        for i in range(1, total_iterations + 1):
            # Call the update method directly (simulating what happens during submission)
            await batch_processor._update_batch_state_with_totals(
                cj_batch_id=batch_id,
                state=CJBatchStateEnum.WAITING_CALLBACKS,
                iteration_comparisons=comparisons_per_iteration,
                correlation_id=uuid4(),
            )

            # Verify state after this iteration
            async with postgres_session_provider.session() as session:
                state = await session.get(CJBatchState, batch_id)
                assert state is not None

                # Total budget should be locked at 100 from the first iteration
                assert state.total_budget == 100

                # Counters should accumulate
                expected_total = i * comparisons_per_iteration
                assert state.total_comparisons == expected_total
                assert state.submitted_comparisons == expected_total

                # Iteration count should track loop index
                assert state.current_iteration == i

                # State should be WAITING_CALLBACKS
                assert state.state == CJBatchStateEnum.WAITING_CALLBACKS

        # 4. Final verification
        async with postgres_session_provider.session() as session:
            final_state = await session.get(CJBatchState, batch_id)
            assert final_state is not None
            assert final_state.total_budget == 100
            assert final_state.total_comparisons == 100
            assert final_state.submitted_comparisons == 100
            assert final_state.current_iteration == 10
