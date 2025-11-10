from __future__ import annotations

import pytest

from scripts.cj_experiments_runners.eng5_np.anchor_utils import extract_grade_from_filename


def test_extract_grade_from_simple_filename() -> None:
    assert extract_grade_from_filename("A1.docx") == "A"


def test_extract_grade_preserves_signs() -> None:
    assert extract_grade_from_filename("F+2.docx") == "F+"
    assert extract_grade_from_filename("c-.docx") == "C-"


def test_extract_grade_raises_when_missing() -> None:
    with pytest.raises(ValueError):
        extract_grade_from_filename("123.docx")
