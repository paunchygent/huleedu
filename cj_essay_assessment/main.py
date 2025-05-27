"""Main entry point for the CJ Essay Assessment system.

This module provides the orchestration logic to process essay batches
through the complete comparative judgment workflow.
"""

import argparse
import asyncio
import sys
import time

from loguru import logger

from src.cj_essay_assessment.config import (Settings,  # Import Settings
                                            get_settings)
from src.cj_essay_assessment.db.db_handler import DatabaseHandler
from src.cj_essay_assessment.db.models_db import BatchStatusEnum
from src.cj_essay_assessment.essay_processor import process_essays_for_batch
# Import CacheManager from llm_caller
from src.cj_essay_assessment.llm_caller import (CacheManager,
                                                process_comparison_tasks_async)
from src.cj_essay_assessment.nlp_analyzer import compute_and_store_nlp_stats
from src.cj_essay_assessment.pair_generator import generate_comparison_tasks
from src.cj_essay_assessment.ranking_handler import (
    check_score_stability, record_comparisons_and_update_scores)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure loguru logging with the specified level.

    Args:
        log_level: The logging level to use (DEBUG, INFO, WARNING, ERROR)

    """
    # Remove default logger
    logger.remove()

    # Add console logger with proper formatting
    format_string = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        level=log_level,
        format=format_string,
    )

    # Add file logger for persistent logs
    logger.add(
        "logs/cj_system_{time}.log",
        level=log_level,
        rotation="100 MB",
        retention="30 days",
        compression="zip",
    )

    logger.info(f"Logging configured at level {log_level}")


async def run_comparative_judgment_for_batch(batch_id: int) -> bool:
    """
    Run the complete comparative judgment workflow for a batch.

    This function processes a batch of essays, computes NLP features, performs iterative
    pairwise LLM comparisons, tracks and logs status, and logs the final ranking using
    ranking_handler.get_essay_rankings for accuracy and richer output.

    Args:
        batch_id: The ID of the batch to process

    Returns:
        bool: True if process completed successfully, False otherwise
    """
    start_time = time.time()
    settings: Settings = get_settings()  # Called once
    db_handler = DatabaseHandler(settings)
    # Instantiate CacheManager once here, passing the settings object
    cache_manager = CacheManager(settings=settings)
    # Note: CacheManager's __init__ calls get_settings() internally.
    # This is acceptable as it's instantiated once here.

    logger.info(f"Starting comparative judgment process for batch ID: {batch_id}")

    try:
        # Create tables if they don't exist
        await db_handler.create_tables()
        logger.info("Database tables created or verified")

        # Step 1: Process essays for batch
        logger.info(f"Processing essays for batch {batch_id}")
        essays_for_comparison = await process_essays_for_batch(
            db_handler,
            settings,
            batch_id,
        )

        if not essays_for_comparison:
            logger.error(f"No essays ready for comparison in batch {batch_id}")
            return False

        logger.info(f"Prepared {len(essays_for_comparison)} essays for comparison")

        # Step 2: Compute NLP features
        try:
            logger.info(f"B{batch_id} status: {BatchStatusEnum.PROCESSING_NLP.name}")
            async with db_handler.session() as status_session:
                await db_handler.update_batch_status(
                    status_session,
                    batch_id,
                    BatchStatusEnum.PROCESSING_NLP,
                )

            logger.info(f"B{batch_id}: Computing NLP features...")
            await compute_and_store_nlp_stats(db_handler, settings, essays_for_comparison)
            logger.info(f"B{batch_id}: NLP features computed.")

            logger.info(
                f"B{batch_id} status: {BatchStatusEnum.READY_FOR_COMPARISON.name}",
            )
            async with db_handler.session() as status_session:
                await db_handler.update_batch_status(
                    status_session,
                    batch_id,
                    BatchStatusEnum.READY_FOR_COMPARISON,
                )
        except Exception as nlp_e:
            logger.exception(f"B{batch_id}: NLP error: {nlp_e}")
            try:
                logger.error(f"B{batch_id}: Set {BatchStatusEnum.ERROR_NLP.name} fail.")
                async with db_handler.session() as error_session:
                    await db_handler.update_batch_status(
                        error_session,
                        batch_id,
                        BatchStatusEnum.ERROR_NLP,
                    )
                logger.info(f"B{batch_id}: Status is {BatchStatusEnum.ERROR_NLP.name}.")
            except Exception as update_err:
                logger.error(
                    f"CRITICAL B{batch_id}: {BatchStatusEnum.ERROR_NLP.name} ERR: {update_err}",
                    exc_info=True,
                )
            return False  # Exit processing if NLP fails

        # Step 3: Initialize comparison loop variables
        previous_bt_scores: dict[int, float] = {}
        total_comparisons = 0
        iteration = 0
        is_stable = False
        loop_error_occurred = False  # Flag for loop-breaking error

        # Attempt to set status to PERFORMING_COMPARISONS
        try:
            logger.info(
                f"B{batch_id} status: {BatchStatusEnum.PERFORMING_COMPARISONS.name}",
            )
            async with db_handler.session() as status_session:
                await db_handler.update_batch_status(
                    status_session,
                    batch_id,
                    BatchStatusEnum.PERFORMING_COMPARISONS,
                )
        except Exception as update_err:
            logger.error(
                f"CRIT B{batch_id}: Set {BatchStatusEnum.PERFORMING_COMPARISONS.name} fail: {update_err}",
                exc_info=True,
            )
            return False  # Cannot proceed

        # Step 4: Run comparison iterations
        try:
            while (
                total_comparisons < settings.max_pairwise_comparisons
                and not is_stable
                and not loop_error_occurred
            ):
                iteration += 1
                logger.info(f"Iter {iteration} for B{batch_id}")
                try:
                    # Step 4.1: Generate comparison pairs
                    async with db_handler.session() as session:
                        comparison_tasks = await generate_comparison_tasks(
                            essays_for_comparison,
                            session,
                            batch_id,
                            settings,
                        )

                    if not comparison_tasks:
                        logger.warning(
                            f"B{batch_id}: No new tasks. Ending after {total_comparisons} comps.",
                        )
                        break  # Break while loop

                    this_round_count = len(comparison_tasks)
                    logger.info(f"B{batch_id}: Gen {this_round_count} tasks")

                    # Step 4.2: Process comparisons with LLM
                    # Pass the single cache_manager and settings instances
                    comparison_results = await process_comparison_tasks_async(
                        comparison_tasks,
                        cache_manager,  # Pass instance
                        settings,  # Pass instance
                    )
                    valid_results = [
                        r
                        for r in comparison_results
                        if r.llm_assessment is not None
                        and r.llm_assessment.winner != "Error"
                    ]
                    logger.info(
                        f"B{batch_id}: LLM tasks {len(comparison_results)}, {len(valid_results)} valid",
                    )

                    # Step 4.3: Record results and update scores
                    current_bt_scores = await record_comparisons_and_update_scores(
                        db_handler,
                        batch_id,
                        iteration,
                        comparison_results,
                        essays_for_comparison,
                    )
                    total_comparisons += this_round_count
                    logger.info(f"B{batch_id}: Total comps: {total_comparisons}")

                    # Step 4.4: Check for score stability
                    if (
                        total_comparisons >= settings.min_comparisons_for_stability_check
                        and previous_bt_scores
                    ):
                        max_change = check_score_stability(
                            current_bt_scores,
                            previous_bt_scores,
                        )
                        logger.info(f"B{batch_id}: Max score change: {max_change:.5f}")
                        is_stable = max_change < settings.score_stability_threshold
                        if is_stable:
                            logger.info(
                                f"B{batch_id}: Scores stable (change {max_change:.5f})",
                            )

                    previous_bt_scores = current_bt_scores.copy()
                    for essay in essays_for_comparison:
                        if essay.id in current_bt_scores:
                            essay.current_bt_score = current_bt_scores[essay.id]

                except Exception as e_iteration:  # Error in single iteration
                    logger.exception(f"B{batch_id} iter {iteration} ERR: {e_iteration}")
                    loop_error_occurred = True
                    try:
                        logger.error(
                            f"B{batch_id}: Set {BatchStatusEnum.ERROR_COMPARISON.name} iter fail.",
                        )
                        async with db_handler.session() as error_session:
                            await db_handler.update_batch_status(
                                error_session,
                                batch_id,
                                BatchStatusEnum.ERROR_COMPARISON,
                            )
                        logger.info(
                            f"B{batch_id}: Status {BatchStatusEnum.ERROR_COMPARISON.name}.",
                        )
                    except Exception as update_err_iter:
                        logger.error(
                            f"CRIT B{batch_id}: {BatchStatusEnum.ERROR_COMPARISON.name} ERR: {update_err_iter}",
                            exc_info=True,
                        )
                    break  # Break while loop

        except Exception as e_loop_setup:  # Error in loop setup/outer scope
            logger.exception(f"B{batch_id}: Loop setup ERR: {e_loop_setup}")
            loop_error_occurred = True
            current_batch_status_val = None
            async with db_handler.session() as s:  # Check current status
                b = await db_handler.get_batch_by_id(s, batch_id)
                if b:
                    current_batch_status_val = b.status

            if current_batch_status_val != BatchStatusEnum.ERROR_COMPARISON:
                try:
                    logger.error(
                        f"B{batch_id}: Set {BatchStatusEnum.ERROR_COMPARISON.name} setup fail.",
                    )
                    async with db_handler.session() as error_session:
                        await db_handler.update_batch_status(
                            error_session,
                            batch_id,
                            BatchStatusEnum.ERROR_COMPARISON,
                        )
                    logger.info(
                        f"B{batch_id}: Status {BatchStatusEnum.ERROR_COMPARISON.name}.",
                    )
                except Exception as update_err_setup:
                    logger.error(
                        f"CRIT B{batch_id}: {BatchStatusEnum.ERROR_COMPARISON.name} ERR: {update_err_setup}",
                        exc_info=True,
                    )

        # Step 5: Determine and set final batch status
        final_status_to_set: BatchStatusEnum | None = None
        if loop_error_occurred:  # Prioritize error status
            final_status_to_set = BatchStatusEnum.ERROR_COMPARISON
        elif is_stable:
            final_status_to_set = BatchStatusEnum.COMPLETE_STABLE
        elif total_comparisons >= settings.max_pairwise_comparisons:
            final_status_to_set = BatchStatusEnum.COMPLETE_MAX_COMPARISONS

        if final_status_to_set:
            try:
                logger.info(f"B{batch_id}: Final status {final_status_to_set.name}")
                async with db_handler.session() as final_status_session:
                    await db_handler.update_batch_status(
                        final_status_session,
                        batch_id,
                        final_status_to_set,
                    )
                logger.info(f"B{batch_id}: Final status set: {final_status_to_set.name}.")
            except Exception as update_final_err:
                logger.error(
                    f"CRIT B{batch_id}: Final status {final_status_to_set.name} ERR: {update_final_err}",
                    exc_info=True,
                )

        # Step 6: Log final results
        run_time = time.time() - start_time
        current_status_for_log = (
            BatchStatusEnum.PERFORMING_COMPARISONS
        )  # Default if not set
        if final_status_to_set:
            current_status_for_log = final_status_to_set
        elif (
            loop_error_occurred
        ):  # If error occurred but final_status was not ERROR_COMPARISON yet
            current_status_for_log = BatchStatusEnum.ERROR_COMPARISON

        log_parts = [
            f"CJ B{batch_id} done.",
            f"Status: {current_status_for_log.name}.",
            f"Comps: {total_comparisons}.",
            f"Time: {run_time:.1f}s.",
        ]
        if is_stable:
            log_parts.append("(Stable)")
        elif total_comparisons >= settings.max_pairwise_comparisons:
            log_parts.append("(Max comps)")
        elif loop_error_occurred:
            log_parts.append("(Loop ERR)")
        logger.info(" ".join(log_parts))

        # Generate and log final ranking using get_essay_rankings
        try:
            from . import \
                ranking_handler  # Local import to avoid circular dependency

            final_rankings = await ranking_handler.get_essay_rankings(
                db_handler, batch_id
            )
            if final_rankings:
                logger.info("Final ranking (top 10 essays):")
                for entry in final_rankings[:10]:
                    logger.info(
                        f"#{entry['rank']}: Essay ID {entry['id']}, Filename: {entry['original_filename']}, Score: {entry['bt_score']:.5f}"
                    )
            else:
                logger.info("No essays found for final ranking.")
        except Exception as ranking_log_exc:
            logger.error(f"Error logging final rankings: {ranking_log_exc}")

        # Return False if an error occurred within the loop
        return not loop_error_occurred

    except Exception as e:
        logger.exception(f"Error in comparative judgment process: {e}")
        # Fallback: Attempt to set batch status to ERROR_COMPARISON if possible
        try:
            async with db_handler.session() as error_session:
                batch = await db_handler.get_batch_by_id(error_session, batch_id)
                if batch is not None:
                    await db_handler.update_batch_status(
                        error_session,
                        batch_id,
                        BatchStatusEnum.ERROR_COMPARISON,
                    )
                    logger.error(
                        f"B{batch_id}: Set fallback status {BatchStatusEnum.ERROR_COMPARISON.name} due to top-level error.",
                    )
                else:
                    logger.error(
                        f"B{batch_id}: Batch not found when attempting fallback error status."
                    )
        except Exception as status_update_err:
            logger.error(
                f"CRITICAL B{batch_id}: Could not set fallback ERROR_COMPARISON status due to: {status_update_err}",
                exc_info=True,
            )
        return False


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace

    """
    parser = argparse.ArgumentParser(
        description="Comparative Judgment System for Essay Assessment",
    )

    parser.add_argument(
        "--batch-id",
        type=int,
        required=True,
        help="ID of the batch to process",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    return parser.parse_args()


def main_entry_point() -> int:
    """Main entry point for the script when run from command line.

    Returns:
        Exit code (0 for success, non-zero for errors)

    """
    logger.info("Application starting...")
    try:
        # Load settings and parse arguments first
        settings = get_settings()
        args = parse_arguments()
        configure_logging(args.log_level)

        # Run the async workflow
        success = asyncio.run(run_comparative_judgment_for_batch(args.batch_id))
        return 0 if success else 1

    except SystemExit as e:
        logger.info(f"Exiting with code: {e.code}")
        return e.code if isinstance(e.code, int) else 1  # Ensure returning int
    except Exception as e:
        logger.exception(f"Unhandled exception in main: {e}")
        return 1  # General error exit code


if __name__ == "__main__":
    sys.exit(main_entry_point())
