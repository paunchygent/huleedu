"""Feature combination utilities for essay scoring."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.ml_training.essay_scoring.config import FeatureSet
from scripts.ml_training.essay_scoring.features.schema import (
    Tier1Features,
    Tier2Features,
    Tier3Features,
    feature_names_for,
)


@dataclass(frozen=True)
class FeatureMatrix:
    """Container for feature matrix and ordered feature names."""

    matrix: np.ndarray
    feature_names: list[str]


def combine_features(
    embedding_vectors: np.ndarray | None,
    tier1: list[Tier1Features] | None,
    tier2: list[Tier2Features] | None,
    tier3: list[Tier3Features] | None,
    feature_set: FeatureSet,
) -> FeatureMatrix:
    """Combine embeddings and tiered features into a single matrix."""

    if feature_set == FeatureSet.EMBEDDINGS:
        if embedding_vectors is None:
            raise ValueError("Embedding vectors required for embeddings-only feature set.")
        feature_names = feature_names_for(feature_set, embedding_vectors.shape[1])
        return FeatureMatrix(matrix=embedding_vectors, feature_names=feature_names)

    if feature_set == FeatureSet.HANDCRAFTED:
        if tier1 is None or tier2 is None or tier3 is None:
            raise ValueError("Tiered features required for handcrafted feature set.")
        handcrafted = _stack_tiered_features(tier1, tier2, tier3)
        feature_names = feature_names_for(feature_set, 0)
        return FeatureMatrix(matrix=handcrafted, feature_names=feature_names)

    if embedding_vectors is None or tier1 is None or tier2 is None or tier3 is None:
        raise ValueError("Embeddings and tiered features are required for combined feature set.")

    handcrafted = _stack_tiered_features(tier1, tier2, tier3)
    matrix = np.concatenate([embedding_vectors, handcrafted], axis=1)
    feature_names = feature_names_for(feature_set, embedding_vectors.shape[1])
    return FeatureMatrix(matrix=matrix, feature_names=feature_names)


def _stack_tiered_features(
    tier1: list[Tier1Features],
    tier2: list[Tier2Features],
    tier3: list[Tier3Features],
) -> np.ndarray:
    """Stack tiered features in canonical order."""

    rows = []
    for t1, t2, t3 in zip(tier1, tier2, tier3, strict=True):
        rows.append(t1.to_list() + t2.to_list() + t3.to_list())
    return np.array(rows, dtype=float)
