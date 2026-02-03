from __future__ import annotations

import pandas as pd

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, OutputConfig
from scripts.ml_training.essay_scoring.dataset import load_ellipse_train_test_dataset
from scripts.ml_training.essay_scoring.split_definitions import generate_splits, load_splits
from scripts.ml_training.essay_scoring.text_processing import (
    normalize_text_for_hashing,
    sha256_text,
)


def _make_text(word_count: int, *, seed: str) -> str:
    return " ".join(f"{seed}_w{i}" for i in range(word_count))


def test_generate_splits_no_group_leakage_and_full_coverage(tmp_path) -> None:
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    rows = []
    for i in range(6):
        rows.append({"full_text": _make_text(250, seed=f"a{i}"), "prompt": "P1", "Overall": "1.0"})
    for i in range(6):
        rows.append({"full_text": _make_text(250, seed=f"b{i}"), "prompt": "P2", "Overall": "2.0"})
    rows[1]["full_text"] = rows[0]["full_text"]
    rows[7]["full_text"] = rows[6]["full_text"]

    pd.DataFrame(rows).to_csv(train_path, index=False)
    pd.DataFrame(
        [
            {"full_text": _make_text(250, seed="t1"), "prompt": "P3", "Overall": "1.0"},
            {"full_text": _make_text(250, seed="t2"), "prompt": "P4", "Overall": "2.0"},
        ]
    ).to_csv(test_path, index=False)

    config = ExperimentConfig(
        dataset_kind=DatasetKind.ELLIPSE,
        ellipse_train_path=train_path,
        ellipse_test_path=test_path,
        output=OutputConfig(base_dir=tmp_path, run_name="splits"),
    )

    summary = generate_splits(config, min_words=200, max_words=1000, n_splits=3)
    manifest = load_splits(summary.splits_path)

    dataset = load_ellipse_train_test_dataset(train_path, test_path, excluded_prompts=set())
    train_records = dataset.train_records
    record_to_group = {
        record.record_id: sha256_text(normalize_text_for_hashing(record.essay))
        for record in train_records
    }
    record_to_prompt = {record.record_id: record.question for record in train_records}

    train_ids = {record.record_id for record in train_records}
    strat_val_union: set[str] = set()
    for fold in manifest.stratified_text_folds:
        fold_train = set(fold.train_record_ids)
        fold_val = set(fold.val_record_ids)
        assert fold_train.isdisjoint(fold_val)

        train_groups = {record_to_group[rid] for rid in fold_train}
        val_groups = {record_to_group[rid] for rid in fold_val}
        assert train_groups.isdisjoint(val_groups)

        strat_val_union.update(fold_val)

    assert strat_val_union == train_ids

    for fold in manifest.prompt_holdout_folds:
        fold_train = set(fold.train_record_ids)
        fold_val = set(fold.val_record_ids)
        assert fold_train.isdisjoint(fold_val)

        train_prompts = {record_to_prompt[rid] for rid in fold_train}
        val_prompts = {record_to_prompt[rid] for rid in fold_val}
        assert train_prompts.isdisjoint(val_prompts)


def test_generate_splits_supports_multiclass_float_labels(tmp_path) -> None:
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    rows = []
    for i in range(6):
        rows.append({"full_text": _make_text(250, seed=f"a{i}"), "prompt": "P1", "Overall": "1.0"})
    for i in range(6):
        rows.append({"full_text": _make_text(250, seed=f"b{i}"), "prompt": "P2", "Overall": "1.5"})
    for i in range(6):
        rows.append({"full_text": _make_text(250, seed=f"c{i}"), "prompt": "P3", "Overall": "2.0"})

    pd.DataFrame(rows).to_csv(train_path, index=False)
    pd.DataFrame(
        [
            {"full_text": _make_text(250, seed="t1"), "prompt": "P4", "Overall": "1.0"},
            {"full_text": _make_text(250, seed="t2"), "prompt": "P5", "Overall": "1.5"},
            {"full_text": _make_text(250, seed="t3"), "prompt": "P6", "Overall": "2.0"},
        ]
    ).to_csv(test_path, index=False)

    config = ExperimentConfig(
        dataset_kind=DatasetKind.ELLIPSE,
        ellipse_train_path=train_path,
        ellipse_test_path=test_path,
        output=OutputConfig(base_dir=tmp_path, run_name="splits_multi"),
    )

    summary = generate_splits(config, min_words=200, max_words=1000, n_splits=3)
    manifest = load_splits(summary.splits_path)
    assert manifest.n_splits == 3
