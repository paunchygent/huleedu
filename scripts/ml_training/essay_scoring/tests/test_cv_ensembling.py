"""Tests for CV ensembling support in the essay scoring research pipeline.

Purpose:
    Verify that fold-level training can ensemble across multiple model seeds and that the
    returned fold predictions are the simple average of member predictions (as specified in
    `TASKS/assessment/essay-scoring-cv-ensembling-ellipse-cv-first.md`).

Relationships:
    - Targets `scripts.ml_training.essay_scoring.cv_shared.run_fold_with_predictions`.
"""

from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.config import ExperimentConfig
from scripts.ml_training.essay_scoring.cv_shared import run_fold_with_predictions
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.split_definitions import FoldDefinition


class _FakeBooster:
    def __init__(self, value: float) -> None:
        self._value = float(value)

    def predict(self, dmatrix: object) -> np.ndarray:
        num_row = getattr(dmatrix, "num_row")
        n_rows = int(num_row()) if callable(num_row) else int(num_row)
        return np.full(n_rows, self._value, dtype=float)


class _FakeArtifacts:
    def __init__(self, seed: int) -> None:
        self.model = _FakeBooster(seed)
        self.best_iteration = int(seed)


def test_run_fold_with_predictions_ensembles_by_averaging_member_predictions(monkeypatch) -> None:
    import scripts.ml_training.essay_scoring.cv_shared as cv_shared

    def fake_train_model(*args: object, **kwargs: object) -> _FakeArtifacts:
        training_config = args[4]
        seed = int(getattr(training_config, "random_seed"))
        return _FakeArtifacts(seed)

    monkeypatch.setattr(cv_shared, "train_model", fake_train_model)

    record_ids = [f"r{i}" for i in range(6)]
    id_to_idx = {record_id: idx for idx, record_id in enumerate(record_ids)}

    features = FeatureMatrix(
        matrix=np.zeros((6, 2), dtype=float),
        feature_names=["f1", "f2"],
    )
    y = np.array([1.0, 1.5, 2.0, 2.5, 3.0, 3.5], dtype=float)
    fold = FoldDefinition(
        fold=0,
        train_record_ids=record_ids[:4],
        val_record_ids=record_ids[4:],
    )

    member_seeds = [10, 20, 30]
    outcome = run_fold_with_predictions(
        fold=fold,
        train_id_to_idx=id_to_idx,
        features=features,
        y=y,
        config=ExperimentConfig(),
        member_seeds=member_seeds,
        min_band=1.0,
        max_band=5.0,
        keep_feature_indices=None,
    )

    expected_mean = float(np.mean(member_seeds))
    assert outcome.fold_result["best_iteration"] == int(expected_mean)
    assert np.allclose(outcome.val_pred_raw, np.full(2, expected_mean, dtype=float))
