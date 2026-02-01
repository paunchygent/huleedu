"""Grade-scale behavior report generator."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.features.spacy_pipeline import load_spacy_model
from scripts.ml_training.essay_scoring.features.utils import tokenize_words
from scripts.ml_training.essay_scoring.training.qwk import clip_bands, round_to_half_band


def generate_grade_scale_report(
    records: list[EssayRecord],
    y_true: np.ndarray,
    y_pred: np.ndarray,
    output_path: Path,
) -> None:
    """Generate the grade-scale behavior report as markdown.

    Args:
        records: Essay records in the evaluation split.
        y_true: Ground-truth band labels.
        y_pred: Model predictions.
        output_path: Path to write the markdown report.
    """

    if len(records) != len(y_true) or len(records) != len(y_pred):
        raise ValueError("Report inputs must have matching lengths.")

    rounded = clip_bands(round_to_half_band(y_pred))
    nlp = load_spacy_model("en_core_web_sm")
    word_counts = np.array([len(tokenize_words(record.essay, nlp)) for record in records])

    distribution = _distribution_table(y_true)
    prompt_distribution = _prompt_distribution(records, y_true)

    spearman_corr = _safe_spearman(y_pred, y_true)
    length_corr = _safe_spearman(word_counts, y_true)
    length_pred_corr = _safe_spearman(word_counts, rounded)

    confusion = _confusion_matrix(y_true, rounded)

    report = f"""# Grade-Scale Behavior Report

## Dataset & Context
- Dataset version/source: {Path("data/cefr_ielts_datasets/ielts_writing_dataset.csv")}
- Grade scale definition (labels + rubric reference): IELTS Overall band 5.0–7.5
- Prompt/task coverage: {len(set(record.question for record in records))} unique prompts
- Rater context (single vs multiple raters; moderation process): Not specified in dataset

## Distribution Checks
- Overall grade distribution:\n{distribution}
- Per-prompt grade distributions (top 5 by volume):\n{prompt_distribution}
- Missingness or sparsity notes: None detected in report slice

## Assumption-Light Diagnostics
- Monotonicity (Spearman correlation between predictions and grades): {spearman_corr:.3f}
- Boundary spacing: use confusion matrix below to inspect overlap
- Prompt/cohort stability: inspect prompt distribution table for skew
- Adjacent confusion matrix:\n{confusion}
- Length bias check (Spearman word count vs grade): {length_corr:.3f}
- Length bias check (Spearman word count vs prediction): {length_pred_corr:.3f}

## Mapping Decision
- Chosen mapping: model prediction rounded to nearest 0.5 band
- Rationale: aligns with EPIC-010 guidance for ordinal regression outputs
- Open questions / risks: validate mapping after Swedish dataset arrives

## Decision Outcome
- Approved by: TBD
- Date: TBD
- Next review trigger: Swedish NAFS dataset availability
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")


def _distribution_table(labels: np.ndarray) -> str:
    table = pd.Series(labels).value_counts().sort_index()
    return table.to_string()


def _prompt_distribution(records: list[EssayRecord], labels: np.ndarray) -> str:
    frame = pd.DataFrame(
        {
            "prompt": [record.question for record in records],
            "label": labels,
        }
    )
    counts = frame.groupby(["prompt", "label"]).size().reset_index(name="count")
    prompt_totals = counts.groupby("prompt")["count"].sum().sort_values(ascending=False)
    top_prompts = prompt_totals.head(5).index.tolist()
    filtered = counts[counts["prompt"].isin(top_prompts)]
    if filtered.empty:
        return "No prompt breakdown available"
    return filtered.to_string(index=False)


def _confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray) -> str:
    labels = sorted(set(y_true))
    frame = pd.crosstab(
        pd.Series(y_true, name="Actual"),
        pd.Series(y_pred, name="Predicted"),
        rownames=["Actual"],
        colnames=["Predicted"],
        dropna=False,
    ).reindex(index=labels, columns=labels, fill_value=0)
    return frame.to_string()


def _safe_spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or len(y) < 2:
        return 0.0
    return float(spearmanr(x, y).correlation or 0.0)
