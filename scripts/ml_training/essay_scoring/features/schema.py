"""Pydantic feature schemas for the essay scoring pipeline.

This module defines the canonical ordering and naming of features used by:
- `scripts/ml_training/essay_scoring/features/combiner.py` (feature matrices + names)
- `scripts/ml_training/essay_scoring/feature_store.py` (persisted feature stores)
- `scripts/ml_training/essay_scoring/runner.py` (training artifacts + feature_schema.json)

Naming conventions:
- Tier 1 LanguageTool-derived error rates are encoded with their units (per 100 words) to avoid
  ambiguity during analysis.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from scripts.ml_training.essay_scoring.config import FeatureSet

TIER1_FEATURE_NAMES = [
    "grammar_errors_per_100_words",
    "spelling_errors_per_100_words",
    "punctuation_errors_per_100_words",
    "flesch_kincaid",
    "smog",
    "coleman_liau",
    "ari",
    "avg_sentence_length",
    "ttr",
    "word_count",
    "avg_word_length",
]

TIER2_FEATURE_NAMES = [
    "parse_tree_depth",
    "clause_count",
    "passive_ratio",
    "dep_distance",
    "connective_diversity",
    "sent_similarity_variance",
    "prompt_similarity",
    "intro_prompt_sim",
    "min_para_relevance",
]

TIER3_FEATURE_NAMES = [
    "paragraph_count",
    "has_intro",
    "has_conclusion",
    "lexical_overlap",
    "pronoun_noun_ratio",
]


class Tier1Features(BaseModel):
    """Tier 1 feature set (error density, readability, core length)."""

    model_config = ConfigDict(extra="forbid")

    grammar_errors_per_100_words: float
    spelling_errors_per_100_words: float
    punctuation_errors_per_100_words: float
    flesch_kincaid: float
    smog: float
    coleman_liau: float
    ari: float
    avg_sentence_length: float
    ttr: float
    word_count: float
    avg_word_length: float

    def to_list(self) -> list[float]:
        """Return features as a list in canonical order."""

        return [
            self.grammar_errors_per_100_words,
            self.spelling_errors_per_100_words,
            self.punctuation_errors_per_100_words,
            self.flesch_kincaid,
            self.smog,
            self.coleman_liau,
            self.ari,
            self.avg_sentence_length,
            self.ttr,
            self.word_count,
            self.avg_word_length,
        ]


class Tier2Features(BaseModel):
    """Tier 2 feature set (syntactic complexity, cohesion, prompt relevance)."""

    model_config = ConfigDict(extra="forbid")

    parse_tree_depth: float
    clause_count: float
    passive_ratio: float
    dep_distance: float
    connective_diversity: float
    sent_similarity_variance: float
    prompt_similarity: float
    intro_prompt_sim: float
    min_para_relevance: float

    def to_list(self) -> list[float]:
        """Return features as a list in canonical order."""

        return [
            self.parse_tree_depth,
            self.clause_count,
            self.passive_ratio,
            self.dep_distance,
            self.connective_diversity,
            self.sent_similarity_variance,
            self.prompt_similarity,
            self.intro_prompt_sim,
            self.min_para_relevance,
        ]


class Tier3Features(BaseModel):
    """Tier 3 feature set (structure, lexical overlap, ratios)."""

    model_config = ConfigDict(extra="forbid")

    paragraph_count: float
    has_intro: float
    has_conclusion: float
    lexical_overlap: float
    pronoun_noun_ratio: float

    def to_list(self) -> list[float]:
        """Return features as a list in canonical order."""

        return [
            self.paragraph_count,
            self.has_intro,
            self.has_conclusion,
            self.lexical_overlap,
            self.pronoun_noun_ratio,
        ]


class FeatureSchema(BaseModel):
    """Schema describing feature ordering for training artifacts."""

    model_config = ConfigDict(extra="forbid")

    embedding_dim: int
    tier1: list[str]
    tier2: list[str]
    tier3: list[str]
    combined: list[str]


def build_feature_schema(embedding_dim: int) -> FeatureSchema:
    """Build a feature schema aligned with EPIC-010 naming.

    Args:
        embedding_dim: Number of embedding dimensions.

    Returns:
        FeatureSchema for combined features.
    """

    embedding_names = [f"embedding_{idx:03d}" for idx in range(embedding_dim)]
    combined = embedding_names + TIER1_FEATURE_NAMES + TIER2_FEATURE_NAMES + TIER3_FEATURE_NAMES
    return FeatureSchema(
        embedding_dim=embedding_dim,
        tier1=list(TIER1_FEATURE_NAMES),
        tier2=list(TIER2_FEATURE_NAMES),
        tier3=list(TIER3_FEATURE_NAMES),
        combined=combined,
    )


def feature_names_for(feature_set: FeatureSet, embedding_dim: int) -> list[str]:
    """Return ordered feature names for the selected feature set."""

    if feature_set == FeatureSet.HANDCRAFTED:
        return TIER1_FEATURE_NAMES + TIER2_FEATURE_NAMES + TIER3_FEATURE_NAMES
    if feature_set == FeatureSet.EMBEDDINGS:
        return [f"embedding_{idx:03d}" for idx in range(embedding_dim)]
    return (
        [f"embedding_{idx:03d}" for idx in range(embedding_dim)]
        + TIER1_FEATURE_NAMES
        + TIER2_FEATURE_NAMES
        + TIER3_FEATURE_NAMES
    )
