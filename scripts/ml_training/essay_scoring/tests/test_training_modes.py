"""Tests for training mode helpers (ordinal multiclass encoding/decoding)."""

from __future__ import annotations

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.training.training_modes import (
    TrainingMode,
    decode_predictions,
    encode_ordinal_labels,
    ordinal_num_classes,
    qwk_custom_metric,
)


def test_encode_ordinal_labels_produces_contiguous_class_ids() -> None:
    y_true = np.array([1.0, 2.0, 5.0], dtype=np.float32)
    encoded = encode_ordinal_labels(y_true, min_band=1.0, max_band=5.0)
    assert encoded.tolist() == [0, 2, 8]


def test_decode_predictions_expected_value() -> None:
    min_band = 1.0
    max_band = 5.0
    n_classes = ordinal_num_classes(min_band=min_band, max_band=max_band)

    proba = np.zeros((2, n_classes), dtype=np.float32)
    proba[0, 0] = 0.5  # 1.0
    proba[0, 1] = 0.5  # 1.5
    proba[1, 8] = 1.0  # 5.0

    decoded = decode_predictions(
        proba,
        min_band=min_band,
        max_band=max_band,
        mode=TrainingMode.ORDINAL_MULTICLASS_EXPECTED,
    )
    assert np.isclose(decoded[0], 1.25)
    assert np.isclose(decoded[1], 5.0)


def test_decode_predictions_argmax() -> None:
    min_band = 1.0
    max_band = 5.0
    n_classes = ordinal_num_classes(min_band=min_band, max_band=max_band)

    proba = np.zeros((2, n_classes), dtype=np.float32)
    proba[0, 1] = 1.0  # 1.5
    proba[1, 8] = 1.0  # 5.0

    decoded = decode_predictions(
        proba,
        min_band=min_band,
        max_band=max_band,
        mode=TrainingMode.ORDINAL_MULTICLASS_ARGMAX,
    )
    assert decoded.tolist() == [1.5, 5.0]


def test_qwk_custom_metric_for_ordinal_handles_perfect_predictions() -> None:
    min_band = 1.0
    max_band = 5.0
    y_true = np.array([1.0, 1.5, 2.0, 5.0], dtype=np.float32)
    y_class = encode_ordinal_labels(y_true, min_band=min_band, max_band=max_band).astype(float)

    n_classes = ordinal_num_classes(min_band=min_band, max_band=max_band)
    proba = np.zeros((y_true.shape[0], n_classes), dtype=np.float32)
    for i, cls in enumerate(y_class.astype(int)):
        proba[i, cls] = 1.0

    metric = qwk_custom_metric(
        min_band=min_band,
        max_band=max_band,
        mode=TrainingMode.ORDINAL_MULTICLASS_ARGMAX,
    )
    dtrain = xgb.DMatrix(np.zeros((y_true.shape[0], 1), dtype=np.float32), label=y_class)
    name, value = metric(proba, dtrain)
    assert name == "qwk"
    assert np.isclose(value, 1.0)
