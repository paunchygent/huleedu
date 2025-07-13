from __future__ import annotations

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
        l2_errors = load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)

        if not l2_errors and settings.ENABLE_L2_CORRECTIONS:
            logger.warning(f"{log_prefix}L2 dictionary is empty but L2 corrections are enabled")

        # 2. Apply L2 corrections
        l2_corrected_text, l2_corrections = apply_l2_corrections(text, l2_errors)
        l2_correction_count = len(l2_corrections)

        if l2_correction_count > 0:
            logger.debug(
                f"{log_prefix}Applied {l2_correction_count} L2 corrections",
                extra={**log_extra, "l2_corrections": l2_correction_count},
            )

        # 3. Initialize pyspellchecker
        logger.debug(
            f"{log_prefix}Initializing SpellChecker for language: {language}", extra=log_extra
        )
        try:
            spell_checker = SpellChecker(language=language)
        except Exception as e:
            logger.warning(
                f"{log_prefix}Failed to initialize SpellChecker for language '{language}': {e}, "
                f"falling back to L2 corrections only",
                extra=log_extra,
            )
            # Fallback to L2 corrections only
            return l2_corrected_text, l2_correction_count

        # 4. Apply pyspellchecker corrections
        logger.debug(f"{log_prefix}Running pyspellchecker on L2-corrected text", extra=log_extra)

        # Tokenize using pattern from prototype
        token_pattern = re.compile(r"\w+(?:[-']\w+)*|[^\s\w]+|\s+")
        word_pattern = re.compile(r"^\w+(?:[-']\w+)*$")

        tokens = token_pattern.findall(l2_corrected_text)
        pyspellchecker_corrections = []
        final_corrected_tokens = []
        current_pos = 0

        # Collect words for spell checking
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

        # Find misspelled words - check lowercase versions for consistency
        lowercase_words = [word.lower() for word in words_to_check]
        misspelled_lowercase = spell_checker.unknown(lowercase_words)

        # Map back to original case words that need correction
        misspelled_words = set()
        for i, lowercase_word in enumerate(lowercase_words):
            if lowercase_word in misspelled_lowercase:
                misspelled_words.add(words_to_check[i])  # Add original case word

        # Apply corrections
        current_pos = 0
        word_idx_counter = 0

        for token_text in tokens:
            token_len = len(token_text)
            if word_pattern.fullmatch(token_text):
                original_word = words_to_check[word_idx_counter]

                if original_word in misspelled_words:
                    corrected_word = spell_checker.correction(original_word.lower())

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

        final_corrected_text = "".join(final_corrected_tokens)
        pyspell_correction_count = len(pyspellchecker_corrections)
        total_corrections = l2_correction_count + pyspell_correction_count

        # 5. Log correction details if enabled
        if settings.ENABLE_CORRECTION_LOGGING and essay_id:
            try:
                from .spell_logic.correction_logger import log_essay_corrections

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

                log_essay_corrections(
                    essay_id=essay_id,
                    original_text=text,
                    initial_l2_corrected_text=l2_corrected_text,
                    final_corrected_text=final_corrected_text,
                    applied_initial_l2_corrections=l2_corrections_formatted,
                    main_checker_corrections=pyspellchecker_corrections,
                    l2_context_reverted_count=0,  # Not implemented in simplified flow
                    output_dir=settings.effective_correction_log_dir,
                )
                logger.debug(f"{log_prefix}Detailed correction logging completed", extra=log_extra)
            except Exception as e:
                logger.warning(
                    f"{log_prefix}Failed to log detailed corrections: {e}", extra=log_extra
                )

        logger.info(
            f"{log_prefix}L2 + pyspellchecker algorithm completed: "
            f"{l2_correction_count} L2 corrections, "
            f"{pyspell_correction_count} pyspellchecker corrections, "
            f"{total_corrections} total corrections",
            extra={**log_extra, "total_corrections": total_corrections},
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
