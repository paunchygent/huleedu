"""Helpers for anchor essay processing."""

from __future__ import annotations

import re
from pathlib import Path

GRADE_SUFFIX_RE = re.compile(r"[0-9]+$")


def extract_grade_from_filename(filename: str) -> str:
    """Infer the ENG5 grade from an anchor filename."""

    stem = Path(filename).stem
    grade = GRADE_SUFFIX_RE.sub("", stem).strip()
    if not grade:
        raise ValueError(f"Unable to determine grade from anchor filename: {filename}")
    return grade.upper()
