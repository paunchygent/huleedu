from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field

from services.spellchecker_service.implementations.parallel_processor_impl import (
    get_adaptive_edit_distance,
)

# OpenTelemetry tracing handled by HuleEduError automatically

if TYPE_CHECKING:
    from services.spellchecker_service.protocols import ParallelProcessorProtocol, WhitelistProtocol

logger = create_service_logger("spellchecker_service.core_logic")


class SpellcheckMetrics(BaseModel):
    """Detailed metrics from spellcheck processing."""

    corrected_text: str = Field(description="The corrected text after all spellcheck operations")
    total_corrections: int = Field(description="Total number of corrections made")
    l2_dictionary_corrections: int = Field(description="Number of L2 learner error corrections")
    spellchecker_corrections: int = Field(description="Number of general spelling corrections")
    word_count: int = Field(description="Total word count in the text")
    correction_density: float = Field(description="Corrections per 100 words")


# Global cache for SpellChecker instances per language and distance
# Key format: "{language}_d{distance}" (e.g., "en_d1", "en_d2")
# This prevents recreating the dictionary for every essay
#
# Design rationale for dual caching:
# - PySpellChecker sets edit distance at initialization (cannot change per-word)
# - Creating new instances per word would reload dictionary (very slow)
# - Two cached instances trade ~10MB memory for 1000x performance gain
# - Instances are read-only after creation, safe for concurrent async use
_spellchecker_cache: Dict[str, Any] = {}


async def default_perform_spell_check_algorithm(
    text: str,
    l2_errors: dict[str, str],
    essay_id: str | None = None,
    language: str = "en",
    correlation_id: UUID | None = None,
    whitelist: WhitelistProtocol | None = None,
    parallel_processor: ParallelProcessorProtocol | None = None,
    enable_parallel: bool = True,
    max_concurrent: int = 10,
    batch_size: int = 100,
    parallel_timeout: float = 5.0,
    min_words_for_parallel: int = 5,
) -> SpellcheckMetrics:
    """
    Complete L2 + pyspellchecker pipeline implementation.

    Args:
        text: Text to spell check
        l2_errors: Pre-loaded L2 error dictionary (cached at service startup)
        essay_id: Essay identifier for logging
        language: Language for spell checking
        correlation_id: Request correlation ID for tracing
        whitelist: WhitelistProtocol implementation for proper name handling
        parallel_processor: ParallelProcessorProtocol implementation for word correction
        enable_parallel: Enable parallel word correction processing
        max_concurrent: Maximum concurrent word corrections (semaphore limit)
        batch_size: Maximum words per batch for parallel processing
        parallel_timeout: Timeout per word correction in seconds
        min_words_for_parallel: Minimum words to trigger parallel processing

    Pipeline:
    1. Apply L2 corrections using pre-loaded dictionary
    2. Run pyspellchecker on L2-corrected text (skipping whitelisted words)
    3. Log detailed correction information
    4. Return final corrected text + correction count
    """
    log_prefix = f"Essay {essay_id}: " if essay_id else ""
    log_extra = {"essay_id": essay_id, "text_length": len(text), "language": language}
    if correlation_id:
        log_extra["correlation_id"] = str(correlation_id)

    logger.info(
        f"{log_prefix}Starting spell check algorithm (l2_errors: {len(l2_errors)})",
        extra=log_extra,
    )

    import json
    import re
    import time
    from pathlib import Path

    from spellchecker import SpellChecker

    from services.spellchecker_service.config import settings

    total_corrections = 0
    all_corrections: list[dict[str, Any]] = []

    # Phase 1: Apply L2 error corrections
    l2_corrections = []
    l2_start = time.time()

    for error_word, correction in l2_errors.items():
        # Case-insensitive replacement preserving original case
        # Use word boundaries to avoid partial matches
        pattern = re.compile(r"\b" + re.escape(error_word) + r"\b", re.IGNORECASE)
        matches = list(pattern.finditer(text))

        for match in matches:
            original = match.group()
            start = match.start()
            end = match.end()

            # Preserve case of the original word
            if original.isupper() and len(original) > 1:
                replacement = correction.upper()
            elif original[0].isupper():
                replacement = correction[0].upper() + correction[1:]
            else:
                replacement = correction

            # Only replace if actually different
            if original != replacement:
                text = text[:start] + replacement + text[end:]
                l2_corrections.append(
                    {
                        "original_word": original,
                        "corrected_word": replacement,
                        "start": start,
                        "end": end - 1,
                        "rule": "l2_swedish_learner",
                    },
                )
                total_corrections += 1

                # Adjust positions for subsequent replacements
                len(replacement) - len(original)
                for future_match in matches[matches.index(match) + 1 :]:
                    if future_match.start() > start:
                        # This is a hack to adjust the position, but re.Match is immutable
                        # We'll need to recalculate on next iteration
                        break

    l2_time = time.time() - l2_start
    logger.info(
        f"{log_prefix}L2 corrections completed: {len(l2_corrections)} "
        f"corrections in {l2_time:.3f}s",
        extra={
            **log_extra,
            "l2_corrections_count": len(l2_corrections),
            "l2_time_seconds": l2_time,
        },
    )

    # Phase 2: Apply pyspellchecker corrections
    # Create or get cached SpellChecker instances
    cache_key_d1 = f"{language}_d1"
    cache_key_d2 = f"{language}_d2"

    if cache_key_d1 not in _spellchecker_cache:
        logger.info(f"Creating SpellChecker instance for {language} with distance=1")
        _spellchecker_cache[cache_key_d1] = SpellChecker(language=language, distance=1)

    if cache_key_d2 not in _spellchecker_cache:
        logger.info(f"Creating SpellChecker instance for {language} with distance=2")
        _spellchecker_cache[cache_key_d2] = SpellChecker(language=language, distance=2)

    # Tokenize text to identify words
    # Using simple regex tokenization to preserve position information
    word_pattern = re.compile(r"\b[A-Za-z]+(?:['-][A-Za-z]+)*\b")
    pyspellchecker_start = time.time()

    # First pass: tokenize and preserve all tokens (words and non-words)
    tokens = []
    last_end = 0
    for match in word_pattern.finditer(text):
        # Add any non-word content before this word
        if match.start() > last_end:
            tokens.append(text[last_end : match.start()])
        # Add the word itself
        tokens.append(match.group())
        last_end = match.end()
    # Add any remaining non-word content
    if last_end < len(text):
        tokens.append(text[last_end:])

    # Extract just the words for spell checking
    words_to_check = [token for token in tokens if word_pattern.fullmatch(token)]
    lowercase_words = [w.lower() for w in words_to_check]

    # Filter out whitelisted words before checking
    words_to_spellcheck = []
    if whitelist:
        whitelist_skip_count = 0
        for word in lowercase_words:
            # Check original case word in whitelist
            original_idx = lowercase_words.index(word)
            original_word = words_to_check[original_idx]
            if whitelist.is_whitelisted(original_word):
                whitelist_skip_count += 1
                logger.debug(
                    f"{log_prefix}Skipping whitelisted word: '{original_word}'",
                    extra={**log_extra, "whitelisted_word": original_word},
                )
            else:
                words_to_spellcheck.append(word)

        if whitelist_skip_count > 0:
            logger.info(
                f"{log_prefix}Skipped {whitelist_skip_count} whitelisted words",
                extra={**log_extra, "whitelist_skip_count": whitelist_skip_count},
            )
    else:
        words_to_spellcheck = lowercase_words

    # Use SpellChecker.unknown() to find misspelled words
    # This is much faster than checking each word individually
    unknown_check_start = time.time()

    # Temporarily use distance=2 checker for unknown() to get better coverage
    # We'll use adaptive distance for actual corrections
    # Filter out whitelisted words from spellchecking
    if whitelist:
        words_to_spellcheck = []
        for word in lowercase_words:
            # Find original case version
            original_idx = lowercase_words.index(word)
            original_word = words_to_check[original_idx]
            if not whitelist.is_whitelisted(original_word):
                words_to_spellcheck.append(word)
    else:
        words_to_spellcheck = lowercase_words

    spell_checker_d2 = _spellchecker_cache[cache_key_d2]
    misspelled_lowercase = spell_checker_d2.unknown(words_to_spellcheck)
    unknown_check_time = time.time() - unknown_check_start
    logger.info(
        f"{log_prefix}SpellChecker.unknown() time: {unknown_check_time:.3f}s, "
        f"found {len(misspelled_lowercase)} misspelled words",
        extra={
            **log_extra,
            "unknown_check_time_seconds": unknown_check_time,
            "misspelled_count": len(misspelled_lowercase),
        },
    )

    # Map back to original case words that need correction
    misspelled_words = set()
    for i, lowercase_word in enumerate(lowercase_words):
        if lowercase_word in misspelled_lowercase:
            misspelled_words.add(words_to_check[i])  # Add original case word

    # Apply corrections
    corrections_start = time.time()
    correction_times = []

    # Collect words that need correction
    words_needing_correction = []
    word_idx_counter = 0

    for token_text in tokens:
        if word_pattern.fullmatch(token_text):
            original_word = words_to_check[word_idx_counter]

            # Skip whitelisted words
            if whitelist and whitelist.is_whitelisted(original_word):
                word_idx_counter += 1
                continue

            # Add to correction list if misspelled
            if original_word in misspelled_words:
                words_needing_correction.append((word_idx_counter, original_word))
            word_idx_counter += 1

    # Decide between parallel and sequential processing
    use_parallel = (
        enable_parallel
        and len(words_needing_correction) >= min_words_for_parallel
        and correlation_id is not None
    )

    pyspellchecker_corrections = []
    final_corrected_tokens = []

    if use_parallel:
        logger.info(
            f"{log_prefix}Using parallel processing for "
            f"{len(words_needing_correction)} corrections",
            extra={
                **log_extra,
                "parallel_mode": True,
                "words_to_correct": len(words_needing_correction),
                "max_concurrent": max_concurrent,
            },
        )

        # Process in batches if needed
        parallel_corrections: dict[int, tuple[str | None, float]] = {}
        for batch_start in range(0, len(words_needing_correction), batch_size):
            batch_end = min(batch_start + batch_size, len(words_needing_correction))
            batch_words = words_needing_correction[batch_start:batch_end]

            if correlation_id is None:
                # Create a new correlation ID if not provided
                correlation_id = UUID("00000000-0000-0000-0000-000000000000")

            if parallel_processor is None:
                raise ValueError("parallel_processor is required when enable_parallel=True")

            batch_corrections = await parallel_processor.process_corrections_parallel(
                words_to_correct=batch_words,
                spell_checker_cache=_spellchecker_cache,
                correlation_id=correlation_id,
                essay_id=essay_id,
            )
            parallel_corrections.update(batch_corrections)

        # Apply parallel corrections to tokens
        current_pos = 0
        word_idx_counter = 0

        for token_text in tokens:
            token_len = len(token_text)
            if word_pattern.fullmatch(token_text):
                original_word = words_to_check[word_idx_counter]

                if whitelist and whitelist.is_whitelisted(original_word):
                    final_corrected_tokens.append(original_word)
                elif word_idx_counter in parallel_corrections:
                    corrected_word, correction_time = parallel_corrections[word_idx_counter]
                    correction_times.append(correction_time)

                    if corrected_word and corrected_word.lower() != original_word.lower():
                        # Preserve case
                        if original_word.isupper() and len(original_word) > 1:
                            corrected_word = corrected_word.upper()
                        elif original_word.istitle():
                            corrected_word = corrected_word.title()
                        elif original_word[0].isupper():
                            corrected_word = corrected_word[0].upper() + corrected_word[1:]

                        if corrected_word != original_word:
                            pyspellchecker_corrections.append(
                                {
                                    "original_word": original_word,
                                    "corrected_word": corrected_word,
                                    "start": current_pos,
                                    "end": current_pos + token_len - 1,
                                    "rule": "pyspellchecker_parallel",
                                },
                            )
                            final_corrected_tokens.append(corrected_word)
                        else:
                            final_corrected_tokens.append(original_word)
                    else:
                        final_corrected_tokens.append(original_word)
                else:
                    final_corrected_tokens.append(original_word)
                word_idx_counter += 1
            else:
                final_corrected_tokens.append(token_text)
            current_pos += token_len

    else:
        # Sequential processing (original implementation)
        logger.info(
            f"{log_prefix}Using sequential processing for "
            f"{len(words_needing_correction)} corrections",
            extra={
                **log_extra,
                "parallel_mode": False,
                "words_to_correct": len(words_needing_correction),
            },
        )

        current_pos = 0
        word_idx_counter = 0

        for token_text in tokens:
            token_len = len(token_text)
            if word_pattern.fullmatch(token_text):
                original_word = words_to_check[word_idx_counter]

                # Skip whitelisted words even if they were marked as misspelled
                if whitelist and whitelist.is_whitelisted(original_word):
                    final_corrected_tokens.append(original_word)
                elif original_word in misspelled_words:
                    # Select appropriate SpellChecker based on word characteristics
                    optimal_distance = get_adaptive_edit_distance(original_word)
                    if optimal_distance == 1:
                        spell_checker = _spellchecker_cache[cache_key_d1]
                    else:
                        spell_checker = _spellchecker_cache[cache_key_d2]

                    correction_start = time.time()
                    corrected_word = spell_checker.correction(original_word.lower())
                    correction_time = time.time() - correction_start
                    correction_times.append(correction_time)

                    if correction_time > 0.1:  # Log slow corrections
                        logger.warning(
                            f"{log_prefix}Slow correction: '{original_word}' -> "
                            f"'{corrected_word}' took {correction_time:.3f}s "
                            f"(distance={optimal_distance})",
                            extra={
                                **log_extra,
                                "slow_word": original_word,
                                "correction_time_seconds": correction_time,
                                "edit_distance": optimal_distance,
                            },
                        )
                    else:
                        # Log adaptive distance usage for monitoring
                        logger.debug(
                            f"{log_prefix}Corrected '{original_word}' using "
                            f"distance={optimal_distance} in {correction_time:.3f}s",
                            extra={
                                **log_extra,
                                "word": original_word,
                                "edit_distance": optimal_distance,
                                "correction_time_seconds": correction_time,
                            },
                        )

                    if corrected_word and corrected_word.lower() != original_word.lower():
                        # Preserve case
                        if original_word.isupper() and len(original_word) > 1:
                            corrected_word = corrected_word.upper()
                        elif original_word.istitle():
                            corrected_word = corrected_word.title()
                        elif original_word[0].isupper():
                            corrected_word = corrected_word[0].upper() + corrected_word[1:]

                        if corrected_word != original_word:
                            pyspellchecker_corrections.append(
                                {
                                    "original_word": original_word,
                                    "corrected_word": corrected_word,
                                    "start": current_pos,
                                    "end": current_pos + token_len - 1,
                                    "rule": "pyspellchecker",
                                },
                            )
                            final_corrected_tokens.append(corrected_word)
                        else:
                            final_corrected_tokens.append(original_word)
                    else:
                        final_corrected_tokens.append(original_word)
                else:
                    final_corrected_tokens.append(original_word)
                word_idx_counter += 1
            else:
                final_corrected_tokens.append(token_text)
            current_pos += token_len

    corrections_total_time = time.time() - corrections_start
    if correction_times:
        max_correction_time = max(correction_times)
        avg_correction_time = sum(correction_times) / len(correction_times)
    else:
        max_correction_time = 0
        avg_correction_time = 0

    pyspellchecker_time = time.time() - pyspellchecker_start

    # Reconstruct the corrected text from tokens
    corrected_text = "".join(final_corrected_tokens)

    # Count pyspellchecker corrections
    total_corrections += len(pyspellchecker_corrections)

    # Combine all corrections for logging
    all_corrections = l2_corrections + pyspellchecker_corrections

    # Calculate word count from already tokenized words
    word_count = len(words_to_check)

    # Calculate correction density (corrections per 100 words)
    correction_density = (total_corrections / word_count * 100) if word_count > 0 else 0.0

    # Log detailed performance metrics
    logger.info(
        f"{log_prefix}Spell check completed: {total_corrections} total corrections "
        f"(L2: {len(l2_corrections)}, PySpell: {len(pyspellchecker_corrections)}). "
        f"Total time: {l2_time + pyspellchecker_time:.3f}s",
        extra={
            **log_extra,
            "total_corrections": total_corrections,
            "l2_corrections_count": len(l2_corrections),
            "pyspell_corrections_count": len(pyspellchecker_corrections),
            "l2_time_seconds": l2_time,
            "pyspell_time_seconds": pyspellchecker_time,
            "total_time_seconds": l2_time + pyspellchecker_time,
            "unknown_check_time_seconds": unknown_check_time,
            "corrections_apply_time_seconds": corrections_total_time,
            "max_correction_time_seconds": max_correction_time,
            "avg_correction_time_seconds": avg_correction_time,
            "misspelled_words_count": len(misspelled_words),
        },
    )

    # Save corrections to file if enabled
    if settings.ENABLE_CORRECTION_LOGGING and essay_id:
        try:
            output_dir = Path(settings.effective_correction_log_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f"{essay_id}_corrections.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "essay_id": essay_id,
                        "total_corrections": total_corrections,
                        "l2_corrections": l2_corrections,
                        "pyspellchecker_corrections": pyspellchecker_corrections,
                        "all_corrections": all_corrections,
                        "original_length": len(text),
                        "corrected_length": len(corrected_text),
                        "processing_time": {
                            "l2_seconds": l2_time,
                            "pyspellchecker_seconds": pyspellchecker_time,
                            "total_seconds": l2_time + pyspellchecker_time,
                        },
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            logger.debug(
                f"{log_prefix}Saved correction details to {output_file}",
                extra={**log_extra, "output_file": str(output_file)},
            )
        except Exception as e:
            logger.warning(
                f"{log_prefix}Failed to save correction log: {e}",
                extra={**log_extra, "error": str(e)},
            )

    return SpellcheckMetrics(
        corrected_text=corrected_text,
        total_corrections=total_corrections,
        l2_dictionary_corrections=len(l2_corrections),
        spellchecker_corrections=len(pyspellchecker_corrections),
        word_count=word_count,
        correction_density=correction_density,
    )
