"""Admin blueprint modules for CJ Assessment Service."""

from __future__ import annotations

__all__ = [
    "anchors_bp",
    "instructions_bp",
    "student_prompts_bp",
    "judge_rubrics_bp",
]

from .anchors import anchors_bp  # noqa: E402  (re-export after definition)
from .instructions import instructions_bp  # noqa: E402  (re-export after definition)
from .judge_rubrics import judge_rubrics_bp  # noqa: E402
from .student_prompts import student_prompts_bp  # noqa: E402
