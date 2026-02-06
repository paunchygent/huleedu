"""Cross-validation report generator for essay scoring CV runs.

Purpose:
    Render a concise Markdown report (`cv_report.md`) from the CV metrics payload produced by
    `scripts.ml_training.essay_scoring.cross_validation`.

Relationships:
    - Called by `scripts.ml_training.essay_scoring.cross_validation` after CV completes.
    - Consumes fold-level results from `scripts.ml_training.essay_scoring.cv_shared`.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Any, Mapping


def build_cv_report(payload: Mapping[str, Any]) -> str:
    """Build the markdown CV report.

    Args:
        payload: Metrics payload written to `artifacts/cv_metrics.json`.

    Returns:
        Markdown report content.
    """

    summary = payload["summary"]
    folds = payload["folds"]
    final_eval = payload["final_train_val_test"]

    qwk_mean = summary["val_qwk_mean"]
    qwk_std = summary["val_qwk_std"]
    mae_mean = summary["val_mae_mean"]
    mae_std = summary["val_mae_std"]
    adj_mean = summary["val_adjacent_accuracy_mean"]
    adj_std = summary["val_adjacent_accuracy_std"]
    elapsed_s = summary["elapsed_s"]
    predictor_selection = payload.get("predictor_feature_selection", None)

    grade_band_weighting_line = None
    if "grade_band_weighting" in payload:
        cap = payload.get("grade_band_weight_cap", "n/a")
        grade_band_weighting_line = (
            f"- grade_band_weighting: `{payload['grade_band_weighting']}` (cap={cap})"
        )

    prediction_mapping_line = None
    if "prediction_mapping" in payload:
        prediction_mapping_line = f"- prediction_mapping: `{payload['prediction_mapping']}`"

    lines = [
        "# Cross-Validation Report",
        "",
        "## Summary",
        "",
        f"- dataset_kind: `{payload['dataset_kind']}`",
        f"- feature_set: `{payload['feature_set']}`",
        *([f"- ensemble_size: `{payload['ensemble_size']}`"] if "ensemble_size" in payload else []),
        *([f"- training_mode: `{payload['training_mode']}`"] if "training_mode" in payload else []),
        *([grade_band_weighting_line] if grade_band_weighting_line is not None else []),
        *([prediction_mapping_line] if prediction_mapping_line is not None else []),
        *_predictor_selection_lines(predictor_selection),
        f"- scheme: `{payload['scheme']}`",
        f"- n_splits: `{payload['n_splits']}`",
        f"- word_count_window: `{payload['word_count_window']}`",
        f"- records: `{payload['record_counts']}`",
        "",
        "## CV Metrics (val)",
        "",
        f"- qwk_mean±std: `{qwk_mean:.4f}` ± `{qwk_std:.4f}`",
        f"- mae_mean±std: `{mae_mean:.4f}` ± `{mae_std:.4f}`",
        f"- adjacent_acc_mean±std: `{adj_mean:.4f}` ± `{adj_std:.4f}`",
        f"- elapsed_s: `{elapsed_s:.1f}`",
        "",
        "## Folds",
        "",
        _fold_table(folds),
        "",
        "## Final (single split) + Locked Test",
        "",
        _final_table(final_eval),
        "",
    ]
    return "\n".join(lines)


def _predictor_selection_lines(selection: Any | None) -> list[str]:
    if not isinstance(selection, MappingABC):
        return []

    mode = str(selection.get("mode", "unknown"))
    embedding_dim = selection.get("embedding_dim", None)
    kept_handcrafted = selection.get("kept_handcrafted_feature_count", None)
    kept_total = selection.get("kept_feature_count", None)
    total = selection.get("feature_count_total", None)

    pieces = [f"mode={mode}"]
    if embedding_dim is not None:
        pieces.append(f"embedding_dim={embedding_dim}")
    if kept_handcrafted is not None:
        pieces.append(f"kept_handcrafted={kept_handcrafted}")
    if kept_total is not None and total is not None:
        pieces.append(f"kept_total={kept_total}/{total}")
    line = "- predictor_feature_selection: `" + ", ".join(pieces) + "`"

    keep_names = selection.get("kept_handcrafted_features", None)
    if isinstance(keep_names, list) and keep_names:
        keep_line = "- predictor_handcrafted_keep: `" + ", ".join(map(str, keep_names)) + "`"
        return [line, keep_line]

    return [line]


def _fold_table(folds: list[Mapping[str, Any]]) -> str:
    rows: list[tuple[str, ...]] = [("fold", "train", "val", "val_qwk", "val_mae", "best_iter")]
    for fold in folds:
        rows.append(
            (
                str(fold["fold"]),
                str(fold["sizes"]["train"]),
                str(fold["sizes"]["val"]),
                f"{fold['val']['qwk']:.4f}",
                f"{fold['val']['mean_absolute_error']:.4f}",
                str(fold["best_iteration"]),
            )
        )
    return _markdown_table(rows)


def _final_table(final_eval: Mapping[str, Any]) -> str:
    rows: list[tuple[str, ...]] = [
        ("split", "qwk", "mae", "adjacent_acc"),
        (
            "val",
            f"{final_eval['val']['qwk']:.4f}",
            f"{final_eval['val']['mean_absolute_error']:.4f}",
            f"{final_eval['val']['adjacent_accuracy']:.4f}",
        ),
        (
            "test",
            f"{final_eval['test']['qwk']:.4f}",
            f"{final_eval['test']['mean_absolute_error']:.4f}",
            f"{final_eval['test']['adjacent_accuracy']:.4f}",
        ),
    ]
    return _markdown_table(rows)


def _markdown_table(rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return ""
    headers = rows[0]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows[1:]:
        escaped = [cell.replace("\n", " ").replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)
