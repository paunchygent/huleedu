"""Validate transformer fine-tuning helper behavior.

Purpose:
    Cover deterministic helper logic in transformer fine-tuning so regressions
    are caught without downloading models or running GPU training loops.

Relationships:
    - Targets `scripts.ml_training.essay_scoring.transformer_finetune`.
    - Complements integration-style CV research tests by validating local
      chunking, telemetry, precision selection, and config guards.
"""

from __future__ import annotations

import pytest
import torch

from scripts.ml_training.essay_scoring.transformer_finetune import (
    ChunkedEssay,
    MixedPrecisionMode,
    TransformerFinetuneConfig,
    _resolve_precision_runtime,
    _validate_finetune_config,
    build_chunk_spans,
    compute_truncation_coverage,
)


def _base_finetune_config() -> TransformerFinetuneConfig:
    return TransformerFinetuneConfig(
        model_name="distilbert-base-uncased",
        max_length=128,
        chunk_overlap_tokens=32,
        train_batch_size=8,
        eval_batch_size=16,
        gradient_accumulation_steps=2,
        learning_rate=2e-5,
        weight_decay=0.01,
        num_epochs=3,
        warmup_ratio=0.1,
        early_stopping_patience=2,
        max_grad_norm=1.0,
        mixed_precision=MixedPrecisionMode.AUTO,
        gradient_checkpointing=True,
        use_lora=False,
        lora_r=8,
        lora_alpha=16,
        lora_dropout=0.1,
        random_seed=42,
        dataloader_num_workers=0,
        dataloader_prefetch_factor=2,
    )


def test_build_chunk_spans_handles_empty_and_short_essays() -> None:
    assert build_chunk_spans(token_count=0, max_content_tokens=10, chunk_overlap_tokens=2) == [
        (0, 0)
    ]
    assert build_chunk_spans(token_count=7, max_content_tokens=10, chunk_overlap_tokens=2) == [
        (0, 7)
    ]


def test_build_chunk_spans_generates_overlap_windows_without_gaps() -> None:
    spans = build_chunk_spans(token_count=12, max_content_tokens=5, chunk_overlap_tokens=2)
    assert spans == [(0, 5), (3, 8), (6, 11), (9, 12)]


def test_compute_truncation_coverage_reports_expected_fields() -> None:
    essays = [
        ChunkedEssay(
            record_id="a",
            prompt="p1",
            label=3.0,
            token_count=14,
            chunk_input_ids=[[1, 2, 3], [1, 2, 3]],
        ),
        ChunkedEssay(
            record_id="b",
            prompt="p2",
            label=4.0,
            token_count=6,
            chunk_input_ids=[[1, 2, 3]],
        ),
    ]
    coverage = compute_truncation_coverage(
        essays=essays,
        max_length=10,
        chunk_overlap_tokens=2,
    )

    assert coverage["pct_essays_exceeding_max_length"] == pytest.approx(50.0)
    assert coverage["avg_tokens_truncated_before_chunking"] == pytest.approx(3.0)
    assert coverage["avg_chunks_per_essay"] == pytest.approx(1.5)
    assert coverage["p95_chunks_per_essay"] == pytest.approx(1.95)
    assert coverage["max_length"] == 10
    assert coverage["chunk_overlap_tokens"] == 2


def test_validate_finetune_config_accepts_valid_defaults() -> None:
    _validate_finetune_config(_base_finetune_config())


@pytest.mark.parametrize(
    ("field_name", "bad_value", "error_pattern"),
    [
        ("max_length", 7, "max_length must be"),
        ("chunk_overlap_tokens", -1, "chunk_overlap_tokens must be"),
        ("warmup_ratio", 0.6, "warmup_ratio must be"),
        ("dataloader_num_workers", -1, "dataloader_num_workers must be"),
        ("dataloader_prefetch_factor", 0, "dataloader_prefetch_factor must be"),
    ],
)
def test_validate_finetune_config_rejects_invalid_values(
    field_name: str,
    bad_value: int | float,
    error_pattern: str,
) -> None:
    config = _base_finetune_config()
    config_dict = config.__dict__.copy()
    config_dict[field_name] = bad_value
    invalid = TransformerFinetuneConfig(**config_dict)

    with pytest.raises(ValueError, match=error_pattern):
        _validate_finetune_config(invalid)


def test_resolve_precision_runtime_returns_none_for_non_cuda_device() -> None:
    runtime = _resolve_precision_runtime(
        mode=MixedPrecisionMode.AUTO,
        device=torch.device("cpu"),
    )
    assert runtime.enabled is False
    assert runtime.dtype is None
    assert runtime.use_grad_scaler is False
    assert runtime.label == "none"


def test_resolve_precision_runtime_prefers_bf16_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_bf16_supported", lambda: True)
    runtime = _resolve_precision_runtime(
        mode=MixedPrecisionMode.AUTO,
        device=torch.device("cuda"),
    )

    assert runtime.enabled is True
    assert runtime.dtype == torch.bfloat16
    assert runtime.use_grad_scaler is False
    assert runtime.label == "bf16"


def test_resolve_precision_runtime_falls_back_to_fp16_when_bf16_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_bf16_supported", lambda: False)
    runtime = _resolve_precision_runtime(
        mode=MixedPrecisionMode.BF16,
        device=torch.device("cuda"),
    )

    assert runtime.enabled is True
    assert runtime.dtype == torch.float16
    assert runtime.use_grad_scaler is True
    assert runtime.label == "fp16"
