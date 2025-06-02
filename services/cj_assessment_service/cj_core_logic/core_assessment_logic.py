"""Core assessment logic for the CJ Assessment Service.

This module orchestrates the complete CJ assessment workflow,
from processing incoming requests to publishing final results.
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from config import Settings
from enums_db import CJBatchStatusEnum
from huleedu_service_libs.logging_utils import create_service_logger
from models_api import ComparisonResult, ComparisonTask, EssayForComparison

from services.cj_assessment_service.protocols import (
    CJDatabaseProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

from . import pair_generation, scoring_ranking

logger = create_service_logger("cj_assessment_service.core_assessment_logic")


async def run_cj_assessment_workflow(
    request_data: dict[str, Any],
    correlation_id: str | None,
    database: CJDatabaseProtocol,
    content_client: ContentClientProtocol,
    llm_interaction: LLMInteractionProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
) -> tuple[list[dict[str, Any]], str]:
    """Run the complete CJ assessment workflow for a batch of essays.

    Args:
        request_data: The CJ assessment request data from ELS
        correlation_id: Optional correlation ID for event tracing
        database: Database access protocol implementation
        content_client: Content client protocol implementation
        llm_interaction: LLM interaction protocol implementation
        event_publisher: Event publisher protocol implementation
        settings: Application settings

    Raises:
        Exception: If the workflow encounters an unrecoverable error
    """
    logger.info(f"Starting CJ assessment workflow for correlation_id: {correlation_id}")

    cj_batch_id = None
    try:
        # Extract LLM config overrides from request data
        llm_config_overrides = request_data.get("llm_config_overrides")
        model_override = None
        temperature_override = None
        max_tokens_override = None

        if llm_config_overrides:
            model_override = llm_config_overrides.model_override
            temperature_override = llm_config_overrides.temperature_override
            max_tokens_override = llm_config_overrides.max_tokens_override

            logger.info(
                f"Using LLM overrides - model: {model_override}, "
                f"temperature: {temperature_override}, max_tokens: {max_tokens_override}",
                extra={"correlation_id": correlation_id}
            )

        # Phase 1: Create CJ batch and setup
        async with database.session() as session:
            # Extract data from request
            bos_batch_id = request_data.get("bos_batch_id")
            language = request_data.get("language", "en")
            course_code = request_data.get("course_code", "")
            essay_instructions = request_data.get("essay_instructions", "")
            essays_to_process = request_data.get("essays_to_process", [])

            if not bos_batch_id or not essays_to_process:
                raise ValueError("Missing required fields: bos_batch_id or essays_to_process")

            # Create CJ batch record
            cj_batch = await database.create_new_cj_batch(
                session=session,
                bos_batch_id=bos_batch_id,
                event_correlation_id=correlation_id,
                language=language,
                course_code=course_code,
                essay_instructions=essay_instructions,
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=len(essays_to_process),
            )
            cj_batch_id = cj_batch.id

            logger.info(f"Created CJ batch {cj_batch_id} for BOS batch {bos_batch_id}")

        # Phase 2: Fetch content and prepare essays
        async with database.session() as session:
            await database.update_cj_batch_status(
                session=session, cj_batch_id=cj_batch_id, status=CJBatchStatusEnum.FETCHING_CONTENT
            )

            essays_for_api_model: List[EssayForComparison] = []

            for essay_info in essays_to_process:
                els_essay_id = essay_info.get("els_essay_id")
                text_storage_id = essay_info.get("text_storage_id")

                if not els_essay_id or not text_storage_id:
                    logger.warning(f"Skipping essay with missing IDs: {essay_info}")
                    continue

                try:
                    # Fetch spellchecked content
                    assessment_input_text = await content_client.fetch_content(text_storage_id)

                    # Store essay for CJ processing
                    cj_processed_essay = await database.create_or_update_cj_processed_essay(
                        session=session,
                        cj_batch_id=cj_batch_id,
                        els_essay_id=els_essay_id,
                        text_storage_id=text_storage_id,
                        assessment_input_text=assessment_input_text,
                    )

                    # Create EssayForComparison for the comparison loop
                    essay_for_api = EssayForComparison(
                        id=els_essay_id,  # string ELS essay ID
                        text_content=assessment_input_text,
                        current_bt_score=cj_processed_essay.current_bt_score or 0.0,
                    )
                    essays_for_api_model.append(essay_for_api)

                    logger.debug(f"Prepared essay {els_essay_id} for CJ assessment")

                except Exception as e:
                    logger.error(f"Failed to prepare essay {els_essay_id}: {e}")
                    # Continue with other essays rather than failing entire batch

        # Phase 3: Iterative Comparison Loop (Expanded Implementation)
        async with database.session() as session:
            await database.update_cj_batch_status(
                session=session,
                cj_batch_id=cj_batch_id,
                status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
            )

            previous_bt_scores: Dict[str, float] = {
                essay_api.id: essay_api.current_bt_score
                for essay_api in essays_for_api_model
                if essay_api.current_bt_score is not None
            }
            total_comparisons_performed = 0
            current_iteration = 0
            scores_are_stable = False

            while (
                total_comparisons_performed < settings.MAX_PAIRWISE_COMPARISONS
                and not scores_are_stable
            ):
                current_iteration += 1
                logger.info(f"CJ Iteration {current_iteration} for CJ Batch ID: {cj_batch_id}")

                # Generate comparison tasks
                comparison_tasks_for_llm: List[
                    ComparisonTask
                ] = await pair_generation.generate_comparison_tasks(
                    essays_for_comparison=essays_for_api_model,
                    db_session=session,
                    cj_batch_id=cj_batch_id,
                    existing_pairs_threshold=getattr(
                        settings, "comparisons_per_stability_check_iteration", 5
                    ),
                )

                if not comparison_tasks_for_llm:
                    logger.info("No new comparison tasks generated. Ending comparisons.")
                    break

                # Process comparisons using LLMInteractionProtocol
                llm_comparison_results: List[
                    ComparisonResult
                ] = await llm_interaction.perform_comparisons(
                    comparison_tasks_for_llm,
                    model_override=model_override,
                    temperature_override=temperature_override,
                    max_tokens_override=max_tokens_override,
                )

                # Filter out tasks that resulted in an error from the LLM
                valid_llm_results = [
                    res
                    for res in llm_comparison_results
                    if res.llm_assessment and res.llm_assessment.winner != "Error"
                ]

                if not valid_llm_results and llm_comparison_results:
                    logger.warning(
                        f"All {len(llm_comparison_results)} LLM comparisons in iteration "
                        f"{current_iteration} resulted in errors."
                    )

                # Record valid results and update scores
                current_bt_scores_dict: Dict[
                    str, float
                ] = await scoring_ranking.record_comparisons_and_update_scores(
                    all_essays=essays_for_api_model,
                    comparison_results=valid_llm_results,
                    db_session=session,
                    cj_batch_id=cj_batch_id,
                )

                # Update the running total of comparisons
                total_comparisons_performed += len(valid_llm_results)

                # Update scores in the local essays_for_api_model for the next stability check
                for essay_api_item in essays_for_api_model:
                    if essay_api_item.id in current_bt_scores_dict:
                        essay_api_item.current_bt_score = current_bt_scores_dict[essay_api_item.id]

                # Check for score stability
                if (
                    total_comparisons_performed
                    >= getattr(settings, "MIN_COMPARISONS_FOR_STABILITY_CHECK", 10)
                    and previous_bt_scores
                ):
                    max_score_change = scoring_ranking.check_score_stability(
                        current_bt_scores_dict,
                        previous_bt_scores,
                        stability_threshold=getattr(settings, "SCORE_STABILITY_THRESHOLD", 0.05),
                    )
                    logger.info(f"Max score change: {max_score_change:.5f}")
                    if max_score_change < getattr(settings, "SCORE_STABILITY_THRESHOLD", 0.05):
                        scores_are_stable = True
                        logger.info("Scores are stable.")

                previous_bt_scores = current_bt_scores_dict.copy()
                await session.commit()
                await session.begin()

        # Phase 4: Complete and publish results
        async with database.session() as session:
            # Determine final status
            if scores_are_stable:
                final_status = CJBatchStatusEnum.COMPLETE_STABLE
            else:
                final_status = CJBatchStatusEnum.COMPLETE_MAX_COMPARISONS

            await database.update_cj_batch_status(
                session=session, cj_batch_id=cj_batch_id, status=final_status
            )

            # Get final rankings
            rankings = await scoring_ranking.get_essay_rankings(session, cj_batch_id)

            # Prepare completion event data
            completion_data = {
                "bos_batch_id": bos_batch_id,
                "cj_batch_id": cj_batch_id,
                "essay_rankings": rankings,
                "status": "completed_successfully",
                "processing_metadata": {
                    "total_essays": len(essays_to_process),
                    "successful_essays": len(rankings),
                    "total_comparisons": total_comparisons_performed,
                    "iterations": current_iteration,
                    "converged": scores_are_stable,
                },
            }

            # Publish completion event
            correlation_uuid = UUID(correlation_id) if correlation_id else None
            await event_publisher.publish_assessment_completed(
                completion_data=completion_data,
                correlation_id=correlation_uuid,
            )

            logger.info(
                f"CJ assessment completed for batch {cj_batch_id}. "
                f"Rankings generated for {len(rankings)} essays after "
                f"{current_iteration} iterations."
            )

            # Return rankings and CJ batch ID as expected by event_processor
            return rankings, str(cj_batch_id)

    except Exception as e:
        logger.error(f"CJ assessment workflow failed: {e}", exc_info=True)

        # Try to update batch status to error if we have a batch ID
        if cj_batch_id:
            try:
                async with database.session() as session:
                    await database.update_cj_batch_status(
                        session=session,
                        cj_batch_id=cj_batch_id,
                        status=CJBatchStatusEnum.ERROR_PROCESSING,
                    )
            except Exception as update_error:
                logger.error(f"Failed to update batch status to error: {update_error}")

        # Publish failure event
        try:
            failure_data = {
                "bos_batch_id": request_data.get("bos_batch_id"),
                "cj_batch_id": cj_batch_id,
                "error_message": str(e),
                "status": "failed",
            }
            correlation_uuid = UUID(correlation_id) if correlation_id else None
            await event_publisher.publish_assessment_failed(
                failure_data=failure_data,
                correlation_id=correlation_uuid,
            )
        except Exception as publish_error:
            logger.error(f"Failed to publish failure event: {publish_error}")

        # Re-raise the original exception
        raise
