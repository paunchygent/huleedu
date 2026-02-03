"""Dataset preparation utilities for the essay scoring research pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig
from scripts.ml_training.essay_scoring.dataset import ELLIPSE_REQUIRED_COLUMNS
from scripts.ml_training.essay_scoring.environment import gather_git_sha, repo_root_from_package
from scripts.ml_training.essay_scoring.logging_utils import run_file_logger
from scripts.ml_training.essay_scoring.paths import RunPaths, build_run_paths
from scripts.ml_training.essay_scoring.text_processing import (
    count_words,
    normalize_text_for_hashing,
    sha256_text,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedDatasetSummary:
    """Summary of a completed dataset preparation run."""

    run_paths: RunPaths
    prepared_train_path: Path
    prepared_test_path: Path
    metadata_path: Path
    report_path: Path


def prepare_dataset(
    config: ExperimentConfig,
    *,
    min_words: int,
    max_words: int,
) -> PreparedDatasetSummary:
    """Prepare a dataset for stable experimentation.

    For ELLIPSE this:
    - Applies prompt exclusions (e.g. letter-dominated prompts)
    - Applies a word-count window filter (inclusive)
    - Adds `word_count` and `text_sha256` columns
    - Validates train/test have no identical-text overlap (by `text_sha256`)
    - Writes prepared CSVs + metadata + integrity report under a run directory
    """

    if config.dataset_kind != DatasetKind.ELLIPSE:
        raise ValueError("prepare-dataset currently supports only --dataset-kind=ellipse")
    if min_words < 0 or max_words < 0 or min_words > max_words:
        raise ValueError("Invalid word-count window: min_words must be <= max_words and >= 0.")

    run_paths = build_run_paths(config.output)
    datasets_dir = run_paths.artifacts_dir / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    prepared_train_path = datasets_dir / "ellipse_train_prepared.csv"
    prepared_test_path = datasets_dir / "ellipse_test_prepared.csv"
    metadata_path = datasets_dir / "prep_metadata.json"
    report_path = run_paths.reports_dir / "dataset_integrity_report.md"

    with run_file_logger(run_paths.log_path):
        excluded_prompts = set(config.ellipse_excluded_prompts)
        logger.info(
            "Preparing dataset kind=%s min_words=%d max_words=%d excluded_prompts=%d",
            config.dataset_kind.value,
            min_words,
            max_words,
            len(excluded_prompts),
        )

        train_frame_raw = _read_csv(config.ellipse_train_path)
        test_frame_raw = _read_csv(config.ellipse_test_path)

        _validate_columns(train_frame_raw, required=ELLIPSE_REQUIRED_COLUMNS, name="train")
        _validate_columns(test_frame_raw, required=ELLIPSE_REQUIRED_COLUMNS, name="test")

        train_frame_prepared, train_stats = _prepare_ellipse_frame(
            train_frame_raw,
            excluded_prompts=excluded_prompts,
            min_words=min_words,
            max_words=max_words,
        )
        test_frame_prepared, test_stats = _prepare_ellipse_frame(
            test_frame_raw,
            excluded_prompts=excluded_prompts,
            min_words=min_words,
            max_words=max_words,
        )

        train_hashes = set(train_frame_prepared["text_sha256"].astype(str))
        test_hashes = set(test_frame_prepared["text_sha256"].astype(str))
        overlap = sorted(train_hashes & test_hashes)
        if overlap:
            raise ValueError(
                "Prepared dataset leakage detected: "
                f"{len(overlap)} identical essays found across train/test (by text_sha256)."
            )

        train_frame_prepared.to_csv(prepared_train_path, index=False)
        test_frame_prepared.to_csv(prepared_test_path, index=False)

        repo_root = repo_root_from_package()
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "git_sha": gather_git_sha(repo_root),
            "dataset_kind": config.dataset_kind.value,
            "source_paths": {
                "ellipse_train": str(config.ellipse_train_path),
                "ellipse_test": str(config.ellipse_test_path),
            },
            "source_sha256": {
                "ellipse_train": _sha256_file(config.ellipse_train_path),
                "ellipse_test": _sha256_file(config.ellipse_test_path),
            },
            "excluded_prompts": sorted(excluded_prompts),
            "word_count_window": {"min": min_words, "max": max_words},
            "train_stats": train_stats,
            "test_stats": test_stats,
            "output_paths": {
                "prepared_train": str(prepared_train_path),
                "prepared_test": str(prepared_test_path),
            },
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        report_md = _build_integrity_report(
            metadata=metadata,
            train_frame=train_frame_prepared,
            test_frame=test_frame_prepared,
        )
        report_path.write_text(report_md, encoding="utf-8")
        logger.info("Prepared dataset written to %s", datasets_dir)

    return PreparedDatasetSummary(
        run_paths=run_paths,
        prepared_train_path=prepared_train_path,
        prepared_test_path=prepared_test_path,
        metadata_path=metadata_path,
        report_path=report_path,
    )


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _validate_columns(frame: pd.DataFrame, *, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"ELLIPSE {name} dataset missing required columns: {sorted(missing)}")


def _prepare_ellipse_frame(
    frame: pd.DataFrame,
    *,
    excluded_prompts: set[str],
    min_words: int,
    max_words: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw_rows = int(frame.shape[0])

    working = frame.copy()
    working = working[(working["full_text"].astype(str).str.strip() != "")]
    working = working[(working["prompt"].astype(str).str.strip() != "")]

    overall = pd.to_numeric(working["Overall"], errors="coerce")
    working = working[overall.notna()].copy()
    working["Overall"] = overall[overall.notna()].astype(float)

    rows_after_required = int(working.shape[0])

    if excluded_prompts:
        working = working[~working["prompt"].isin(excluded_prompts)].copy()
    rows_after_excluded = int(working.shape[0])

    texts = working["full_text"].astype(str).tolist()
    word_counts = [count_words(text) for text in texts]
    working["word_count"] = word_counts

    keep_mask = (working["word_count"] >= min_words) & (working["word_count"] <= max_words)
    working = working[keep_mask].copy()
    rows_after_word_filter = int(working.shape[0])

    normalized_texts = [
        normalize_text_for_hashing(text) for text in working["full_text"].astype(str)
    ]
    working["text_sha256"] = [sha256_text(text) for text in normalized_texts]

    label_counts = (
        working["Overall"].value_counts(dropna=False).sort_index().to_dict()
        if not working.empty
        else {}
    )
    prompt_counts = (
        working["prompt"].value_counts(dropna=False).head(25).to_dict() if not working.empty else {}
    )

    duplicate_groups = working["text_sha256"].value_counts()
    duplicate_hashes = duplicate_groups[duplicate_groups > 1]

    wc_stats = _word_count_stats(word_counts=working["word_count"].tolist())

    stats: dict[str, Any] = {
        "rows": {
            "raw": raw_rows,
            "after_required": rows_after_required,
            "after_excluded_prompts": rows_after_excluded,
            "after_word_count_filter": rows_after_word_filter,
        },
        "label_counts": {str(k): int(v) for k, v in label_counts.items()},
        "top_prompt_counts": {str(k): int(v) for k, v in prompt_counts.items()},
        "word_count_stats": wc_stats,
        "duplicate_text_groups": {
            "unique_texts": int(duplicate_groups.shape[0]),
            "duplicate_hashes": int(duplicate_hashes.shape[0]),
            "duplicate_rows": int(duplicate_hashes.sum()),
        },
    }
    return working, stats


def _word_count_stats(*, word_counts: list[int]) -> dict[str, float]:
    if not word_counts:
        return {"min": 0.0, "p25": 0.0, "median": 0.0, "mean": 0.0, "p75": 0.0, "max": 0.0}
    values = np.array(word_counts, dtype=float)
    return {
        "min": float(np.min(values)),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "p75": float(np.percentile(values, 75)),
        "max": float(np.max(values)),
    }


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _build_integrity_report(
    *,
    metadata: dict[str, Any],
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
) -> str:
    excluded_prompts = metadata.get("excluded_prompts", [])
    word_window = metadata.get("word_count_window", {})
    output_paths = metadata.get("output_paths", {})

    sections: list[str] = [
        "# Dataset Integrity Report",
        "",
        "## Configuration",
        "",
        f"- dataset_kind: `{metadata.get('dataset_kind')}`",
        f"- word_count_window: `{word_window.get('min')}`–`{word_window.get('max')}`",
        f"- excluded_prompts: `{excluded_prompts}`",
        "",
        "## Outputs",
        "",
        f"- prepared_train: `{output_paths.get('prepared_train')}`",
        f"- prepared_test: `{output_paths.get('prepared_test')}`",
        "",
        "## Row Counts",
        "",
        _row_count_table(metadata),
        "",
        "## Label Distribution (Overall)",
        "",
        _label_table(train_frame=train_frame, test_frame=test_frame),
        "",
        "## Prompt Coverage (Top 15)",
        "",
        _prompt_table(train_frame=train_frame, test_frame=test_frame),
        "",
        "## Duplicate Checks",
        "",
        _duplicate_table(train_frame=train_frame, test_frame=test_frame),
        "",
    ]
    return "\n".join(sections)


def _row_count_table(metadata: dict[str, Any]) -> str:
    train_rows = (metadata.get("train_stats", {}) or {}).get("rows", {})
    test_rows = (metadata.get("test_stats", {}) or {}).get("rows", {})
    rows = [
        ("split", "raw", "after_required", "after_excluded_prompts", "after_word_count_filter"),
        (
            "train",
            str(train_rows.get("raw", "")),
            str(train_rows.get("after_required", "")),
            str(train_rows.get("after_excluded_prompts", "")),
            str(train_rows.get("after_word_count_filter", "")),
        ),
        (
            "test",
            str(test_rows.get("raw", "")),
            str(test_rows.get("after_required", "")),
            str(test_rows.get("after_excluded_prompts", "")),
            str(test_rows.get("after_word_count_filter", "")),
        ),
    ]
    return _markdown_table(rows)


def _label_table(*, train_frame: pd.DataFrame, test_frame: pd.DataFrame) -> str:
    train_counts = train_frame["Overall"].value_counts().sort_index()
    test_counts = test_frame["Overall"].value_counts().sort_index()
    labels = sorted(set(train_counts.index.tolist()) | set(test_counts.index.tolist()))

    rows = [("Overall", "train_count", "test_count")]
    for label in labels:
        rows.append(
            (
                str(float(label)),
                str(int(train_counts.get(label, 0))),
                str(int(test_counts.get(label, 0))),
            )
        )
    return _markdown_table(rows)


def _prompt_table(*, train_frame: pd.DataFrame, test_frame: pd.DataFrame) -> str:
    train_counts = train_frame["prompt"].value_counts()
    test_counts = test_frame["prompt"].value_counts()
    prompts = (
        train_counts.add(test_counts, fill_value=0)
        .sort_values(ascending=False)
        .head(15)
        .index.tolist()
    )
    rows = [("prompt", "train_count", "test_count")]
    for prompt in prompts:
        rows.append(
            (
                str(prompt),
                str(int(train_counts.get(prompt, 0))),
                str(int(test_counts.get(prompt, 0))),
            )
        )
    return _markdown_table(rows)


def _duplicate_table(*, train_frame: pd.DataFrame, test_frame: pd.DataFrame) -> str:
    train_dupes = train_frame["text_sha256"].value_counts()
    test_dupes = test_frame["text_sha256"].value_counts()
    train_dup_rows = int(train_dupes[train_dupes > 1].sum())
    test_dup_rows = int(test_dupes[test_dupes > 1].sum())
    overlap = len(set(train_frame["text_sha256"]) & set(test_frame["text_sha256"]))

    rows = [
        ("check", "train", "test"),
        ("duplicate_rows_by_text_sha256", str(train_dup_rows), str(test_dup_rows)),
        ("train_test_overlap_by_text_sha256", str(overlap), str(overlap)),
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
