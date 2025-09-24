"""Tests for the kernel-based ordinal consensus model."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.bayesian_consensus_model.bayesian_consensus_model import (
    ConsensusModel,
    ConsensusResult,
    GRADES,
    KernelConfig,
)


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
