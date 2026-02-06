"""Transformer fine-tuning command registrations.

Purpose:
    Provide a canonical `transformer-finetune` command for Gate G3 CV-first
    experiments with frozen ELLIPSE inputs and anti-truncation telemetry.

Relationships:
    - Registered by `scripts.ml_training.essay_scoring.cli`.
    - Delegates training/evaluation to `run_transformer_finetune_cv`.
    - Validates CV feature-store lineage via `resolve_cv_feature_store_dir`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.commands.common import (
    apply_overrides,
    load_config,
    resolve_split_scheme,
)
from scripts.ml_training.essay_scoring.config import DatasetKind, OffloadBackend
from scripts.ml_training.essay_scoring.cv_feature_store import resolve_cv_feature_store_dir
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging
from scripts.ml_training.essay_scoring.transformer_finetune import (
    MixedPrecisionMode,
    TransformerFinetuneConfig,
    run_transformer_finetune_cv,
)


def register(app: typer.Typer) -> None:
    """Register transformer fine-tuning command on the provided app."""

    @app.command("transformer-finetune")
    def transformer_finetune_command(
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
        config_path: Path | None = typer.Option(
            None,
            help="Path to JSON config overrides.",
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
            help=(
                "Reference CV feature store directory (or parent run dir) used for "
                "frozen-input lineage. Validated before training."
            ),
            exists=True,
            dir_okay=True,
            file_okay=False,
        ),
        run_name: str = typer.Option(
            "ellipse_gate_g3_1_transformer_lora_prompt_holdout",
            help="Run name suffix (timestamp prefix is added automatically).",
        ),
        model_name: str = typer.Option(
            "microsoft/deberta-v3-base",
            help="Transformer backbone checkpoint.",
        ),
        max_length: int = typer.Option(
            512,
            help="Tokenizer max sequence length for chunk windows.",
            min=8,
            max=4096,
        ),
        chunk_overlap_tokens: int = typer.Option(
            128,
            help="Overlap between neighboring chunks for long essays.",
            min=0,
            max=2048,
        ),
        train_batch_size: int = typer.Option(
            4,
            help="Per-device train batch size.",
            min=1,
            max=256,
        ),
        eval_batch_size: int = typer.Option(
            8,
            help="Per-device eval batch size.",
            min=1,
            max=256,
        ),
        gradient_accumulation_steps: int = typer.Option(
            8,
            help="Gradient accumulation steps (controls effective batch size).",
            min=1,
            max=256,
        ),
        learning_rate: float = typer.Option(
            2e-5,
            help="Optimizer learning rate.",
            min=1e-7,
            max=1e-2,
        ),
        weight_decay: float = typer.Option(
            0.01,
            help="AdamW weight decay.",
            min=0.0,
            max=1.0,
        ),
        num_epochs: int = typer.Option(
            5,
            help="Maximum epoch count.",
            min=1,
            max=100,
        ),
        warmup_ratio: float = typer.Option(
            0.1,
            help="Linear warmup ratio in [0.0, 0.5].",
            min=0.0,
            max=0.5,
        ),
        early_stopping_patience: int = typer.Option(
            2,
            help="Stop after this many non-improving epochs.",
            min=1,
            max=20,
        ),
        max_grad_norm: float = typer.Option(
            1.0,
            help="Gradient clipping norm.",
            min=0.0,
            max=100.0,
        ),
        mixed_precision: MixedPrecisionMode = typer.Option(
            MixedPrecisionMode.AUTO,
            help="Precision mode: auto, bf16, fp16, none.",
        ),
        gradient_checkpointing: bool = typer.Option(
            True,
            help="Enable transformer gradient checkpointing.",
        ),
        use_lora: bool = typer.Option(
            True,
            help="Enable LoRA adapters for parameter-efficient fine-tuning.",
        ),
        lora_r: int = typer.Option(
            16,
            help="LoRA rank.",
            min=1,
            max=256,
        ),
        lora_alpha: int = typer.Option(
            32,
            help="LoRA alpha.",
            min=1,
            max=512,
        ),
        lora_dropout: float = typer.Option(
            0.1,
            help="LoRA dropout rate.",
            min=0.0,
            max=1.0,
        ),
        random_seed: int = typer.Option(
            42,
            help="Global random seed.",
        ),
        dataloader_num_workers: int = typer.Option(
            4,
            help="DataLoader worker processes.",
            min=0,
            max=32,
        ),
        dataloader_prefetch_factor: int = typer.Option(
            2,
            help="DataLoader prefetch factor (used when num_workers > 0).",
            min=1,
            max=16,
        ),
        require_gpu: bool = typer.Option(
            True,
            help="Fail fast when CUDA/HIP GPU is unavailable (required for Gate G3 runs).",
        ),
    ) -> None:
        """Run CV-first transformer fine-tuning with Gate G3-ready artifacts."""

        configure_console_logging()
        resolved_store_dir = resolve_cv_feature_store_dir(reuse_cv_feature_store_dir)
        typer.echo(f"Reference CV feature store: {resolved_store_dir}")

        config = apply_overrides(
            config=load_config(config_path),
            dataset_kind=DatasetKind.ELLIPSE,
            dataset_path=None,
            ellipse_train_path=ellipse_train_path,
            ellipse_test_path=ellipse_test_path,
            run_name=run_name,
            backend=OffloadBackend.LOCAL,
            offload_service_url=None,
            offload_request_timeout_s=None,
            embedding_service_url=None,
            language_tool_service_url=None,
        )
        summary = run_transformer_finetune_cv(
            config,
            splits_path=splits_path,
            scheme=resolve_split_scheme(scheme=scheme),
            finetune_config=TransformerFinetuneConfig(
                model_name=model_name,
                max_length=max_length,
                chunk_overlap_tokens=chunk_overlap_tokens,
                train_batch_size=train_batch_size,
                eval_batch_size=eval_batch_size,
                gradient_accumulation_steps=gradient_accumulation_steps,
                learning_rate=learning_rate,
                weight_decay=weight_decay,
                num_epochs=num_epochs,
                warmup_ratio=warmup_ratio,
                early_stopping_patience=early_stopping_patience,
                max_grad_norm=max_grad_norm,
                mixed_precision=mixed_precision,
                gradient_checkpointing=gradient_checkpointing,
                use_lora=use_lora,
                lora_r=lora_r,
                lora_alpha=lora_alpha,
                lora_dropout=lora_dropout,
                random_seed=random_seed,
                dataloader_num_workers=dataloader_num_workers,
                dataloader_prefetch_factor=dataloader_prefetch_factor,
                require_gpu=require_gpu,
            ),
        )
        typer.echo(f"Transformer CV complete: {summary.run_paths.run_dir}")
        typer.echo(f"Metrics: {summary.metrics_path}")
        typer.echo(f"Report: {summary.report_path}")
        typer.echo(f"Residual report: {summary.residual_report_path}")
        typer.echo(f"Truncation coverage: {summary.truncation_coverage_path}")
