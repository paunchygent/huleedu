"""Tier 3 feature extraction: structure, lexical overlap, ratios."""

from __future__ import annotations

from dataclasses import dataclass

import spacy
from spacy.language import Language

from scripts.ml_training.essay_scoring.features.schema import Tier3Features
from scripts.ml_training.essay_scoring.features.utils import (
    safe_divide,
    split_paragraphs,
    tokenize_sentences,
    tokenize_words,
)

CONCLUSION_MARKERS = {
    "in conclusion",
    "to conclude",
    "in summary",
    "overall",
    "to sum up",
}


@dataclass
class Tier3FeatureExtractor:
    """Extract Tier 3 features using heuristics and spaCy."""

    spacy_model: str = "en_core_web_sm"
    nlp: Language | None = None

    def __post_init__(self) -> None:
        if self.nlp is None:
            try:
                self.nlp = spacy.load(self.spacy_model)
            except OSError as exc:
                raise RuntimeError(
                    "spaCy model not available. Install with: python -m spacy download "
                    f"{self.spacy_model}"
                ) from exc

    def extract(self, text: str, prompt: str) -> Tier3Features:
        """Extract Tier 3 features from essay text."""

        paragraphs = split_paragraphs(text)
        paragraph_count = float(len(paragraphs))
        has_intro = 1.0 if self._has_intro(paragraphs, self.nlp) else 0.0
        has_conclusion = 1.0 if self._has_conclusion(paragraphs) else 0.0
        lexical_overlap = self._lexical_overlap(text, self.nlp)
        pronoun_noun_ratio = self._pronoun_noun_ratio(text)

        return Tier3Features(
            paragraph_count=paragraph_count,
            has_intro=has_intro,
            has_conclusion=has_conclusion,
            lexical_overlap=lexical_overlap,
            pronoun_noun_ratio=pronoun_noun_ratio,
        )

    @staticmethod
    def _has_intro(paragraphs: list[str], nlp: Language) -> bool:
        if not paragraphs:
            return False
        first_words = tokenize_words(paragraphs[0], nlp)
        return len(first_words) >= 30

    @staticmethod
    def _has_conclusion(paragraphs: list[str]) -> bool:
        if not paragraphs:
            return False
        last_paragraph = paragraphs[-1].lower()
        return any(marker in last_paragraph for marker in CONCLUSION_MARKERS)

    @staticmethod
    def _lexical_overlap(text: str, nlp: Language) -> float:
        sentences = tokenize_sentences(text, nlp)
        if len(sentences) < 2:
            return 0.0
        overlaps = []
        for idx in range(len(sentences) - 1):
            tokens_a = set(token.lower() for token in tokenize_words(sentences[idx], nlp))
            tokens_b = set(token.lower() for token in tokenize_words(sentences[idx + 1], nlp))
            if not tokens_a or not tokens_b:
                overlaps.append(0.0)
            else:
                intersection = tokens_a.intersection(tokens_b)
                union = tokens_a.union(tokens_b)
                overlaps.append(safe_divide(float(len(intersection)), float(len(union))))
        return float(sum(overlaps) / len(overlaps))

    def _pronoun_noun_ratio(self, text: str) -> float:
        doc = self.nlp(text)
        pronouns = sum(1 for token in doc if token.pos_ == "PRON")
        nouns = sum(1 for token in doc if token.pos_ in {"NOUN", "PROPN"})
        return safe_divide(float(pronouns), float(nouns))
