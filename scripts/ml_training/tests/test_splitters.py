from __future__ import annotations

from scripts.ml_training.essay_scoring.config import TrainingConfig
from scripts.ml_training.essay_scoring.dataset import EssayDataset, EssayRecord
from scripts.ml_training.essay_scoring.splitters import stratified_split


def _record(idx: int, label: float) -> EssayRecord:
    return EssayRecord(
        record_id=f"record-{idx}",
        task_type="1",
        question="Prompt?",
        essay=f"Essay {idx}",
        overall=label,
        component_scores={},
    )


def test_stratified_split_moves_rare_labels_to_train() -> None:
    records = []
    records += [_record(i, 5.0) for i in range(6)]
    records += [_record(i + 10, 6.0) for i in range(6)]
    records += [_record(999, 1.0)]

    dataset = EssayDataset(records=records)
    config = TrainingConfig(train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, random_seed=42)

    split = stratified_split(dataset, config)

    train_labels = [record.overall for record in split.train]
    val_labels = [record.overall for record in split.val]
    test_labels = [record.overall for record in split.test]

    assert train_labels.count(1.0) == 1
    assert 1.0 not in val_labels
    assert 1.0 not in test_labels
    assert len(split.train) + len(split.val) + len(split.test) == len(records)


def test_stratified_split_allows_zero_test_ratio() -> None:
    records = []
    records += [_record(i, 5.0) for i in range(20)]
    records += [_record(i + 100, 6.0) for i in range(20)]

    dataset = EssayDataset(records=records)
    config = TrainingConfig(train_ratio=0.8, val_ratio=0.2, test_ratio=0.0, random_seed=42)

    split = stratified_split(dataset, config)

    assert split.test == []
    assert split.val
    assert len(split.train) + len(split.val) == len(records)
