"""
Orchestrates a multi-stage spell checking pipeline for essays.

This module processes essays through:
1.  Initial L2 (second language learner) error correction using a filtered dictionary.
2.  Standard Spark NLP spell checking (e.g., Norvig, Symmetric, ContextSpellChecker) on the

It uses loguru for detailed logging and outputs corrected essays and comprehensive
correction logs for each processing stage.
"""

from __future__ import annotations

import os
import re  # Added for tokenization
import sys
from typing import Any
import argparse # Added for CLI argument parsing

from loguru import logger  # Using loguru
from spellchecker import SpellChecker  # Added for pyspellchecker

from src.cj_essay_assessment.spell_checker.l2_dictionary_loader import (
    apply_l2_corrections, load_l2_errors)
from src.cj_essay_assessment.spell_checker.l2_filter import \
    create_filtered_l2_dictionary
# Import the new logging utility
from src.cj_essay_assessment.utils.correction_logger_util import \
    log_essay_corrections

# Path to the L2 corrections file in the package directory
L2_ERRORS_FILE = os.path.join(
    os.path.dirname(__file__), "l2_error_dict", "nortvig_master_SWE_L2_corrections.txt"
)


def configure_logging(log_level: str = "INFO") -> None:
    """Configures loguru logging."""
    logger.remove()
    format_string = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(sys.stderr, level=log_level.upper(), format=format_string)
    # Create logs directory if it doesn't exist for file logging
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/spellcheck_debug_{time}.log",
        level=log_level.upper(),
        rotation="10 MB",
        retention="3 days",
        compression="zip",
        format=format_string,
    )
    logger.info(f"Logging configured at level {log_level.upper()}")


LOG_LEVEL = os.environ.get("LOGURU_LEVEL", "DEBUG")
configure_logging(LOG_LEVEL)


# L2 dictionary functions moved to l2_dictionary_loader.py


# apply_l2_corrections function moved to l2_dictionary_loader.py


# create_word_boundaries_map function moved to l2_dictionary_loader.py


# create_filtered_l2_dictionary function moved to l2_dictionary_loader.py


def load_essays(essays_dir: str = "data/test_subset") -> list[dict[str, str]]:
    """Load essays from a directory.

    Args:
        essays_dir: Directory containing essay text files.

    Returns:
        List of dictionaries containing essay IDs and their content.
    """
    essays = []
    try:
        for filename in os.listdir(essays_dir):
            if filename.endswith(".txt"):
                essay_id = filename.split(" ")[0]  # Extract essay ID from filename
                file_path = os.path.join(essays_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read().strip()
                        if content:  # Only add non-empty essays
                            essays.append({"essay_id": essay_id, "text": content})
                except Exception as e:
                    logger.error(f"Error reading essay {filename}: {e}")
        logger.info(f"Loaded {len(essays)} essays from {essays_dir}")
    except Exception as e:
        logger.error(f"Error loading essays: {e}")
    return essays


def run_spellcheck(
    essays_dir: str = "data/test_subset",
    output_dir: str = "data/corrected_essays",
    language: str = "en",  # Changed from model_name to language
    log_level: str = "INFO",
) -> dict:
    """Runs the multi-stage spell checking pipeline on a directory of essays.

    The process involves:
    1.  Loading essays and initializing pyspellchecker.
    2.  Preparing L2 error dictionaries (master and filtered).
    3.  For each essay:
        a.  Applying initial L2 corrections from the filtered dictionary.
        b.  Running the main pyspellchecker spell checking pipeline on the L2-corrected text.
        c.  Logging detailed correction information.
        d.  Reconstructing and saving the final corrected text.

    Args:
        essays_dir: Directory containing essay text files to process.
        output_dir: Directory to save corrected essays and detailed logs.
        language: Language code for the spell checker (e.g., "en", "es").
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        dict: A dictionary containing processing results and statistics, including
              the number of L2 corrections applied.
    """
    configure_logging(log_level)
    logger.info(f"Starting spell check with language: {language}")

    results: dict[str, Any] = {
        "total_essays": 0,
        "successful": 0,
        "failed": 0,
        "l2_corrections_applied_from_filtered_dict": 0,
        "output_dir": output_dir,
    }

    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Initialize Pyspellchecker
        try:
            spell_checker = SpellChecker(language=language)
            logger.info(f"Pyspellchecker initialized for language: {language}")
        except Exception as e:
            logger.error(f"Failed to initialize SpellChecker for language '{language}': {e}")
            # Depending on desired behavior, could re-raise or handle to skip spellcheck
            # For now, let it proceed, subsequent steps might fail or log no corrections
            spell_checker = None # Ensure it's defined for later checks

        # --- L2 Dictionary Preparation ---
        logger.info(f"Loading master L2 error dictionary from: {L2_ERRORS_FILE}")
        raw_l2_errors_master = load_l2_errors(L2_ERRORS_FILE, filter_entries=False)

        # Define path for the filtered L2 dictionary for production use
        filtered_dict_path = os.path.join(output_dir, "filtered_l2_production_dict.txt")
        logger.info(f"Creating filtered L2 dictionary for production at: {filtered_dict_path}")
        create_filtered_l2_dictionary(raw_l2_errors_master, filtered_dict_path)

        logger.info(f"Loading production L2 dictionary from: {filtered_dict_path}")
        production_l2_dict = load_l2_errors(filtered_dict_path, filter_entries=False)
        if not production_l2_dict:
            logger.warning("Production L2 dictionary is empty. No L2 pre-corrections will be applied.")

        # Load essays
        essays = load_essays(essays_dir)
        if not essays:
            logger.warning(f"No essays found in {essays_dir}. Exiting.")
            return results  # Return empty results if no essays to process

        results["total_essays"] = len(essays)

        logger.info("Configuring spell checking pipeline...")

        # Process each essay individually
        for essay_data in essays:
            try:
                essay_id = essay_data["essay_id"]
                original_text = essay_data["text"]
                logger.info(f"Processing essay ID: {essay_id}")

                # --- Apply L2 Pre-corrections (Sub-task 6.6) ---
                l2_corrected_text, initial_applied_l2_corrections_data = apply_l2_corrections(
                    original_text, production_l2_dict
                )

                applied_l2_count = len(initial_applied_l2_corrections_data)
                if applied_l2_count > 0:
                    logger.debug(
                        f"Essay ID {essay_id}: Applied {applied_l2_count} initial L2 corrections."
                    )
                    results["l2_corrections_applied_from_filtered_dict"] += applied_l2_count
                
                # Prepare L2 corrections data for logging
                applied_l2_for_log = {
                    f"{item['original_word']}_{item['start']}": item['corrected_word'] 
                    for item in initial_applied_l2_corrections_data
                }

                # --- Pyspellchecker Spell Checking ---
                pyspellchecker_applied_corrections = []
                final_corrected_text = l2_corrected_text # Default if spell_checker failed or no corrections

                if spell_checker:
                    final_corrected_parts = []
                    current_pos_in_l2_text = 0

                    token_pattern = re.compile(r"\w+(?:[-']\w+)*|[^\s\w]+|\s+")
                    word_pattern = re.compile(r"^\w+[-']?\w*$")

                    l2_tokens = token_pattern.findall(l2_corrected_text)
                    
                    words_from_l2_text = [t for t in l2_tokens if word_pattern.fullmatch(t)]
                    if words_from_l2_text:
                        misspelled_words = spell_checker.unknown(words_from_l2_text)
                    else:
                        misspelled_words = set()

                    for token_text in l2_tokens:
                        token_start_pos = current_pos_in_l2_text
                        current_pos_in_l2_text += len(token_text)
                        token_end_pos = current_pos_in_l2_text - 1

                        if word_pattern.fullmatch(token_text):
                            original_word_case = token_text
                            if original_word_case in misspelled_words or original_word_case.lower() in misspelled_words:
                                # Prefer checking original case first, then lower, as `unknown` might be case sensitive
                                # depending on dictionary. `correction` method is typically case-insensitive for input.
                                correction = spell_checker.correction(original_word_case) 
                                
                                if correction and correction != original_word_case:
                                    # Attempt to preserve original capitalization style
                                    if original_word_case.isupper() and len(original_word_case) > 1:
                                        corrected_word_display = correction.upper()
                                    elif original_word_case.istitle():
                                        corrected_word_display = correction.title()
                                    elif original_word_case[0].islower() and len(original_word_case) > 0 : # all lower
                                         corrected_word_display = correction.lower()
                                    else: # Mixed case or single char, use correction's default casing
                                        corrected_word_display = correction
                                    
                                    # Log if actual change happens after case adjustment
                                    if corrected_word_display != original_word_case:
                                        pyspellchecker_applied_corrections.append({
                                            "original_word": original_word_case,
                                            "corrected_word": corrected_word_display,
                                            "start": token_start_pos,
                                            "end": token_end_pos,
                                        })
                                        final_corrected_parts.append(corrected_word_display)
                                    else:
                                        final_corrected_parts.append(original_word_case) # Corrected but same after case adjustment
                                else:
                                    final_corrected_parts.append(original_word_case) # No correction found or correction is same as original
                            else:
                                final_corrected_parts.append(original_word_case) # Not in misspelled set
                        else:
                            final_corrected_parts.append(token_text) # Non-word token
                    
                    if final_corrected_parts: # Ensure parts were actually processed
                        final_corrected_text = "".join(final_corrected_parts)
            
                results["successful"] += 1

                # --- Logging and Saving ---
                log_essay_corrections(
                    essay_id=essay_id,
                    original_text=original_text,
                    initial_l2_corrected_text=l2_corrected_text,
                    final_corrected_text=final_corrected_text,
                    applied_initial_l2_corrections=initial_applied_l2_corrections_data, # Pass the list of dicts
                    main_checker_corrections=pyspellchecker_applied_corrections, # Pass pyspellchecker corrections
                    l2_context_reverted_count=0,  # Assuming 0 for simplified flow
                    output_dir=output_dir,
                )

                # Save the final corrected essay
                output_essay_path = os.path.join(output_dir, f"{essay_id}_corrected.txt")
                with open(output_essay_path, "w", encoding="utf-8") as f:
                    f.write(final_corrected_text)
                logger.info(
                    f"Essay {essay_id}: Saved final corrected text to {output_essay_path}"
                )

                results[essay_id] = {
                    "status": "success",
                    "l2_applied": len(initial_applied_l2_corrections_data), 
                    "output_path": output_essay_path,
                }

            except Exception as e:
                error_msg = f"An error occurred while processing essay {essay_id}: {e}"
                logger.opt(exception=True).error(error_msg)
                results["failed"] += 1
                results[essay_id] = {"status": "error", "error": str(e)}

        logger.info("\n\n--- Finished Individual Essay Processing ---")
        logger.info(
            f"Successfully processed {results['successful']} out of {results['total_essays']} essays"
        )
        logger.info(
            f"L2 corrections applied from filtered dictionary: {results['l2_corrections_applied_from_filtered_dict']}"
        )

        if results["failed"] > 0:
            logger.warning(f"Failed to process {results['failed']} essays")

        return results

    except Exception as e:
        error_msg = f"An error occurred during the spell check execution: {e}"
        logger.opt(exception=True).error(error_msg)
        results["error"] = error_msg
        return results


def main():
    """Command-line entry point for running the spell checker."""
    parser = argparse.ArgumentParser(description="Run spell checking on essays.")
    parser.add_argument(
        "--essays-dir",
        type=str,
        default="data/test_subset",
        help="Directory containing essay text files.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/corrected_essays",
        help="Directory to save corrected essays and logs.",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Language code for the spell checker (e.g., 'en', 'es').",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level.",
    )
    args = parser.parse_args()

    results = run_spellcheck(
        essays_dir=args.essays_dir,
        output_dir=args.output_dir,
        language=args.language,  # Changed from model_name
        log_level=args.log_level,
    )

    # Exit with appropriate status code
    if results and results.get("failed", 0) > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
