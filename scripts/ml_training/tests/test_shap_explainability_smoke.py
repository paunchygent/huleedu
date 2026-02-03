from __future__ import annotations

import numpy as np
import xgboost as xgb

import scripts.ml_training.essay_scoring.training.shap_explainability as shap_module
from scripts.ml_training.essay_scoring.training.shap_explainability import generate_shap_artifacts


def test_generate_shap_artifacts_writes_expected_files(tmp_path) -> None:
    class _DummyExplainer:
        def __init__(self, _model: xgb.Booster) -> None:
            self.expected_value = 0.0

        def shap_values(self, features: np.ndarray) -> np.ndarray:
            return np.zeros_like(features, dtype=np.float32)

    def _dummy_explainer_factory(model: xgb.Booster) -> _DummyExplainer:
        return _DummyExplainer(model)

    def _dummy_summary_plot(*_args, **_kwargs) -> None:
        from matplotlib import pyplot as plt

        plt.figure()

    rng = np.random.default_rng(0)
    features = rng.normal(size=(25, 3)).astype(np.float32)
    labels = rng.normal(size=(25,)).astype(np.float32)
    feature_names = ["f0", "f1", "f2"]

    model = xgb.train(
        params={"objective": "reg:squarederror", "max_depth": 2, "learning_rate": 0.3, "seed": 42},
        dtrain=xgb.DMatrix(features, label=labels, feature_names=feature_names),
        num_boost_round=3,
    )

    artifacts = generate_shap_artifacts(
        model=model,
        features=features,
        feature_names=feature_names,
        output_dir=tmp_path,
        max_samples=5,
        explainer_factory=_dummy_explainer_factory,
        summary_plot_fn=_dummy_summary_plot,
    )

    assert artifacts.shap_values_path.exists()
    assert artifacts.base_values_path.exists()
    assert artifacts.summary_plot_path.exists()
    assert artifacts.bar_plot_path.exists()

    shap_values = np.load(artifacts.shap_values_path)
    assert shap_values.shape == (5, 3)

    base_values = np.load(artifacts.base_values_path)
    assert base_values.size == 1


def test_sample_features_noop_when_small() -> None:
    features = np.zeros((3, 2), dtype=np.float32)
    sampled = shap_module._sample_features(features, max_samples=10)
    assert sampled is features
