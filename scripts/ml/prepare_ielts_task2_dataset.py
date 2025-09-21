#!/usr/bin/env python3
"""Prepare IELTS Task 2 dataset for CEFR/IELTS modeling pipeline.

This script loads the train/test CSV files provided in
``data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/`` and produces
cleaned Parquet files with CEFR labels.

Processing steps:
    * Drop the AI-generated ``evaluation`` column immediately.
    * Ensure ``prompt`` and ``essay`` fields are present and non-empty.
    * Convert ``band`` to floating point values and map to CEFR labels/codes.
    * Persist the cleaned split to a ``processed`` directory alongside the CSVs.

Usage examples
--------------
Run with defaults (expects repository root as current working directory)::

    pdm run python scripts/data_preparation/prepare_ielts_task2_dataset.py

Optionally override the dataset directory or output format::

    pdm run python scripts/data_preparation/prepare_ielts_task2_dataset.py \
        --dataset-dir data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation \
        --output-format parquet

The script prints a JSON summary describing the rows processed and any rows
removed because ``prompt`` or ``essay`` content was missing after trimming.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

# CEFR mapping thresholds are inclusive on the lower bound.
_CEFR_THRESHOLDS: list[tuple[float, str, int]] = [
    (8.5, "C2", 5),
    (7.0, "C1", 4),
    (6.0, "B2", 3),
    (5.0, "B1", 2),
    (4.0, "A2", 1),
]


@dataclass
class SplitSummary:
    """Processing summary for a dataset split."""

    split_name: str
    input_rows: int
    dropped_missing_text: int
    dropped_missing_band: int
    output_rows: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "split": self.split_name,
            "input_rows": self.input_rows,
            "dropped_missing_text": self.dropped_missing_text,
            "dropped_missing_band": self.dropped_missing_band,
            "output_rows": self.output_rows,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation"),
        help="Directory containing train.csv and test.csv",
    )
    parser.add_argument(
        "--output-format",
        choices=("parquet", "csv"),
        default="parquet",
        help="Output file format for cleaned splits",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing processed files if present",
    )
    return parser.parse_args()


def map_band_to_cefr(band_value: float) -> tuple[str, int]:
    for threshold, label, code in _CEFR_THRESHOLDS:
        if band_value >= threshold:
            return label, code
    return "A1", 0


def ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    missing_columns = {column for column in ("prompt", "essay", "band") if column not in df}
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing_columns)}")
    return df


def normalise_text_column(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Normalise text column and flag missing results.

    Empty strings and null-like values are treated as missing after trimming.
    """

    normalised = series.fillna("").astype(str).str.strip()
    missing_mask = normalised.eq("")
    return normalised, missing_mask


def process_split(
    csv_path: Path,
    output_path: Path,
    output_format: str,
    overwrite: bool,
) -> SplitSummary:
    if not csv_path.exists():
        raise FileNotFoundError(f"Expected dataset split not found: {csv_path}")

    df = pd.read_csv(csv_path, sep=None, engine="python")
    df = ensure_required_columns(df)
    input_rows = len(df)

    if "evaluation" in df:
        df = df.drop(columns=["evaluation"])

    df["prompt"], prompt_missing = normalise_text_column(df["prompt"])
    df["essay"], essay_missing = normalise_text_column(df["essay"])
    missing_text_mask = prompt_missing | essay_missing
    dropped_missing_text = int(missing_text_mask.sum())
    if dropped_missing_text:
        df = df.loc[~missing_text_mask].copy()

    df["band"] = pd.to_numeric(df["band"], errors="coerce")
    band_missing_mask = df["band"].isna()
    dropped_missing_band = int(band_missing_mask.sum())
    if dropped_missing_band:
        df = df.loc[~band_missing_mask].copy()

    cefr_labels, cefr_codes = zip(*(map_band_to_cefr(value) for value in df["band"].tolist()))
    df["cefr_label"] = cefr_labels
    df["cefr_code"] = cefr_codes

    df = df[["prompt", "essay", "band", "cefr_label", "cefr_code"]]

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {output_path}. Use --overwrite to replace it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "parquet":
        df.to_parquet(output_path, index=False)
    else:
        df.to_csv(output_path, index=False)

    return SplitSummary(
        split_name=csv_path.stem,
        input_rows=input_rows,
        dropped_missing_text=dropped_missing_text,
        dropped_missing_band=dropped_missing_band,
        output_rows=len(df),
    )


def iter_splits(dataset_dir: Path) -> Iterable[tuple[str, Path]]:
    for split_name in ("train", "test"):
        yield split_name, dataset_dir / f"{split_name}.csv"


def main() -> None:
    args = parse_args()
    dataset_dir: Path = args.dataset_dir
    output_format: str = args.output_format
    overwrite: bool = args.overwrite

    summaries: list[SplitSummary] = []
    for split_name, csv_path in iter_splits(dataset_dir):
        if output_format == "parquet":
            output_filename = f"{split_name}.parquet"
        else:
            output_filename = f"{split_name}.clean.csv"
        processed_dir = dataset_dir / "processed"
        output_path = processed_dir / output_filename
        summary = process_split(csv_path, output_path, output_format, overwrite)
        summaries.append(summary)

    print(json.dumps([summary.to_dict() for summary in summaries], indent=2))


if __name__ == "__main__":
    main()
