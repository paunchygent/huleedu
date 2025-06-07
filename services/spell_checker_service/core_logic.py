from __future__ import annotations

from typing import Optional, Tuple

import aiohttp  # For ClientSession type hint
from aiohttp import ClientTimeout

# from common_core.enums import ContentType # Not directly used by these low-level functions
# from common_core.events.spellcheck_models import SpellcheckResultDataV1 # Not directly returned
# from common_core.metadata_models import StorageReferenceMetadata # Not directly used
from huleedu_service_libs.logging_utils import create_service_logger

# Protocols are not implemented here, but these functions can be *used* by their implementations
# from .protocols import (
#     ContentClientProtocol,
#     ResultStoreProtocol,
#     SpellLogicProtocol,
# )

logger = create_service_logger("spell_checker_service.core_logic")


# --- Default Implementations / Helpers ---


async def default_fetch_content_impl(
    session: aiohttp.ClientSession,
    storage_id: str,
    content_service_url: str,
    essay_id: Optional[str] = None,
) -> str:
    """
    Default implementation for fetching content from the content service.
    Raises exception on failure.
    """
    url = f"{content_service_url}/{storage_id}"
    log_prefix = f"Essay {essay_id}: " if essay_id else ""
    logger.debug(f"{log_prefix}Fetching content from URL: {url}")
    try:
        timeout = ClientTimeout(total=10)
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            content = await response.text()
            logger.debug(
                f"{log_prefix}Fetched content from {storage_id} (first 100 chars: {content[:100]})"
            )
            return content
    except Exception as e:
        logger.error(
            f"{log_prefix}Error fetching content {storage_id} from {url}: {e}",
            exc_info=True,
        )
        raise  # Re-raise after logging


async def default_store_content_impl(
    session: aiohttp.ClientSession,
    text_content: str,
    content_service_url: str,
    essay_id: Optional[str] = None,
) -> str:
    """
    Default implementation for storing content to the content service.
    Raises exception on failure.
    """
    log_prefix = f"Essay {essay_id}: " if essay_id else ""
    logger.debug(
        f"{log_prefix}Storing content (length: {len(text_content)}) "
        f"to Content Service via {content_service_url}"
    )
    try:
        timeout = ClientTimeout(total=10)
        async with session.post(
            content_service_url, data=text_content.encode("utf-8"), timeout=timeout
        ) as response:
            response.raise_for_status()
            # Assuming Content Service returns JSON like {"storage_id": "..."}
            data: dict[str, str] = await response.json()
            storage_id = data.get("storage_id")
            if not storage_id:
                raise ValueError("Content service response did not include 'storage_id'")
            logger.info(f"{log_prefix}Stored corrected text, new_storage_id: {storage_id}")
            return storage_id
    except Exception as e:
        logger.error(f"{log_prefix}Error storing content: {e}", exc_info=True)
        raise  # Re-raise after logging


async def default_perform_spell_check_algorithm(
    text: str, essay_id: Optional[str] = None, language: str = "en"
) -> Tuple[str, int]:
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
    logger.info(
        f"{log_prefix}Performing L2 + pyspellchecker algorithm for text (length: {len(text)})"
    )

    # Skip empty content or content with less than 20 words
    if not text or len(text.strip().split()) < 20:
        logger.warning(f"{log_prefix}Text too short (less than 20 words), skipping spell check")
        return text, 0

    try:
        # Import the migrated modules (local to service)
        import re

        from spell_logic.l2_dictionary_loader import apply_l2_corrections, load_l2_errors
        from spellchecker import SpellChecker

        from services.spell_checker_service.config import settings

        # 1. Load L2 dictionaries using environment-aware configuration
        logger.debug(
            f"{log_prefix}Loading L2 error dictionary from: {settings.effective_filtered_dict_path}"
        )
        l2_errors = load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)

        if not l2_errors and settings.ENABLE_L2_CORRECTIONS:
            logger.warning(f"{log_prefix}L2 dictionary is empty but L2 corrections are enabled")

        # 2. Apply L2 corrections
        l2_corrected_text, l2_corrections = apply_l2_corrections(text, l2_errors)
        l2_correction_count = len(l2_corrections)

        if l2_correction_count > 0:
            logger.debug(f"{log_prefix}Applied {l2_correction_count} L2 corrections")

        # 3. Initialize pyspellchecker
        logger.debug(f"{log_prefix}Initializing SpellChecker for language: {language}")
        try:
            spell_checker = SpellChecker(language=language)
        except Exception as e:
            logger.error(
                f"{log_prefix}Failed to initialize SpellChecker for language '{language}': {e}"
            )
            # Fallback to L2 corrections only
            return l2_corrected_text, l2_correction_count

        # 4. Apply pyspellchecker corrections
        logger.debug(f"{log_prefix}Running pyspellchecker on L2-corrected text")

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
                                }
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
                from spell_logic.correction_logger import log_essay_corrections

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
                        }
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
                logger.debug(f"{log_prefix}Detailed correction logging completed")
            except Exception as e:
                logger.warning(f"{log_prefix}Failed to log detailed corrections: {e}")

        logger.info(
            f"{log_prefix}L2 + pyspellchecker algorithm completed:\n"
            f"{l2_correction_count} L2 corrections, "
            f"{pyspell_correction_count} pyspellchecker corrections, "
            f"{total_corrections} total corrections"
        )

        return final_corrected_text, total_corrections

    except Exception as e:
        logger.error(f"{log_prefix}Error in spell check algorithm: {e}", exc_info=True)
        # Fallback to original text
        return text, 0


# The classes ContentClient, ResultStore, SpellLogic that implement the protocols
# will likely live in event_router.py or a new di.py and use these _impl functions.
# For now, core_logic.py provides these fundamental pieces.
