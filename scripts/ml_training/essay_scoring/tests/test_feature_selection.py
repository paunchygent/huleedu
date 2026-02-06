"""Tests for predictor feature selection helpers."""

from __future__ import annotations

import pytest

from scripts.ml_training.essay_scoring.config import FeatureSet
from scripts.ml_training.essay_scoring.training.feature_selection import (
    feature_selection_summary,
    resolve_keep_feature_indices,
)


def test_resolve_keep_feature_indices_keeps_all_embeddings_and_allowlisted_handcrafted() -> None:
    feature_names = [
        "embedding_000",
        "embedding_001",
        "grammar_errors_per_100_words",
        "spelling_errors_per_100_words",
        "has_conclusion",
    ]
    keep = resolve_keep_feature_indices(
        feature_names,
        feature_set=FeatureSet.COMBINED,
        handcrafted_keep=["grammar_errors_per_100_words", "spelling_errors_per_100_words"],
    )
    assert keep == [0, 1, 2, 3]

    summary = feature_selection_summary(
        feature_names,
        feature_set=FeatureSet.COMBINED,
        keep_feature_indices=keep,
        handcrafted_keep=["grammar_errors_per_100_words", "spelling_errors_per_100_words"],
    )
    assert summary["mode"] == "handcrafted_allowlist"
    assert summary["embedding_dim"] == 2
    assert summary["kept_handcrafted_feature_count"] == 2
    assert "has_conclusion" not in summary["kept_handcrafted_features"]


def test_resolve_keep_feature_indices_raises_on_unknown_feature() -> None:
    with pytest.raises(ValueError, match="Unknown handcrafted feature names"):
        resolve_keep_feature_indices(
            ["embedding_000", "grammar_errors_per_100_words"],
            feature_set=FeatureSet.COMBINED,
            handcrafted_keep=["not_a_real_feature"],
        )


def test_resolve_keep_feature_indices_raises_for_embeddings_only_feature_set() -> None:
    with pytest.raises(ValueError, match="not supported for embeddings-only"):
        resolve_keep_feature_indices(
            ["embedding_000", "embedding_001"],
            feature_set=FeatureSet.EMBEDDINGS,
            handcrafted_keep=["grammar_errors_per_100_words"],
        )


def test_resolve_keep_feature_indices_filters_handcrafted_only_sets() -> None:
    feature_names = ["grammar_errors_per_100_words", "smog", "has_conclusion"]
    keep = resolve_keep_feature_indices(
        feature_names,
        feature_set=FeatureSet.HANDCRAFTED,
        handcrafted_keep=["smog"],
    )
    assert keep == [1]


def test_resolve_keep_feature_indices_supports_handcrafted_denylist() -> None:
    feature_names = [
        "embedding_000",
        "embedding_001",
        "grammar_errors_per_100_words",
        "spelling_errors_per_100_words",
        "has_conclusion",
    ]
    keep = resolve_keep_feature_indices(
        feature_names,
        feature_set=FeatureSet.COMBINED,
        handcrafted_keep=None,
        handcrafted_drop=["has_conclusion"],
    )
    assert keep == [0, 1, 2, 3]
