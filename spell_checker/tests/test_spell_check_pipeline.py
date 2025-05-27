import pytest
import os
from pathlib import Path

# Ensure imports are correct for the project structure
from src.cj_essay_assessment.spell_checker.spell_check_pipeline import run_spellcheck

@pytest.fixture
def temp_spellcheck_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary directories for essay input and spellcheck output."""
    input_dir = tmp_path / "input_essays"
    output_dir = tmp_path / "output_corrected"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return input_dir, output_dir

def test_simple_pyspellchecker_correction(temp_spellcheck_dirs: tuple[Path, Path]):
    """
    Tests basic pyspellchecker correction on an essay with simple misspellings.
    Verifies corrected output content and log entries.
    """
    input_dir, output_dir = temp_spellcheck_dirs

    essay_filename = "essay_simple_errors.txt"
    # Misspellings: Thiss -> This, documment -> document, twoo -> two, errrors -> errors
    original_content = "Thiss is a sample documment with twoo errrors."
    expected_corrected_content = "This is a sample document with two errors."

    essay_file_path = input_dir / essay_filename
    with open(essay_file_path, "w", encoding="utf-8") as f:
        f.write(original_content)

    # Run the spellcheck pipeline
    # This test relies on 'data/l2_dictionaries/l2_error_dictionary_MASTER.txt' being accessible
    # from the project root for L2 dictionary processing.
    results_summary = run_spellcheck(
        essays_dir=str(input_dir),
        output_dir=str(output_dir),
        language="en",
        log_level="DEBUG" 
    )

    # 1. Assertions on the processing summary
    assert results_summary.get("total_essays") == 1, "Should process one essay."
    assert results_summary.get("successful") == 1, "Processing should be successful."
    assert results_summary.get("failed") == 0, "No essays should fail."

    # 2. Assertions on the corrected file content
    corrected_essay_file_path = output_dir / f"{essay_filename}_corrected.txt"
    assert corrected_essay_file_path.exists(), "Corrected essay file should be created."

    with open(corrected_essay_file_path, "r", encoding="utf-8") as f:
        corrected_content = f.read()
    assert corrected_content == expected_corrected_content, "Corrected content does not match expected."

    # 3. Assertions on the correction log content
    correction_log_path = output_dir / f"{essay_filename}_corrections_log.txt"
    assert correction_log_path.exists(), "Correction log file should be created."

    with open(correction_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    # Verify main spell checker corrections are logged with correct details
    # Original text: "Thiss is a sample documment with twoo errrors."
    # Indices:        01234 5...           18-26          33-36   43-49
    assert "Section 4: Main Spell Checker Corrections" in log_content, "Log missing main checker section."
    assert "- 'Thiss' -> 'This' (indices 0-4)" in log_content, "Log missing 'Thiss' correction."
    assert "- 'documment' -> 'document' (indices 18-26)" in log_content, "Log missing 'documment' correction."
    assert "- 'twoo' -> 'two' (indices 33-36)" in log_content, "Log missing 'twoo' correction."
    assert "- 'errrors' -> 'errors' (indices 38-44)" in log_content, "Log missing 'errrors' correction."


def test_l2_correction_before_pyspellchecker(temp_spellcheck_dirs: tuple[Path, Path]):
    """
    Tests that L2 corrections are applied before pyspellchecker,
    and pyspellchecker operates on the L2-corrected text.
    """
    input_dir, output_dir = temp_spellcheck_dirs

    essay_filename = "essay_l2_then_pyspell.txt"
    # L2 error: "becouse" -> "because"
    # Pyspellchecker error: "hapened" -> "happened"
    original_content = "This hapened becouse of reasons."
    # Expected after L2: "This hapened because of reasons."
    # Expected final: "This happened because of reasons."
    expected_final_corrected_content = "This happened because of reasons."

    essay_file_path = input_dir / essay_filename
    with open(essay_file_path, "w", encoding="utf-8") as f:
        f.write(original_content)

    results_summary = run_spellcheck(
        essays_dir=str(input_dir),
        output_dir=str(output_dir),
        language="en",
        log_level="DEBUG"
    )

    # 1. Assertions on the processing summary
    assert results_summary.get("successful") == 1, "Processing should be successful."

    # 2. Assertions on the corrected file content
    corrected_essay_file_path = output_dir / f"{essay_filename}_corrected.txt"
    assert corrected_essay_file_path.exists(), "Corrected essay file should be created."
    with open(corrected_essay_file_path, "r", encoding="utf-8") as f:
        corrected_content = f.read()
    assert corrected_content == expected_final_corrected_content, "Final corrected content does not match."

    # 3. Assertions on the correction log content
    correction_log_path = output_dir / f"{essay_filename}_corrections_log.txt"
    assert correction_log_path.exists(), "Correction log file should be created."
    with open(correction_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    # Verify L2 corrections (Section 2)
    # Original: "This hapened becouse of reasons." (becouse: 12-18)
    assert "Section 2: Initial L2 Corrections Applied:" in log_content
    assert "  - 'becouse' -> 'because' at indices 13-19 (Rule: L2 dictionary)" in log_content

    # Verify text entering main spell checker (Section 3)
    assert "Section 3: Text Entering Main Spell Checker (Initial L2 Corrected Text):" in log_content
    assert "This hapened because of reasons." in log_content # Text after L2

    # Verify main spell checker corrections (Section 4)
    # L2 Corrected: "This hapened because of reasons." (hapened: 5-11)
    assert "Section 4: Main Spell Checker Corrections" in log_content
    assert "  - 'hapened' -> 'happened' (indices 5-11)" in log_content


def test_corrections_with_punctuation(temp_spellcheck_dirs: tuple[Path, Path]):
    """
    Tests corrections involving words adjacent to punctuation to ensure
    tokenization and reconstruction handle them correctly.
    """
    input_dir, output_dir = temp_spellcheck_dirs

    essay_filename = "essay_with_punctuation.txt"
    # L2: "teh" -> "the"
    # Pyspellchecker: "verry" -> "very", "agrede" -> "agree"
    original_content = "Look at teh cat, it's verry cute. She agrede."
    # Expected after L2: "Look at the cat, it's verry cute. She agrede."
    # Expected final: "Look at the cat, it's very cute. She agree."
    expected_final_corrected_content = "Look at the cat, it's very cute. She agree."

    essay_file_path = input_dir / essay_filename
    with open(essay_file_path, "w", encoding="utf-8") as f:
        f.write(original_content)

    results_summary = run_spellcheck(
        essays_dir=str(input_dir),
        output_dir=str(output_dir),
        language="en",
        log_level="DEBUG"
    )

    assert results_summary.get("successful") == 1, "Processing should be successful."

    corrected_essay_file_path = output_dir / f"{essay_filename}_corrected.txt"
    assert corrected_essay_file_path.exists(), "Corrected essay file should be created."
    with open(corrected_essay_file_path, "r", encoding="utf-8") as f:
        corrected_content = f.read()
    assert corrected_content == expected_final_corrected_content, "Final corrected content does not match."

    correction_log_path = output_dir / f"{essay_filename}_corrections_log.txt"
    assert correction_log_path.exists(), "Correction log file should be created."
    with open(correction_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    # Original: "Look at teh cat, it's verry cute. She agrede."
    # "teh": 8-10
    # "verry": 22-26
    # "agrede": 38-43
    assert "Section 2: Initial L2 Corrections Applied:" in log_content
    assert "  - 'teh' -> 'the' at indices 8-10 (Rule: L2 dictionary)" in log_content

    assert "Section 3: Text Entering Main Spell Checker (Initial L2 Corrected Text):" in log_content
    assert "Look at the cat, it's very cute. She agrede." in log_content

    assert "Section 4: Main Spell Checker Corrections" in log_content
    # L2 Corrected: "Look at the cat, it's very cute. She agrede."
    # "agrede": 37-42 (since "verry" was corrected by L2, changing prior indices)
    assert "  - 'verry' -> 'very'" not in log_content.split("Section 4: Main Spell Checker Corrections")[1], "'verry' should have been corrected by L2, not main checker"
    assert "  - 'agrede' -> 'agree' (indices 37-42)" in log_content

