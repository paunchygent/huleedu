"""Grade utility functions for CJ Assessment Service."""

from __future__ import annotations


def _grade_to_normalized(grade: str | None) -> float:
    """Convert letter grade to normalized score (0.0-1.0).
    
    Args:
        grade: Letter grade (A, B, C, D, E, F, U) or None
        
    Returns:
        Normalized score between 0.0 and 1.0
    """
    grade_map = {
        "A": 1.0,
        "B": 0.8,
        "C": 0.6,
        "D": 0.4,
        "E": 0.2,
        "F": 0.0,
        "U": 0.0,  # Ungraded
    }
    return grade_map.get(grade, 0.0) if grade else 0.0