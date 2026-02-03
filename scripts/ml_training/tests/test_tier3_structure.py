from __future__ import annotations

import spacy

from scripts.ml_training.essay_scoring.features.tier3_structure import Tier3FeatureExtractor


def test_tier3_extract_counts_paragraphs_and_detects_intro_and_conclusion() -> None:
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")

    extractor = Tier3FeatureExtractor(nlp=nlp)

    intro = " ".join(["Intro"] * 35)
    body = "This is the body. It repeats some words. This is the body."
    conclusion = "In conclusion, this is the end."
    text = f"{intro}\n\n{body}\n\n{conclusion}"

    features = extractor.extract(text, prompt="Prompt")

    assert features.paragraph_count == 3.0
    assert features.has_intro == 1.0
    assert features.has_conclusion == 1.0
    assert 0.0 <= features.lexical_overlap <= 1.0
    assert features.pronoun_noun_ratio == 0.0


def test_tier3_extract_handles_single_sentence_and_empty_paragraphs() -> None:
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    extractor = Tier3FeatureExtractor(nlp=nlp)

    features = extractor.extract("One sentence only.", prompt="Prompt")

    assert features.paragraph_count == 1.0
    assert features.has_intro == 0.0
    assert features.has_conclusion == 0.0
    assert features.lexical_overlap == 0.0
