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

from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.transformer_finetune import (
    ChunkedEssay,
    MixedPrecisionMode,
    TransformerFinetuneConfig,
    _build_bucketed_batch_indices,
    _chunk_records,
    _enforce_gpu_requirement,
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


def test_build_bucketed_batch_indices_keeps_similar_lengths_together() -> None:
    batches = _build_bucketed_batch_indices(
        sample_lengths=[10, 2, 9, 3, 8, 4],
        batch_size=2,
        shuffle=False,
        bucket_size_multiplier=3,
    )

    assert batches == [[0, 2], [4, 5], [3, 1]]


def test_build_bucketed_batch_indices_rejects_invalid_settings() -> None:
    with pytest.raises(ValueError, match="batch_size must be > 0"):
        _build_bucketed_batch_indices(
            sample_lengths=[1, 2, 3],
            batch_size=0,
            shuffle=False,
            bucket_size_multiplier=2,
        )
    with pytest.raises(ValueError, match="bucket_size_multiplier must be > 0"):
        _build_bucketed_batch_indices(
            sample_lengths=[1, 2, 3],
            batch_size=2,
            shuffle=False,
            bucket_size_multiplier=0,
        )


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


class _TokenizerWithoutBuildInputs:
    """Minimal tokenizer stub exposing only methods used by `_chunk_records`."""

    def __init__(self) -> None:
        self.cls_token_id = 101
        self.sep_token_id = 102
        self.bos_token_id = None
        self.eos_token_id = None

    def encode(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        truncation: bool,
    ) -> list[int]:
        assert add_special_tokens is False
        assert truncation is False
        return [ord(char) % 50 + 10 for char in text]


def test_chunk_records_uses_tokenizer_special_ids_for_chunk_boundaries() -> None:
    record = EssayRecord(
        record_id="r1",
        task_type="task2",
        question="prompt-a",
        essay="abcdefghij",
        overall=5.0,
        component_scores={},
    )
    tokenizer = _TokenizerWithoutBuildInputs()
    chunked = _chunk_records(
        records=[record],
        tokenizer=tokenizer,
        max_length=6,
        chunk_overlap_tokens=1,
    )

    essay = chunked["r1"]
    assert essay.token_count == 10
    assert len(essay.chunk_input_ids) > 1
    assert all(chunk[0] == 101 and chunk[-1] == 102 for chunk in essay.chunk_input_ids)


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
        ("bucket_size_multiplier", 0, "bucket_size_multiplier must be"),
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
    monkeypatch.setattr(torch.version, "hip", None, raising=False)
    runtime = _resolve_precision_runtime(
        mode=MixedPrecisionMode.AUTO,
        device=torch.device("cuda"),
    )

    assert runtime.enabled is True
    assert runtime.dtype == torch.bfloat16
    assert runtime.use_grad_scaler is False
    assert runtime.label == "bf16"


def test_resolve_precision_runtime_auto_disables_amp_on_rocm_when_bf16_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_bf16_supported", lambda: True)
    monkeypatch.setattr(torch.version, "hip", "7.2.0", raising=False)
    runtime = _resolve_precision_runtime(
        mode=MixedPrecisionMode.AUTO,
        device=torch.device("cuda"),
    )

    assert runtime.enabled is False
    assert runtime.dtype is None
    assert runtime.use_grad_scaler is False
    assert runtime.label == "none"


def test_resolve_precision_runtime_falls_back_to_fp16_when_bf16_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.cuda, "is_bf16_supported", lambda: False)
    monkeypatch.setattr(torch.version, "hip", None, raising=False)
    runtime = _resolve_precision_runtime(
        mode=MixedPrecisionMode.BF16,
        device=torch.device("cuda"),
    )

    assert runtime.enabled is True
    assert runtime.dtype == torch.float16
    assert runtime.use_grad_scaler is True
    assert runtime.label == "fp16"


def test_resolve_precision_runtime_fp16_mode_keeps_scaler_on_rocm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(torch.version, "hip", "7.2.0", raising=False)
    runtime = _resolve_precision_runtime(
        mode=MixedPrecisionMode.FP16,
        device=torch.device("cuda"),
    )

    assert runtime.enabled is True
    assert runtime.dtype == torch.float16
    assert runtime.use_grad_scaler is True
    assert runtime.label == "fp16"


def test_enforce_gpu_requirement_raises_on_non_cuda_device() -> None:
    with pytest.raises(RuntimeError, match="GPU is required"):
        _enforce_gpu_requirement(device=torch.device("cpu"), require_gpu=True)


def test_enforce_gpu_requirement_allows_optional_gpu() -> None:
    _enforce_gpu_requirement(device=torch.device("cpu"), require_gpu=False)
