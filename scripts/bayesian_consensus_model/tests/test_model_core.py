"""Tests for the kernel-based ordinal consensus model."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.bayesian_consensus_model.bayesian_consensus_model import (
    GRADES,
    ConsensusModel,
    ConsensusResult,
    KernelConfig,
)
from scripts.bayesian_consensus_model.models import (
    compute_rater_bias_posteriors_eb,
    compute_rater_weights,
)

GRADE_TO_INDEX = {grade: idx for idx, grade in enumerate(GRADES)}


@pytest.fixture
def sample_ratings() -> pd.DataFrame:
    data = [
        {"essay_id": "E1", "rater_id": "R1", "grade": "C+"},
        {"essay_id": "E1", "rater_id": "R2", "grade": "C+"},
        {"essay_id": "E1", "rater_id": "R3", "grade": "B"},
        {"essay_id": "E2", "rater_id": "R1", "grade": "D+"},
        {"essay_id": "E2", "rater_id": "R2", "grade": "C-"},
        {"essay_id": "E2", "rater_id": "R3", "grade": "C-"},
        {"essay_id": "E3", "rater_id": "R1", "grade": "F+"},
        {"essay_id": "E3", "rater_id": "R2", "grade": "E-"},
        {"essay_id": "E3", "rater_id": "R3", "grade": "C-"},
    ]
    return pd.DataFrame(data)


def test_prepare_data_validation(sample_ratings: pd.DataFrame) -> None:
    model = ConsensusModel()
    cleaned = model.prepare_data(sample_ratings)
    assert len(cleaned) == len(sample_ratings)
    assert cleaned["grade"].isin(GRADES).all()


def test_prepare_data_requires_fields() -> None:
    model = ConsensusModel()
    with pytest.raises(ValueError):
        model.prepare_data(pd.DataFrame({"essay_id": ["E1"], "grade": ["A"]}))


def test_fit_requires_valid_grades() -> None:
    model = ConsensusModel()
    with pytest.raises(ValueError):
        model.fit(pd.DataFrame(columns=["essay_id", "rater_id", "grade"]))


def test_fit_and_consensus(sample_ratings: pd.DataFrame) -> None:
    model = ConsensusModel(KernelConfig(sigma=0.8, pseudo_count=0.01))
    model.fit(sample_ratings)
    results = model.get_consensus()

    assert set(results) == {"E1", "E2", "E3"}
    result = results["E1"]
    assert isinstance(result, ConsensusResult)
    assert result.sample_size == 3
    assert pytest.approx(sum(result.grade_probabilities.values())) == 1.0
    assert result.consensus_grade in {"C+", "B"}
    assert 0 <= result.expected_grade_index <= 9

    e3 = results["E3"]
    assert e3.grade_probabilities["F+"] > 0.05
    assert e3.grade_probabilities["C-"] < 0.6


def test_consensus_requires_fit(sample_ratings: pd.DataFrame) -> None:
    model = ConsensusModel()
    with pytest.raises(ValueError):
        model.get_consensus()


def test_thresholds_and_abilities_after_fit(sample_ratings: pd.DataFrame) -> None:
    model = ConsensusModel()
    model.fit(sample_ratings)
    results = model.get_consensus()
    assert all(isinstance(res.expected_grade_index, float) for res in results.values())


def test_empirical_bayes_neutrality_returns_zero_bias() -> None:
    neutral_rows = []
    for idx, grade in enumerate(["C+", "D+", "B"], start=1):
        essay_id = f"N{idx}"
        for rater in ("R1", "R2", "R3"):
            neutral_rows.append({"essay_id": essay_id, "rater_id": rater, "grade": grade})
    neutral_df = pd.DataFrame(neutral_rows)

    posteriors = compute_rater_bias_posteriors_eb(neutral_df, GRADE_TO_INDEX)
    assert not posteriors.empty
    assert (posteriors["mu_post"].abs() < 1e-6).all()


def test_empirical_bayes_sparse_shrinkage_moves_toward_zero() -> None:
    rows = []
    base_indices = [6, 7, 5, 6]
    for idx, base_idx in enumerate(base_indices, start=1):
        essay_id = f"S{idx}"
        base_grade = GRADES[base_idx]
        for rater in ("R_dense", "R_anchor"):
            rows.append({"essay_id": essay_id, "rater_id": rater, "grade": base_grade})
    for idx, base_idx in enumerate(base_indices[:2], start=1):
        essay_id = f"S{idx}"
        shifted_index = min(base_idx + 2, len(GRADES) - 1)
        rows.append({"essay_id": essay_id, "rater_id": "R_sparse", "grade": GRADES[shifted_index]})
    df = pd.DataFrame(rows)

    posteriors = compute_rater_bias_posteriors_eb(df, GRADE_TO_INDEX)
    sparse_row = posteriors.loc[posteriors["rater_id"] == "R_sparse"].iloc[0]

    assert sparse_row["n_rated"] == 2
    assert 0 < sparse_row["shrinkage"] < 1
    assert abs(sparse_row["mu_post"]) < abs(sparse_row["b_data"])


def test_consensus_bias_correction_with_empirical_bayes() -> None:
    rows = []
    base_indices = [6, 7, 5, 6, 7]
    base_by_essay: dict[str, float] = {}
    for idx, base_idx in enumerate(base_indices, start=1):
        essay_id = f"B{idx}"
        base_by_essay[essay_id] = float(base_idx)
        base_grade = GRADES[base_idx]
        for rater in ("R1", "R2"):
            rows.append({"essay_id": essay_id, "rater_id": rater, "grade": base_grade})
        shifted_index = min(base_idx + 1, len(GRADES) - 1)
        rows.append({"essay_id": essay_id, "rater_id": "R_bias", "grade": GRADES[shifted_index]})
    df = pd.DataFrame(rows)

    model = ConsensusModel()
    model.fit(df)
    results = model.get_consensus()
    bias_df = model.rater_bias_posteriors
    assert not bias_df.empty
    assert bias_df["applied"].all()
    biased_mu = bias_df.loc[bias_df["rater_id"] == "R_bias", "mu_post"].iloc[0]
    assert biased_mu > 0.5

    enriched = df.assign(grade_index=df["grade"].map(GRADE_TO_INDEX))
    for essay_id, group in enriched.groupby("essay_id"):
        expected_idx = results[essay_id].expected_grade_index
        naive_mean = float(group["grade_index"].mean())
        base_idx = base_by_essay[essay_id]
        assert abs(expected_idx - base_idx) < abs(naive_mean - base_idx)


def test_bias_correction_toggle_restores_naive_expectation() -> None:
    rows = []
    base_indices = [6, 7, 5, 6, 7]
    for idx, base_idx in enumerate(base_indices, start=1):
        essay_id = f"B{idx}"
        base_grade = GRADES[base_idx]
        for rater in ("R1", "R2"):
            rows.append({"essay_id": essay_id, "rater_id": rater, "grade": base_grade})
        shifted_index = min(base_idx + 1, len(GRADES) - 1)
        rows.append({"essay_id": essay_id, "rater_id": "R_bias", "grade": GRADES[shifted_index]})
    df = pd.DataFrame(rows)

    model_off = ConsensusModel(KernelConfig(bias_correction=False))
    model_off.fit(df)
    results_off = model_off.get_consensus()
    bias_df_off = model_off.rater_bias_posteriors
    if not bias_df_off.empty:
        assert not bias_df_off["applied"].any()

    weights, _ = compute_rater_weights(df, GRADE_TO_INDEX)
    for essay_id, group in df.groupby("essay_id"):
        expected_off = results_off[essay_id].expected_grade_index
        weighted_sum = 0.0
        weight_total = 0.0
        for _, row in group.iterrows():
            w = weights.get(row["rater_id"], 1.0)
            idx = GRADE_TO_INDEX[row["grade"]]
            weighted_sum += w * idx
            weight_total += w
        assert weight_total > 0
        assert expected_off == pytest.approx(weighted_sum / weight_total)

    model_on = ConsensusModel(KernelConfig(bias_correction=True))
    model_on.fit(df)
    results_on = model_on.get_consensus()
    differing = False
    for essay_id in results_on:
        if (
            not pytest.approx(results_on[essay_id].expected_grade_index)
            == results_off[essay_id].expected_grade_index
        ):
            differing = True
            break
    assert differing
