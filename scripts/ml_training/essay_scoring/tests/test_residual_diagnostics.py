"""Tests for residual diagnostics artifacts and report generation."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.reports.residual_diagnostics import (
    build_residual_frame,
    generate_residual_diagnostics_report,
    persist_residual_artifacts,
)


def test_build_residual_frame_includes_covariates_and_rounding() -> None:
    feature_names = [
        "word_count",
        "grammar_errors_per_100_words",
        "spelling_errors_per_100_words",
        "punctuation_errors_per_100_words",
        "prompt_similarity",
    ]
    features = FeatureMatrix(
        matrix=np.array(
            [
                [250.0, 1.0, 2.0, 0.5, 0.8],
                [300.0, 3.0, 1.0, 0.0, 0.4],
                [500.0, 5.0, 5.0, 1.5, 0.1],
            ],
            dtype=np.float32,
        ),
        feature_names=feature_names,
    )

    record_ids = ["a", "b", "c"]
    prompts = ["P1", "P2", "P1"]
    y_true = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    y_pred_raw = np.array([1.1, 2.7, 5.4], dtype=np.float32)

    frame = build_residual_frame(
        record_ids=record_ids,
        prompts=prompts,
        y_true=y_true,
        y_pred_raw=y_pred_raw,
        min_band=1.0,
        max_band=5.0,
        split_label="cv_val_oof",
        feature_matrix=features,
    )

    assert frame.shape[0] == 3
    assert frame.loc[0, "y_pred"] == 1.0
    assert frame.loc[1, "y_pred"] == 2.5
    assert frame.loc[2, "y_pred"] == 5.0  # clipped (5.5 -> 5.0)

    assert frame.loc[0, "within_half_band"] == 1
    assert frame.loc[1, "within_half_band"] == 1
    assert frame.loc[2, "within_half_band"] == 0

    assert frame.loc[0, "word_count"] == 250.0
    assert frame.loc[0, "grammar_errors_per_100_words"] == 1.0
    assert np.isclose(float(frame.loc[0, "prompt_similarity"]), 0.8)


def test_persist_and_report_roundtrip(tmp_path: Path) -> None:
    features = FeatureMatrix(
        matrix=np.array([[250.0, 1.0, 2.0, 0.5, 0.8]], dtype=np.float32),
        feature_names=[
            "word_count",
            "grammar_errors_per_100_words",
            "spelling_errors_per_100_words",
            "punctuation_errors_per_100_words",
            "prompt_similarity",
        ],
    )
    frame = build_residual_frame(
        record_ids=["a"],
        prompts=["P1"],
        y_true=np.array([1.0], dtype=np.float32),
        y_pred_raw=np.array([1.4], dtype=np.float32),
        min_band=1.0,
        max_band=5.0,
        split_label="locked_test",
        feature_matrix=features,
    )

    artifacts = persist_residual_artifacts(frame, output_stem=tmp_path / "residuals")
    assert artifacts.csv_path.exists()
    assert artifacts.jsonl_path.exists()

    report_path = tmp_path / "residual_diagnostics.md"
    generate_residual_diagnostics_report(
        frames={"locked_test": frame},
        min_band=1.0,
        max_band=5.0,
        output_path=report_path,
        min_prompt_n=1,
        top_prompts=5,
        worst_examples=5,
    )
    text = report_path.read_text(encoding="utf-8")
    assert "Residual Diagnostics Report" in text
    assert "## Split: `locked_test`" in text


def test_build_residual_frame_respects_mapped_predictions() -> None:
    record_ids = ["a", "b", "c"]
    prompts = ["P1", "P2", "P3"]
    y_true = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    y_pred_raw = np.array([1.1, 2.7, 5.4], dtype=np.float32)
    y_pred_mapped = np.array([1.5, 2.0, 4.5], dtype=np.float32)

    frame = build_residual_frame(
        record_ids=record_ids,
        prompts=prompts,
        y_true=y_true,
        y_pred_raw=y_pred_raw,
        y_pred_mapped=y_pred_mapped,
        min_band=1.0,
        max_band=5.0,
        split_label="cv_val_oof",
        feature_matrix=None,
    )

    assert frame.loc[0, "y_pred"] == 1.5
    assert frame.loc[1, "y_pred"] == 2.0
    assert frame.loc[2, "y_pred"] == 4.5
