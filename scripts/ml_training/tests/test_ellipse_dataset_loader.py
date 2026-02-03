from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ml_training.essay_scoring.dataset import load_ellipse_train_test_dataset


def _write_csv(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_load_ellipse_train_test_dataset_excludes_prompts(tmp_path: Path) -> None:
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    _write_csv(
        train_path,
        "full_text,prompt,Overall,task\n"
        '"Essay A","Letter to employer",3.0,Independent\n'
        '"Essay B","Distance learning",4.0,Independent\n',
    )
    _write_csv(
        test_path,
        "full_text,prompt,Overall,task\n"
        '"Essay C","Letter to employer",2.0,Independent\n'
        '"Essay D","Impact of technology",5.0,Independent\n',
    )

    loaded = load_ellipse_train_test_dataset(
        train_path,
        test_path,
        excluded_prompts={"Letter to employer"},
    )

    assert len(loaded.train_records) == 1
    assert len(loaded.test_records) == 1
    assert len(loaded.dataset.records) == 2
    assert all(record.question != "Letter to employer" for record in loaded.dataset.records)


def test_load_ellipse_train_test_dataset_detects_overlap(tmp_path: Path) -> None:
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    _write_csv(
        train_path,
        'full_text,prompt,Overall,task\n"Essay A","Distance learning",3.0,Independent\n',
    )
    _write_csv(
        test_path,
        'full_text,prompt,Overall,task\n"Essay A","Impact of technology",4.0,Independent\n',
    )

    with pytest.raises(ValueError, match="split leakage"):
        load_ellipse_train_test_dataset(train_path, test_path)
