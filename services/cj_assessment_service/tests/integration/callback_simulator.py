"""Callback simulator for integration testing of async CJ assessment workflow.

This module provides a clean way to simulate LLM provider callbacks in tests,
allowing the full async workflow to complete without modifying production code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from common_core import EssayComparisonWinner, LLMProviderType
from common_core.events.llm_provider_events import (
    LLMComparisonResultV1,
    TokenUsage,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select

from services.cj_assessment_service.cj_core_logic.batch_callback_handler import (
    continue_cj_assessment_workflow,
)
from services.cj_assessment_service.models_api import ComparisonTask
from services.cj_assessment_service.models_db import ComparisonPair

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.models_api import ComparisonResult
    from services.cj_assessment_service.protocols import (
        AssessmentInstructionRepositoryProtocol,
        CJBatchRepositoryProtocol,
        CJComparisonRepositoryProtocol,
        CJEssayRepositoryProtocol,
        CJEventPublisherProtocol,
        ContentClientProtocol,
        SessionProviderProtocol,
    )

logger = create_service_logger("cj_assessment_service.test.callback_simulator")


class CallbackSimulator:
    """Simulates LLM provider callbacks for integration testing.

    This class bridges the gap between mock LLM responses and the async
    callback-driven workflow, allowing tests to complete the full assessment
    flow without modifying production code.
    """

    async def simulate_callbacks_from_mock_results(
        self,
        mock_llm_interaction: AsyncMock,
        event_publisher: CJEventPublisherProtocol,
        settings: Settings,
        content_client: ContentClientProtocol,
        correlation_id: UUID,
        session_provider: SessionProviderProtocol,
        batch_repository: CJBatchRepositoryProtocol,
        essay_repository: CJEssayRepositoryProtocol,
        comparison_repository: CJComparisonRepositoryProtocol,
        instruction_repository: AssessmentInstructionRepositoryProtocol,
        grade_projector: "GradeProjector",
        cj_batch_id: int | None = None,
    ) -> int:
        """Process mock LLM results as if they were callbacks.

        This method:
        1. Extracts comparison results from the mock LLM interaction
        2. Creates ComparisonPair records (simulating what LLM Provider Service would do)
        3. Creates callback events from the mock results
        4. Processes callbacks through the production callback handler

        Args:
            mock_llm_interaction: Mock LLM interaction with comparison results
            event_publisher: Event publisher for completion events
            settings: Application settings
            content_client: Content client for fetching content if needed
            correlation_id: Original request correlation ID
            session_provider: Session provider for database transactions
            batch_repository: Repository for batch operations
            essay_repository: Repository for essay operations
            comparison_repository: Repository for comparison operations
            instruction_repository: Repository for instruction metadata
            cj_batch_id: Optional CJ batch ID (will be retrieved if not provided)

        Returns:
            Number of callbacks processed
        """
        logger.info("Starting callback simulation", extra={"correlation_id": str(correlation_id)})

        # Extract comparison results from mock
        if not mock_llm_interaction.perform_comparisons.called:
            logger.warning("Mock LLM interaction was not called, no callbacks to simulate")
            return 0

        # Get the comparison tasks and results from the mock call
        call_args = mock_llm_interaction.perform_comparisons.call_args
        logger.debug(f"Mock call_args: {call_args}")

        # Handle both positional and keyword arguments
        if call_args:
            if call_args.args:
                comparison_tasks = call_args.args[0]  # First positional argument
                correlation_arg = call_args.args[1] if len(call_args.args) > 1 else None
            elif call_args.kwargs:
                comparison_tasks = call_args.kwargs.get("tasks", [])
                correlation_arg = call_args.kwargs.get("correlation_id", None)
            else:
                logger.warning("No arguments found in mock call")
                return 0
        else:
            logger.warning("No call_args found in mock")
            return 0

        # Check if the mock has stored submitted tasks (for async mocks)
        if hasattr(mock_llm_interaction, "_submitted_tasks"):
            # This is an async mock that returned None - generate results
            comparison_tasks = mock_llm_interaction._submitted_tasks
            mock_results = self._generate_mock_results(comparison_tasks)
        else:
            # Try to get results from the mock's side_effect or return_value
            original_call_count = mock_llm_interaction.perform_comparisons.call_count

            # Call the side_effect function to get the results
            side_effect = mock_llm_interaction.perform_comparisons.side_effect
            if callable(side_effect):
                # Call with the same args
                mock_results = await side_effect(
                    comparison_tasks,
                    correlation_arg,
                    call_args.kwargs.get("model_override") if call_args.kwargs else None,
                    call_args.kwargs.get("temperature_override") if call_args.kwargs else None,
                    call_args.kwargs.get("max_tokens_override") if call_args.kwargs else None,
                )
            else:
                # If no side_effect, try return_value
                mock_results = mock_llm_interaction.perform_comparisons.return_value
                if hasattr(mock_results, "__await__"):
                    mock_results = await mock_results

            # Reset the call count to what it was before (to avoid double-counting)
            mock_llm_interaction.perform_comparisons.call_count = original_call_count

            # Filter out None results (async processing)
            if mock_results:
                mock_results = [r for r in mock_results if r is not None]

        if not mock_results:
            logger.warning("No mock results returned, no callbacks to simulate")
            return 0

        # Get CJ batch ID if not provided
        if cj_batch_id is None:
            cj_batch_id = await self._get_batch_id_from_session_provider(session_provider)
            if cj_batch_id is None:
                logger.error("No CJ batch found in database")
                return 0

        # Create ComparisonPair records (simulating what LLM Provider Service would do)
        await self._create_comparison_pairs_for_tasks(
            session_provider=session_provider,
            comparison_tasks=comparison_tasks,
            cj_batch_id=cj_batch_id,
        )

        # Find correlation IDs from database for these comparisons
        comparison_to_correlation = await self._map_comparisons_to_correlations(
            session_provider=session_provider,
            comparison_results=mock_results,
        )

        # Process each result as a callback
        callbacks_processed = 0
        for comparison_result in mock_results:
            # Find the correlation ID for this comparison
            task = comparison_result.task
            key = (task.essay_a.id, task.essay_b.id)
            request_correlation_id = comparison_to_correlation.get(key)

            if not request_correlation_id:
                logger.warning(f"No correlation ID found for comparison {key}, skipping callback")
                continue

            # Create callback event from mock result
            callback_event = self._create_callback_event(
                comparison_result=comparison_result,
                request_correlation_id=request_correlation_id,
            )

            # Process through production callback handler
            await continue_cj_assessment_workflow(
                comparison_result=callback_event,
                correlation_id=correlation_id,
                session_provider=session_provider,
                batch_repository=batch_repository,
                essay_repository=essay_repository,
                comparison_repository=comparison_repository,
                event_publisher=event_publisher,
                settings=settings,
                content_client=content_client,
                llm_interaction=mock_llm_interaction,
                instruction_repository=instruction_repository,
                grade_projector=grade_projector,
                retry_processor=None,  # Not needed for successful callbacks
            )

            callbacks_processed += 1
            logger.debug(
                f"Processed callback {callbacks_processed}/{len(mock_results)}",
                extra={
                    "correlation_id": str(correlation_id),
                    "request_id": callback_event.request_id,
                },
            )

        logger.info(
            f"Completed callback simulation: {callbacks_processed} callbacks processed",
            extra={"correlation_id": str(correlation_id)},
        )

        return callbacks_processed

    async def _map_comparisons_to_correlations(
        self,
        session_provider: SessionProviderProtocol,
        comparison_results: list[ComparisonResult],
    ) -> dict[tuple[str, str], UUID]:
        """Map comparison pairs to their correlation IDs from the database.

        For test environments, this also assigns correlation IDs to pairs that don't have them yet,
        simulating what would happen in production when the LLM provider returns request IDs.

        Args:
            session_provider: Session provider for database access
            comparison_results: List of comparison results from mock

        Returns:
            Dictionary mapping (essay_a_id, essay_b_id) to correlation ID
        """
        mapping = {}

        async with session_provider.session() as session:
            # First, try to get pairs that already have correlation IDs
            stmt = select(ComparisonPair).where(
                ComparisonPair.winner.is_(None),
                ComparisonPair.request_correlation_id.isnot(None),
            )
            result = await session.execute(stmt)
            pairs = result.scalars().all()

            logger.debug(f"Found {len(pairs)} comparison pairs with correlation IDs")

            # If no pairs have correlation IDs, get all pending pairs and assign them
            if not pairs:
                stmt = select(ComparisonPair).where(
                    ComparisonPair.winner.is_(None),
                )
                result = await session.execute(stmt)
                pairs = result.scalars().all()

                logger.debug(f"Found {len(pairs)} pending comparison pairs without correlation IDs")

                # Assign correlation IDs to simulate what happens in production
                for pair in pairs:
                    if pair.request_correlation_id is None:
                        pair.request_correlation_id = uuid4()
                        logger.debug(
                            f"Assigned correlation ID {pair.request_correlation_id} to pair "
                            f"({pair.essay_a_els_id}, {pair.essay_b_els_id})"
                        )

                # Commit the correlation IDs
                await session.commit()

            # Build mapping
            for pair in pairs:
                # Store both orderings since we might not know which order was used
                # Ensure correlation ID is not None (it was assigned above if missing)
                if pair.request_correlation_id is not None:
                    mapping[(pair.essay_a_els_id, pair.essay_b_els_id)] = (
                        pair.request_correlation_id
                    )
                    mapping[(pair.essay_b_els_id, pair.essay_a_els_id)] = (
                        pair.request_correlation_id
                    )

        return mapping

    async def _get_batch_id_from_session_provider(
        self,
        session_provider: SessionProviderProtocol,
    ) -> int | None:
        """Get the most recent CJ batch ID using the session provider.

        Args:
            session_provider: Session provider for database access

        Returns:
            CJ batch ID or None if not found
        """
        async with session_provider.session() as session:
            from sqlalchemy import desc, select

            from services.cj_assessment_service.models_db import CJBatchUpload

            stmt = select(CJBatchUpload).order_by(desc(CJBatchUpload.id)).limit(1)
            result = await session.execute(stmt)
            batch = result.scalar_one_or_none()

            if batch:
                logger.debug(f"Found CJ batch ID {batch.id} from database")
                return batch.id
            return None

    async def _create_comparison_pairs_for_tasks(
        self,
        session_provider: SessionProviderProtocol,
        comparison_tasks: list[Any],
        cj_batch_id: int,
    ) -> None:
        """Create ComparisonPair records for submitted tasks.

        This simulates what the LLM Provider Service would do when it queues requests.
        In production, the LLM Provider Service creates tracking records with correlation IDs.

        Args:
            session_provider: Session provider for database access
            comparison_tasks: List of comparison tasks that were submitted
            cj_batch_id: CJ batch ID
        """
        from datetime import UTC, datetime

        async with session_provider.session() as session:
            for task in comparison_tasks:
                # Check if pair already exists
                stmt = select(ComparisonPair).where(
                    ComparisonPair.cj_batch_id == cj_batch_id,
                    ComparisonPair.essay_a_els_id == task.essay_a.id,
                    ComparisonPair.essay_b_els_id == task.essay_b.id,
                )
                result = await session.execute(stmt)
                existing_pair = result.scalar_one_or_none()

                if existing_pair:
                    # If pair exists but has no correlation ID, assign one
                    if not existing_pair.request_correlation_id:
                        existing_pair.request_correlation_id = uuid4()
                        logger.debug(
                            f"Assigned correlation ID {existing_pair.request_correlation_id} "
                            f"to existing pair ({task.essay_a.id}, {task.essay_b.id})"
                        )
                    # If pair already has a winner, skip (already processed)
                    elif existing_pair.winner:
                        logger.debug(
                            f"Pair ({task.essay_a.id}, {task.essay_b.id}) already has winner: "
                            f"{existing_pair.winner}, skipping"
                        )
                else:
                    # Create new pair with correlation ID (simulating LLM Provider Service)
                    new_pair = ComparisonPair(
                        cj_batch_id=cj_batch_id,
                        essay_a_els_id=task.essay_a.id,
                        essay_b_els_id=task.essay_b.id,
                        prompt_text=task.prompt,
                        request_correlation_id=uuid4(),  # Assign correlation ID
                        submitted_at=datetime.now(UTC),
                    )
                    session.add(new_pair)
                    logger.debug(
                        f"Created ComparisonPair for ({task.essay_a.id}, {task.essay_b.id}) "
                        f"with correlation ID {new_pair.request_correlation_id}"
                    )

            await session.commit()

    def _generate_mock_results(
        self,
        comparison_tasks: list[ComparisonTask],
    ) -> list[ComparisonResult]:
        """Generate mock comparison results for async processing simulation.

        Args:
            comparison_tasks: List of comparison tasks

        Returns:
            List of mock comparison results
        """
        from common_core.domain_enums import EssayComparisonWinner

        from services.cj_assessment_service.models_api import (
            ComparisonResult,
            LLMAssessmentResponseSchema,
        )

        results = []
        for i, task in enumerate(comparison_tasks):
            # Alternate winners for variety
            winner = EssayComparisonWinner.ESSAY_A if i % 2 == 0 else EssayComparisonWinner.ESSAY_B

            assessment = LLMAssessmentResponseSchema(
                winner=winner,
                confidence=3.5 + (i % 3) * 0.5,  # Vary confidence 3.5-4.5
                justification=f"Essay {winner.value} demonstrates stronger argumentation",
            )

            result = ComparisonResult(
                task=task,
                llm_assessment=assessment,
                raw_llm_response_content=f'{{"winner": "{winner.value}"}}',
                error_detail=None,
            )
            results.append(result)

        return results

    def _create_callback_event(
        self,
        comparison_result: ComparisonResult,
        request_correlation_id: UUID,
    ) -> LLMComparisonResultV1:
        """Create a callback event from a mock comparison result.

        Args:
            comparison_result: Mock comparison result
            request_correlation_id: Correlation ID for the request

        Returns:
            LLM comparison result event for callback processing
        """
        # Determine winner from the mock result
        winner = EssayComparisonWinner.ESSAY_A
        if comparison_result.llm_assessment:
            # Use the winner directly from the assessment (it's already an enum)
            winner = comparison_result.llm_assessment.winner

        # Create callback event
        return LLMComparisonResultV1(
            request_id=str(request_correlation_id),  # Use correlation ID as request ID
            correlation_id=request_correlation_id,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku-20240307",
            winner=winner,
            confidence=comparison_result.llm_assessment.confidence
            if comparison_result.llm_assessment
            else 3.0,
            justification=comparison_result.llm_assessment.justification
            if comparison_result.llm_assessment
            else "Test justification",
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
            is_error=False,
        )
