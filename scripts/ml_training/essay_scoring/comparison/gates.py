"""Gate-threshold evaluation for CV comparisons.

Encodes the strict decision contracts for:
- `prompt_holdout_primary` (worst-prompt, mean QWK, tail guardrails)
- `stratified_stability` (mean-QWK stability bound)
"""

from __future__ import annotations

from scripts.ml_training.essay_scoring.comparison.models import (
    ComparisonGateProfile,
    GateCheck,
)


def evaluate_gate_checks(
    *,
    gate_profile: ComparisonGateProfile,
    deltas: dict[str, float],
    worst_prompt_min_delta: float,
    mean_qwk_max_regression: float,
    tail_adjacent_max_regression: float,
    stability_mean_qwk_max_regression: float,
) -> list[GateCheck]:
    """Evaluate threshold checks for a selected gate profile."""

    if gate_profile == ComparisonGateProfile.NONE:
        return []
    if gate_profile == ComparisonGateProfile.PROMPT_HOLDOUT_PRIMARY:
        return [
            GateCheck(
                name="worst_prompt_qwk_delta",
                passed=bool(deltas["worst_prompt_qwk"] >= worst_prompt_min_delta),
                observed=float(deltas["worst_prompt_qwk"]),
                threshold=f">= {worst_prompt_min_delta:.6f}",
            ),
            GateCheck(
                name="mean_qwk_delta",
                passed=bool(deltas["mean_qwk"] >= -mean_qwk_max_regression),
                observed=float(deltas["mean_qwk"]),
                threshold=f">= -{mean_qwk_max_regression:.6f}",
            ),
            GateCheck(
                name="low_tail_adjacent_accuracy_delta",
                passed=bool(deltas["low_tail_adjacent_accuracy"] >= -tail_adjacent_max_regression),
                observed=float(deltas["low_tail_adjacent_accuracy"]),
                threshold=f">= -{tail_adjacent_max_regression:.6f}",
            ),
            GateCheck(
                name="high_tail_adjacent_accuracy_delta",
                passed=bool(deltas["high_tail_adjacent_accuracy"] >= -tail_adjacent_max_regression),
                observed=float(deltas["high_tail_adjacent_accuracy"]),
                threshold=f">= -{tail_adjacent_max_regression:.6f}",
            ),
        ]
    if gate_profile == ComparisonGateProfile.STRATIFIED_STABILITY:
        return [
            GateCheck(
                name="mean_qwk_delta",
                passed=bool(deltas["mean_qwk"] >= -stability_mean_qwk_max_regression),
                observed=float(deltas["mean_qwk"]),
                threshold=f">= -{stability_mean_qwk_max_regression:.6f}",
            )
        ]
    raise ValueError(f"Unsupported gate profile: {gate_profile}")


def validate_gate_scheme_compatibility(
    *,
    gate_profile: ComparisonGateProfile,
    reference_scheme: str,
    candidate_scheme: str,
) -> None:
    """Validate that run schemes are compatible with the selected gate profile."""

    if reference_scheme != candidate_scheme:
        raise ValueError(
            "Reference and candidate runs must use the same split scheme. "
            f"reference={reference_scheme}, candidate={candidate_scheme}"
        )

    if (
        gate_profile == ComparisonGateProfile.PROMPT_HOLDOUT_PRIMARY
        and reference_scheme != "prompt_holdout"
    ):
        raise ValueError("prompt_holdout_primary gate requires runs with scheme=prompt_holdout.")
    if (
        gate_profile == ComparisonGateProfile.STRATIFIED_STABILITY
        and reference_scheme != "stratified_text"
    ):
        raise ValueError("stratified_stability gate requires runs with scheme=stratified_text.")
