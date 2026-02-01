"""Dataset splitting utilities for essay scoring."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass

import numpy as np
from sklearn.model_selection import train_test_split

from scripts.ml_training.essay_scoring.config import TrainingConfig
from scripts.ml_training.essay_scoring.dataset import EssayDataset, EssayRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetSplit:
    """Train/validation/test split for essay records."""

    train: list[EssayRecord]
    val: list[EssayRecord]
    test: list[EssayRecord]


def stratified_split(dataset: EssayDataset, config: TrainingConfig) -> DatasetSplit:
    """Perform a stratified train/val/test split by band labels.

    Args:
        dataset: Dataset to split.
        config: Training configuration containing split ratios.

    Returns:
        DatasetSplit with train, validation, and test records. Any class with fewer
        than two samples is assigned entirely to the train split before stratifying
        the remaining data.

    Raises:
        ValueError: If split ratios are invalid.
    """

    if not np.isclose(config.train_ratio + config.val_ratio + config.test_ratio, 1.0):
        raise ValueError("Train/val/test ratios must sum to 1.0")

    labels = np.array(dataset.labels)
    rare_records, common_records, common_labels = _split_rare_labels(dataset.records, labels)
    if not common_records:
        return DatasetSplit(train=list(dataset.records), val=[], test=[])

    train_records, temp_records, train_labels, temp_labels = train_test_split(
        common_records,
        common_labels,
        train_size=config.train_ratio,
        random_state=config.random_seed,
        stratify=common_labels,
    )

    temp_rare_records, temp_records, temp_labels = _split_rare_labels(
        list(temp_records), temp_labels
    )

    train_records = list(train_records) + rare_records + temp_rare_records

    if not temp_records:
        return DatasetSplit(train=train_records, val=[], test=[])

    val_ratio = config.val_ratio / (config.val_ratio + config.test_ratio)
    val_records, test_records, _, _ = train_test_split(
        temp_records,
        temp_labels,
        train_size=val_ratio,
        random_state=config.random_seed,
        stratify=temp_labels,
    )

    return DatasetSplit(
        train=list(train_records),
        val=list(val_records),
        test=list(test_records),
    )


def _split_rare_labels(
    records: list[EssayRecord], labels: np.ndarray, min_count: int = 2
) -> tuple[list[EssayRecord], list[EssayRecord], np.ndarray]:
    """Split records into rare and common groups based on label counts."""

    label_counts = Counter(labels)
    rare_labels = {label for label, count in label_counts.items() if count < min_count}
    if not rare_labels:
        return [], list(records), np.array(labels)

    logger.warning("Assigning rare labels to train: %s", sorted(rare_labels))
    rare_records = [
        record for record, label in zip(records, labels, strict=True) if label in rare_labels
    ]
    common_records = [
        record for record, label in zip(records, labels, strict=True) if label not in rare_labels
    ]
    common_labels = np.array([label for label in labels if label not in rare_labels])
    return rare_records, common_records, common_labels
