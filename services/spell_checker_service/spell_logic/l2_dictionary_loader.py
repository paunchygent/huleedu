"""
L2 Dictionary Loader Module

This module provides functionality for loading, filtering, and applying L2 error corrections.
It's used for pre-processing text before spell checking to handle common L2 errors.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger(__name__)

# Import the filter with proper type checking to avoid circular imports
if TYPE_CHECKING:
    from .l2_filter import filter_l2_entries

    FILTER_AVAILABLE = True
else:
    try:
        from .l2_filter import filter_l2_entries

        FILTER_AVAILABLE = True
    except ImportError:
        logger.warning("L2 filter not available. Running without filtering.")
        FILTER_AVAILABLE = False

        def filter_l2_entries(x):  # type: ignore
            """No-op fallback when L2 filter is not available."""
            return x


def load_l2_errors(filename: str, filter_entries: bool = True) -> dict[str, str]:
    """Load L2 errors and their corrections from a file.

    Args:
        filename: The path to the file containing L2 errors and corrections.
                 Can be an absolute path or relative to the data directory.
        filter_entries: Whether to filter out unwanted corrections.

    Returns:
        Dictionary mapping errors to their corrections.
    """
    l2_errors = {}
    try:
        # If filename is not an absolute path, look in the data directory
        if not os.path.isabs(filename):
            # First try the path as-is (for backward compatibility)
            if os.path.exists(filename):
                file_path = filename
            # Then try in the data directory
            elif os.path.exists(os.path.join("data", filename)):
                file_path = os.path.join("data", filename)
            else:
                file_path = filename  # Will raise FileNotFoundError with original path
        else:
            file_path = filename

        logger.debug(f"Loading L2 corrections from: {file_path}")
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line:
                    wrong, correct = line.split(":", 1)
                    wrong = wrong.strip()
                    correct = correct.strip()

                    # Don't include entries where wrong is a single character or punctuation
                    if len(wrong) <= 1:
                        continue

                    # Add targeted logging for specific words
                    if wrong == "recrutie":
                        logger.debug(f"LOAD_L2_ERRORS: Found 'recrutie': '{wrong}' -> '{correct}'")
                    if wrong == "comited":
                        logger.debug(f"LOAD_L2_ERRORS: Found 'comited': '{wrong}' -> '{correct}'")

                    l2_errors[wrong] = correct

        logger.info(f"Loaded {len(l2_errors)} L2 error corrections")
        if l2_errors:
            sample = dict(list(l2_errors.items())[:5])
            logger.info(f"Sample corrections: {sample}")

        # Filter the entries if requested and filter is available
        if filter_entries and FILTER_AVAILABLE:
            l2_errors = filter_l2_entries(l2_errors)
            logger.info(f"After filtering: {len(l2_errors)} L2 error corrections")
            if l2_errors:
                sample = dict(list(l2_errors.items())[:5])
                logger.info(f"Sample filtered corrections: {sample}")

    except Exception as e:
        logger.error(f"Error loading L2 errors file: {e}")

    return l2_errors


def apply_l2_corrections(text: str, l2_errors: dict[str, str]) -> tuple[str, list[dict]]:
    """Apply L2 corrections to text directly, before Spark processing.

    This function tokenizes text into words, punctuation, and whitespace,
    then applies L2 corrections to word tokens while tracking changes.
    Handles various word forms including hyphenated words and contractions.

    Args:
        text: The essay text to correct
        l2_errors: Dictionary mapping incorrect spellings to corrections

    Returns:
        Tuple of (corrected_text, applied_corrections) where applied_corrections
        is a list of dicts with keys: original_word, corrected_word, rule, start, end
    """
    # Pre-compile regex patterns
    token_pattern = re.compile(r"\w+(?:[-']\w+)*|[^\s\w]+|\s+")
    word_pattern = re.compile(r"^\w+(?:[-']\w+)*$")

    # Tokenize the input text
    tokens = token_pattern.findall(text)
    applied_corrections = []
    corrected_tokens = []
    pos = 0  # Tracks position in the original text

    for token in tokens:
        # Skip non-word tokens (whitespace, punctuation)
        if not word_pattern.fullmatch(token):
            corrected_tokens.append(token)
            pos += len(token)
            continue

        # Check for corrections
        correction = None
        original_case = token
        lowercase_token = token.lower()

        # Case 1: Exact match
        if token in l2_errors:
            correction = l2_errors[token]
        # Case 2: Lowercase match with case preservation
        elif lowercase_token in l2_errors:
            correction = l2_errors[lowercase_token]
            # Apply original token's capitalization to correction
            if token.isupper() and len(token) > 1:
                correction = correction.upper()
            elif token[0].isupper() and correction and correction[0].islower():
                correction = correction[0].upper() + correction[1:]
        # Case 3: Handle hyphenated words by checking individual parts
        elif "-" in token:
            parts = token.split("-")
            corrected_parts = []
            any_correction = False

            for part in parts:
                part_correction = part  # Default to original part
                lowercase_part = part.lower()

                if part in l2_errors:
                    part_correction = l2_errors[part]
                    any_correction = True
                elif lowercase_part in l2_errors:
                    part_correction = l2_errors[lowercase_part]
                    # Apply original part's capitalization to correction
                    if part.isupper() and len(part) > 1:
                        part_correction = part_correction.upper()
                    elif part[0].isupper() and part_correction and part_correction[0].islower():
                        part_correction = part_correction[0].upper() + part_correction[1:]
                    any_correction = True

                corrected_parts.append(part_correction)

            if any_correction:
                correction = "-".join(corrected_parts)

        # Apply correction if found
        if correction:
            applied_corrections.append(
                {
                    "original_word": original_case,
                    "corrected_word": correction,
                    "rule": "L2 dictionary",
                    "start": pos,
                    "end": pos + len(original_case) - 1,
                },
            )
            corrected_tokens.append(correction)
        else:
            corrected_tokens.append(token)

        pos += len(token)

    return "".join(corrected_tokens), applied_corrections


def create_filtered_l2_dictionary(l2_errors: dict[str, str], output_path: str) -> bool:
    """Create a filtered dictionary file that Normalizer can use safely.

    This is a convenience wrapper around the implementation in l2_filter.

    Args:
        l2_errors: Dictionary of error corrections
        output_path: Path to save the filtered dictionary

    Returns:
        bool: True if successful, False otherwise

    Note:
        This function requires the `l2_filter` module and its dependencies.
        If the module is not available, this function will log an error and return False.
    """
    try:
        from .l2_filter import create_filtered_l2_dictionary as _create_filtered_dict

        return _create_filtered_dict(l2_errors, output_path)
    except ImportError as e:
        logger.error(f"Failed to import l2_filter: {e}")
        return False
    except Exception as e:
        logger.error(f"Error creating filtered L2 dictionary: {e}")
        return False


def apply_specific_corrections(text: str, corrections_to_apply: list[dict]) -> str:
    """Apply specific corrections to text directly, without dictionary lookup.

    This function applies only the corrections provided in corrections_to_apply list,
    rather than looking up corrections in a dictionary.

    Args:
        text: The essay text to correct
        corrections_to_apply: List of corrections to apply, each a dict with keys:
                             original_word, corrected_word, start, end

    Returns:
        The text with only the specified corrections applied
    """
    if not corrections_to_apply:
        return text

    # Sort corrections by start position to process them in order
    sorted_corrections = sorted(corrections_to_apply, key=lambda c: c["start"])

    # Build the corrected text piece by piece
    result = []
    last_end = 0

    for correction in sorted_corrections:
        start = correction["start"]
        end = correction["end"] + 1  # end is inclusive in correction dict, exclusive for slicing
        original_word = correction["original_word"]
        corrected_word = correction["corrected_word"]

        # Validate correction boundaries
        if start < last_end:
            logger.warning(f"Overlapping correction at position {start}-{end - 1}, skipping")
            continue

        if end > len(text):
            logger.warning(f"Correction boundary {end - 1} exceeds text length {len(text)}")
            continue

        # Verify that the text at this position matches the original word
        text_slice = text[start:end]
        if text_slice != original_word:
            logger.warning(
                f"Text at position {start}-{end - 1} ('{text_slice}') "
                f"doesn't match expected original word '{original_word}', skipping",
            )
            continue

        # Add text between last correction and this one
        result.append(text[last_end:start])

        # Add the corrected word
        result.append(corrected_word)

        # Update last_end for next iteration
        last_end = end

    # Add any remaining text after the last correction
    result.append(text[last_end:])

    return "".join(result)


def create_word_boundaries_map(text: str) -> dict[int, tuple[int, int]]:
    """Create a map of word indices to their character positions in the text.

    Args:
        text: The text to analyze

    Returns:
        Dictionary mapping word positions to character positions (start, end)
    """
    words = re.finditer(r"\S+", text)
    word_map = {}
    for i, match in enumerate(words):
        word_map[i] = (match.start(), match.end() - 1)
    return word_map
