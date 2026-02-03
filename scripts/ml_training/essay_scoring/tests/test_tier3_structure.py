"""Tests for Tier 3 feature extraction."""

from __future__ import annotations

import spacy

from scripts.ml_training.essay_scoring.features.tier3_structure import Tier3FeatureExtractor


def test_tier3_lexical_overlap_uses_sentence_boundaries() -> None:
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")

    extractor = Tier3FeatureExtractor(nlp=nlp)
    # Ensure punctuation is tokenized separately so the sentencizer can split.
    features = extractor.extract("A B . A C .", prompt="ignored")

    # Sent1 tokens: {a, b, .}
    # Sent2 tokens: {a, c, .}
    # Jaccard = 2/4 = 0.5
    assert features.lexical_overlap == 0.5


def test_tier3_has_intro_counts_tokens_in_first_paragraph() -> None:
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")

    extractor = Tier3FeatureExtractor(nlp=nlp)

    enough = " ".join([f"w{i}" for i in range(30)]) + "\n\nshort."
    not_enough = " ".join([f"w{i}" for i in range(29)]) + "\n\nshort."

    assert extractor.extract(enough, prompt="ignored").has_intro == 1.0
    assert extractor.extract(not_enough, prompt="ignored").has_intro == 0.0
