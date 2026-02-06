"""Transformer fine-tuning CV runner for essay scoring research.

Purpose:
    Run CV-first transformer fine-tuning experiments (baseline and invariance-ready
    scaffolding) under the same split discipline and artifact contracts used by the
    XGBoost pipeline.

Relationships:
    - Invoked by `scripts.ml_training.essay_scoring.commands.transformer_commands`.
    - Reuses split/dataset guards from `scripts.ml_training.essay_scoring.cv_shared`.
    - Persists residual diagnostics through
      `scripts.ml_training.essay_scoring.reports.residual_diagnostics`.
"""

from __future__ import annotations

import json
import logging
import math
import random
import statistics
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, TypedDict

import numpy as np
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset, Sampler
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    PreTrainedTokenizerBase,
    get_linear_schedule_with_warmup,
)

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig
from scripts.ml_training.essay_scoring.cv_shared import (
    SplitScheme,
    filter_by_word_count,
    raise_on_overlap,
    select_folds,
    validate_record_ids_against_splits,
    validate_splits_compatibility,
)
from scripts.ml_training.essay_scoring.dataset import EssayRecord, load_ellipse_train_test_dataset
from scripts.ml_training.essay_scoring.logging_utils import (
    ProgressWriter,
    run_file_logger,
    stage_timer,
)
from scripts.ml_training.essay_scoring.paths import RunPaths, build_run_paths
from scripts.ml_training.essay_scoring.reports.residual_diagnostics import (
    build_residual_frame,
    generate_residual_diagnostics_report,
    persist_residual_artifacts,
)
from scripts.ml_training.essay_scoring.split_definitions import load_splits
from scripts.ml_training.essay_scoring.training.evaluation import (
    EvaluationResult,
    evaluate_predictions,
)

logger = logging.getLogger(__name__)

_CV_METRICS_SCHEMA_VERSION = 6


class MixedPrecisionMode(str, Enum):
    """Supported mixed precision modes for transformer fine-tuning."""

    AUTO = "auto"
    BF16 = "bf16"
    FP16 = "fp16"
    NONE = "none"


class FoldSizes(TypedDict):
    """Train/validation record counts for one fold."""

    train: int
    val: int


class FoldEval(TypedDict):
    """Validation metrics for one fold split."""

    qwk: float
    adjacent_accuracy: float
    mean_absolute_error: float


class TransformerFoldResult(TypedDict):
    """Fold-level training and evaluation summary."""

    fold: int
    sizes: FoldSizes
    best_iteration: int
    train: FoldEval
    val: FoldEval


class WordCountWindow(TypedDict):
    """Word-count filtering window used for the run."""

    min: int
    max: int


class RecordCounts(TypedDict):
    """Record counts after filtering and split discipline."""

    train: int
    test: int


class TransformerCvSummary(TypedDict):
    """Aggregated CV metrics summary."""

    val_qwk_mean: float
    val_qwk_std: float
    val_mae_mean: float
    val_mae_std: float
    val_adjacent_accuracy_mean: float
    val_adjacent_accuracy_std: float
    elapsed_s: float


class TruncationCoverage(TypedDict):
    """Telemetry for anti-truncation policy monitoring."""

    pct_essays_exceeding_max_length: float
    avg_tokens_truncated_before_chunking: float
    avg_chunks_per_essay: float
    p95_chunks_per_essay: float
    max_length: int
    chunk_overlap_tokens: int


class TransformerCvMetricsPayload(TypedDict):
    """Machine-readable CV artifact payload for transformer fine-tuning."""

    schema_version: int
    created_at: str
    dataset_kind: str
    feature_set: str
    model_family: str
    model_name: str
    use_lora: bool
    mixed_precision: str
    scheme: SplitScheme
    n_splits: int
    word_count_window: WordCountWindow
    record_counts: RecordCounts
    folds: list[TransformerFoldResult]
    summary: TransformerCvSummary


@dataclass(frozen=True)
class TransformerFinetuneConfig:
    """Training/runtime configuration for transformer CV fine-tuning."""

    model_name: str
    max_length: int
    chunk_overlap_tokens: int
    train_batch_size: int
    eval_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    weight_decay: float
    num_epochs: int
    warmup_ratio: float
    early_stopping_patience: int
    max_grad_norm: float
    mixed_precision: MixedPrecisionMode
    gradient_checkpointing: bool
    use_lora: bool
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    random_seed: int
    dataloader_num_workers: int
    dataloader_prefetch_factor: int
    require_gpu: bool = False
    use_length_bucketing: bool = True
    bucket_size_multiplier: int = 20


@dataclass(frozen=True)
class TransformerFinetuneSummary:
    """Summary paths for a completed transformer fine-tuning CV run."""

    run_paths: RunPaths
    metrics_path: Path
    report_path: Path
    residual_report_path: Path
    truncation_coverage_path: Path


@dataclass(frozen=True)
class ChunkedEssay:
    """One essay represented as multiple windowed token chunks."""

    record_id: str
    prompt: str
    label: float
    token_count: int
    chunk_input_ids: list[list[int]]


@dataclass(frozen=True)
class ChunkSample:
    """One chunk-level training/evaluation sample."""

    record_id: str
    label: float
    input_ids: list[int]
    attention_mask: list[int]


@dataclass(frozen=True)
class CollatedBatch:
    """Batch container produced by the chunk collate function."""

    input_ids: torch.Tensor
    attention_mask: torch.Tensor
    labels: torch.Tensor
    record_ids: list[str]


@dataclass(frozen=True)
class PrecisionRuntime:
    """Resolved precision runtime for autocast/scaler control."""

    enabled: bool
    dtype: torch.dtype | None
    use_grad_scaler: bool
    label: str


@dataclass(frozen=True)
class FoldTrainingOutcome:
    """Fold outputs needed for metrics and residual artifacts."""

    fold_result: TransformerFoldResult
    val_record_ids: list[str]
    val_true: np.ndarray
    val_pred_raw: np.ndarray


class ChunkDataset(Dataset[ChunkSample]):
    """Simple chunk dataset for transformer fine-tuning."""

    def __init__(self, samples: list[ChunkSample]) -> None:
        self._samples = samples
        self._sample_lengths = [len(sample.input_ids) for sample in samples]

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, index: int) -> ChunkSample:
        return self._samples[index]

    def sample_lengths(self) -> list[int]:
        """Return token lengths for each sample in index order."""

        return self._sample_lengths


class BucketBatchSampler(Sampler[list[int]]):
    """Sampler that yields precomputed batches of sample indices."""

    def __init__(self, batches: list[list[int]]) -> None:
        self._batches = batches

    def __iter__(self) -> Iterator[list[int]]:
        return iter(self._batches)

    def __len__(self) -> int:
        return len(self._batches)


def run_transformer_finetune_cv(
    config: ExperimentConfig,
    *,
    splits_path: Path,
    scheme: SplitScheme,
    finetune_config: TransformerFinetuneConfig,
) -> TransformerFinetuneSummary:
    """Run transformer fine-tuning under CV discipline with residual artifacts."""

    _validate_finetune_config(finetune_config)
    if config.dataset_kind != DatasetKind.ELLIPSE:
        raise ValueError("transformer-finetune currently supports only --dataset-kind=ellipse")

    splits = load_splits(splits_path)
    validate_splits_compatibility(
        config=config,
        splits=splits,
        min_words=None,
        max_words=None,
    )

    min_words = int(splits.word_count_window["min"])
    max_words = int(splits.word_count_window["max"])
    word_window: WordCountWindow = {"min": min_words, "max": max_words}

    run_paths = build_run_paths(config.output)
    metrics_path = run_paths.artifacts_dir / "cv_metrics.json"
    report_path = run_paths.reports_dir / "cv_report.md"
    residual_report_path = run_paths.reports_dir / "residual_diagnostics.md"
    truncation_coverage_path = run_paths.artifacts_dir / "truncation_coverage.json"

    with run_file_logger(run_paths.log_path):
        progress = ProgressWriter(run_paths.run_dir)
        _seed_everything(finetune_config.random_seed)
        device = _resolve_device()
        _enforce_gpu_requirement(device=device, require_gpu=finetune_config.require_gpu)
        precision = _resolve_precision_runtime(
            mode=finetune_config.mixed_precision,
            device=device,
        )
        progress.update(
            substage="transformer_cv.bootstrap",
            processed=0,
            total=1,
            unit="stage",
            details={"device": device.type, "precision": precision.label},
            force=True,
        )

        logger.info(
            "Starting transformer CV run_dir=%s model=%s scheme=%s device=%s precision=%s",
            run_paths.run_dir,
            finetune_config.model_name,
            scheme,
            device.type,
            precision.label,
        )

        dataset = load_ellipse_train_test_dataset(
            config.ellipse_train_path,
            config.ellipse_test_path,
            excluded_prompts=set(config.ellipse_excluded_prompts),
        )
        train_records = filter_by_word_count(
            dataset.train_records,
            min_words=min_words,
            max_words=max_words,
        )
        test_records = filter_by_word_count(
            dataset.test_records,
            min_words=min_words,
            max_words=max_words,
        )
        raise_on_overlap(train_records=train_records, test_records=test_records)
        validate_record_ids_against_splits(
            splits=splits,
            train_records=train_records,
            test_records=test_records,
        )

        tokenizer = AutoTokenizer.from_pretrained(finetune_config.model_name)
        chunked_by_id = _chunk_records(
            records=train_records,
            tokenizer=tokenizer,
            max_length=finetune_config.max_length,
            chunk_overlap_tokens=finetune_config.chunk_overlap_tokens,
        )
        truncation_coverage = compute_truncation_coverage(
            essays=list(chunked_by_id.values()),
            max_length=finetune_config.max_length,
            chunk_overlap_tokens=finetune_config.chunk_overlap_tokens,
        )
        truncation_coverage_path.write_text(
            json.dumps(truncation_coverage, indent=2),
            encoding="utf-8",
        )

        folds = select_folds(splits, scheme=scheme)
        min_band = float(min(record.overall for record in train_records))
        max_band = float(max(record.overall for record in train_records))

        fold_results: list[TransformerFoldResult] = []
        oof_val_record_ids: list[str] = []
        oof_val_fold_ids: list[int] = []
        oof_val_true: list[np.ndarray] = []
        oof_val_pred_raw: list[np.ndarray] = []
        train_id_to_prompt = {record.record_id: record.question for record in train_records}

        with stage_timer(
            run_paths.run_dir,
            logger,
            "transformer_cv_folds_train_eval",
            scheme=scheme,
            model_family="transformer",
            n_splits=len(folds),
        ):
            start = time.monotonic()
            for index, fold in enumerate(folds):
                train_essays = [chunked_by_id[record_id] for record_id in fold.train_record_ids]
                val_essays = [chunked_by_id[record_id] for record_id in fold.val_record_ids]
                outcome = _run_fold(
                    fold_index=int(fold.fold),
                    train_essays=train_essays,
                    val_essays=val_essays,
                    finetune_config=finetune_config,
                    tokenizer=tokenizer,
                    device=device,
                    precision=precision,
                    min_band=min_band,
                    max_band=max_band,
                )
                fold_results.append(outcome.fold_result)
                oof_val_record_ids.extend(outcome.val_record_ids)
                oof_val_fold_ids.extend([int(fold.fold)] * len(outcome.val_record_ids))
                oof_val_true.append(outcome.val_true)
                oof_val_pred_raw.append(outcome.val_pred_raw)
                progress.update(
                    substage="transformer_cv.folds",
                    processed=index + 1,
                    total=len(folds),
                    unit="folds",
                )
            elapsed_s = time.monotonic() - start

        if not oof_val_true or not oof_val_pred_raw:
            raise ValueError("No OOF validation predictions were produced.")
        y_true_all = np.concatenate(oof_val_true, axis=0)
        y_pred_raw_all = np.concatenate(oof_val_pred_raw, axis=0)
        prompts = [train_id_to_prompt[record_id] for record_id in oof_val_record_ids]
        residual_frame = build_residual_frame(
            record_ids=oof_val_record_ids,
            prompts=prompts,
            y_true=y_true_all,
            y_pred_raw=y_pred_raw_all,
            min_band=min_band,
            max_band=max_band,
            split_label="cv_val_oof",
            feature_matrix=None,
            row_indices=None,
            fold_ids=oof_val_fold_ids,
        )
        persist_residual_artifacts(
            residual_frame,
            output_stem=run_paths.artifacts_dir / "residuals_cv_val_oof",
        )
        generate_residual_diagnostics_report(
            frames={"cv_val_oof": residual_frame},
            min_band=min_band,
            max_band=max_band,
            output_path=residual_report_path,
            min_prompt_n=30,
            top_prompts=15,
            worst_examples=20,
        )

        summary_payload: TransformerCvSummary = _build_summary_payload(
            fold_results=fold_results,
            elapsed_s=elapsed_s,
        )
        metrics_payload: TransformerCvMetricsPayload = {
            "schema_version": _CV_METRICS_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset_kind": config.dataset_kind.value,
            "feature_set": "text_only",
            "model_family": "transformer",
            "model_name": finetune_config.model_name,
            "use_lora": finetune_config.use_lora,
            "mixed_precision": precision.label,
            "scheme": scheme,
            "n_splits": len(folds),
            "word_count_window": word_window,
            "record_counts": {"train": len(train_records), "test": len(test_records)},
            "folds": fold_results,
            "summary": summary_payload,
        }
        metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
        report_path.write_text(
            _build_cv_report_markdown(metrics_payload=metrics_payload),
            encoding="utf-8",
        )
        logger.info("Transformer CV complete: %s", run_paths.run_dir)

    return TransformerFinetuneSummary(
        run_paths=run_paths,
        metrics_path=metrics_path,
        report_path=report_path,
        residual_report_path=residual_report_path,
        truncation_coverage_path=truncation_coverage_path,
    )


def build_chunk_spans(
    *,
    token_count: int,
    max_content_tokens: int,
    chunk_overlap_tokens: int,
) -> list[tuple[int, int]]:
    """Return inclusive-exclusive token spans for chunking one essay."""

    if token_count <= 0:
        return [(0, 0)]
    if token_count <= max_content_tokens:
        return [(0, token_count)]
    stride = max(1, max_content_tokens - chunk_overlap_tokens)
    spans: list[tuple[int, int]] = []
    start = 0
    while start < token_count:
        end = min(start + max_content_tokens, token_count)
        spans.append((start, end))
        if end >= token_count:
            break
        start += stride
    return spans


def compute_truncation_coverage(
    *,
    essays: list[ChunkedEssay],
    max_length: int,
    chunk_overlap_tokens: int,
) -> TruncationCoverage:
    """Compute anti-truncation telemetry for one run."""

    max_content_tokens = max_length - 2
    if not essays:
        return {
            "pct_essays_exceeding_max_length": 0.0,
            "avg_tokens_truncated_before_chunking": 0.0,
            "avg_chunks_per_essay": 0.0,
            "p95_chunks_per_essay": 0.0,
            "max_length": max_length,
            "chunk_overlap_tokens": chunk_overlap_tokens,
        }

    exceed_counts = 0
    truncated_tokens: list[float] = []
    chunk_counts: list[float] = []
    for essay in essays:
        exceeds = essay.token_count > max_content_tokens
        if exceeds:
            exceed_counts += 1
        truncated_tokens.append(float(max(essay.token_count - max_content_tokens, 0)))
        chunk_counts.append(float(len(essay.chunk_input_ids)))
    chunk_count_array = np.array(chunk_counts, dtype=np.float32)
    pct_exceeding = 100.0 * (float(exceed_counts) / float(len(essays)))
    return {
        "pct_essays_exceeding_max_length": pct_exceeding,
        "avg_tokens_truncated_before_chunking": float(statistics.fmean(truncated_tokens)),
        "avg_chunks_per_essay": float(statistics.fmean(chunk_counts)),
        "p95_chunks_per_essay": float(np.percentile(chunk_count_array, 95.0)),
        "max_length": max_length,
        "chunk_overlap_tokens": chunk_overlap_tokens,
    }


def _run_fold(
    *,
    fold_index: int,
    train_essays: list[ChunkedEssay],
    val_essays: list[ChunkedEssay],
    finetune_config: TransformerFinetuneConfig,
    tokenizer: PreTrainedTokenizerBase,
    device: torch.device,
    precision: PrecisionRuntime,
    min_band: float,
    max_band: float,
) -> FoldTrainingOutcome:
    """Train one fold and return fold metrics + validation predictions."""

    train_samples = _flatten_chunk_samples(train_essays)
    val_samples = _flatten_chunk_samples(val_essays)
    train_dataset = ChunkDataset(train_samples)
    val_dataset = ChunkDataset(val_samples)
    collate_fn = _build_collate_fn(tokenizer)

    train_loader = _build_dataloader(
        dataset=train_dataset,
        batch_size=finetune_config.train_batch_size,
        shuffle=True,
        collate_fn=collate_fn,
        num_workers=finetune_config.dataloader_num_workers,
        prefetch_factor=finetune_config.dataloader_prefetch_factor,
        pin_memory=device.type == "cuda",
        use_length_bucketing=finetune_config.use_length_bucketing,
        bucket_size_multiplier=finetune_config.bucket_size_multiplier,
    )
    train_eval_loader = _build_dataloader(
        dataset=train_dataset,
        batch_size=finetune_config.eval_batch_size,
        shuffle=False,
        collate_fn=collate_fn,
        num_workers=finetune_config.dataloader_num_workers,
        prefetch_factor=finetune_config.dataloader_prefetch_factor,
        pin_memory=device.type == "cuda",
        use_length_bucketing=finetune_config.use_length_bucketing,
        bucket_size_multiplier=finetune_config.bucket_size_multiplier,
    )
    val_loader = _build_dataloader(
        dataset=val_dataset,
        batch_size=finetune_config.eval_batch_size,
        shuffle=False,
        collate_fn=collate_fn,
        num_workers=finetune_config.dataloader_num_workers,
        prefetch_factor=finetune_config.dataloader_prefetch_factor,
        pin_memory=device.type == "cuda",
        use_length_bucketing=finetune_config.use_length_bucketing,
        bucket_size_multiplier=finetune_config.bucket_size_multiplier,
    )

    model = _build_model(
        model_name=finetune_config.model_name,
        use_lora=finetune_config.use_lora,
        lora_r=finetune_config.lora_r,
        lora_alpha=finetune_config.lora_alpha,
        lora_dropout=finetune_config.lora_dropout,
        gradient_checkpointing=finetune_config.gradient_checkpointing,
    ).to(device)

    optimizer = AdamW(
        params=[parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=finetune_config.learning_rate,
        weight_decay=finetune_config.weight_decay,
    )
    steps_per_epoch = max(
        1,
        math.ceil(len(train_loader) / float(finetune_config.gradient_accumulation_steps)),
    )
    total_steps = steps_per_epoch * finetune_config.num_epochs
    warmup_steps = int(round(total_steps * finetune_config.warmup_ratio))
    scheduler = get_linear_schedule_with_warmup(
        optimizer=optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )
    scaler = torch.amp.GradScaler("cuda", enabled=precision.use_grad_scaler)

    best_qwk = float("-inf")
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    epochs_without_improvement = 0

    for epoch in range(1, finetune_config.num_epochs + 1):
        train_loss = _train_one_epoch(
            model=model,
            loader=train_loader,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=scaler,
            device=device,
            precision=precision,
            gradient_accumulation_steps=finetune_config.gradient_accumulation_steps,
            max_grad_norm=finetune_config.max_grad_norm,
        )
        _, val_y_true_epoch, val_y_pred_epoch = _predict_by_record(
            model=model,
            loader=val_loader,
            device=device,
            precision=precision,
        )
        val_eval_epoch = evaluate_predictions(
            val_y_true_epoch,
            val_y_pred_epoch,
            min_band=min_band,
            max_band=max_band,
        )
        logger.info(
            "fold=%d epoch=%d loss=%.5f val_qwk=%.5f val_mae=%.5f",
            fold_index,
            epoch,
            train_loss,
            val_eval_epoch.qwk,
            val_eval_epoch.mean_absolute_error,
        )
        if val_eval_epoch.qwk > best_qwk:
            best_qwk = float(val_eval_epoch.qwk)
            best_epoch = int(epoch)
            best_state = {
                key: value.detach().cpu().clone() for key, value in model.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= finetune_config.early_stopping_patience:
                logger.info(
                    "fold=%d early-stop at epoch=%d best_epoch=%d best_qwk=%.5f",
                    fold_index,
                    epoch,
                    best_epoch,
                    best_qwk,
                )
                break

    if best_state is None:
        raise ValueError("Best model state was not captured during fold training.")
    model.load_state_dict(best_state)

    train_record_ids, train_y_true, train_y_pred = _predict_by_record(
        model=model,
        loader=train_eval_loader,
        device=device,
        precision=precision,
    )
    val_record_ids, val_y_true, val_y_pred = _predict_by_record(
        model=model,
        loader=val_loader,
        device=device,
        precision=precision,
    )
    if not train_record_ids or not val_record_ids:
        raise ValueError("Fold produced empty train/val prediction sets.")

    train_eval = evaluate_predictions(
        train_y_true,
        train_y_pred,
        min_band=min_band,
        max_band=max_band,
    )
    val_eval = evaluate_predictions(
        val_y_true,
        val_y_pred,
        min_band=min_band,
        max_band=max_band,
    )
    fold_result: TransformerFoldResult = {
        "fold": int(fold_index),
        "sizes": {"train": len(train_essays), "val": len(val_essays)},
        "best_iteration": int(best_epoch),
        "train": _fold_eval_payload(train_eval),
        "val": _fold_eval_payload(val_eval),
    }
    return FoldTrainingOutcome(
        fold_result=fold_result,
        val_record_ids=val_record_ids,
        val_true=val_y_true,
        val_pred_raw=val_y_pred,
    )


def _build_model(
    *,
    model_name: str,
    use_lora: bool,
    lora_r: int,
    lora_alpha: int,
    lora_dropout: float,
    gradient_checkpointing: bool,
) -> torch.nn.Module:
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=1,
        problem_type="regression",
    )
    if gradient_checkpointing:
        model.gradient_checkpointing_enable()
    if not use_lora:
        return model
    try:
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError as exc:
        raise RuntimeError(
            "LoRA requires `peft`. Install with `pdm install -G ml-research` "
            "or run with --use-lora false."
        ) from exc

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
    )
    return get_peft_model(model, lora_config)


def _train_one_epoch(
    *,
    model: torch.nn.Module,
    loader: DataLoader[CollatedBatch],
    optimizer: AdamW,
    scheduler: torch.optim.lr_scheduler.LRScheduler,
    scaler: torch.amp.GradScaler,
    device: torch.device,
    precision: PrecisionRuntime,
    gradient_accumulation_steps: int,
    max_grad_norm: float,
) -> float:
    model.train()
    optimizer.zero_grad(set_to_none=True)
    total_loss = 0.0
    n_batches = 0
    for step, batch in enumerate(loader, start=1):
        input_ids = batch.input_ids.to(device)
        attention_mask = batch.attention_mask.to(device)
        labels = batch.labels.to(device)
        with torch.amp.autocast(
            device_type=device.type,
            dtype=precision.dtype,
            enabled=precision.enabled,
        ):
            output = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
            )
            if output.loss is None:
                raise ValueError("Model did not return a loss tensor.")
            loss = output.loss
            loss_step = loss / float(gradient_accumulation_steps)

        if precision.use_grad_scaler:
            scaler.scale(loss_step).backward()
        else:
            loss_step.backward()

        should_step = step % gradient_accumulation_steps == 0 or step == len(loader)
        if should_step:
            if max_grad_norm > 0.0:
                if precision.use_grad_scaler:
                    scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            if precision.use_grad_scaler:
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
        total_loss += float(loss.detach().cpu())
        n_batches += 1
    if n_batches == 0:
        raise ValueError("Training loader produced zero batches.")
    return total_loss / float(n_batches)


@torch.no_grad()
def _predict_by_record(
    *,
    model: torch.nn.Module,
    loader: DataLoader[CollatedBatch],
    device: torch.device,
    precision: PrecisionRuntime,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    model.eval()
    preds_by_record: dict[str, list[float]] = {}
    label_by_record: dict[str, float] = {}
    for batch in loader:
        input_ids = batch.input_ids.to(device)
        attention_mask = batch.attention_mask.to(device)
        with torch.amp.autocast(
            device_type=device.type,
            dtype=precision.dtype,
            enabled=precision.enabled,
        ):
            output = model(input_ids=input_ids, attention_mask=attention_mask)
        logits = output.logits.squeeze(-1).detach().cpu().to(torch.float32).numpy()
        labels = batch.labels.detach().cpu().to(torch.float32).numpy()
        for index, record_id in enumerate(batch.record_ids):
            preds_by_record.setdefault(record_id, []).append(float(logits[index]))
            if record_id not in label_by_record:
                label_by_record[record_id] = float(labels[index])
    ordered_record_ids = sorted(preds_by_record.keys())
    y_true = np.array([label_by_record[record_id] for record_id in ordered_record_ids], dtype=float)
    y_pred = np.array(
        [float(statistics.fmean(preds_by_record[record_id])) for record_id in ordered_record_ids],
        dtype=float,
    )
    return ordered_record_ids, y_true, y_pred


def _fold_eval_payload(result: EvaluationResult) -> FoldEval:
    return {
        "qwk": float(result.qwk),
        "adjacent_accuracy": float(result.adjacent_accuracy),
        "mean_absolute_error": float(result.mean_absolute_error),
    }


def _flatten_chunk_samples(essays: list[ChunkedEssay]) -> list[ChunkSample]:
    samples: list[ChunkSample] = []
    for essay in essays:
        for chunk_ids in essay.chunk_input_ids:
            samples.append(
                ChunkSample(
                    record_id=essay.record_id,
                    label=essay.label,
                    input_ids=chunk_ids,
                    attention_mask=[1] * len(chunk_ids),
                )
            )
    return samples


def _build_collate_fn(
    tokenizer: PreTrainedTokenizerBase,
) -> Callable[[list[ChunkSample]], CollatedBatch]:
    def collate(samples: list[ChunkSample]) -> CollatedBatch:
        encoded = tokenizer.pad(
            {
                "input_ids": [sample.input_ids for sample in samples],
                "attention_mask": [sample.attention_mask for sample in samples],
            },
            padding=True,
            return_tensors="pt",
        )
        labels = torch.tensor([sample.label for sample in samples], dtype=torch.float32)
        record_ids = [sample.record_id for sample in samples]
        return CollatedBatch(
            input_ids=encoded["input_ids"],
            attention_mask=encoded["attention_mask"],
            labels=labels,
            record_ids=record_ids,
        )

    return collate


def _build_dataloader(
    *,
    dataset: ChunkDataset,
    batch_size: int,
    shuffle: bool,
    collate_fn,
    num_workers: int,
    prefetch_factor: int,
    pin_memory: bool,
    use_length_bucketing: bool,
    bucket_size_multiplier: int,
) -> DataLoader[CollatedBatch]:
    if use_length_bucketing:
        bucket_batches = _build_bucketed_batch_indices(
            sample_lengths=dataset.sample_lengths(),
            batch_size=batch_size,
            shuffle=shuffle,
            bucket_size_multiplier=bucket_size_multiplier,
        )
        batch_sampler = BucketBatchSampler(bucket_batches)
        if num_workers > 0:
            return DataLoader(
                dataset,
                batch_sampler=batch_sampler,
                num_workers=num_workers,
                persistent_workers=True,
                prefetch_factor=prefetch_factor,
                pin_memory=pin_memory,
                collate_fn=collate_fn,
            )
        return DataLoader(
            dataset,
            batch_sampler=batch_sampler,
            num_workers=0,
            pin_memory=pin_memory,
            collate_fn=collate_fn,
        )

    if num_workers > 0:
        return DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=num_workers,
            persistent_workers=True,
            prefetch_factor=prefetch_factor,
            pin_memory=pin_memory,
            collate_fn=collate_fn,
        )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=0,
        pin_memory=pin_memory,
        collate_fn=collate_fn,
    )


def _build_bucketed_batch_indices(
    *,
    sample_lengths: list[int],
    batch_size: int,
    shuffle: bool,
    bucket_size_multiplier: int,
) -> list[list[int]]:
    """Construct length-aware batches to reduce padding overhead."""

    if batch_size <= 0:
        raise ValueError("batch_size must be > 0 for length bucketing.")
    if bucket_size_multiplier <= 0:
        raise ValueError("bucket_size_multiplier must be > 0 for length bucketing.")
    if not sample_lengths:
        return []

    indices = list(range(len(sample_lengths)))
    if shuffle:
        random.shuffle(indices)

    bucket_size = max(batch_size, batch_size * bucket_size_multiplier)
    batches: list[list[int]] = []
    for bucket_start in range(0, len(indices), bucket_size):
        bucket = indices[bucket_start : bucket_start + bucket_size]
        bucket.sort(key=lambda index: sample_lengths[index], reverse=True)
        for batch_start in range(0, len(bucket), batch_size):
            batch = bucket[batch_start : batch_start + batch_size]
            if batch:
                batches.append(batch)
    if shuffle:
        random.shuffle(batches)
    return batches


def _chunk_records(
    *,
    records: list[EssayRecord],
    tokenizer: PreTrainedTokenizerBase,
    max_length: int,
    chunk_overlap_tokens: int,
) -> dict[str, ChunkedEssay]:
    max_content_tokens = max_length - 2
    if max_content_tokens <= 0:
        raise ValueError("max_length must be >= 3 to reserve special tokens.")
    chunked: dict[str, ChunkedEssay] = {}
    for record in records:
        token_ids = tokenizer.encode(
            record.essay,
            add_special_tokens=False,
            truncation=False,
        )
        spans = build_chunk_spans(
            token_count=len(token_ids),
            max_content_tokens=max_content_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
        )
        chunks: list[list[int]] = []
        for start, end in spans:
            content = token_ids[start:end]
            chunks.append(_with_chunk_special_tokens(tokenizer=tokenizer, content=content))
        chunked[record.record_id] = ChunkedEssay(
            record_id=record.record_id,
            prompt=record.question,
            label=float(record.overall),
            token_count=len(token_ids),
            chunk_input_ids=chunks,
        )
    return chunked


def _with_chunk_special_tokens(
    *, tokenizer: PreTrainedTokenizerBase, content: list[int]
) -> list[int]:
    cls_token_id = tokenizer.cls_token_id
    sep_token_id = tokenizer.sep_token_id
    if cls_token_id is not None and sep_token_id is not None:
        return [int(cls_token_id), *content, int(sep_token_id)]

    bos_token_id = tokenizer.bos_token_id
    eos_token_id = tokenizer.eos_token_id
    if bos_token_id is not None and eos_token_id is not None:
        return [int(bos_token_id), *content, int(eos_token_id)]

    raise ValueError(
        "Tokenizer must provide cls/sep or bos/eos special token IDs for chunk construction."
    )


def _build_summary_payload(
    *,
    fold_results: list[TransformerFoldResult],
    elapsed_s: float,
) -> TransformerCvSummary:
    val_qwk = [float(fold["val"]["qwk"]) for fold in fold_results]
    val_mae = [float(fold["val"]["mean_absolute_error"]) for fold in fold_results]
    val_adjacent = [float(fold["val"]["adjacent_accuracy"]) for fold in fold_results]
    return {
        "val_qwk_mean": float(statistics.fmean(val_qwk)),
        "val_qwk_std": float(statistics.pstdev(val_qwk)) if len(val_qwk) > 1 else 0.0,
        "val_mae_mean": float(statistics.fmean(val_mae)),
        "val_mae_std": float(statistics.pstdev(val_mae)) if len(val_mae) > 1 else 0.0,
        "val_adjacent_accuracy_mean": float(statistics.fmean(val_adjacent)),
        "val_adjacent_accuracy_std": (
            float(statistics.pstdev(val_adjacent)) if len(val_adjacent) > 1 else 0.0
        ),
        "elapsed_s": float(elapsed_s),
    }


def _build_cv_report_markdown(*, metrics_payload: TransformerCvMetricsPayload) -> str:
    summary = metrics_payload["summary"]
    rows = [
        "| fold | train_n | val_n | val_qwk | val_mae | best_epoch |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for fold in metrics_payload["folds"]:
        rows.append(
            (
                f"| {fold['fold']} | {fold['sizes']['train']} | {fold['sizes']['val']} | "
                f"{fold['val']['qwk']:.4f} | {fold['val']['mean_absolute_error']:.4f} | "
                f"{fold['best_iteration']} |"
            )
        )
    return "\n".join(
        [
            "# Transformer CV Report",
            "",
            "## Summary",
            "",
            f"- dataset_kind: `{metrics_payload['dataset_kind']}`",
            f"- model_family: `{metrics_payload['model_family']}`",
            f"- model_name: `{metrics_payload['model_name']}`",
            f"- use_lora: `{metrics_payload['use_lora']}`",
            f"- mixed_precision: `{metrics_payload['mixed_precision']}`",
            f"- scheme: `{metrics_payload['scheme']}`",
            f"- n_splits: `{metrics_payload['n_splits']}`",
            f"- word_count_window: `{metrics_payload['word_count_window']}`",
            f"- record_counts: `{metrics_payload['record_counts']}`",
            "",
            "## CV Metrics (val)",
            "",
            f"- qwk_mean±std: `{summary['val_qwk_mean']:.4f}` ± `{summary['val_qwk_std']:.4f}`",
            f"- mae_mean±std: `{summary['val_mae_mean']:.4f}` ± `{summary['val_mae_std']:.4f}`",
            (
                "- adjacent_acc_mean±std: "
                f"`{summary['val_adjacent_accuracy_mean']:.4f}` ± "
                f"`{summary['val_adjacent_accuracy_std']:.4f}`"
            ),
            f"- elapsed_s: `{summary['elapsed_s']:.1f}`",
            "",
            "## Folds",
            "",
            *rows,
            "",
        ]
    )


def _resolve_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _resolve_precision_runtime(
    *,
    mode: MixedPrecisionMode,
    device: torch.device,
) -> PrecisionRuntime:
    if device.type != "cuda":
        return PrecisionRuntime(enabled=False, dtype=None, use_grad_scaler=False, label="none")

    is_rocm_runtime = getattr(torch.version, "hip", None) is not None
    fp16_use_grad_scaler = not is_rocm_runtime

    if mode == MixedPrecisionMode.NONE:
        return PrecisionRuntime(enabled=False, dtype=None, use_grad_scaler=False, label="none")

    if mode == MixedPrecisionMode.BF16:
        if torch.cuda.is_bf16_supported():
            return PrecisionRuntime(
                enabled=True,
                dtype=torch.bfloat16,
                use_grad_scaler=False,
                label="bf16",
            )
        logger.warning("bf16 requested but unsupported; falling back to fp16.")
        return PrecisionRuntime(
            enabled=True,
            dtype=torch.float16,
            use_grad_scaler=fp16_use_grad_scaler,
            label="fp16",
        )

    if mode == MixedPrecisionMode.FP16:
        return PrecisionRuntime(
            enabled=True,
            dtype=torch.float16,
            use_grad_scaler=fp16_use_grad_scaler,
            label="fp16",
        )

    if torch.cuda.is_bf16_supported():
        if is_rocm_runtime:
            logger.warning(
                "auto mixed precision on ROCm resolves to fp16 without grad scaling due observed "
                "bf16/scaler instability."
            )
            return PrecisionRuntime(
                enabled=True,
                dtype=torch.float16,
                use_grad_scaler=fp16_use_grad_scaler,
                label="fp16",
            )
        return PrecisionRuntime(
            enabled=True,
            dtype=torch.bfloat16,
            use_grad_scaler=False,
            label="bf16",
        )
    return PrecisionRuntime(
        enabled=True,
        dtype=torch.float16,
        use_grad_scaler=fp16_use_grad_scaler,
        label="fp16",
    )


def _enforce_gpu_requirement(*, device: torch.device, require_gpu: bool) -> None:
    """Fail fast when a research run requires GPU but runtime resolved to CPU/MPS."""

    if require_gpu and device.type != "cuda":
        raise RuntimeError(
            "GPU is required for this transformer fine-tuning run, but runtime resolved "
            f"to '{device.type}'."
        )


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _validate_finetune_config(config: TransformerFinetuneConfig) -> None:
    if config.max_length < 8:
        raise ValueError("max_length must be >= 8.")
    if config.chunk_overlap_tokens < 0:
        raise ValueError("chunk_overlap_tokens must be >= 0.")
    if config.chunk_overlap_tokens >= config.max_length - 2:
        raise ValueError("chunk_overlap_tokens must be less than max_length - 2.")
    if config.train_batch_size < 1 or config.eval_batch_size < 1:
        raise ValueError("Batch sizes must be >= 1.")
    if config.gradient_accumulation_steps < 1:
        raise ValueError("gradient_accumulation_steps must be >= 1.")
    if config.num_epochs < 1:
        raise ValueError("num_epochs must be >= 1.")
    if not (0.0 <= config.warmup_ratio <= 0.5):
        raise ValueError("warmup_ratio must be between 0.0 and 0.5.")
    if config.early_stopping_patience < 1:
        raise ValueError("early_stopping_patience must be >= 1.")
    if config.dataloader_num_workers < 0:
        raise ValueError("dataloader_num_workers must be >= 0.")
    if config.dataloader_prefetch_factor < 1:
        raise ValueError("dataloader_prefetch_factor must be >= 1.")
    if config.bucket_size_multiplier < 1:
        raise ValueError("bucket_size_multiplier must be >= 1.")
