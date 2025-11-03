"""Tests covering modular improvements for the consensus model."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.bayesian_consensus_model.bayesian_consensus_model import ConsensusModel, KernelConfig


def _build_dataframe(rows: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_argmax_decision_prefers_highest_probability() -> None:
    rows = [
        {"essay_id": "E1", "rater_id": "R1", "grade": "C+"},
        {"essay_id": "E1", "rater_id": "R2", "grade": "C+"},
        {"essay_id": "E1", "rater_id": "R3", "grade": "D+"},
    ]
    df = _build_dataframe(rows)

    round_config = KernelConfig(sigma=0.5, pseudo_count=0.0, bias_correction=False)
    round_model = ConsensusModel(round_config)
    round_model.fit(df)
    round_grade = round_model.get_consensus()["E1"].consensus_grade

    argmax_config = KernelConfig(
        sigma=0.5,
        pseudo_count=0.0,
        bias_correction=False,
        use_argmax_decision=True,
    )
    argmax_model = ConsensusModel(argmax_config)
    argmax_model.fit(df)
    argmax_result = argmax_model.get_consensus()["E1"]

    assert round_grade == "C-"
    assert argmax_result.consensus_grade == "C+"
    assert argmax_result.confidence == pytest.approx(argmax_result.grade_probabilities["C+"])


def test_leave_one_out_alignment_increases_bias_penalty() -> None:
    rows = []
    for essay_idx in range(1, 4):
        essay_id = f"E{essay_idx}"
        rows.extend(
            [
                {"essay_id": essay_id, "rater_id": "R_stable1", "grade": "C-"},
                {"essay_id": essay_id, "rater_id": "R_stable2", "grade": "C-"},
                {"essay_id": essay_id, "rater_id": "R_stable3", "grade": "C-"},
                {"essay_id": essay_id, "rater_id": "R_stable4", "grade": "C-"},
                {"essay_id": essay_id, "rater_id": "R_bias", "grade": "B"},
            ]
        )
    df = _build_dataframe(rows)

    baseline_model = ConsensusModel(KernelConfig())
    baseline_model.fit(df)
    loo_model = ConsensusModel(KernelConfig(use_loo_alignment=True))
    loo_model.fit(df)

    baseline_bias = baseline_model.rater_bias_posteriors.set_index("rater_id")
    loo_bias = loo_model.rater_bias_posteriors.set_index("rater_id")

    assert loo_bias.loc["R_bias", "mu_post"] > baseline_bias.loc["R_bias", "mu_post"]
    for stable_id in ("R_stable1", "R_stable2", "R_stable3", "R_stable4"):
        assert abs(loo_bias.loc[stable_id, "mu_post"]) > abs(
            baseline_bias.loc[stable_id, "mu_post"]
        )


def test_precision_weighting_downscales_high_variance_raters() -> None:
    rows = []
    assignments = [
        ("E1", {"R_cons": "C+", "R_anchor": "C+", "R_noisy": "A"}),
        ("E2", {"R_cons": "C-", "R_anchor": "C-", "R_noisy": "F+"}),
        ("E3", {"R_cons": "C+", "R_anchor": "C+", "R_noisy": "B"}),
        ("E4", {"R_cons": "C-", "R_anchor": "C-"}),
        ("E5", {"R_cons": "C+", "R_anchor": "C+"}),
        ("E6", {"R_cons": "C-", "R_anchor": "C-"}),
    ]
    for essay_id, grade_map in assignments:
        for rater_id, grade in grade_map.items():
            rows.append({"essay_id": essay_id, "rater_id": rater_id, "grade": grade})
    df = _build_dataframe(rows)

    baseline_model = ConsensusModel(KernelConfig(bias_correction=True))
    baseline_model.fit(df)
    precision_model = ConsensusModel(KernelConfig(bias_correction=True, use_precision_weights=True))
    precision_model.fit(df)

    base_metrics = baseline_model.rater_metrics.set_index("rater_id")
    precision_metrics = precision_model.rater_metrics.set_index("rater_id")

    assert precision_metrics.loc["R_noisy", "precision_factor"] < 1.0
    assert (
        precision_metrics.loc["R_noisy", "precision_factor"]
        < precision_metrics.loc["R_cons", "precision_factor"]
    )
    assert precision_metrics.loc["R_noisy", "weight"] < base_metrics.loc["R_noisy", "weight"]
    assert precision_metrics.loc["R_anchor", "weight"] == pytest.approx(
        base_metrics.loc["R_anchor", "weight"]
    )


def test_neutral_metrics_reports_neutral_ess() -> None:
    rows: list[dict[str, str]] = []
    assignments = [
        ("E1", {"R_neutral1": "C-", "R_neutral2": "C-", "R_neutral3": "C-", "R_biased": "B"}),
        ("E2", {"R_neutral1": "C-", "R_neutral2": "C-", "R_neutral3": "C-", "R_biased": "B"}),
    ]
    for essay_id, grade_map in assignments:
        for rater_id, grade in grade_map.items():
            rows.append({"essay_id": essay_id, "rater_id": rater_id, "grade": grade})
    df = _build_dataframe(rows)

    gating_config = KernelConfig(
        use_neutral_gating=True,
        neutral_delta_mu=0.3,
        neutral_var_max=1.0,
    )
    model = ConsensusModel(gating_config)
    model.fit(df)
    result = model.get_consensus()["E1"]

    assert result.neutral_ess == pytest.approx(3.0)
    assert result.needs_more_ratings is False

    baseline_config = KernelConfig(use_neutral_gating=False)
    baseline_model = ConsensusModel(baseline_config)
    baseline_model.fit(df)
    baseline_result = baseline_model.get_consensus()["E1"]
    assert baseline_result.neutral_ess == 0.0
    assert baseline_result.needs_more_ratings is False
