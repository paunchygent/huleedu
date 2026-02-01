from __future__ import annotations

import numpy as np
import spacy

from scripts.ml_training.essay_scoring.features.tier2_syntactic_cohesion import (
    Tier2FeatureExtractor,
)


class _DummyEmbeddingExtractor:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        rows = []
        for text in texts:
            rows.append(
                [
                    float(len(text)),
                    float(text.count("a")),
                    float(text.count("b")),
                ]
            )
        return np.array(rows, dtype=np.float32)


def test_tier2_extract_batch_offloads_and_batches_embeddings() -> None:
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    embedder = _DummyEmbeddingExtractor()

    extractor = Tier2FeatureExtractor(nlp=nlp, embedding_extractor=embedder)
    texts = ["A sentence. Another sentence.\n\nA new paragraph here."]
    prompts = ["Describe a thing."]

    features = extractor.extract_batch(texts, prompts)
    assert len(features) == 1
    assert len(embedder.calls) == 1
    assert embedder.calls[0]
