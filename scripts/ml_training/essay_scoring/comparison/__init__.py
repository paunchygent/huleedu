"""Comparison toolkit for Gate G1 CV decisions.

Exports the small set of types and functions needed to:
- load CV run evidence,
- compute fold-paired deltas with bootstrap confidence intervals,
- evaluate strict pass/fail gate checks.
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
