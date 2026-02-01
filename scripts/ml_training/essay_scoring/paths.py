"""Path helpers for essay scoring research artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.ml_training.essay_scoring.config import OutputConfig


@dataclass(frozen=True)
class RunPaths:
    """Resolved run output paths for artifacts."""

    run_dir: Path
    artifacts_dir: Path
    reports_dir: Path
    shap_dir: Path
    metadata_path: Path
    metrics_path: Path
    model_path: Path
    feature_schema_path: Path
    grade_scale_report_path: Path
    log_path: Path


def build_run_paths(output_config: OutputConfig) -> RunPaths:
    """Create directories and resolve artifact paths for a run.

    Args:
        output_config: Output configuration with base directory and run name.

    Returns:
        RunPaths containing resolved directories and file paths.
    """

    run_dir = output_config.resolve_run_dir()
    artifacts_dir = run_dir / "artifacts"
    reports_dir = run_dir / "reports"
    shap_dir = run_dir / "shap"

    for directory in (run_dir, artifacts_dir, reports_dir, shap_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return RunPaths(
        run_dir=run_dir,
        artifacts_dir=artifacts_dir,
        reports_dir=reports_dir,
        shap_dir=shap_dir,
        metadata_path=artifacts_dir / "metadata.json",
        metrics_path=artifacts_dir / "metrics.json",
        model_path=artifacts_dir / "xgboost_regressor.json",
        feature_schema_path=artifacts_dir / "feature_schema.json",
        grade_scale_report_path=reports_dir / "grade_scale_report.md",
        log_path=run_dir / "run.log",
    )
