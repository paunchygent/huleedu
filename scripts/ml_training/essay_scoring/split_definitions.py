"""Reusable split definitions for gold-standard evaluation."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sklearn.model_selection import StratifiedGroupKFold

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig
from scripts.ml_training.essay_scoring.dataset import (
    EssayRecord,
    load_ellipse_train_test_dataset,
)
from scripts.ml_training.essay_scoring.environment import gather_git_sha, repo_root_from_package
from scripts.ml_training.essay_scoring.logging_utils import run_file_logger
from scripts.ml_training.essay_scoring.paths import RunPaths, build_run_paths
from scripts.ml_training.essay_scoring.text_processing import (
    count_words,
    normalize_text_for_hashing,
    sha256_text,
)

logger = logging.getLogger(__name__)

_SPLIT_SCHEMA_VERSION = 1


class FoldDefinition(BaseModel):
    """One fold split definition."""

    model_config = ConfigDict(extra="forbid")

    fold: int = Field(ge=0)
    train_record_ids: list[str]
    val_record_ids: list[str]
    val_groups: list[str] = Field(default_factory=list)


class SplitDefinitions(BaseModel):
    """Persisted CV split definitions."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=_SPLIT_SCHEMA_VERSION, ge=1)
    created_at: str
    git_sha: str

    dataset_kind: DatasetKind
    dataset_sources: dict[str, str]
    dataset_sha256: dict[str, str]
    dataset_excluded_prompts: list[str] = Field(default_factory=list)
    word_count_window: dict[str, int]

    record_counts: dict[str, int]
    label_counts_train: dict[str, int]

    n_splits: int = Field(ge=2, le=20)
    test_record_ids: list[str]

    stratified_text_folds: list[FoldDefinition]
    prompt_holdout_folds: list[FoldDefinition]


@dataclass(frozen=True)
class SplitDefinitionsSummary:
    run_paths: RunPaths
    splits_path: Path
    report_path: Path


def generate_splits(
    config: ExperimentConfig,
    *,
    min_words: int,
    max_words: int,
    n_splits: int,
) -> SplitDefinitionsSummary:
    """Generate reusable CV splits for ELLIPSE.

    - StratifiedGroupKFold by Overall with grouping on `text_sha256` (leakage guard)
    - Prompt-holdout folds using grouping on `prompt` (unseen prompt evaluation)
    """

    if config.dataset_kind != DatasetKind.ELLIPSE:
        raise ValueError("make-splits currently supports only --dataset-kind=ellipse")
    if min_words < 0 or max_words < 0 or min_words > max_words:
        raise ValueError("Invalid word-count window: min_words must be <= max_words and >= 0.")

    run_paths = build_run_paths(config.output)
    splits_path = run_paths.artifacts_dir / "splits.json"
    report_path = run_paths.reports_dir / "splits_report.md"

    with run_file_logger(run_paths.log_path):
        excluded_prompts = set(config.ellipse_excluded_prompts)
        dataset = load_ellipse_train_test_dataset(
            config.ellipse_train_path,
            config.ellipse_test_path,
            excluded_prompts=excluded_prompts,
        )

        train_records = _filter_by_word_count(
            dataset.train_records, min_words=min_words, max_words=max_words
        )
        test_records = _filter_by_word_count(
            dataset.test_records, min_words=min_words, max_words=max_words
        )
        _raise_on_overlap(train_records=train_records, test_records=test_records)

        train_labels = np.array([record.overall for record in train_records], dtype=float)
        label_counts = _label_counts(train_labels)
        min_label_count = min(label_counts.values()) if label_counts else 0
        if min_label_count < n_splits:
            raise ValueError(
                "Not enough samples per label for the requested n_splits. "
                f"min_label_count={min_label_count} n_splits={n_splits}."
            )

        text_groups = [
            sha256_text(normalize_text_for_hashing(record.essay)) for record in train_records
        ]
        stratified_text_folds = _build_folds(
            records=train_records,
            labels=train_labels,
            groups=text_groups,
            n_splits=n_splits,
            random_seed=config.training.random_seed,
        )

        prompt_groups = [record.question for record in train_records]
        prompt_holdout_folds = _build_folds(
            records=train_records,
            labels=train_labels,
            groups=prompt_groups,
            n_splits=n_splits,
            random_seed=config.training.random_seed,
            include_val_groups=True,
        )

        repo_root = repo_root_from_package()
        manifest = SplitDefinitions(
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            git_sha=gather_git_sha(repo_root),
            dataset_kind=config.dataset_kind,
            dataset_sources={
                "ellipse_train": str(config.ellipse_train_path),
                "ellipse_test": str(config.ellipse_test_path),
            },
            dataset_sha256={
                "ellipse_train": _sha256_file(config.ellipse_train_path),
                "ellipse_test": _sha256_file(config.ellipse_test_path),
            },
            dataset_excluded_prompts=sorted(excluded_prompts),
            word_count_window={"min": int(min_words), "max": int(max_words)},
            record_counts={"train": len(train_records), "test": len(test_records)},
            label_counts_train={str(k): int(v) for k, v in label_counts.items()},
            n_splits=n_splits,
            test_record_ids=[record.record_id for record in test_records],
            stratified_text_folds=stratified_text_folds,
            prompt_holdout_folds=prompt_holdout_folds,
        )
        splits_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        report_md = _build_splits_report(manifest, train_records=train_records)
        report_path.write_text(report_md, encoding="utf-8")

        logger.info("Splits written: %s", splits_path)

    return SplitDefinitionsSummary(
        run_paths=run_paths, splits_path=splits_path, report_path=report_path
    )


def load_splits(path: Path) -> SplitDefinitions:
    if not path.exists():
        raise FileNotFoundError(f"Split definitions not found at {path}")
    return SplitDefinitions.model_validate_json(path.read_text(encoding="utf-8"))


def _filter_by_word_count(
    records: list[EssayRecord], *, min_words: int, max_words: int
) -> list[EssayRecord]:
    filtered = []
    for record in records:
        wc = count_words(record.essay)
        if min_words <= wc <= max_words:
            filtered.append(record)
    return filtered


def _raise_on_overlap(*, train_records: list[EssayRecord], test_records: list[EssayRecord]) -> None:
    train_hashes = {
        sha256_text(normalize_text_for_hashing(record.essay)) for record in train_records
    }
    overlap = [
        record.record_id
        for record in test_records
        if sha256_text(normalize_text_for_hashing(record.essay)) in train_hashes
    ]
    if overlap:
        raise ValueError(
            "Train/test leakage detected after filtering: "
            f"{len(overlap)} test records share identical essay text with train."
        )


def _build_folds(
    *,
    records: list[EssayRecord],
    labels: np.ndarray,
    groups: list[str],
    n_splits: int,
    random_seed: int,
    include_val_groups: bool = False,
) -> list[FoldDefinition]:
    splitter = StratifiedGroupKFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=random_seed,
    )
    x_dummy = np.zeros((len(records), 1), dtype=float)
    labels_for_split = _labels_for_stratification(labels)

    folds: list[FoldDefinition] = []
    for fold_index, (train_idx, val_idx) in enumerate(
        splitter.split(x_dummy, labels_for_split, groups)
    ):
        train_ids = [records[i].record_id for i in train_idx]
        val_ids = [records[i].record_id for i in val_idx]
        val_groups: list[str] = []
        if include_val_groups:
            val_groups = sorted({groups[i] for i in val_idx})
        folds.append(
            FoldDefinition(
                fold=fold_index,
                train_record_ids=train_ids,
                val_record_ids=val_ids,
                val_groups=val_groups,
            )
        )
    return folds


def _label_counts(labels: np.ndarray) -> dict[float, int]:
    unique, counts = np.unique(labels, return_counts=True)
    return {float(k): int(v) for k, v in zip(unique.tolist(), counts.tolist(), strict=True)}


def _labels_for_stratification(labels: np.ndarray) -> np.ndarray:
    """Convert regression labels into stable stratification classes.

    `StratifiedGroupKFold` requires classification targets. Our label scales are
    half-step bands (e.g. 1.0, 1.5, 2.0...), so we bucket by the nearest 0.5.
    """

    half_steps = np.round(labels * 2.0).astype(int)
    return half_steps.astype(str)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _build_splits_report(manifest: SplitDefinitions, *, train_records: list[EssayRecord]) -> str:
    min_words = manifest.word_count_window.get("min")
    max_words = manifest.word_count_window.get("max")
    lines = [
        "# Split Definitions Report",
        "",
        "## Summary",
        "",
        f"- dataset_kind: `{manifest.dataset_kind.value}`",
        f"- word_count_window: `{min_words}`–`{max_words}`",
        f"- n_splits: `{manifest.n_splits}`",
        f"- train_records: `{manifest.record_counts.get('train')}`",
        f"- test_records: `{manifest.record_counts.get('test')}`",
        "",
        "## Train Label Counts (Overall)",
        "",
        _markdown_kv_table(manifest.label_counts_train),
        "",
        "## Folds",
        "",
        _fold_table(manifest),
        "",
    ]
    prompt_coverage = len({record.question for record in train_records})
    lines.extend(
        [
            "## Prompt Coverage (train)",
            "",
            f"- unique_prompts: `{prompt_coverage}`",
            "",
        ]
    )
    return "\n".join(lines)


def _fold_table(manifest: SplitDefinitions) -> str:
    rows: list[tuple[str, ...]] = [("scheme", "fold", "train", "val", "val_groups")]

    for fold in manifest.stratified_text_folds:
        rows.append(
            (
                "stratified_text",
                str(fold.fold),
                str(len(fold.train_record_ids)),
                str(len(fold.val_record_ids)),
                str(len(fold.val_groups)),
            )
        )

    for fold in manifest.prompt_holdout_folds:
        rows.append(
            (
                "prompt_holdout",
                str(fold.fold),
                str(len(fold.train_record_ids)),
                str(len(fold.val_record_ids)),
                str(len(fold.val_groups)),
            )
        )

    return _markdown_table(rows)


def _markdown_kv_table(values: dict[str, int]) -> str:
    rows: list[tuple[str, ...]] = [("key", "value")]
    for key, value in values.items():
        rows.append((key, str(value)))
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
