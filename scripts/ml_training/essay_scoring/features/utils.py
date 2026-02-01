"""Shared text utilities for feature extraction."""

from __future__ import annotations

import re
from typing import Iterable

import numpy as np
from spacy.language import Language

_WHITESPACE_RE = re.compile(r"\s+")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for consistent tokenization."""

    return _WHITESPACE_RE.sub(" ", text).strip()


def split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs using blank lines."""

    cleaned = text.strip()
    if not cleaned:
        return []
    paragraphs = [segment.strip() for segment in _PARAGRAPH_RE.split(cleaned) if segment.strip()]
    return paragraphs or [cleaned]


def tokenize_words(text: str, nlp: Language) -> list[str]:
    """Tokenize words using spaCy."""

    if nlp is None:
        raise RuntimeError("spaCy pipeline required for tokenization.")
    doc = nlp(text)
    return [token.text for token in doc if not token.is_space]


def tokenize_sentences(text: str, nlp: Language) -> list[str]:
    """Tokenize sentences using spaCy."""

    if nlp is None:
        raise RuntimeError("spaCy pipeline required for sentence tokenization.")
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers with a default fallback for zero denominators."""

    if denominator == 0:
        return default
    return numerator / denominator


def density_per_100_words(count: float, word_count: float) -> float:
    """Convert raw counts into densities per 100 words."""

    return safe_divide(count, word_count, default=0.0) * 100.0


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""

    denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
    if denom == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / denom)


def variance(values: Iterable[float]) -> float:
    """Compute variance for a sequence of floats."""

    values_list = list(values)
    if len(values_list) < 2:
        return 0.0
    return float(np.var(np.array(values_list, dtype=float)))
