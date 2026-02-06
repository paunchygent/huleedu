"""Predictor feature selection helpers for essay scoring experiments.

Purpose:
    Provide a small, reproducible way to select a subset of *columns* from an existing feature
    matrix (usually loaded from a feature store), without re-extracting features. This is used
    for controlled experiments like "pruned handcrafted subset" while keeping embeddings intact.

Relationships:
    - Used by `scripts.ml_training.essay_scoring.cross_validation` to pass `keep_feature_indices`
      into fold training (`scripts.ml_training.essay_scoring.cv_shared`).
    - Intended to keep feature-selection logic out of the runners so they stay below the repo's
      file size limits.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from scripts.ml_training.essay_scoring.config import FeatureSet

_EMBEDDING_PREFIX = "embedding_"


def resolve_keep_feature_indices(
    feature_names: Sequence[str],
    *,
    feature_set: FeatureSet,
    handcrafted_keep: Sequence[str] | None,
    handcrafted_drop: Sequence[str] | None = None,
) -> list[int] | None:
    """Resolve feature indices to keep for training.

    For `feature_set=combined`, all embedding dimensions are always included. When an allowlist of
    handcrafted features is provided, only those handcrafted features are kept (in addition to all
    embeddings). Alternatively, a denylist can be provided to drop specific handcrafted features.

    Args:
        feature_names: Ordered list of feature names for the matrix columns.
        feature_set: Feature set used to produce the matrix.
        handcrafted_keep: Optional allowlist of handcrafted feature names to keep.
        handcrafted_drop: Optional denylist of handcrafted feature names to drop.

    Returns:
        `None` when no filtering is requested (keep all columns). Otherwise a list of indices to
        keep, preserving the original column order.
    """

    if handcrafted_keep and handcrafted_drop:
        raise ValueError("Use only one of handcrafted_keep or handcrafted_drop (not both).")

    if not handcrafted_keep and not handcrafted_drop:
        return None

    if feature_set == FeatureSet.EMBEDDINGS:
        raise ValueError(
            "handcrafted_keep/handcrafted_drop is not supported for embeddings-only feature sets."
        )

    keep_set = _normalize_keep_set(handcrafted_keep or [])
    drop_set = _normalize_keep_set(handcrafted_drop or [])

    if any(name.startswith(_EMBEDDING_PREFIX) for name in drop_set):
        raise ValueError("Dropping embedding dimensions is not supported.")

    requested = keep_set or drop_set
    missing = sorted(name for name in requested if name not in feature_names)
    if missing:
        raise ValueError(f"Unknown handcrafted feature names: {missing}")

    keep_indices: list[int] = []
    for idx, name in enumerate(feature_names):
        if name.startswith(_EMBEDDING_PREFIX):
            keep_indices.append(idx)
        elif keep_set and name in keep_set:
            keep_indices.append(idx)
        elif drop_set and name not in drop_set:
            keep_indices.append(idx)

    if not keep_indices:
        raise ValueError("Feature selection produced an empty keep set.")

    return keep_indices


def feature_selection_summary(
    feature_names: Sequence[str],
    *,
    feature_set: FeatureSet,
    keep_feature_indices: Sequence[int] | None,
    handcrafted_keep: Sequence[str] | None,
    handcrafted_drop: Sequence[str] | None = None,
) -> dict[str, object]:
    """Build a small JSON-serializable summary of predictor feature selection."""

    embedding_dim = sum(1 for name in feature_names if name.startswith(_EMBEDDING_PREFIX))

    if keep_feature_indices is None:
        return {
            "mode": "all",
            "feature_set": feature_set.value,
            "embedding_dim": int(embedding_dim),
            "feature_count_total": int(len(feature_names)),
            "kept_feature_count": int(len(feature_names)),
            "kept_handcrafted_feature_count": int(len(feature_names) - embedding_dim),
        }

    kept_names = [feature_names[int(idx)] for idx in keep_feature_indices]
    kept_handcrafted = [name for name in kept_names if not name.startswith(_EMBEDDING_PREFIX)]

    if handcrafted_drop:
        return {
            "mode": "handcrafted_denylist",
            "feature_set": feature_set.value,
            "embedding_dim": int(embedding_dim),
            "feature_count_total": int(len(feature_names)),
            "kept_feature_count": int(len(kept_names)),
            "kept_handcrafted_feature_count": int(len(kept_handcrafted)),
            "handcrafted_drop": list(_normalize_keep_set(handcrafted_drop)),
            "kept_handcrafted_features": kept_handcrafted,
        }

    return {
        "mode": "handcrafted_allowlist",
        "feature_set": feature_set.value,
        "embedding_dim": int(embedding_dim),
        "feature_count_total": int(len(feature_names)),
        "kept_feature_count": int(len(kept_names)),
        "kept_handcrafted_feature_count": int(len(kept_handcrafted)),
        "handcrafted_keep": list(_normalize_keep_set(handcrafted_keep or [])),
        "kept_handcrafted_features": kept_handcrafted,
    }


def _normalize_keep_set(values: Iterable[str]) -> set[str]:
    keep_set: set[str] = set()
    for raw in values:
        cleaned = raw.strip()
        if cleaned:
            keep_set.add(cleaned)
    return keep_set
