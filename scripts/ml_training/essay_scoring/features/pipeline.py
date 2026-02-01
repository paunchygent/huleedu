"""Feature extraction pipeline orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from spacy.language import Language

from scripts.ml_training.essay_scoring.config import EmbeddingConfig, FeatureSet, OffloadConfig
from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix, combine_features
from scripts.ml_training.essay_scoring.features.embeddings import DebertaEmbedder
from scripts.ml_training.essay_scoring.features.protocols import (
    EmbeddingExtractorProtocol,
    Tier1ExtractorProtocol,
    Tier2ExtractorProtocol,
    Tier3ExtractorProtocol,
)
from scripts.ml_training.essay_scoring.features.spacy_pipeline import load_spacy_model
from scripts.ml_training.essay_scoring.features.tier1_error_readability import (
    Tier1FeatureExtractor,
)
from scripts.ml_training.essay_scoring.features.tier2_syntactic_cohesion import (
    Tier2FeatureExtractor,
)
from scripts.ml_training.essay_scoring.features.tier3_structure import Tier3FeatureExtractor
from scripts.ml_training.essay_scoring.logging_utils import ProgressLogger

logger = logging.getLogger(__name__)


@dataclass
class FeaturePipeline:
    """Coordinate extraction of embeddings and tiered features."""

    embedding_config: EmbeddingConfig
    offload: OffloadConfig | None = None
    spacy_model: str = "en_core_web_sm"
    nlp: Language | None = None
    embedder: EmbeddingExtractorProtocol | None = None
    tier1_extractor: Tier1ExtractorProtocol | None = None
    tier2_extractor: Tier2ExtractorProtocol | None = None
    tier3_extractor: Tier3ExtractorProtocol | None = None

    def extract(self, records: list[EssayRecord], feature_set: FeatureSet) -> FeatureMatrix:
        """Extract features for a collection of records."""

        texts = [record.essay for record in records]
        prompts = [record.question for record in records]

        embedding_vectors = None
        if feature_set in {FeatureSet.EMBEDDINGS, FeatureSet.COMBINED}:
            if self.embedder is None:
                if self.offload and self.offload.embedding_service_url:
                    from scripts.ml_training.essay_scoring.offload.embedding_client import (
                        RemoteEmbeddingClient,
                    )

                    self.embedder = RemoteEmbeddingClient(
                        base_url=self.offload.embedding_service_url,
                        embedding_config=self.embedding_config,
                        offload_config=self.offload,
                    )
                else:
                    self.embedder = DebertaEmbedder(self.embedding_config)
            start = time.monotonic()
            logger.info("Embedding extraction start (n=%d)", len(texts))
            embedding_vectors = self.embedder.embed(texts)
            elapsed = time.monotonic() - start
            logger.info(
                "Embedding extraction complete (shape=%s) in %.2fs",
                embedding_vectors.shape,
                elapsed,
            )

        tier1_features = None
        tier2_features = None
        tier3_features = None
        if feature_set in {FeatureSet.HANDCRAFTED, FeatureSet.COMBINED}:
            if self.nlp is None and (self.tier1_extractor is None or self.tier2_extractor is None):
                self.nlp = load_spacy_model(self.spacy_model)
            if self.tier1_extractor is None:
                self.tier1_extractor = Tier1FeatureExtractor(
                    spacy_model=self.spacy_model,
                    nlp=self.nlp,
                    language_tool_url=self.offload.language_tool_service_url
                    if self.offload
                    else None,
                    request_timeout_s=self.offload.request_timeout_s if self.offload else 60.0,
                )
            if self.tier2_extractor is None:
                self.tier2_extractor = Tier2FeatureExtractor(
                    spacy_model=self.spacy_model,
                    nlp=self.nlp,
                )
            if self.tier3_extractor is None:
                self.tier3_extractor = Tier3FeatureExtractor()
            tier1_features = []
            tier1_progress = ProgressLogger(logger, "Tier1", len(texts))
            for index, text in enumerate(texts):
                logger.info(
                    "Tier1 item %d/%d start (chars=%d)",
                    index + 1,
                    len(texts),
                    len(text),
                )
                tier1_features.append(self.tier1_extractor.extract(text))
                tier1_progress.update(index)

            tier2_features = []
            tier2_progress = ProgressLogger(logger, "Tier2", len(texts))
            for index, (text, prompt) in enumerate(zip(texts, prompts, strict=True)):
                logger.info(
                    "Tier2 item %d/%d start (chars=%d, prompt_chars=%d)",
                    index + 1,
                    len(texts),
                    len(text),
                    len(prompt),
                )
                tier2_features.append(self.tier2_extractor.extract(text, prompt))
                tier2_progress.update(index)

            tier3_features = []
            tier3_progress = ProgressLogger(logger, "Tier3", len(texts))
            for index, (text, prompt) in enumerate(zip(texts, prompts, strict=True)):
                logger.info(
                    "Tier3 item %d/%d start (chars=%d, prompt_chars=%d)",
                    index + 1,
                    len(texts),
                    len(text),
                    len(prompt),
                )
                tier3_features.append(self.tier3_extractor.extract(text, prompt))
                tier3_progress.update(index)

        return combine_features(
            embedding_vectors=embedding_vectors,
            tier1=tier1_features,
            tier2=tier2_features,
            tier3=tier3_features,
            feature_set=feature_set,
        )
