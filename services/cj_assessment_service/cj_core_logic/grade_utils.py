"""Grade utility functions for CJ Assessment Service."""

from __future__ import annotations


def _grade_to_normalized(grade: str | None) -> float:
    """Convert fine-grained letter grade to normalized score (0.0-1.0).

    Args:
        grade: Fine-grained letter grade (A, A-, B+, B, B-, etc.) or None

    Returns:
        Normalized score between 0.0 and 1.0
    """
    # Fine-grained 15-point grade scale mapping
    grade_map = {
        "A": 1.00,
        "A-": 0.93,
        "B+": 0.87,
        "B": 0.80,
        "B-": 0.73,
        "C+": 0.67,
        "C": 0.60,
        "C-": 0.53,
        "D+": 0.47,
        "D": 0.40,
        "D-": 0.33,
        "E+": 0.27,
        "E": 0.20,
        "E-": 0.13,
        "F+": 0.07,
        "F": 0.00,
        "U": 0.00,  # Ungraded
    }
    return grade_map.get(grade, 0.0) if grade else 0.0
