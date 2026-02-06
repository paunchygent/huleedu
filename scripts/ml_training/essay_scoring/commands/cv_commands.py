"""Cross-validation and drop-column command registrations.

Purpose:
    Host commands for CV execution and handcrafted-feature drop-column
    diagnostics, including training-mode and calibration controls.

Relationships:
    - Registered by `scripts.ml_training.essay_scoring.cli`.
    - Uses `run_cross_validation` and `run_drop_column_importance`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.commands.common import (
    apply_overrides,
    load_config,
    resolve_split_scheme,
)
from scripts.ml_training.essay_scoring.config import DatasetKind, FeatureSet, OffloadBackend
from scripts.ml_training.essay_scoring.cross_validation import run_cross_validation
from scripts.ml_training.essay_scoring.drop_column_importance import run_drop_column_importance
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging
from scripts.ml_training.essay_scoring.training.grade_band_weighting import GradeBandWeighting
from scripts.ml_training.essay_scoring.training.prediction_mapping import PredictionMapping
from scripts.ml_training.essay_scoring.training.training_modes import TrainingMode


def register(app: typer.Typer) -> None:
    """Register CV and drop-column commands on the app."""

    @app.command("cv")
    def cv_command(
        splits_path: Path = typer.Option(
            ...,
            help="Path to a splits.json file created by `make-splits`.",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        scheme: str = typer.Option(
            "stratified_text",
            help="Split scheme: stratified_text or prompt_holdout.",
        ),
        ensemble_size: int = typer.Option(
            1,
            help=(
                "Number of models to train per fold (seed ensemble). "
                "CV metrics are computed on the averaged predictions."
            ),
            min=1,
            max=10,
        ),
        config_path: Path | None = typer.Option(
            None,
            help="Path to JSON config overrides",
        ),
        dataset_kind: DatasetKind | None = typer.Option(
            None,
            help="Dataset kind to load (ielts, ellipse).",
        ),
        feature_set: FeatureSet | None = typer.Option(
            None,
            help="Feature set to train (handcrafted, embeddings, combined)",
        ),
        training_mode: TrainingMode = typer.Option(
            TrainingMode.REGRESSION,
            help=(
                "Training mode for model fitting. "
                "Use ordinal_multiclass_* to study grade-band compression and tail behavior "
                "(currently supported in the XGBoost CV path)."
            ),
        ),
        grade_band_weighting: GradeBandWeighting = typer.Option(
            GradeBandWeighting.NONE,
            help=(
                "Optional training-time grade-band weighting scheme to reduce tail bias (Gate D). "
                "Use with prompt_holdout CV only."
            ),
        ),
        grade_band_weight_cap: float = typer.Option(
            3.0,
            help="Maximum per-sample weight when grade-band weighting is enabled.",
            min=1.0,
            max=10.0,
        ),
        prediction_mapping: PredictionMapping = typer.Option(
            PredictionMapping.ROUND_HALF_BAND,
            help=(
                "Optional post-hoc mapping from y_pred_raw -> y_pred for CV metrics and residual "
                "diagnostics. Use qwk_cutpoints_lfo to learn monotone cutpoints without leakage "
                "(leave-one-fold-out)."
            ),
        ),
        predictor_handcrafted_keep: list[str] | None = typer.Option(
            None,
            help=(
                "Optional allowlist of handcrafted feature names to include in the predictor. "
                "For feature_set=combined, embeddings are always kept; "
                "this filters only handcrafted columns. "
                "Repeat the flag for multiple features."
            ),
        ),
        predictor_handcrafted_drop: list[str] | None = typer.Option(
            None,
            help=(
                "Optional denylist of handcrafted feature names to drop from the predictor. "
                "Cannot be used with --predictor-handcrafted-keep. "
                "Repeat the flag for multiple features."
            ),
        ),
        ellipse_train_path: Path | None = typer.Option(
            None,
            help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
        ),
        ellipse_test_path: Path | None = typer.Option(
            None,
            help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
        ),
        run_name: str | None = typer.Option(
            None,
            help="Optional run name suffix",
        ),
        backend: OffloadBackend = typer.Option(
            OffloadBackend.LOCAL,
            help="Feature extraction backend (local or hemma).",
        ),
        offload_service_url: str | None = typer.Option(
            None,
            help="Combined offload service base URL (Hemma tunnel), e.g. http://127.0.0.1:19000.",
        ),
        offload_request_timeout_s: float | None = typer.Option(
            None,
            help=(
                "Offload request timeout in seconds (applies to Hemma /v1/extract calls). "
                "If omitted, uses the config default (typically 60s)."
            ),
            min=1.0,
            max=600.0,
        ),
        embedding_service_url: str | None = typer.Option(
            None,
            help="Optional Hemma embedding offload base URL (e.g. http://127.0.0.1:19000).",
        ),
        language_tool_service_url: str | None = typer.Option(
            None,
            help="Optional Hemma LanguageTool service base URL (e.g. http://127.0.0.1:18085).",
        ),
        reuse_cv_feature_store_dir: Path | None = typer.Option(
            None,
            help="Reuse a previously generated CV feature store directory (or its parent run dir).",
        ),
        min_words: int | None = typer.Option(
            None,
            help="Optional override for min_words; must match the splits.json window if set.",
            min=0,
        ),
        max_words: int | None = typer.Option(
            None,
            help="Optional override for max_words; must match the splits.json window if set.",
            min=0,
        ),
    ) -> None:
        """Run cross-validation using a pre-generated splits.json definition."""

        configure_console_logging()
        config = apply_overrides(
            config=load_config(config_path),
            dataset_kind=dataset_kind,
            dataset_path=None,
            ellipse_train_path=ellipse_train_path,
            ellipse_test_path=ellipse_test_path,
            run_name=run_name,
            backend=backend,
            offload_service_url=offload_service_url,
            offload_request_timeout_s=offload_request_timeout_s,
            embedding_service_url=embedding_service_url,
            language_tool_service_url=language_tool_service_url,
        )
        summary = run_cross_validation(
            config,
            feature_set=feature_set or config.feature_set,
            splits_path=splits_path,
            scheme=resolve_split_scheme(scheme=scheme),
            ensemble_size=ensemble_size,
            reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
            min_words=min_words,
            max_words=max_words,
            handcrafted_keep=predictor_handcrafted_keep,
            handcrafted_drop=predictor_handcrafted_drop,
            training_mode=training_mode,
            grade_band_weighting=grade_band_weighting,
            grade_band_weight_cap=grade_band_weight_cap,
            prediction_mapping=prediction_mapping,
        )
        typer.echo(f"CV complete: {summary.run_paths.run_dir}")
        typer.echo(f"Metrics: {summary.metrics_path}")
        typer.echo(f"Report: {summary.report_path}")
        typer.echo(f"Residual report: {summary.residual_report_path}")

    @app.command("drop-column")
    def drop_column_command(
        splits_path: Path = typer.Option(
            ...,
            help="Path to a splits.json file created by `make-splits`.",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        scheme: str = typer.Option(
            "stratified_text",
            help="Split scheme: stratified_text or prompt_holdout.",
        ),
        config_path: Path | None = typer.Option(
            None,
            help="Path to JSON config overrides",
        ),
        dataset_kind: DatasetKind | None = typer.Option(
            None,
            help="Dataset kind to load (ielts, ellipse).",
        ),
        feature_set: FeatureSet | None = typer.Option(
            None,
            help="Feature set to train (handcrafted, embeddings, combined)",
        ),
        ellipse_train_path: Path | None = typer.Option(
            None,
            help="Override ELLIPSE train CSV path (only used when --dataset-kind=ellipse).",
        ),
        ellipse_test_path: Path | None = typer.Option(
            None,
            help="Override ELLIPSE test CSV path (only used when --dataset-kind=ellipse).",
        ),
        run_name: str | None = typer.Option(
            None,
            help="Optional run name suffix",
        ),
        backend: OffloadBackend = typer.Option(
            OffloadBackend.LOCAL,
            help="Feature extraction backend (local or hemma).",
        ),
        offload_service_url: str | None = typer.Option(
            None,
            help="Combined offload service base URL (Hemma tunnel), e.g. http://127.0.0.1:19000.",
        ),
        offload_request_timeout_s: float | None = typer.Option(
            None,
            help=(
                "Offload request timeout in seconds (applies to Hemma /v1/extract calls). "
                "If omitted, uses the config default (typically 60s)."
            ),
            min=1.0,
            max=600.0,
        ),
        embedding_service_url: str | None = typer.Option(
            None,
            help="Optional Hemma embedding offload base URL (e.g. http://127.0.0.1:19000).",
        ),
        language_tool_service_url: str | None = typer.Option(
            None,
            help="Optional Hemma LanguageTool service base URL (e.g. http://127.0.0.1:18085).",
        ),
        reuse_cv_feature_store_dir: Path | None = typer.Option(
            None,
            help="Reuse a previously generated CV feature store directory (or its parent run dir).",
        ),
        min_words: int | None = typer.Option(
            None,
            help="Optional override for min_words; must match the splits.json window if set.",
            min=0,
        ),
        max_words: int | None = typer.Option(
            None,
            help="Optional override for max_words; must match the splits.json window if set.",
            min=0,
        ),
    ) -> None:
        """Run CV drop-column importance for handcrafted features."""

        configure_console_logging()
        config = apply_overrides(
            config=load_config(config_path),
            dataset_kind=dataset_kind,
            dataset_path=None,
            ellipse_train_path=ellipse_train_path,
            ellipse_test_path=ellipse_test_path,
            run_name=run_name,
            backend=backend,
            offload_service_url=offload_service_url,
            offload_request_timeout_s=offload_request_timeout_s,
            embedding_service_url=embedding_service_url,
            language_tool_service_url=language_tool_service_url,
        )
        summary = run_drop_column_importance(
            config,
            feature_set=feature_set or config.feature_set,
            splits_path=splits_path,
            scheme=resolve_split_scheme(scheme=scheme),
            reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
            min_words=min_words,
            max_words=max_words,
        )
        typer.echo(f"Drop-column complete: {summary.run_paths.run_dir}")
        typer.echo(f"Metrics: {summary.metrics_path}")
        typer.echo(f"Report: {summary.report_path}")
