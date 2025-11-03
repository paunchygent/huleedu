"""
Grade scale registry for CJ Assessment Service.

Provides centralized definitions for multiple grade scales used across
different assessment contexts (Swedish national exams, ENG5 NP variants, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GradeScaleMetadata:
    """
    Metadata for a specific grade scale.

    Attributes:
        scale_id: Unique identifier for the scale (e.g., "swedish_8_anchor")
        display_name: Human-readable name for UI display
        grades: Ordered list of valid grades from lowest to highest
        population_priors: Optional historical grade distribution {grade: probability}
        description: Purpose and context of this scale
        allows_below_lowest: Whether essays can score below the lowest anchor grade
        below_lowest_grade: Grade assigned when below the lowest anchor (e.g., "F", "0")
    """

    scale_id: str
    display_name: str
    grades: list[str]
    population_priors: dict[str, float] | None
    description: str
    allows_below_lowest: bool
    below_lowest_grade: str | None

    def __post_init__(self) -> None:
        """Validate scale metadata."""
        if not self.scale_id:
            msg = "scale_id cannot be empty"
            raise ValueError(msg)
        if not self.grades:
            msg = "grades list cannot be empty"
            raise ValueError(msg)
        if len(self.grades) != len(set(self.grades)):
            msg = f"grades must be unique: {self.grades}"
            raise ValueError(msg)

        # Validate population priors sum to 1.0 if provided
        if self.population_priors is not None:
            if not self.population_priors:
                msg = "population_priors cannot be empty dict; use None instead"
                raise ValueError(msg)

            total = sum(self.population_priors.values())
            if not (0.99 <= total <= 1.01):  # Allow floating point tolerance
                msg = f"population_priors must sum to 1.0, got {total}"
                raise ValueError(msg)

            # Validate all priors reference valid grades
            invalid_grades = set(self.population_priors.keys()) - set(self.grades)
            if invalid_grades:
                msg = f"population_priors reference unknown grades: {invalid_grades}"
                raise ValueError(msg)

        # Validate below-lowest configuration
        if self.allows_below_lowest and not self.below_lowest_grade:
            msg = "below_lowest_grade must be specified when allows_below_lowest=True"
            raise ValueError(msg)
        if not self.allows_below_lowest and self.below_lowest_grade:
            msg = "below_lowest_grade must be None when allows_below_lowest=False"
            raise ValueError(msg)


# Swedish 8-anchor grade system (historical default)
_SWEDISH_8_ANCHOR = GradeScaleMetadata(
    scale_id="swedish_8_anchor",
    display_name="Swedish National Exam (8-anchor)",
    grades=["F", "E", "D", "D+", "C", "C+", "B", "A"],
    population_priors={
        "F": 0.02,
        "E": 0.08,
        "D": 0.15,
        "D+": 0.20,
        "C": 0.25,
        "C+": 0.15,
        "B": 0.10,
        "A": 0.05,
    },
    description=(
        "Psychometrically robust 8-anchor Swedish national exam grade system. "
        "Uses population priors from historical data. Supports derived minus/plus "
        "grades (E-, B+, etc.) based on quartile positioning within grade bands."
    ),
    allows_below_lowest=False,
    below_lowest_grade=None,
)

# ENG5 NP Legacy 9-step scale (F+ through A)
_ENG5_NP_LEGACY_9_STEP = GradeScaleMetadata(
    scale_id="eng5_np_legacy_9_step",
    display_name="ENG5 NP Legacy (9-step)",
    grades=["F+", "E-", "E+", "D-", "D+", "C-", "C+", "B", "A"],
    population_priors={
        # Uniform priors (1/9 each)
        "F+": 1.0 / 9.0,
        "E-": 1.0 / 9.0,
        "E+": 1.0 / 9.0,
        "D-": 1.0 / 9.0,
        "D+": 1.0 / 9.0,
        "C-": 1.0 / 9.0,
        "C+": 1.0 / 9.0,
        "B": 1.0 / 9.0,
        "A": 1.0 / 9.0,
    },
    description=(
        "ENG5 NP Legacy 9-step scale using letter grades with modifiers. "
        "Anchor IDs like 'F+1', 'F+2' map to grade code 'F+'. "
        "Essays scoring below F+ anchor are assigned grade 'F'. "
        "Uses uniform population priors (1/9 per grade)."
    ),
    allows_below_lowest=True,
    below_lowest_grade="F",
)

# ENG5 NP National 9-step scale (1 through 9)
_ENG5_NP_NATIONAL_9_STEP = GradeScaleMetadata(
    scale_id="eng5_np_national_9_step",
    display_name="ENG5 NP National (9-step)",
    grades=["1", "2", "3", "4", "5", "6", "7", "8", "9"],
    population_priors={
        # Uniform priors (1/9 each)
        "1": 1.0 / 9.0,
        "2": 1.0 / 9.0,
        "3": 1.0 / 9.0,
        "4": 1.0 / 9.0,
        "5": 1.0 / 9.0,
        "6": 1.0 / 9.0,
        "7": 1.0 / 9.0,
        "8": 1.0 / 9.0,
        "9": 1.0 / 9.0,
    },
    description=(
        "ENG5 NP National 9-step numerical scale (1=lowest, 9=highest). "
        "Essays scoring below anchor '1' are assigned grade '0'. "
        "Uses uniform population priors (1/9 per grade). "
        "Functionally similar to legacy scale but uses numerical grades."
    ),
    allows_below_lowest=True,
    below_lowest_grade="0",
)

# Registry mapping scale_id to metadata
GRADE_SCALES: dict[str, GradeScaleMetadata] = {
    _SWEDISH_8_ANCHOR.scale_id: _SWEDISH_8_ANCHOR,
    _ENG5_NP_LEGACY_9_STEP.scale_id: _ENG5_NP_LEGACY_9_STEP,
    _ENG5_NP_NATIONAL_9_STEP.scale_id: _ENG5_NP_NATIONAL_9_STEP,
}


def get_scale(scale_id: str) -> GradeScaleMetadata:
    """
    Retrieve grade scale metadata by ID.

    Args:
        scale_id: Unique scale identifier

    Returns:
        GradeScaleMetadata for the requested scale

    Raises:
        ValueError: If scale_id is not registered
    """
    if scale_id not in GRADE_SCALES:
        available = ", ".join(sorted(GRADE_SCALES.keys()))
        msg = f"Unknown grade scale '{scale_id}'. Available scales: {available}"
        raise ValueError(msg)
    return GRADE_SCALES[scale_id]


def validate_grade_for_scale(grade: str, scale_id: str) -> bool:
    """
    Check if a grade is valid for a specific scale.

    Args:
        grade: Grade code to validate (e.g., "A", "E+", "5")
        scale_id: Scale identifier

    Returns:
        True if grade is valid for the scale, False otherwise

    Raises:
        ValueError: If scale_id is not registered
    """
    scale = get_scale(scale_id)

    # Check if grade is in the scale's grade list
    if grade in scale.grades:
        return True

    # Check if it's the below-lowest grade
    if scale.allows_below_lowest and grade == scale.below_lowest_grade:
        return True

    return False


def list_available_scales() -> list[str]:
    """
    Get list of all registered grade scale IDs.

    Returns:
        Sorted list of scale identifiers
    """
    return sorted(GRADE_SCALES.keys())


def get_grade_index(grade: str, scale_id: str) -> int:
    """
    Get the ordinal position of a grade within its scale.

    Args:
        grade: Grade code
        scale_id: Scale identifier

    Returns:
        Zero-based index (0=lowest grade), or -1 for below-lowest grades

    Raises:
        ValueError: If grade is invalid for the scale or scale_id unknown
    """
    scale = get_scale(scale_id)

    # Handle below-lowest grade
    if scale.allows_below_lowest and grade == scale.below_lowest_grade:
        return -1

    if grade not in scale.grades:
        msg = f"Grade '{grade}' is not valid for scale '{scale_id}'"
        raise ValueError(msg)

    return scale.grades.index(grade)


def get_uniform_priors(scale_id: str) -> dict[str, float]:
    """
    Generate uniform priors for a grade scale.

    Args:
        scale_id: Scale identifier

    Returns:
        Dictionary mapping each grade to equal probability

    Raises:
        ValueError: If scale_id is not registered
    """
    scale = get_scale(scale_id)
    n_grades = len(scale.grades)
    return {grade: 1.0 / n_grades for grade in scale.grades}
