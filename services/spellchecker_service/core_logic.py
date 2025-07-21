from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

import aiohttp  # For ClientSession type hint
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_processing_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

# OpenTelemetry tracing handled by HuleEduError automatically

# Protocols are not implemented here, but these functions can be *used* by their implementations
# from .protocols import (
#     ContentClientProtocol,
#     ResultStoreProtocol,
#     SpellLogicProtocol,
# )

logger = create_service_logger("spellchecker_service.core_logic")

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


# --- Default Implementations / Helpers ---


async def default_fetch_content_impl(
    session: aiohttp.ClientSession,
    storage_id: str,
    content_service_url: str,
    correlation_id: UUID,
    essay_id: str | None = None,
) -> str:
    """
    Default implementation for fetching content from the content service.
    Uses structured error handling with HuleEduError exceptions.
    """
    url = f"{content_service_url}/{storage_id}"
    log_prefix = f"Essay {essay_id}: " if essay_id else ""

    logger.debug(
        f"{log_prefix}Fetching content from URL: {url}",
        extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
    )

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(url, timeout=timeout) as response:
            # Use response.raise_for_status() to handle all 2xx codes correctly
            response.raise_for_status()
            # Parse response - only reached on successful 2xx response
            content = await response.text()
            logger.debug(
                f"{log_prefix}Successfully fetched content from {storage_id} "
                f"(length: {len(content)})",
                extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
            )
            return content

    except aiohttp.ClientResponseError as e:
        # Handle HTTP errors (4xx/5xx) from raise_for_status()
        if e.status == 404:
            raise_content_service_error(
                service="spellchecker_service",
                operation="fetch_content",
                message=f"Content not found: {storage_id}",
                correlation_id=correlation_id,
                content_service_url=content_service_url,
                status_code=e.status,
                storage_id=storage_id,
            )
        else:
            # Note: response body is not available in ClientResponseError
            raise_content_service_error(
                service="spellchecker_service",
                operation="fetch_content",
                message=f"Content Service HTTP error: {e.status} - {e.message}",
                correlation_id=correlation_id,
                content_service_url=content_service_url,
                status_code=e.status,
                storage_id=storage_id,
                response_text=e.message[:200] if e.message else "No error message",
            )

    except aiohttp.ServerTimeoutError:
        raise_content_service_error(
            service="spellchecker_service",
            operation="fetch_content",
            message=f"Timeout fetching content from {storage_id}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            storage_id=storage_id,
            timeout_seconds=10,
        )

    except aiohttp.ClientError as e:
        raise_content_service_error(
            service="spellchecker_service",
            operation="fetch_content",
            message=f"Connection error fetching content: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            storage_id=storage_id,
            client_error_type=type(e).__name__,
        )

    except Exception as e:
        logger.error(
            f"{log_prefix}Unexpected error fetching content {storage_id}: {e}",
            exc_info=True,
            extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
        )
        raise_content_service_error(
            service="spellchecker_service",
            operation="fetch_content",
            message=f"Unexpected error fetching content: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            storage_id=storage_id,
            error_type=type(e).__name__,
        )


async def default_store_content_impl(
    session: aiohttp.ClientSession,
    text_content: str,
    content_service_url: str,
    correlation_id: UUID,
    essay_id: str | None = None,
) -> str:
    """
    Default implementation for storing content to the content service.
    Uses structured error handling with HuleEduError exceptions.
    """
    log_prefix = f"Essay {essay_id}: " if essay_id else ""

    logger.debug(
        f"{log_prefix}Storing content (length: {len(text_content)}) to Content Service "
        f"via {content_service_url}",
        extra={"correlation_id": str(correlation_id), "content_length": len(text_content)},
    )

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.post(
            content_service_url,
            data=text_content.encode("utf-8"),
            timeout=timeout,
        ) as response:
            # Use response.raise_for_status() to handle all 2xx codes correctly
            response.raise_for_status()
            # Parse response JSON - only reached on successful 2xx response
            try:
                # Assuming Content Service returns JSON like {"storage_id": "..."}
                data: dict[str, str] = await response.json()
                storage_id = data.get("storage_id")

                if not storage_id:
                    raise_content_service_error(
                        service="spellchecker_service",
                        operation="store_content",
                        message="Content service response missing 'storage_id' field",
                        correlation_id=correlation_id,
                        content_service_url=content_service_url,
                        status_code=response.status,
                        response_data=str(data),
                    )

                logger.info(
                    f"{log_prefix}Successfully stored content, new storage_id: {storage_id}",
                    extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
                )
                return storage_id

            except Exception as json_error:
                response_text = await response.text()
                raise_content_service_error(
                    service="spellchecker_service",
                    operation="store_content",
                    message=f"Failed to parse Content Service JSON response: {str(json_error)}",
                    correlation_id=correlation_id,
                    content_service_url=content_service_url,
                    status_code=response.status,
                    response_text=response_text[:200],
                    json_error=str(json_error),
                )

    except aiohttp.ClientResponseError as e:
        # Handle HTTP errors (4xx/5xx) from raise_for_status()
        # Note: response body is not available in ClientResponseError
        raise_content_service_error(
            service="spellchecker_service",
            operation="store_content",
            message=f"Content Service HTTP error: {e.status} - {e.message}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            status_code=e.status,
            content_length=len(text_content),
            response_text=e.message[:200] if e.message else "No error message",
        )

    except aiohttp.ServerTimeoutError:
        raise_content_service_error(
            service="spellchecker_service",
            operation="store_content",
            message="Timeout storing content to Content Service",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            content_length=len(text_content),
            timeout_seconds=10,
        )

    except aiohttp.ClientError as e:
        raise_content_service_error(
            service="spellchecker_service",
            operation="store_content",
            message=f"Connection error storing content: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            content_length=len(text_content),
            client_error_type=type(e).__name__,
        )

    except Exception as e:
        logger.error(
            f"{log_prefix}Unexpected error storing content: {e}",
            exc_info=True,
            extra={"correlation_id": str(correlation_id), "content_length": len(text_content)},
        )
        raise_content_service_error(
            service="spellchecker_service",
            operation="store_content",
            message=f"Unexpected error storing content: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            content_length=len(text_content),
            error_type=type(e).__name__,
        )


def get_adaptive_edit_distance(word: str) -> int:
    """
    Determine optimal edit distance based on word characteristics.

    Returns:
        1 for long words (>9 chars) or compound words (containing '-' or "'")
        2 for short, simple words (better accuracy)
    """
    # Long words create exponential candidate generation with distance=2
    if len(word) > 9:
        return 1

    # Compound words and contractions are problematic with distance=2
    if "-" in word or "'" in word:
        return 1

    # Short, simple words benefit from distance=2 for better accuracy
    return 2


async def default_perform_spell_check_algorithm(
    text: str,
    essay_id: str | None = None,
    language: str = "en",
    correlation_id: UUID | None = None,
) -> tuple[str, int]:
    """
    Complete L2 + pyspellchecker pipeline implementation.

    Pipeline:
    1. Load/filter L2 error dictionary
    2. Apply L2 corrections to input text
    3. Run pyspellchecker on L2-corrected text
    4. Log detailed correction information
    5. Return final corrected text + correction count
    """
    log_prefix = f"Essay {essay_id}: " if essay_id else ""
    log_extra = {"essay_id": essay_id, "text_length": len(text), "language": language}
    if correlation_id:
        log_extra["correlation_id"] = str(correlation_id)

    import time

    start_time = time.time()

    logger.info(
        f"{log_prefix}Performing L2 + pyspellchecker algorithm for text (length: {len(text)})",
        extra=log_extra,
    )

    # Skip empty content or content with less than 20 words
    # if not text or len(text.strip().split()) < 20:
    #    logger.warning(f"{log_prefix}Text too short (less than 20 words), skipping spell check")
    #    return text, 0

    try:
        # Import the migrated modules (local to service)
        import re

        from spellchecker import SpellChecker

        from services.spellchecker_service.config import settings

        from .spell_logic.l2_dictionary_loader import apply_l2_corrections, load_l2_errors

        # 1. Load L2 dictionaries using environment-aware configuration
        logger.debug(
            f"{log_prefix}Loading L2 error dictionary from: "
            f"{settings.effective_filtered_dict_path}",
            extra=log_extra,
        )
        l2_load_start = time.time()
        l2_errors = load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)
        l2_load_time = time.time() - l2_load_start
        logger.info(
            f"{log_prefix}L2 dictionary load time: {l2_load_time:.3f}s",
            extra={**log_extra, "l2_load_time_seconds": l2_load_time},
        )

        if not l2_errors and settings.ENABLE_L2_CORRECTIONS:
            logger.warning(f"{log_prefix}L2 dictionary is empty but L2 corrections are enabled")

        # 2. Apply L2 corrections
        l2_apply_start = time.time()
        l2_corrected_text, l2_corrections = apply_l2_corrections(text, l2_errors)
        l2_correction_count = len(l2_corrections)
        l2_apply_time = time.time() - l2_apply_start
        logger.info(
            f"{log_prefix}L2 corrections apply time: {l2_apply_time:.3f}s",
            extra={**log_extra, "l2_apply_time_seconds": l2_apply_time},
        )

        if l2_correction_count > 0:
            logger.debug(
                f"{log_prefix}Applied {l2_correction_count} L2 corrections",
                extra={**log_extra, "l2_corrections": l2_correction_count},
            )

        # 3. Get or create cached pyspellchecker instances
        # We maintain two instances per language: distance=1 and distance=2
        global _spellchecker_cache

        # Create cache keys for both distances
        cache_key_d1 = f"{language}_d1"
        cache_key_d2 = f"{language}_d2"

        # Initialize SpellChecker with distance=1 if not cached
        if cache_key_d1 not in _spellchecker_cache:
            logger.debug(
                f"{log_prefix}Creating new SpellChecker for language: {language}, distance=1 (first time)",
                extra=log_extra,
            )
            spellchecker_init_start = time.time()
            _spellchecker_cache[cache_key_d1] = SpellChecker(language=language, distance=1)
            spellchecker_init_time = time.time() - spellchecker_init_start
            logger.info(
                f"{log_prefix}SpellChecker (distance=1) created and cached: {spellchecker_init_time:.3f}s",
                extra={
                    **log_extra,
                    "spellchecker_init_time_seconds": spellchecker_init_time,
                    "distance": 1,
                    "cache_hit": False,
                },
            )

        # Initialize SpellChecker with distance=2 if not cached
        if cache_key_d2 not in _spellchecker_cache:
            logger.debug(
                f"{log_prefix}Creating new SpellChecker for language: {language}, distance=2 (first time)",
                extra=log_extra,
            )
            spellchecker_init_start = time.time()
            _spellchecker_cache[cache_key_d2] = SpellChecker(language=language, distance=2)
            spellchecker_init_time = time.time() - spellchecker_init_start
            logger.info(
                f"{log_prefix}SpellChecker (distance=2) created and cached: {spellchecker_init_time:.3f}s",
                extra={
                    **log_extra,
                    "spellchecker_init_time_seconds": spellchecker_init_time,
                    "distance": 2,
                    "cache_hit": False,
                },
            )

        # 4. Apply pyspellchecker corrections
        logger.debug(f"{log_prefix}Running pyspellchecker on L2-corrected text", extra=log_extra)

        # Tokenize using pattern from prototype
        tokenize_start = time.time()
        token_pattern = re.compile(r"\w+(?:[-']\w+)*|[^\s\w]+|\s+")
        word_pattern = re.compile(r"^\w+(?:[-']\w+)*$")

        tokens = token_pattern.findall(l2_corrected_text)
        tokenize_time = time.time() - tokenize_start
        logger.debug(
            f"{log_prefix}Tokenization time: {tokenize_time:.3f}s, found {len(tokens)} tokens",
            extra={**log_extra, "tokenize_time_seconds": tokenize_time, "token_count": len(tokens)},
        )

        pyspellchecker_corrections = []
        final_corrected_tokens = []
        current_pos = 0

        # Collect words for spell checking
        word_collect_start = time.time()
        words_to_check = []
        word_indices_map = {}
        temp_word_idx = 0

        for i, token_text in enumerate(tokens):
            if word_pattern.fullmatch(token_text):
                words_to_check.append(token_text)
                word_indices_map[temp_word_idx] = {
                    "original_token_idx": i,
                    "text": token_text,
                    "start": current_pos,
                }
                temp_word_idx += 1
            current_pos += len(token_text)

        word_collect_time = time.time() - word_collect_start
        logger.debug(
            f"{log_prefix}Word collection time: {word_collect_time:.3f}s, found {len(words_to_check)} words",
            extra={
                **log_extra,
                "word_collect_time_seconds": word_collect_time,
                "word_count": len(words_to_check),
            },
        )

        # Find misspelled words - use distance=2 checker for unknown() as it has the full dictionary
        unknown_check_start = time.time()
        lowercase_words = [word.lower() for word in words_to_check]
        spell_checker_d2 = _spellchecker_cache[cache_key_d2]
        misspelled_lowercase = spell_checker_d2.unknown(lowercase_words)
        unknown_check_time = time.time() - unknown_check_start
        logger.info(
            f"{log_prefix}SpellChecker.unknown() time: {unknown_check_time:.3f}s, found {len(misspelled_lowercase)} misspelled words",
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
        current_pos = 0
        word_idx_counter = 0
        correction_times = []

        for token_text in tokens:
            token_len = len(token_text)
            if word_pattern.fullmatch(token_text):
                original_word = words_to_check[word_idx_counter]

                if original_word in misspelled_words:
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
                            f"{log_prefix}Slow correction: '{original_word}' -> '{corrected_word}' took {correction_time:.3f}s (distance={optimal_distance})",
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
                            f"{log_prefix}Corrected '{original_word}' using distance={optimal_distance} in {correction_time:.3f}s",
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
            logger.info(
                f"{log_prefix}Corrections loop time: {corrections_total_time:.3f}s, "
                f"max single correction: {max_correction_time:.3f}s, "
                f"avg correction: {avg_correction_time:.3f}s, "
                f"total corrections attempted: {len(correction_times)}",
                extra={
                    **log_extra,
                    "corrections_loop_time_seconds": corrections_total_time,
                    "max_correction_time_seconds": max_correction_time,
                    "avg_correction_time_seconds": avg_correction_time,
                    "corrections_attempted": len(correction_times),
                },
            )

        final_corrected_text = "".join(final_corrected_tokens)
        pyspell_correction_count = len(pyspellchecker_corrections)
        total_corrections = l2_correction_count + pyspell_correction_count

        # 5. Log correction details if enabled
        # Log detailed corrections if essay_id is provided (asynchronous, non-blocking)
        if essay_id:
            import asyncio

            async def log_corrections_async() -> None:
                """Background task for correction logging to avoid blocking request processing."""
                try:
                    from .spell_logic.correction_logger import log_essay_corrections_async

                    # Convert L2 corrections to expected format
                    l2_corrections_formatted = []
                    for corr in l2_corrections:
                        l2_corrections_formatted.append(
                            {
                                "original_word": corr.get("original_word", ""),
                                "corrected_word": corr.get("corrected_word", ""),
                                "start": corr.get("start", 0),
                                "end": corr.get("end", 0),
                                "rule": corr.get("rule", "L2"),
                            },
                        )

                    await log_essay_corrections_async(
                        essay_id=essay_id,
                        original_text=text,
                        initial_l2_corrected_text=l2_corrected_text,
                        final_corrected_text=final_corrected_text,
                        applied_initial_l2_corrections=l2_corrections_formatted,
                        main_checker_corrections=pyspellchecker_corrections,
                        l2_context_reverted_count=0,  # Not implemented in simplified flow
                        output_dir=settings.effective_correction_log_dir,
                    )
                    logger.debug(
                        f"{log_prefix}Detailed correction logging completed", extra=log_extra
                    )
                except Exception as e:
                    logger.warning(
                        f"{log_prefix}Failed to log detailed corrections: {e}", extra=log_extra
                    )

            # Schedule logging as background task (fire-and-forget)
            asyncio.create_task(log_corrections_async())
            logger.debug(
                f"{log_prefix}Scheduled correction logging as background task", extra=log_extra
            )

        total_time = time.time() - start_time
        logger.info(
            f"{log_prefix}L2 + pyspellchecker algorithm completed: "
            f"{l2_correction_count} L2 corrections, "
            f"{pyspell_correction_count} pyspellchecker corrections, "
            f"{total_corrections} total corrections "
            f"(total time: {total_time:.3f}s)",
            extra={
                **log_extra,
                "total_corrections": total_corrections,
                "total_processing_time_seconds": total_time,
            },
        )

        return final_corrected_text, total_corrections

    except Exception as e:
        logger.error(
            f"{log_prefix}Critical error in spell check algorithm: {e}",
            exc_info=True,
            extra=log_extra,
        )

        if correlation_id:
            raise_processing_error(
                service="spellchecker_service",
                operation="perform_spell_check_algorithm",
                message=f"Spell check algorithm failed: {str(e)}",
                correlation_id=correlation_id,
                algorithm_stage="spell_processing",
                content_length=len(text),
                language=language,
                essay_id=essay_id,
            )
        else:
            # Legacy fallback for backwards compatibility when correlation_id not provided
            logger.warning(
                f"{log_prefix}Falling back to original text due to algorithm error", extra=log_extra
            )
            return text, 0


# The classes ContentClient, ResultStore, SpellLogic that implement the protocols
# will likely live in event_router.py or a new di.py and use these _impl functions.
# For now, core_logic.py provides these fundamental pieces.
