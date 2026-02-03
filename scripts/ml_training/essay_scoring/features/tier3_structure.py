"""Tier 3 feature extraction: structure, lexical overlap, ratios."""

from __future__ import annotations

from dataclasses import dataclass

import spacy
from spacy.language import Language
from spacy.tokens import Doc

from scripts.ml_training.essay_scoring.features.schema import Tier3Features
from scripts.ml_training.essay_scoring.features.utils import (
    safe_divide,
    split_paragraphs,
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

        if self.nlp is None:
            raise RuntimeError("spaCy pipeline not initialized for Tier 3 extractor.")

        doc = self.nlp(text)
        paragraphs = split_paragraphs(text)
        paragraph_count = float(len(paragraphs))
        has_intro = 1.0 if self._has_intro(paragraphs, self.nlp) else 0.0
        has_conclusion = 1.0 if self._has_conclusion(paragraphs) else 0.0
        lexical_overlap = self._lexical_overlap_from_doc(doc)
        pronoun_noun_ratio = self._pronoun_noun_ratio_from_doc(doc)

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
        # Tokenizer-only (no tagger/parser) is enough for word-count heuristics.
        doc = nlp.make_doc(paragraphs[0])
        return sum(1 for token in doc if not token.is_space) >= 30

    @staticmethod
    def _has_conclusion(paragraphs: list[str]) -> bool:
        if not paragraphs:
            return False
        last_paragraph = paragraphs[-1].lower()
        return any(marker in last_paragraph for marker in CONCLUSION_MARKERS)

    @staticmethod
    def _lexical_overlap_from_doc(doc: Doc) -> float:
        sentences = list(doc.sents)
        if len(sentences) < 2:
            return 0.0
        overlaps: list[float] = []
        for sent_a, sent_b in zip(sentences, sentences[1:], strict=False):
            tokens_a = {token.text.lower() for token in sent_a if not token.is_space}
            tokens_b = {token.text.lower() for token in sent_b if not token.is_space}
            if not tokens_a or not tokens_b:
                overlaps.append(0.0)
                continue
            intersection = tokens_a.intersection(tokens_b)
            union = tokens_a.union(tokens_b)
            overlaps.append(safe_divide(float(len(intersection)), float(len(union))))
        return float(sum(overlaps) / len(overlaps))

    @staticmethod
    def _pronoun_noun_ratio_from_doc(doc: Doc) -> float:
        pronouns = sum(1 for token in doc if token.pos_ == "PRON")
        nouns = sum(1 for token in doc if token.pos_ in {"NOUN", "PROPN"})
        return safe_divide(float(pronouns), float(nouns))
