"""Protocols for feature extraction components."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from scripts.ml_training.essay_scoring.features.schema import (
    Tier1Features,
    Tier2Features,
    Tier3Features,
)


class EmbeddingExtractorProtocol(Protocol):
    """Protocol for embedding extraction."""

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return embeddings for a list of texts."""


class Tier1ExtractorProtocol(Protocol):
    """Protocol for Tier 1 feature extraction."""

    def extract(self, text: str) -> Tier1Features:
        """Extract Tier 1 features from a single essay."""

    def extract_batch(self, texts: list[str]) -> list[Tier1Features]:
        """Extract Tier 1 features for a batch of essays."""


class Tier2ExtractorProtocol(Protocol):
    """Protocol for Tier 2 feature extraction."""

    def extract(self, text: str, prompt: str) -> Tier2Features:
        """Extract Tier 2 features from a single essay and prompt."""

    def extract_batch(self, texts: list[str], prompts: list[str]) -> list[Tier2Features]:
        """Extract Tier 2 features for a batch of essays and prompts."""


class Tier3ExtractorProtocol(Protocol):
    """Protocol for Tier 3 feature extraction."""

    def extract(self, text: str, prompt: str) -> Tier3Features:
        """Extract Tier 3 features from a single essay and prompt."""
