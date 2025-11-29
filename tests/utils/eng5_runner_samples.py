"""Helpers for loading ENG5 runner sample essays for functional tests."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

ENG5_RUNNER_STUDENT_DIR = Path("test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/student_essays")


def load_eng5_runner_student_files(max_files: int = 12) -> List[Path]:
    """
    Return up to `max_files` ENG5 runner student essays (docx) in deterministic order.

    Skips the calling test if the runner assets are not available locally.
    """
    if not ENG5_RUNNER_STUDENT_DIR.exists():
        pytest.skip("ENG5 runner student essays not found; add test_uploads assets to proceed.")

    essay_files = sorted(ENG5_RUNNER_STUDENT_DIR.glob("*.docx"))
    if not essay_files:
        pytest.skip("ENG5 runner student essays directory is empty.")

    return essay_files[:max_files]
