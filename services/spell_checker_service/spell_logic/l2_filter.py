"""
L2 Correction Filter Module

This module provides functionality to filter and validate L2 error-correction
pairs using simple, high-precision heuristic rules to remove unwanted
corrections such as pluralization or very short words.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Union

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from logging import Logger

MODULE_LOGGER = create_service_logger(__name__)


class L2CorrectionFilter:
    """Filter L2 corrections using simple heuristic rules."""

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the filter with an optional logger dependency."""
        self.logger = logger or MODULE_LOGGER

    def is_pluralization_change(self, error: str, correction: str) -> bool:
        """Check if the correction only adds/removes -s/-es for pluralization.

        Args:
            error: The original error text
            correction: The suggested correction

        Returns:
            bool: True if the change is only a pluralization change, False otherwise
        """
        if len(error) <= 2 or len(correction) <= 2:
            return False

        # (err_suff, corr_suff) means: if error matches stem + err_suff,
        # then correction should match stem + corr_suff.
        plural_transformations = [
            # Plural to Singular
            ("s", ""),  # cats -> cat
            ("es", ""),  # boxes -> box
            ("ies", "y"),  # cities -> city
            # Singular to Plural
            ("", "s"),  # cat -> cats  (error is stem)
            ("", "es"),  # box -> boxes (error is stem)
            (
                "y",
                "ies",
            ),  # city -> cities (error ends with y, which is replaced, stem is error[:-1])
        ]

        for err_suff, corr_suff in plural_transformations:
            if error.endswith(err_suff):
                # Determine stem: if err_suff is empty, error is the stem.
                # Otherwise, stem is error without err_suff.
                stem = error[: -len(err_suff)] if len(err_suff) > 0 else error

                if correction == stem + corr_suff:
                    self.logger.debug(
                        f"Pluralization change: '{error}' <-> '{correction}' "
                        f"via rule ('{err_suff}' -> '{corr_suff}')"
                    )
                    return True
        return False

    def is_valid_correction(self, error: str, correction: str) -> bool:
        """Check if a correction is valid based on linguistic rules.

        Args:
            error: The error word
            correction: The suggested correction

        Returns:
            bool: True if the correction is valid, False otherwise
        """
        self.logger.debug(f"Validating correction: '{error}' -> '{correction}'")

        if len(error) <= 2 or len(correction) <= 2:
            self.logger.debug("Skipping short word (length <= 2)")
            return False

        if self.is_pluralization_change(error, correction):
            return False

        return True


def filter_l2_entries(l2_errors: Dict[str, str], logger: Optional[Logger] = None) -> Dict[str, str]:
    """Filter a dictionary of L2 errors to remove unwanted corrections.

    Args:
        l2_errors: Dictionary mapping errors to corrections.
        logger: Optional logger instance.

    Returns:
        Dict[str, str]: Filtered dictionary of corrections. Returns an empty
        dictionary on error.
    """
    log = logger or MODULE_LOGGER

    if not isinstance(l2_errors, dict):
        log.warning("Invalid input: expected a dictionary")
        return {}

    if not l2_errors:
        return {}

    try:
        correction_filter = L2CorrectionFilter(logger=log)
        filtered: Dict[str, str] = {}
        invalid_count = 0
        processed_count = 0

        for wrong, correct in l2_errors.items():
            processed_count += 1
            if not isinstance(wrong, str) or not isinstance(correct, str):
                log.info(f"Skipping non-string entry: {wrong} -> {correct}")
                invalid_count += 1
                continue

            try:
                if correction_filter.is_valid_correction(wrong, correct):
                    filtered[wrong] = correct
                else:
                    invalid_count += 1
            except Exception as e:  # pylint: disable=broad-except
                log.warning(f"Error validating correction '{wrong}' -> '{correct}': {e}")
                log.debug("Validation error details:", exc_info=True)
                invalid_count += 1

        if invalid_count > 0:
            log.info(
                f"Filtered out {invalid_count} invalid corrections "
                f"({len(filtered)} remaining out of {processed_count} processed)"
            )

        return filtered

    except Exception as e:  # pylint: disable=broad-except
        log.error(f"Critical error in filter_l2_entries: {e}")
        log.debug("Error details:", exc_info=True)
        return {}


def create_filtered_l2_dictionary(
    l2_errors: Dict[str, str], output_path: Union[str, Path], logger: Optional[Logger] = None
) -> bool:
    """Create a filtered L2 dictionary file with valid corrections.

    Args:
        l2_errors: Dictionary mapping incorrect words to their corrections.
        output_path: Path where the filtered dictionary will be saved.
        logger: Optional logger instance.

    Returns:
        bool: True if the dictionary was created successfully, False otherwise.

    Raises:
        ValueError: If l2_errors is empty or invalid.
        OSError: If there are file system errors.
    """
    log = logger or MODULE_LOGGER
    if not l2_errors:
        log.warning("No corrections provided to create_filtered_l2_dictionary")
        return False

    try:
        output_path = Path(output_path)
        log.debug(f"Creating filtered dictionary at: {output_path}")

        # Ensure output directory exists
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error(f"Failed to create directory {output_path.parent}: {e}")
            return False

        # Filter the entries using our validation logic
        filtered_errors = filter_l2_entries(l2_errors, logger=log)

        if not filtered_errors:
            log.warning("No valid corrections after filtering")
            return False

        # Sort entries alphabetically for consistency
        sorted_entries = sorted(filtered_errors.items(), key=lambda x: x[0].lower())

        # Write to file with error handling for file operations
        try:
            with output_path.open("w", encoding="utf-8") as f:
                for wrong, correct in sorted_entries:
                    f.write(f"{wrong}:{correct}\n")
        except (IOError, OSError) as e:
            log.error(f"Failed to write to {output_path}: {e}")
            return False

        log.info(
            f"Successfully created filtered L2 dictionary with {len(filtered_errors)} "
            f"entries (of {len(l2_errors)} original entries) at {output_path}"
        )
        return True

    except (ValueError, OSError) as e:
        log.error(f"Failed to create filtered dictionary: {e}")
        log.debug("Error details:", exc_info=True)
        return False
    except Exception as e:  # pylint: disable=broad-except
        log.error(f"Unexpected error creating filtered dictionary: {e}")
        log.debug("Error details:", exc_info=True)
        return False
