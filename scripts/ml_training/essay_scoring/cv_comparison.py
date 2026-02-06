"""Public import surface for CV run comparison.

This module exposes a stable API for comparing two completed CV runs and
evaluating gate thresholds. It returns typed results with:
- machine-readable comparison artifacts (`cv_comparison.json`)
- human-readable gate reports (`cv_comparison.md`)
"""

from scripts.ml_training.essay_scoring.comparison.models import (
    ComparisonGateProfile,
    CvRunComparisonSummary,
    GateCheck,
    PairwiseDeltaSummary,
    RunMetrics,
)
from scripts.ml_training.essay_scoring.comparison.runner import compare_cv_runs

__all__ = [
    "ComparisonGateProfile",
    "CvRunComparisonSummary",
    "GateCheck",
    "PairwiseDeltaSummary",
    "RunMetrics",
    "compare_cv_runs",
]
