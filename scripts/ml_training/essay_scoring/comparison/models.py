"""Typed data contracts for CV comparison.

Defines the minimal metric payload schema we read from `cv_metrics.json`,
plus typed structures for:
- per-run derived diagnostics,
- paired-delta summaries,
- explicit gate checks and final comparison summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, TypedDict

from scripts.ml_training.essay_scoring.hyperparameter_sweep import SliceMetrics
from scripts.ml_training.essay_scoring.optuna_sweep import PromptSliceMetrics

FoldMetricName = Literal["qwk", "adjacent_accuracy", "mean_absolute_error"]
SplitSchemeName = Literal["stratified_text", "prompt_holdout"]


class FoldValMetricsPayload(TypedDict):
    """Validation metrics payload for a single fold."""

    qwk: float
    adjacent_accuracy: float
    mean_absolute_error: float


class FoldPayload(TypedDict):
    """Fold-level payload shape read from `cv_metrics.json`."""

    fold: int
    val: FoldValMetricsPayload


class SummaryPayload(TypedDict):
    """Summary-level payload shape read from `cv_metrics.json`."""

    val_qwk_mean: float


class CvMetricsPayload(TypedDict):
    """Minimal `cv_metrics.json` contract required for run comparisons."""

    scheme: str
    model_family: str
    summary: SummaryPayload
    folds: list[FoldPayload]


class ComparisonGateProfile(str, Enum):
    """Supported gate profiles for CV comparison decisions."""

    NONE = "none"
    PROMPT_HOLDOUT_PRIMARY = "prompt_holdout_primary"
    STRATIFIED_STABILITY = "stratified_stability"


@dataclass(frozen=True)
class PairwiseDeltaSummary:
    """Fold-paired delta summary with bootstrap confidence interval."""

    n_folds: int
    mean_delta: float
    std_delta: float
    bootstrap_ci_low: float
    bootstrap_ci_high: float
    deltas_by_fold: dict[str, float]


@dataclass(frozen=True)
class GateCheck:
    """One explicit gate threshold check result."""

    name: str
    passed: bool
    observed: float
    threshold: str


@dataclass(frozen=True)
class RunMetrics:
    """Derived diagnostics for one completed CV run directory."""

    run_dir: Path
    scheme: str
    model_family: str
    mean_qwk: float
    worst_prompt_qwk: float
    low_tail: SliceMetrics
    high_tail: SliceMetrics
    mid_band_adjacent_accuracy: float
    fold_val_qwk: dict[str, float]
    fold_val_adjacent_accuracy: dict[str, float]
    fold_val_mae: dict[str, float]
    bottom_prompts: list[PromptSliceMetrics]


@dataclass(frozen=True)
class CvRunComparisonSummary:
    """Paths and gate outcome for a completed CV comparison run."""

    run_dir: Path
    report_path: Path
    artifact_path: Path
    gate_passed: bool
