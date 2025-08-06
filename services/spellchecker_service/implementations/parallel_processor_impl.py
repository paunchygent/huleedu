"""Default implementation of ParallelProcessorProtocol."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.spellchecker_service.config import settings
from services.spellchecker_service.protocols import ParallelProcessorProtocol

logger = create_service_logger("spellchecker_service.parallel_processor")


def get_adaptive_edit_distance(word: str) -> int:
    """
    Determine optimal edit distance based on word characteristics.

    Returns:
        1 for long words (>5 chars) or compound words (containing '-' or "'")
        2 for short, simple words (better accuracy)
    """
    # Long words create exponential candidate generation with distance=2
    if len(word) > 5:
        return 1

    # Compound words and contractions are problematic with distance=2
    if "-" in word or "'" in word:
        return 1

    # Short, simple words benefit from distance=2 for better accuracy
    return 2


class DefaultParallelProcessor(ParallelProcessorProtocol):
    """Default implementation of parallel word correction processing."""

    def __init__(self) -> None:
        """Initialize with configuration settings."""
        self.max_concurrent = settings.MAX_CONCURRENT_CORRECTIONS
        self.timeout_seconds = settings.PARALLEL_TIMEOUT_SECONDS

    async def process_corrections_parallel(
        self,
        words_to_correct: list[tuple[int, str]],
        spell_checker_cache: dict[str, Any],
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> dict[int, tuple[str | None, float]]:
        """Process word corrections in parallel using asyncio.to_thread.

        PySpellChecker releases the GIL in its C extensions, allowing true parallelism.

        Args:
            words_to_correct: List of (index, word) tuples to correct
            spell_checker_cache: Dictionary of cached SpellChecker instances by distance
            correlation_id: Request correlation ID for logging
            essay_id: Optional essay ID for logging context

        Returns:
            Dictionary mapping word index to (corrected_word, time_taken)
            Returns None for corrections that timeout or fail
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results: dict[int, tuple[str | None, float]] = {}
        log_prefix = f"Essay {essay_id}: " if essay_id else ""

        async def correct_single_word(idx: int, word: str) -> tuple[int, str | None, float]:
            """Correct a single word with timeout and error handling."""
            async with semaphore:
                start_time = time.time()
                try:
                    # Determine appropriate edit distance
                    optimal_distance = get_adaptive_edit_distance(word)
                    cache_key = f"en_d{optimal_distance}"
                    spell_checker = spell_checker_cache[cache_key]

                    # Run correction in thread pool (releases GIL)
                    corrected = await asyncio.wait_for(
                        asyncio.to_thread(spell_checker.correction, word.lower()),
                        timeout=self.timeout_seconds,
                    )

                    elapsed = time.time() - start_time

                    if elapsed > 0.1:  # Log slow corrections
                        logger.warning(
                            f"{log_prefix}Parallel correction slow: '{word}' -> "
                            f"'{corrected}' took {elapsed:.3f}s (distance={optimal_distance})",
                            extra={
                                "correlation_id": str(correlation_id),
                                "essay_id": essay_id,
                                "word": word,
                                "correction_time_seconds": elapsed,
                                "edit_distance": optimal_distance,
                                "parallel": True,
                            },
                        )

                    return idx, corrected, elapsed

                except asyncio.TimeoutError:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"{log_prefix}Parallel correction timeout: '{word}' "
                        f"after {self.timeout_seconds}s",
                        extra={
                            "correlation_id": str(correlation_id),
                            "essay_id": essay_id,
                            "word": word,
                            "timeout_seconds": self.timeout_seconds,
                            "parallel": True,
                        },
                    )
                    return idx, None, elapsed

                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"{log_prefix}Parallel correction error for '{word}': {str(e)}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "essay_id": essay_id,
                            "word": word,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "parallel": True,
                        },
                    )
                    return idx, None, elapsed

        # Create all correction tasks
        tasks = [correct_single_word(idx, word) for idx, word in words_to_correct]

        # Execute all corrections concurrently
        completed_corrections = await asyncio.gather(*tasks, return_exceptions=False)

        # Build results dictionary
        for idx, corrected, elapsed in completed_corrections:
            results[idx] = (corrected, elapsed)

        return results
