"""
Utility functions for logging essay corrections (L2 and Spark NLP).
"""

from __future__ import annotations

import os
from io import StringIO
from typing import TYPE_CHECKING, Any

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger(__name__)

# To avoid circular imports if Spark NLP types are complex
if TYPE_CHECKING:
    pass  # No specific type imports needed here for now


def log_essay_corrections(
    essay_id: str,
    original_text: str,
    initial_l2_corrected_text: str,
    final_corrected_text: str,
    applied_initial_l2_corrections: list[dict[str, Any]] | None,
    main_checker_corrections: list[dict[str, Any]] | None,  # Changed from spark_nlp_annotations
    l2_context_reverted_count: int,
    output_dir: str = "data/corrected_essays",
) -> None:
    """
    Logs the multi-stage L2 and Spark NLP corrections applied to an essay.

    The logging process includes:
    1.  Initial L2 corrections applied from the filtered dictionary.
    2.  Contextual L2 reversions (if any, typically 0 with simplified L2 flow).
    3.  Spark NLP spell corrections applied on top of the initial L2-corrected text.

    Writes a consolidated log file for the essay.

    Args:
        essay_id: The unique identifier for the essay.
        original_text: The text of the essay before any corrections.
        initial_l2_corrected_text: Text after applying the filtered L2 dictionary.
        final_corrected_text: Text after the main spell checker corrections (e.g., pyspellchecker)
                              have been applied to the initial_l2_corrected_text.
        applied_initial_l2_corrections: List of L2 corrections initially applied (dicts).
        main_checker_corrections: List of corrections (dicts) from the main spell checker
                                  (e.g., {'original_word': str, 'corrected_word': str,
                                  'start': int, 'end': int}).
        l2_context_reverted_count: Number of L2 corrections reverted by contextual validation.
        output_dir: Directory to save the correction log file.
    """
    log_buffer = StringIO()
    log_buffer.write(f"Correction Analysis for Essay ID: {essay_id}\n")
    log_buffer.write("=" * 80 + "\n")

    # --- Section 1: Original Text ---
    log_buffer.write("\nSection 1: Original Text Snippet:\n")
    log_buffer.write("-" * 80 + "\n")
    log_buffer.write(original_text[:200] + ("..." if len(original_text) > 200 else "") + "\n")

    # --- Section 2: Initial L2 Corrections Applied ---
    log_buffer.write("\nSection 2: Initial L2 Corrections Applied:\n")
    log_buffer.write("-" * 80 + "\n")
    if applied_initial_l2_corrections:
        log_buffer.write(
            f"Total initial L2 corrections applied: {len(applied_initial_l2_corrections)}\n",
        )
        for corr in applied_initial_l2_corrections:
            log_buffer.write(
                f"  - '{corr['original_word']}' -> '{corr['corrected_word']}' "
                f"at indices {corr['start']}-{corr['end']} (Rule: {corr.get('rule', 'N/A')})\n",
            )
        import difflib

        # Using splitlines for potentially better readability of multiline diffs
        diff1 = "\n".join(
            difflib.unified_diff(
                original_text.splitlines(),
                initial_l2_corrected_text.splitlines(),
                lineterm="",
                fromfile="Original Text",
                tofile="Initial L2 Corrected Text",
            ),
        )
        if diff1.strip():  # Check if diff is not empty
            log_buffer.write("\nDiff Original -> Initial L2 Corrected:\n" + diff1 + "\n")
        else:
            log_buffer.write(
                "No textual changes from Original to Initial L2 Corrected "
                "(based on diff, check applied count).\n",
            )
    else:
        log_buffer.write("No initial L2 corrections were applied or data not provided.\n")

    # --- Section 2b: Contextual L2 Reversions (Simplified Logging) ---
    log_buffer.write("\nSection 2b: Contextual L2 Reversions (Simplified Logging):\n")
    log_buffer.write("-" * 80 + "\n")
    log_buffer.write(
        f"Number of L2 corrections reverted by contextual validation: "
        f"{l2_context_reverted_count}\n",
    )
    log_buffer.write(
        "(Note: With the current simplified L2 flow, this count is expected to be 0.)\n",
    )

    # --- Section 3: Text Entering Main Spell Checker (Initial L2 Corrected) ---
    log_buffer.write("\nSection 3: Text Entering Main Spell Checker (Initial L2 Corrected Text):\n")
    log_buffer.write("-" * 80 + "\n")
    log_buffer.write(
        initial_l2_corrected_text[:200]
        + ("..." if len(initial_l2_corrected_text) > 200 else "")
        + "\n",
    )

    # --- Section 4: Main Spell Checker Corrections (on Initial L2 Corrected Text) ---
    log_buffer.write(
        "\nSection 4: Main Spell Checker Corrections (Applied to Initial L2 Corrected Text):\n",
    )
    log_buffer.write("-" * 80 + "\n")

    if main_checker_corrections:
        spell_changes_found = False
        for correction in main_checker_corrections:
            original_word = correction.get("original_word", "N/A")
            corrected_word = correction.get("corrected_word", "N/A")
            start_offset = correction.get("start", -1)
            end_offset = correction.get("end", -1)

            if original_word != corrected_word:
                log_buffer.write(
                    f"  - '{original_word}' -> '{corrected_word}' "
                    f"(indices {start_offset}-{end_offset})\n",
                )
                spell_changes_found = True

        if not spell_changes_found:
            log_buffer.write(
                "No specific spell corrections made by the main spell checker "
                "relative to Initial L2 Corrected Text.\n",
            )
    else:
        log_buffer.write(
            "No main spell checker corrections provided or available to process "
            "for detailed correction listing.\n",
        )

    import difflib

    # Diffing initial_l2_corrected_text against the final_corrected_text (passed from caller)
    # provides the most accurate representation of changes from the caller's perspective.
    diff2 = "\n".join(
        difflib.unified_diff(
            initial_l2_corrected_text.splitlines(),
            final_corrected_text.splitlines(),  # Use the final text from the caller
            lineterm="",
            fromfile="Initial L2 Corrected Text",
            tofile="Final Corrected Text (Caller)",
        ),
    )
    if diff2.strip():  # Check if diff is not empty
        log_buffer.write(
            "\nDiff Initial L2 Corrected -> Final Corrected (Caller Perspective):\n" + diff2 + "\n",
        )
    else:
        log_buffer.write(
            "No textual changes from Initial L2 Corrected to Final Corrected "
            "(Caller Perspective based on diff).\n",
        )

    # --- Section 5: Final Text Overview ---
    log_buffer.write("\nSection 5: Final Texts Overview:\n")
    log_buffer.write("-" * 80 + "\n")
    log_buffer.write(
        "Original: " + original_text[:100] + ("..." if len(original_text) > 100 else "") + "\n",
    )
    log_buffer.write(
        "Initial L2 Corrected: "
        + initial_l2_corrected_text[:100]
        + ("..." if len(initial_l2_corrected_text) > 100 else "")
        + "\n",
    )
    log_buffer.write(
        "Final Main Checker Corrected (from Caller): "
        + final_corrected_text[:100]
        + ("..." if len(final_corrected_text) > 100 else "")
        + "\n",
    )

    # --- Save the combined correction log to file ---
    log_output_path = os.path.join(output_dir, f"{essay_id}_corrections_log.txt")
    try:
        os.makedirs(output_dir, exist_ok=True)  # Ensure output directory exists
        with open(log_output_path, "w", encoding="utf-8") as f:
            f.write(log_buffer.getvalue())
        logger.info(f"Saved detailed correction log to: {log_output_path}")
    except Exception as e:
        logger.error(f"Error saving correction log for essay {essay_id} to {log_output_path}: {e}")

    log_buffer.close()
