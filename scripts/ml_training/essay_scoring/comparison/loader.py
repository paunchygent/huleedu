"""Load and validate CV run artifacts for comparison.

Given a run directory, this module parses:
- `artifacts/cv_metrics.json` for fold and summary metrics,
- `artifacts/residuals_cv_val_oof.csv` for prompt/tail diagnostics.

It returns a typed `RunMetrics` object used by gate comparisons.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ml_training.essay_scoring.comparison.models import (
    CvMetricsPayload,
    FoldMetricName,
    RunMetrics,
)
from scripts.ml_training.essay_scoring.hyperparameter_sweep import (
    compute_tail_slice_metrics,
)
from scripts.ml_training.essay_scoring.optuna_sweep import (
    compute_prompt_slice_metrics,
)


def load_run_metrics(
    *,
    run_dir: Path,
    min_prompt_n: int,
    bottom_k_prompts: int,
) -> RunMetrics:
    """Load one run's artifacts and compute comparison diagnostics."""

    metrics_path = run_dir / "artifacts" / "cv_metrics.json"
    residuals_path = run_dir / "artifacts" / "residuals_cv_val_oof.csv"
    if not metrics_path.exists():
        raise FileNotFoundError(f"Missing metrics artifact: {metrics_path}")
    if not residuals_path.exists():
        raise FileNotFoundError(f"Missing residual artifact: {residuals_path}")

    payload = _parse_cv_metrics_payload(json.loads(metrics_path.read_text(encoding="utf-8")))
    fold_val_qwk = _fold_metric_map(payload=payload, metric_name="qwk")
    fold_val_adjacent = _fold_metric_map(payload=payload, metric_name="adjacent_accuracy")
    fold_val_mae = _fold_metric_map(payload=payload, metric_name="mean_absolute_error")
    prompt_metrics = compute_prompt_slice_metrics(
        residuals_path=residuals_path,
        min_prompt_n=min_prompt_n,
    )
    low_tail, high_tail, mid_adjacent = compute_tail_slice_metrics(residuals_path)
    mean_qwk = float(payload["summary"]["val_qwk_mean"])
    bottom_prompts = prompt_metrics[:bottom_k_prompts]
    worst_prompt_qwk = bottom_prompts[0].qwk if bottom_prompts else mean_qwk

    return RunMetrics(
        run_dir=run_dir,
        scheme=payload["scheme"],
        model_family=payload["model_family"],
        mean_qwk=mean_qwk,
        worst_prompt_qwk=float(worst_prompt_qwk),
        low_tail=low_tail,
        high_tail=high_tail,
        mid_band_adjacent_accuracy=float(mid_adjacent),
        fold_val_qwk=fold_val_qwk,
        fold_val_adjacent_accuracy=fold_val_adjacent,
        fold_val_mae=fold_val_mae,
        bottom_prompts=bottom_prompts,
    )


def _fold_metric_map(
    *,
    payload: CvMetricsPayload,
    metric_name: FoldMetricName,
) -> dict[str, float]:
    mapping: dict[str, float] = {}
    for fold in payload["folds"]:
        fold_id = str(fold["fold"])
        metric_value = float(fold["val"][metric_name])
        mapping[fold_id] = metric_value
    return mapping


def _parse_cv_metrics_payload(raw_payload: object) -> CvMetricsPayload:
    if not isinstance(raw_payload, dict):
        raise ValueError("Invalid CV metrics payload: expected object.")
    if "summary" not in raw_payload or "folds" not in raw_payload:
        raise ValueError("Invalid CV metrics payload: missing summary/folds.")

    summary_raw = raw_payload["summary"]
    folds_raw = raw_payload["folds"]
    if not isinstance(summary_raw, dict):
        raise ValueError("Invalid CV metrics payload: summary must be an object.")
    if not isinstance(folds_raw, list) or not folds_raw:
        raise ValueError("Invalid CV metrics payload: folds must be a non-empty array.")

    val_qwk_mean_raw = summary_raw.get("val_qwk_mean")
    if not isinstance(val_qwk_mean_raw, (float, int)):
        raise ValueError("Invalid CV metrics payload: summary.val_qwk_mean must be numeric.")

    folds = []
    for fold_raw in folds_raw:
        if not isinstance(fold_raw, dict):
            raise ValueError("Invalid CV metrics payload: fold must be an object.")
        fold_id_raw = fold_raw.get("fold")
        fold_val_raw = fold_raw.get("val")
        if not isinstance(fold_id_raw, int):
            raise ValueError("Invalid CV metrics payload: fold id must be int.")
        if not isinstance(fold_val_raw, dict):
            raise ValueError("Invalid CV metrics payload: fold val must be an object.")

        qwk_raw = fold_val_raw.get("qwk")
        adj_raw = fold_val_raw.get("adjacent_accuracy")
        mae_raw = fold_val_raw.get("mean_absolute_error")
        if not isinstance(qwk_raw, (float, int)):
            raise ValueError("Invalid CV metrics payload: fold val.qwk must be numeric.")
        if not isinstance(adj_raw, (float, int)):
            raise ValueError(
                "Invalid CV metrics payload: fold val.adjacent_accuracy must be numeric."
            )
        if not isinstance(mae_raw, (float, int)):
            raise ValueError("Invalid CV metrics payload: fold val.mean_absolute_error numeric.")
        folds.append(
            {
                "fold": int(fold_id_raw),
                "val": {
                    "qwk": float(qwk_raw),
                    "adjacent_accuracy": float(adj_raw),
                    "mean_absolute_error": float(mae_raw),
                },
            }
        )

    scheme_raw = raw_payload.get("scheme", "unknown")
    model_family_raw = raw_payload.get("model_family", "xgboost")
    scheme = str(scheme_raw)
    model_family = str(model_family_raw)
    return {
        "scheme": scheme,
        "model_family": model_family,
        "summary": {"val_qwk_mean": float(val_qwk_mean_raw)},
        "folds": folds,
    }
