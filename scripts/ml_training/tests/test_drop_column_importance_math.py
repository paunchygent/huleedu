from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.drop_column_importance import _delta_stats, _summarize_deltas


def test_delta_stats_returns_mean_std_and_per_fold() -> None:
    values = np.array([1.0, -1.0], dtype=float)
    stats = _delta_stats(values)
    assert stats["per_fold"] == [1.0, -1.0]
    assert stats["mean"] == 0.0
    assert stats["std"] == 1.0


def test_summarize_deltas_stability_fraction_counts_positive_only() -> None:
    entry = _summarize_deltas(
        feature_name="example",
        deltas_qwk=np.array([0.1, -0.2, 0.0], dtype=float),
        deltas_mae=np.array([0.0, 0.1, 0.2], dtype=float),
        deltas_adj=np.array([-1.0, 1.0, 1.0], dtype=float),
        folds=[],
    )
    assert np.isclose(entry["stability"]["qwk_positive_fraction"], 1.0 / 3.0)
    assert np.isclose(entry["stability"]["mae_positive_fraction"], 2.0 / 3.0)
    assert np.isclose(entry["stability"]["adjacent_positive_fraction"], 2.0 / 3.0)
