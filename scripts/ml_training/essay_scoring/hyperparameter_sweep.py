"""XGBoost hyperparameter sweep utilities for essay-scoring (CV-first).

Purpose:
    Run a small, systematic sweep over XGBoost training hyperparameters using the existing
    cross-validation runner. The sweep is designed to be:
    - CV-selected (never selected on the locked test set),
    - feature-store aware (always reuses an existing CV feature store for speed and drift safety),
    - slice-aware (records low/high tail metrics so we avoid "global QWK wins" that worsen tails).

Relationships:
    - Invoked by `scripts.ml_training.essay_scoring.cli` via the `xgb-sweep` command.
    - Executes each configuration by calling
      `scripts.ml_training.essay_scoring.cross_validation.run_cross_validation`.
    - Uses `scripts.ml_training.essay_scoring.logging_utils.ProgressWriter` to persist a small,
      machine-readable sweep progress file in the sweep run directory.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scripts.ml_training.essay_scoring.config import ExperimentConfig, OutputConfig
from scripts.ml_training.essay_scoring.cross_validation import run_cross_validation
from scripts.ml_training.essay_scoring.cv_shared import SplitScheme
from scripts.ml_training.essay_scoring.logging_utils import ProgressWriter, update_status
from scripts.ml_training.essay_scoring.training.grade_band_weighting import GradeBandWeighting
from scripts.ml_training.essay_scoring.training.prediction_mapping import PredictionMapping
from scripts.ml_training.essay_scoring.training.training_modes import TrainingMode

_DEFAULT_PARAM_GRID: dict[str, list[int | float]] = {
    "max_depth": [3, 4, 5],
    "min_child_weight": [5, 10, 20],
    "reg_lambda": [2.0, 5.0, 10.0],
    "reg_alpha": [0.0, 1.0],
}


class SweepConfigError(ValueError):
    """Raised when the sweep definition is invalid or unsupported."""


@dataclass(frozen=True)
class SliceMetrics:
    """Simple slice metrics computed from per-record residual rows."""

    count: int
    mean_absolute_error: float
    mean_residual: float
    adjacent_accuracy: float


@dataclass(frozen=True)
class SweepRunResult:
    """A single hyperparameter configuration result within a sweep."""

    config_id: str
    training_params: dict[str, Any]
    run_dir: str
    cv_qwk_mean: float
    cv_qwk_std: float
    cv_mae_mean: float
    cv_adjacent_accuracy_mean: float
    low_tail: SliceMetrics
    high_tail: SliceMetrics
    mid_band_adjacent_accuracy: float


def load_param_grid(grid_path: Path | None) -> dict[str, list[int | float]]:
    """Load a parameter grid from JSON, falling back to a small default grid."""

    if grid_path is None:
        return dict(_DEFAULT_PARAM_GRID)

    payload = json.loads(grid_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SweepConfigError("grid JSON must be an object")

    grid = payload.get("training_params_grid", payload.get("grid", payload))
    if not isinstance(grid, dict):
        raise SweepConfigError("grid JSON must contain an object under training_params_grid/grid")

    parsed: dict[str, list[int | float]] = {}
    for key, values in grid.items():
        if not isinstance(key, str) or not key:
            raise SweepConfigError("grid keys must be non-empty strings")
        if not isinstance(values, list) or not values:
            raise SweepConfigError(f"grid[{key}] must be a non-empty list")
        cast_values: list[int | float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SweepConfigError(
                    f"grid[{key}] values must be numbers (int/float); got {value!r}"
                )
            cast_values.append(value)
        parsed[key] = cast_values

    return parsed


def iter_grid_configs(param_grid: dict[str, list[int | float]]) -> Iterable[dict[str, Any]]:
    """Yield training parameter override dicts for the Cartesian product of the grid."""

    keys = sorted(param_grid.keys())
    values = [param_grid[key] for key in keys]
    for combo in itertools.product(*values):
        yield dict(zip(keys, combo, strict=True))


def stable_config_id(params: dict[str, Any]) -> str:
    """Return a stable, short id for a training parameter dict."""

    payload = json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:10]


def _read_residual_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


def _slice_metrics(rows: Iterable[dict[str, str]]) -> SliceMetrics:
    total = 0
    sum_abs = 0.0
    sum_residual = 0.0
    sum_within = 0.0
    for row in rows:
        total += 1
        sum_abs += float(row["abs_residual"])
        sum_residual += float(row["residual"])
        sum_within += float(row["within_half_band"])

    if total == 0:
        return SliceMetrics(
            count=0, mean_absolute_error=0.0, mean_residual=0.0, adjacent_accuracy=0.0
        )

    return SliceMetrics(
        count=total,
        mean_absolute_error=sum_abs / total,
        mean_residual=sum_residual / total,
        adjacent_accuracy=sum_within / total,
    )


def compute_tail_slice_metrics(residuals_path: Path) -> tuple[SliceMetrics, SliceMetrics, float]:
    """Compute low/high tail metrics and mid-band adjacent accuracy from residual rows.

    Args:
        residuals_path: Path to `artifacts/residuals_cv_val_oof.csv`.

    Returns:
        (low_tail_metrics, high_tail_metrics, mid_band_adjacent_accuracy)
    """

    low_rows: list[dict[str, str]] = []
    high_rows: list[dict[str, str]] = []
    mid_within_sum = 0.0
    mid_total = 0

    for row in _read_residual_rows(residuals_path):
        y_true = float(row["y_true"])
        if y_true <= 2.0:
            low_rows.append(row)
        if y_true >= 4.0:
            high_rows.append(row)
        if 2.5 <= y_true <= 3.5:
            mid_total += 1
            mid_within_sum += float(row["within_half_band"])

    mid_adjacent_accuracy = (mid_within_sum / mid_total) if mid_total > 0 else 0.0
    return _slice_metrics(low_rows), _slice_metrics(high_rows), mid_adjacent_accuracy


def run_xgb_hyperparameter_sweep(
    *,
    base_config: ExperimentConfig,
    splits_path: Path,
    scheme: SplitScheme,
    reuse_cv_feature_store_dir: Path,
    sweep_run_name: str,
    param_grid: dict[str, list[int | float]],
    feature_set: Any,
    handcrafted_keep: list[str] | None = None,
    handcrafted_drop: list[str] | None = None,
    training_mode: TrainingMode,
    grade_band_weighting: GradeBandWeighting,
    grade_band_weight_cap: float,
    prediction_mapping: PredictionMapping,
    max_runs: int | None = None,
    shuffle: bool = False,
    shuffle_seed: int = 42,
) -> Path:
    """Run a CV hyperparameter sweep and write a sweep summary under a single run directory.

    Returns:
        The sweep run directory path.
    """

    sweep_dir = OutputConfig(
        base_dir=base_config.output.base_dir, run_name=sweep_run_name
    ).resolve_run_dir()
    sweep_artifacts_dir = sweep_dir / "artifacts"
    sweep_reports_dir = sweep_dir / "reports"
    sweep_variants_base_dir = sweep_dir / "variants"
    sweep_artifacts_dir.mkdir(parents=True, exist_ok=True)
    sweep_reports_dir.mkdir(parents=True, exist_ok=True)
    sweep_variants_base_dir.mkdir(parents=True, exist_ok=True)

    update_status(
        sweep_dir,
        stage="xgb_sweep",
        state="running",
        scheme=str(scheme),
        sweep_run_name=sweep_run_name,
    )
    progress = ProgressWriter(sweep_dir)

    grid_configs = list(iter_grid_configs(param_grid))
    if shuffle:
        import random

        random.Random(shuffle_seed).shuffle(grid_configs)
    if max_runs is not None:
        grid_configs = grid_configs[: int(max_runs)]

    sweep_definition = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sweep_run_dir": str(sweep_dir),
        "splits_path": str(splits_path),
        "scheme": str(scheme),
        "reuse_cv_feature_store_dir": str(reuse_cv_feature_store_dir),
        "feature_set": str(feature_set),
        "training_mode": str(training_mode),
        "grade_band_weighting": str(grade_band_weighting),
        "grade_band_weight_cap": float(grade_band_weight_cap),
        "prediction_mapping": str(prediction_mapping),
        "predictor_handcrafted_keep": list(handcrafted_keep) if handcrafted_keep else None,
        "predictor_handcrafted_drop": list(handcrafted_drop) if handcrafted_drop else None,
        "param_grid": param_grid,
        "grid_size": len(grid_configs),
        "base_training_params": dict(base_config.training.params),
    }
    (sweep_artifacts_dir / "sweep_definition.json").write_text(
        json.dumps(sweep_definition, indent=2), encoding="utf-8"
    )

    results: list[SweepRunResult] = []
    for index, overrides in enumerate(grid_configs, start=1):
        config_id = stable_config_id(overrides)
        run_name = f"{sweep_run_name}_{config_id}"

        updated_training = base_config.training.model_copy(
            update={"params": {**base_config.training.params, **overrides}}
        )
        updated_output = base_config.output.model_copy(
            update={"base_dir": sweep_variants_base_dir, "run_name": run_name}
        )
        variant_config = base_config.model_copy(
            update={"training": updated_training, "output": updated_output}
        )

        progress.update(
            substage="sweep_variants",
            processed=index - 1,
            total=len(grid_configs),
            unit="configs",
            details={"current_config_id": config_id, "current_run_name": run_name},
            force=True,
        )

        summary = run_cross_validation(
            variant_config,
            feature_set=feature_set,
            splits_path=splits_path,
            scheme=scheme,
            reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
            handcrafted_keep=handcrafted_keep,
            handcrafted_drop=handcrafted_drop,
            training_mode=training_mode,
            grade_band_weighting=grade_band_weighting,
            grade_band_weight_cap=grade_band_weight_cap,
            prediction_mapping=prediction_mapping,
        )

        metrics = json.loads(summary.metrics_path.read_text(encoding="utf-8"))
        residuals_path = summary.run_paths.artifacts_dir / "residuals_cv_val_oof.csv"
        low_tail, high_tail, mid_adjacent_accuracy = compute_tail_slice_metrics(residuals_path)

        results.append(
            SweepRunResult(
                config_id=config_id,
                training_params=overrides,
                run_dir=str(summary.run_paths.run_dir),
                cv_qwk_mean=float(metrics["summary"]["val_qwk_mean"]),
                cv_qwk_std=float(metrics["summary"]["val_qwk_std"]),
                cv_mae_mean=float(metrics["summary"]["val_mae_mean"]),
                cv_adjacent_accuracy_mean=float(metrics["summary"]["val_adjacent_accuracy_mean"]),
                low_tail=low_tail,
                high_tail=high_tail,
                mid_band_adjacent_accuracy=float(mid_adjacent_accuracy),
            )
        )

        (sweep_artifacts_dir / "sweep_results.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "results": [asdict(result) for result in results],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    progress.update(
        substage="sweep_variants",
        processed=len(grid_configs),
        total=len(grid_configs),
        unit="configs",
        force=True,
    )
    update_status(sweep_dir, stage="xgb_sweep", state="completed")

    def sort_key(result: SweepRunResult) -> tuple[float, float]:
        return (result.high_tail.adjacent_accuracy, result.cv_qwk_mean)

    sorted_results = sorted(results, key=sort_key, reverse=True)
    lines = [
        f"# XGBoost hyperparameter sweep: `{sweep_run_name}`",
        "",
        "Sorted by: high-tail adjacent accuracy (primary) then CV mean QWK.",
        "",
        "| Rank | config_id | QWK mean±std | High tail adj_acc | High tail MAE | Mid adj_acc | "
        "max_depth | min_child_weight | reg_lambda | reg_alpha | run_dir |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for rank, result in enumerate(sorted_results, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    result.config_id,
                    f"{result.cv_qwk_mean:.5f} ± {result.cv_qwk_std:.5f}",
                    f"{result.high_tail.adjacent_accuracy:.5f}",
                    f"{result.high_tail.mean_absolute_error:.5f}",
                    f"{result.mid_band_adjacent_accuracy:.5f}",
                    str(result.training_params.get("max_depth", "")),
                    str(result.training_params.get("min_child_weight", "")),
                    str(result.training_params.get("reg_lambda", "")),
                    str(result.training_params.get("reg_alpha", "")),
                    f"`{result.run_dir}`",
                ]
            )
            + " |"
        )

    (sweep_reports_dir / "sweep_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sweep_dir
