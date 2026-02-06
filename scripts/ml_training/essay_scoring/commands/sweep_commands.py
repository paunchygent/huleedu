"""Hyperparameter sweep command registrations.

Purpose:
    Host sweep-oriented commands for fixed-grid (`xgb-sweep`) and Optuna
    (`optuna-sweep`) selection workflows.

Relationships:
    - Registered by `scripts.ml_training.essay_scoring.cli`.
    - Uses sweep runners in `hyperparameter_sweep` and `optuna_sweep`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.commands.common import (
    apply_overrides,
    load_config,
    resolve_predictor_filters,
    resolve_split_scheme,
)
from scripts.ml_training.essay_scoring.config import DatasetKind, FeatureSet, OffloadBackend
from scripts.ml_training.essay_scoring.hyperparameter_sweep import (
    load_param_grid,
    run_xgb_hyperparameter_sweep,
)
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging
from scripts.ml_training.essay_scoring.optuna_sweep import (
    OPTUNA_OBJECTIVE_WORST_PROMPT_THEN_MEAN,
    run_optuna_sweep,
)
from scripts.ml_training.essay_scoring.training.grade_band_weighting import GradeBandWeighting
from scripts.ml_training.essay_scoring.training.prediction_mapping import PredictionMapping
from scripts.ml_training.essay_scoring.training.training_modes import TrainingMode


def register(app: typer.Typer) -> None:
    """Register sweep commands on the provided app."""

    @app.command("xgb-sweep")
    def xgb_sweep_command(
        splits_path: Path = typer.Option(
            ...,
            help="Path to a splits.json file created by `make-splits`.",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        scheme: str = typer.Option(
            "prompt_holdout",
            help=(
                "Split scheme: stratified_text or prompt_holdout. "
                "Prefer prompt_holdout for CV-first selection."
            ),
        ),
        grid_path: Path | None = typer.Option(
            None,
            help=(
                "Optional JSON file defining `training_params_grid` for the sweep. "
                "If omitted, uses a small default grid focused on regularization."
            ),
        ),
        max_runs: int | None = typer.Option(
            None,
            help=(
                "Optional cap on the number of configurations to run "
                "(useful for a quick pilot sweep)."
            ),
            min=1,
        ),
        shuffle: bool = typer.Option(
            False,
            help="Shuffle sweep order (useful when running a capped pilot sweep).",
        ),
        shuffle_seed: int = typer.Option(
            42,
            help="Seed used when --shuffle is enabled.",
        ),
        config_path: Path | None = typer.Option(
            None,
            help=(
                "Path to JSON config overrides "
                "(used as the base config before applying grid params)."
            ),
        ),
        feature_set: FeatureSet = typer.Option(
            FeatureSet.COMBINED,
            help="Feature set to train (handcrafted, embeddings, combined).",
        ),
        training_mode: TrainingMode = typer.Option(
            TrainingMode.REGRESSION,
            help="Training mode for the XGBoost model. Sweeps should start with regression.",
        ),
        grade_band_weighting: GradeBandWeighting = typer.Option(
            GradeBandWeighting.SQRT_INV_FREQ,
            help=(
                "Training-time grade-band weighting scheme (default uses Gate D best-current "
                "sqrt_inv_freq)."
            ),
        ),
        grade_band_weight_cap: float = typer.Option(
            3.0,
            help="Maximum per-sample weight when grade-band weighting is enabled.",
            min=1.0,
            max=10.0,
        ),
        prediction_mapping: PredictionMapping = typer.Option(
            PredictionMapping.QWK_CUTPOINTS_LFO,
            help=(
                "Post-hoc mapping for CV metrics/residual diagnostics (default uses Gate D "
                "best-current qwk_cutpoints_lfo)."
            ),
        ),
        predictor_handcrafted_keep: list[str] | None = typer.Option(
            None,
            help=(
                "Optional allowlist of handcrafted feature names to include in the predictor. "
                "For feature_set=combined, embeddings are always kept; "
                "this filters only handcrafted columns."
            ),
        ),
        predictor_handcrafted_drop: list[str] | None = typer.Option(
            None,
            help=(
                "Optional denylist of handcrafted feature names to drop from the predictor. "
                "Cannot be used with --predictor-handcrafted-keep. "
                "If omitted, defaults to the current 'drop-3' prune "
                "(has_conclusion, clause_count, flesch_kincaid)."
            ),
        ),
        ellipse_train_path: Path = typer.Option(
            ...,
            help="ELLIPSE train CSV path (prepared dataset).",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        ellipse_test_path: Path = typer.Option(
            ...,
            help="ELLIPSE test CSV path (prepared dataset).",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        reuse_cv_feature_store_dir: Path = typer.Option(
            ...,
            help="Reuse an existing CV feature store directory (or its parent run dir).",
            exists=True,
            dir_okay=True,
            file_okay=False,
        ),
        run_name: str = typer.Option(
            "ellipse_xgb_sweep_prompt_holdout_drop3_weighting_calibration",
            help="Sweep run name suffix (a timestamp prefix is always added).",
        ),
    ) -> None:
        """Run an XGBoost hyperparameter sweep using CV and feature-store reuse."""

        predictor_handcrafted_keep, predictor_handcrafted_drop = resolve_predictor_filters(
            predictor_handcrafted_keep=predictor_handcrafted_keep,
            predictor_handcrafted_drop=predictor_handcrafted_drop,
        )
        configure_console_logging()
        config = apply_overrides(
            config=load_config(config_path),
            dataset_kind=DatasetKind.ELLIPSE,
            dataset_path=None,
            ellipse_train_path=ellipse_train_path,
            ellipse_test_path=ellipse_test_path,
            run_name=None,
            backend=OffloadBackend.LOCAL,
            offload_service_url=None,
            offload_request_timeout_s=None,
            embedding_service_url=None,
            language_tool_service_url=None,
        )
        sweep_dir = run_xgb_hyperparameter_sweep(
            base_config=config,
            splits_path=splits_path,
            scheme=resolve_split_scheme(scheme=scheme),
            reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
            sweep_run_name=run_name,
            param_grid=load_param_grid(grid_path),
            feature_set=feature_set,
            handcrafted_keep=predictor_handcrafted_keep,
            handcrafted_drop=predictor_handcrafted_drop,
            training_mode=training_mode,
            grade_band_weighting=grade_band_weighting,
            grade_band_weight_cap=grade_band_weight_cap,
            prediction_mapping=prediction_mapping,
            max_runs=max_runs,
            shuffle=shuffle,
            shuffle_seed=shuffle_seed,
        )
        typer.echo(f"Sweep complete: {sweep_dir}")

    @app.command("optuna-sweep")
    def optuna_sweep_command(
        splits_path: Path = typer.Option(
            ...,
            help="Path to a splits.json file created by `make-splits`.",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        scheme: str = typer.Option(
            "prompt_holdout",
            help="Split scheme: stratified_text or prompt_holdout.",
        ),
        n_trials: int = typer.Option(
            40,
            help="Number of Optuna trials to run.",
            min=1,
        ),
        objective: str = typer.Option(
            OPTUNA_OBJECTIVE_WORST_PROMPT_THEN_MEAN,
            help=("Optimization objective. Supported: `worst_prompt_qwk_then_mean_qwk`."),
        ),
        min_prompt_n: int = typer.Option(
            30,
            help="Minimum prompt sample size for prompt-level QWK diagnostics.",
            min=1,
        ),
        bottom_k_prompts: int = typer.Option(
            5,
            help="How many worst prompts to persist/report per trial.",
            min=1,
        ),
        baseline_best_run_dir: Path = typer.Option(
            ...,
            help=(
                "Path to the baseline best run directory containing "
                "`artifacts/cv_metrics.json` and `artifacts/residuals_cv_val_oof.csv`."
            ),
            exists=True,
            dir_okay=True,
            file_okay=False,
        ),
        config_path: Path | None = typer.Option(
            None,
            help="Path to JSON config overrides (base config before trial overrides).",
        ),
        feature_set: FeatureSet = typer.Option(
            FeatureSet.COMBINED,
            help="Feature set to train (handcrafted, embeddings, combined).",
        ),
        training_mode: TrainingMode = typer.Option(
            TrainingMode.REGRESSION,
            help="Training mode for the XGBoost model.",
        ),
        grade_band_weighting: GradeBandWeighting = typer.Option(
            GradeBandWeighting.SQRT_INV_FREQ,
            help="Training-time grade-band weighting scheme.",
        ),
        grade_band_weight_cap: float = typer.Option(
            3.0,
            help="Maximum per-sample weight when grade-band weighting is enabled.",
            min=1.0,
            max=10.0,
        ),
        prediction_mapping: PredictionMapping = typer.Option(
            PredictionMapping.QWK_CUTPOINTS_LFO,
            help="Post-hoc mapping for CV metrics and residual diagnostics.",
        ),
        predictor_handcrafted_keep: list[str] | None = typer.Option(
            None,
            help=(
                "Optional allowlist of handcrafted feature names to include in the predictor. "
                "For feature_set=combined, embeddings are always kept; "
                "this filters only handcrafted columns."
            ),
        ),
        predictor_handcrafted_drop: list[str] | None = typer.Option(
            None,
            help=(
                "Optional denylist of handcrafted feature names to drop from the predictor. "
                "Cannot be used with --predictor-handcrafted-keep. "
                "If omitted, defaults to the current 'drop-3' prune "
                "(has_conclusion, clause_count, flesch_kincaid)."
            ),
        ),
        ellipse_train_path: Path = typer.Option(
            ...,
            help="ELLIPSE train CSV path (prepared dataset).",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        ellipse_test_path: Path = typer.Option(
            ...,
            help="ELLIPSE test CSV path (prepared dataset).",
            exists=True,
            dir_okay=False,
            file_okay=True,
        ),
        reuse_cv_feature_store_dir: Path = typer.Option(
            ...,
            help="Reuse an existing CV feature store directory (or its parent run dir).",
            exists=True,
            dir_okay=True,
            file_okay=False,
        ),
        run_name: str = typer.Option(
            "ellipse_optuna_sweep_prompt_holdout_drop3_wcal",
            help="Sweep run name suffix (a timestamp prefix is always added).",
        ),
    ) -> None:
        """Run an Optuna-based XGBoost CV sweep using feature-store reuse."""

        predictor_handcrafted_keep, predictor_handcrafted_drop = resolve_predictor_filters(
            predictor_handcrafted_keep=predictor_handcrafted_keep,
            predictor_handcrafted_drop=predictor_handcrafted_drop,
        )
        configure_console_logging()
        config = apply_overrides(
            config=load_config(config_path),
            dataset_kind=DatasetKind.ELLIPSE,
            dataset_path=None,
            ellipse_train_path=ellipse_train_path,
            ellipse_test_path=ellipse_test_path,
            run_name=None,
            backend=OffloadBackend.LOCAL,
            offload_service_url=None,
            offload_request_timeout_s=None,
            embedding_service_url=None,
            language_tool_service_url=None,
        )
        sweep_dir = run_optuna_sweep(
            base_config=config,
            splits_path=splits_path,
            scheme=resolve_split_scheme(scheme=scheme),
            reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
            sweep_run_name=run_name,
            feature_set=feature_set,
            n_trials=n_trials,
            objective=objective,
            min_prompt_n=min_prompt_n,
            bottom_k_prompts=bottom_k_prompts,
            baseline_best_run_dir=baseline_best_run_dir,
            handcrafted_keep=predictor_handcrafted_keep,
            handcrafted_drop=predictor_handcrafted_drop,
            training_mode=training_mode,
            grade_band_weighting=grade_band_weighting,
            grade_band_weight_cap=grade_band_weight_cap,
            prediction_mapping=prediction_mapping,
        )
        typer.echo(f"Optuna sweep complete: {sweep_dir}")
