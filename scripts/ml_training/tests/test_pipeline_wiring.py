from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.config import EmbeddingConfig, FeatureSet
from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.features.pipeline import FeaturePipeline
from scripts.ml_training.essay_scoring.features.schema import (
    Tier1Features,
    Tier2Features,
    Tier3Features,
)


class DummyEmbedder:
    def embed(self, texts: list[str]) -> np.ndarray:
        return np.array([[1.0, 2.0] for _ in texts], dtype=float)


class DummyTier1:
    def extract(self, text: str) -> Tier1Features:
        return Tier1Features(
            grammar_errors_per_100_words=1.0,
            spelling_errors_per_100_words=2.0,
            punctuation_errors_per_100_words=3.0,
            flesch_kincaid=4.0,
            smog=5.0,
            coleman_liau=6.0,
            ari=7.0,
            avg_sentence_length=8.0,
            ttr=9.0,
            word_count=10.0,
            avg_word_length=11.0,
        )

    def extract_batch(self, texts: list[str]) -> list[Tier1Features]:
        return [self.extract(text) for text in texts]


class DummyTier2:
    def extract(self, text: str, prompt: str) -> Tier2Features:
        return Tier2Features(
            parse_tree_depth=1.0,
            clause_count=2.0,
            passive_ratio=3.0,
            dep_distance=4.0,
            connective_diversity=5.0,
            sent_similarity_variance=6.0,
            prompt_similarity=7.0,
            intro_prompt_sim=8.0,
            min_para_relevance=9.0,
        )

    def extract_batch(self, texts: list[str], prompts: list[str]) -> list[Tier2Features]:
        return [self.extract(text, prompt) for text, prompt in zip(texts, prompts, strict=True)]


class DummyTier3:
    def extract(self, text: str, prompt: str) -> Tier3Features:
        return Tier3Features(
            paragraph_count=1.0,
            has_intro=0.0,
            has_conclusion=1.0,
            lexical_overlap=0.25,
            pronoun_noun_ratio=0.5,
        )


def _records() -> list[EssayRecord]:
    return [
        EssayRecord(
            record_id="record-1",
            task_type="1",
            question="Vad tycker du om skolan?",
            essay="Jag gillar skolan. Det är viktigt att lära sig om åäö.",
            overall=6.0,
            component_scores={},
        ),
        EssayRecord(
            record_id="record-2",
            task_type="2",
            question="Describe your hometown.",
            essay="My hometown is small but vibrant.",
            overall=6.5,
            component_scores={},
        ),
    ]


def test_pipeline_combined_wiring() -> None:
    pipeline = FeaturePipeline(
        embedding_config=EmbeddingConfig(),
        embedder=DummyEmbedder(),
        tier1_extractor=DummyTier1(),
        tier2_extractor=DummyTier2(),
        tier3_extractor=DummyTier3(),
    )

    features = pipeline.extract(_records(), FeatureSet.COMBINED)
    assert features.matrix.shape == (2, 2 + 11 + 9 + 5)
    assert features.feature_names[0] == "embedding_000"
    assert features.feature_names[1] == "embedding_001"


def test_pipeline_handcrafted_wiring() -> None:
    pipeline = FeaturePipeline(
        embedding_config=EmbeddingConfig(),
        embedder=DummyEmbedder(),
        tier1_extractor=DummyTier1(),
        tier2_extractor=DummyTier2(),
        tier3_extractor=DummyTier3(),
    )

    features = pipeline.extract(_records(), FeatureSet.HANDCRAFTED)
    assert features.matrix.shape == (2, 11 + 9 + 5)
    assert features.feature_names[0] == "grammar_errors_per_100_words"


def test_pipeline_embeddings_wiring() -> None:
    pipeline = FeaturePipeline(
        embedding_config=EmbeddingConfig(),
        embedder=DummyEmbedder(),
        tier1_extractor=DummyTier1(),
        tier2_extractor=DummyTier2(),
        tier3_extractor=DummyTier3(),
    )

    features = pipeline.extract(_records(), FeatureSet.EMBEDDINGS)
    assert features.matrix.shape == (2, 2)
    assert features.feature_names == ["embedding_000", "embedding_001"]
