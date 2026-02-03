from __future__ import annotations

import pandas as pd
import pytest

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, OutputConfig
from scripts.ml_training.essay_scoring.dataset_preparation import prepare_dataset


def _make_text(word_count: int) -> str:
    return " ".join(f"word{i}" for i in range(word_count))


def _make_seeded_text(word_count: int, *, seed: str) -> str:
    return " ".join(f"{seed}{i}" for i in range(word_count))


def test_prepare_dataset_filters_excluded_prompts_and_word_window(tmp_path) -> None:
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    train_df = pd.DataFrame(
        [
            {"full_text": _make_seeded_text(200, seed="train"), "prompt": "OK", "Overall": "3.0"},
            {"full_text": _make_seeded_text(199, seed="short"), "prompt": "OK", "Overall": "3.0"},
            {
                "full_text": _make_seeded_text(250, seed="exclude"),
                "prompt": "Letter to employer",
                "Overall": "4.0",
            },
            {"full_text": _make_seeded_text(1001, seed="long"), "prompt": "OK", "Overall": "2.0"},
            {"full_text": "", "prompt": "OK", "Overall": "3.0"},
        ]
    )
    test_df = pd.DataFrame(
        [
            {"full_text": _make_seeded_text(200, seed="test"), "prompt": "OK", "Overall": "3.5"},
            {
                "full_text": _make_seeded_text(250, seed="exclude_test"),
                "prompt": "Letter to employer",
                "Overall": "4.5",
            },
        ]
    )
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)

    config = ExperimentConfig(
        dataset_kind=DatasetKind.ELLIPSE,
        ellipse_train_path=train_path,
        ellipse_test_path=test_path,
        output=OutputConfig(base_dir=tmp_path, run_name="prep"),
    )

    summary = prepare_dataset(config, min_words=200, max_words=1000)

    prepared_train = pd.read_csv(summary.prepared_train_path)
    prepared_test = pd.read_csv(summary.prepared_test_path)

    assert prepared_train.shape[0] == 1
    assert prepared_test.shape[0] == 1
    assert prepared_train.iloc[0]["prompt"] == "OK"
    assert prepared_test.iloc[0]["prompt"] == "OK"
    assert "word_count" in prepared_train.columns
    assert "text_sha256" in prepared_train.columns
    assert summary.report_path.exists()


def test_prepare_dataset_raises_on_train_test_overlap(tmp_path) -> None:
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    shared = _make_seeded_text(220, seed="shared")
    pd.DataFrame([{"full_text": shared, "prompt": "OK", "Overall": "3.0"}]).to_csv(
        train_path, index=False
    )
    pd.DataFrame([{"full_text": shared, "prompt": "OK", "Overall": "3.5"}]).to_csv(
        test_path, index=False
    )

    config = ExperimentConfig(
        dataset_kind=DatasetKind.ELLIPSE,
        ellipse_train_path=train_path,
        ellipse_test_path=test_path,
        output=OutputConfig(base_dir=tmp_path, run_name="prep_overlap"),
    )

    with pytest.raises(ValueError, match="leakage"):
        prepare_dataset(config, min_words=200, max_words=1000)
