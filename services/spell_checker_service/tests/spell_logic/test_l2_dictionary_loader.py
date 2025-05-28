"""
Tests for the l2_dictionary_loader module, focusing on the apply_specific_corrections function.

This test suite verifies that the apply_specific_corrections function correctly applies
only the specified corrections to text, handles edge cases, and preserves text outside
of correction boundaries.
"""

from typing import Any, Dict, List

from ...spell_logic.l2_dictionary_loader import apply_l2_corrections, apply_specific_corrections


class TestApplySpecificCorrections:
    """Test suite for the apply_specific_corrections function."""

    def test_apply_specific_corrections_basic(self) -> None:
        """Test applying specific corrections with simple text and non-overlapping corrections."""
        # Arrange
        text = "This is a test with some errros and misstakes."

        # Find actual positions of the words to correct
        errros_pos = text.find("errros")
        errros_end = errros_pos + len("errros") - 1
        misstakes_pos = text.find("misstakes")
        misstakes_end = misstakes_pos + len("misstakes") - 1

        corrections: List[Dict[str, Any]] = [
            {
                "original_word": "errros",
                "corrected_word": "errors",
                "rule": "test",
                "start": errros_pos,
                "end": errros_end,
            },
            {
                "original_word": "misstakes",
                "corrected_word": "mistakes",
                "rule": "test",
                "start": misstakes_pos,
                "end": misstakes_end,
            },
        ]
        expected = "This is a test with some errors and mistakes."

        # Act
        result = apply_specific_corrections(text, corrections)

        # Assert
        assert result == expected

    def test_apply_specific_corrections_empty_list(self) -> None:
        """Test with empty corrections list - should return original text unchanged."""
        # Arrange
        text = "This text stays unchanged."
        corrections: List[Dict[str, Any]] = []

        # Act
        result = apply_specific_corrections(text, corrections)

        # Assert
        assert result == text

    def test_apply_specific_corrections_sorted_order(self) -> None:
        """Test that corrections are applied in order regardless of input order."""
        # Arrange
        text = "First second third."
        corrections: List[Dict[str, Any]] = [
            {
                "original_word": "third",
                "corrected_word": "THREE",
                "rule": "test",
                "start": 13,
                "end": 17,
            },
            {
                "original_word": "First",
                "corrected_word": "ONE",
                "rule": "test",
                "start": 0,
                "end": 4,
            },
            {
                "original_word": "second",
                "corrected_word": "TWO",
                "rule": "test",
                "start": 6,
                "end": 11,
            },
        ]
        expected = "ONE TWO THREE."

        # Act
        result = apply_specific_corrections(text, corrections)

        # Assert
        assert result == expected

    def test_apply_specific_corrections_overlapping(self) -> None:
        """Test with overlapping corrections - later ones should be skipped."""
        # Arrange
        text = "This has overlapping corrections."

        # Find actual positions of the words
        has_pos = text.find("has")
        has_pos + len("has") - 1
        overlapping_pos = text.find("overlapping")
        overlapping_end = overlapping_pos + len("overlapping") - 1
        has_overlapping_pos = text.find("has overlapping")
        has_overlapping_end = has_overlapping_pos + len("has overlapping") - 1

        corrections: List[Dict[str, Any]] = [
            {
                "original_word": "overlapping",
                "corrected_word": "OVERLAPPED",
                "rule": "test",
                "start": overlapping_pos,
                "end": overlapping_end,
            },
            {
                # This would overlap with the previous correction (when sorted)
                # and should be skipped
                "original_word": "has overlapping",
                "corrected_word": "contained",
                "rule": "test",
                "start": has_overlapping_pos,
                "end": has_overlapping_end,
            },
        ]

        # Expected result - sorting will put has_overlapping (start:5) first,
        # then overlapping (start:9)
        # overlapping will be skipped due to overlap with already processed has_overlapping
        expected = "This contained corrections."

        # Act
        result = apply_specific_corrections(text, corrections)

        # Assert
        assert result == expected

    def test_apply_specific_corrections_out_of_bounds(self) -> None:
        """Test with corrections that have indices beyond text boundaries."""
        # Arrange
        text = "Short text."
        corrections: List[Dict[str, Any]] = [
            {
                "original_word": "text",
                "corrected_word": "TEXT",
                "rule": "test",
                "start": 6,
                "end": 9,
            },
            {
                # This would be beyond text boundaries and should be skipped
                "original_word": "nonexistent",
                "corrected_word": "INVALID",
                "rule": "test",
                "start": 15,
                "end": 25,
            },
        ]
        expected = "Short TEXT."

        # Act
        result = apply_specific_corrections(text, corrections)

        # Assert
        assert result == expected


class TestApplyL2Corrections:
    """Test suite for the apply_l2_corrections function."""

    def test_apply_l2_corrections_basic(self) -> None:
        """Test basic L2 correction application."""
        # Arrange
        text = "This is a test with some errror and anothr errror."
        l2_errors = {"errror": "error", "anothr": "another"}
        expected_text = "This is a test with some error and another error."
        # Calculate start positions carefully based on the original text
        pos_errror1 = text.find("errror")
        pos_anothr = text.find("anothr")
        # The second "errror" needs to be found after the first one
        pos_errror2 = text.find("errror", pos_errror1 + 1)

        # Adjust expected corrections if the function corrects all instances
        # or only the first. Assuming it corrects all tokens it finds.
        # The current apply_l2_corrections tokenizes and iterates, so all should be found.

        # Let's refine expected_corrections based on sequential token processing
        # original text: "This is a test with some errror and anothr errror."
        # corrected text:"This is a test with some error and another error."
        # indices of original words:
        # "errror" at 27
        # "anothr" at 38
        # "errror" at 49 (this index is in original string)

        # The function returns indices relative to the *original* string.
        expected_corrections = [
            {
                "original_word": "errror",
                "corrected_word": "error",
                "rule": "L2 dictionary",
                "start": pos_errror1,  # 27
                "end": pos_errror1 + len("errror") - 1,
            },
            {
                "original_word": "anothr",
                "corrected_word": "another",
                "rule": "L2 dictionary",
                "start": pos_anothr,  # 38
                "end": pos_anothr + len("anothr") - 1,
            },
            {
                "original_word": "errror",
                "corrected_word": "error",
                "rule": "L2 dictionary",
                "start": pos_errror2,  # 49
                "end": pos_errror2 + len("errror") - 1,
            },
        ]

        # Act
        corrected_text, applied_details = apply_l2_corrections(text, l2_errors)

        # Assert
        assert corrected_text == expected_text
        assert applied_details == expected_corrections

    def test_apply_l2_corrections_no_corrections_needed(self) -> None:
        """Test when no L2 corrections are applicable."""
        # Arrange
        text = "This text is perfectly fine."
        l2_errors = {"mispelled": "misspelled"}
        expected_text = "This text is perfectly fine."
        expected_corrections: List[Dict[str, Any]] = []

        # Act
        corrected_text, applied_details = apply_l2_corrections(text, l2_errors)

        # Assert
        assert corrected_text == expected_text
        assert applied_details == expected_corrections

    def test_apply_l2_corrections_empty_text(self) -> None:
        """Test with empty input text."""
        # Arrange
        text = ""
        l2_errors = {"errror": "error"}
        expected_text = ""
        expected_corrections: List[Dict[str, Any]] = []

        # Act
        corrected_text, applied_details = apply_l2_corrections(text, l2_errors)

        # Assert
        assert corrected_text == expected_text
        assert applied_details == expected_corrections

    def test_apply_l2_corrections_empty_l2_errors(self) -> None:
        """Test with an empty l2_errors dictionary."""
        # Arrange
        text = "Some text with potential errrors."
        l2_errors: Dict[str, str] = {}
        expected_text = "Some text with potential errrors."
        expected_corrections: List[Dict[str, Any]] = []

        # Act
        corrected_text, applied_details = apply_l2_corrections(text, l2_errors)

        # Assert
        assert corrected_text == expected_text
        assert applied_details == expected_corrections

    def test_apply_l2_corrections_case_preservation(self) -> None:
        """Test L2 correction with case preservation."""
        # Arrange
        # Define the misspelled word with three 'r's and its correct form
        misspelled_form_three_r = "errror"  # three 'r's
        correct_form_one_r = "error"  # one 'r'

        # Create different casings of the three-'r' misspelled word
        errror_upper_explicit = "ERRROR"  # 3 R's
        errror_capitalized_explicit = "Errror"  # E, then 3 r's
        errror_lower_explicit = "errror"  # 3 r's

        # Construct the input text using these three-'r' versions
        text = (
            f"This is AN {errror_upper_explicit}, "
            f"another {errror_capitalized_explicit}, "
            f"and one more {errror_lower_explicit}."
        )

        # The L2 errors dictionary should use the lowercase three-'r' misspelled form as the key
        l2_errors = {misspelled_form_three_r: correct_form_one_r}  # {"errror": "error"}

        # Define the expected corrected text. Corrected words should preserve
        # original capitalization.
        expected_corrected_upper = correct_form_one_r.upper()  # "ERROR"
        # For "Errrror" -> "Error", the first letter of the correction should be capitalized
        expected_corrected_capitalized = (
            correct_form_one_r[0].upper() + correct_form_one_r[1:]
        )  # "Error"
        expected_corrected_lower = correct_form_one_r  # "error"

        expected_text = (
            f"This is AN {expected_corrected_upper}, "
            f"another {expected_corrected_capitalized}, "
            f"and one more {expected_corrected_lower}."
        )

        # Define expected correction details
        pos1 = text.find(errror_upper_explicit)
        pos2 = text.find(errror_capitalized_explicit)
        pos3 = text.find(errror_lower_explicit)

        expected_corrections = [
            {
                "original_word": errror_upper_explicit,
                "corrected_word": expected_corrected_upper,
                "rule": "L2 dictionary",
                "start": pos1,
                "end": pos1 + len(errror_upper_explicit) - 1,
            },
            {
                "original_word": errror_capitalized_explicit,
                "corrected_word": expected_corrected_capitalized,
                "rule": "L2 dictionary",
                "start": pos2,
                "end": pos2 + len(errror_capitalized_explicit) - 1,
            },
            {
                "original_word": errror_lower_explicit,
                "corrected_word": expected_corrected_lower,
                "rule": "L2 dictionary",
                "start": pos3,
                "end": pos3 + len(errror_lower_explicit) - 1,
            },
        ]

        # Act
        corrected_text, applied_details = apply_l2_corrections(text, l2_errors)

        # Assert
        assert corrected_text == expected_text
        assert applied_details == expected_corrections

    def test_apply_l2_corrections_with_punctuation(self) -> None:
        """Test L2 corrections with surrounding punctuation."""
        # Arrange
        text = "Hello, wrld! This is a tst. (Another tst!)"
        l2_errors = {"wrld": "world", "tst": "test"}
        expected_text = "Hello, world! This is a test. (Another test!)"

        pos_wrld = text.find("wrld")
        pos_tst1 = text.find("tst")  # First occurrence
        pos_tst2 = text.rfind("tst")  # Second occurrence

        expected_corrections = [
            {
                "original_word": "wrld",
                "corrected_word": "world",
                "rule": "L2 dictionary",
                "start": pos_wrld,
                "end": pos_wrld + len("wrld") - 1,
            },
            {
                "original_word": "tst",
                "corrected_word": "test",
                "rule": "L2 dictionary",
                "start": pos_tst1,
                "end": pos_tst1 + len("tst") - 1,
            },
            {
                "original_word": "tst",
                "corrected_word": "test",
                "rule": "L2 dictionary",
                "start": pos_tst2,
                "end": pos_tst2 + len("tst") - 1,
            },
        ]

        # Act
        corrected_text, applied_details = apply_l2_corrections(text, l2_errors)

        # Assert
        assert corrected_text == expected_text
        assert applied_details == expected_corrections
